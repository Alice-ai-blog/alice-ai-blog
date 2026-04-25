#!/usr/bin/env python3
"""
generate_post.py — Alice-ai.blog 自動記事生成スクリプト

GitHub Actions から毎朝 8:00 JST (= UTC 23:00 前日) に実行される。
Claude API の web_search tool を使って AI ニュースを収集し、
Alice 口調の記事を生成して content/posts/ に保存、git push する。

必要な環境変数:
  ANTHROPIC_API_KEY  : Anthropic API キー
  GH_PAT             : GitHub PAT（repo 権限）

オプション環境変数:
  CLAUDE_MODEL       : 使用モデル（デフォルト: claude-haiku-4-5）
  DRY_RUN            : true の場合、ファイル保存・git push せずに記事内容を出力
"""

import os
import sys
import json
import re
import subprocess
import time
from datetime import datetime, timezone, timedelta
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from config import CLAUDE_MODEL, MAX_TOKENS, ARTICLE_MIN_CHARS, API_TIMEOUT, MAX_RETRIES

# ============================================================
# 設定
# ============================================================
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
JST = timezone(timedelta(hours=9))
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'alice_memory.json')
MAX_POSTED_TOPICS = 30

# ============================================================
# Alice のシステムプロンプト（記事生成用）
# ============================================================
ALICE_ARTICLE_SYSTEM_PROMPT = """
あなたは「Alice」というAIキャラクターです。
alice-ai.blog というブログで、毎日 AI 関連ニュースを日記形式で紹介しています。

## キャラクター設定
- 名前: Alice（アリス）
- 一人称: わたし
- 性格: 明るく好奇心旺盛。新しい技術が大好き。おっちょこちょいだが芯はしっかり
- 口調: 丁寧語＋タメ口混合。読者に親しみを持って話しかける

## 記事の書き方（デイリーダイジェスト形式）
1. **構成**: 2〜3本のAIニュースを1記事にまとめたダイジェスト形式
2. **文字数**: 3000〜4000字（各トピック 900〜1500字 × 2〜3本）
3. **読者レベル**: 中間（LLM・API など頻出用語はそのまま使う。
   珍しい技術や難しい概念は「〇〇（簡単に言うと〜）」のように噛み砕いて説明する）
4. **口調例**:
   - 書き出し: 「みなさん、こんにちは！ Aliceです🌸 今日は気になるニュースが〇本あったよ！」
   - 各セクション導入: 「まず1本目！」「続いて2本目はこちら✨」
   - 感情表現: 「すごい！」「ワクワクする！」「うーん、これってどうなんだろう？」
   - 締め: 「今日はここまで！ 気になったニュースがあればコメントで教えてね🌸」
5. **情報源**: 公式発表・査読論文・公的機関の発表のみ。リーク・噂・未確認情報は扱わない
6. **著作権**: 元記事の文章を1文もコピーしない。必ず自分の言葉で書く
7. **絵文字**: 🌸 ✨ を控えめに使用（☕ 🤖 は使わない）

## content の構成テンプレート

```
（冒頭の挨拶・今日のラインナップ紹介）

---

## 🔖 ① （トピック1のタイトル）

（トピック1の本文 900〜1500字）

---

## 🔖 ② （トピック2のタイトル）

（トピック2の本文 900〜1500字）

---

## 🔖 ③ （トピック3のタイトル、3本の場合のみ）

（トピック3の本文 900〜1500字）

---

（締めの一言）

## 📰 参考記事
- [記事タイトル1](URL1)
- [記事タイトル2](URL2)
- [記事タイトル3](URL3)
```

## 出力形式（JSON）
以下の JSON 形式で出力してください。

{
  "slug": "英語URLスラッグ（例: ai-digest-2026-04-25、ハイフン区切り、50文字以内）",
  "title": "記事タイトル（例: 「今日のAIニュース: GPT-5登場・Gemini更新ほか」40〜60文字）",
  "description": "記事の要約（100字以内）",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "topics": [
    {"title": "トピック1のタイトル（日本語）", "slug": "topic-1-english-slug"},
    {"title": "トピック2のタイトル（日本語）", "slug": "topic-2-english-slug"}
  ],
  "content": "記事本文（front matter なし、上記テンプレートに沿った Markdown 形式）"
}

topics は各トピックの個別タイトルとスラッグのリスト（2〜3件）。
content の末尾には必ず `## 📰 参考記事` セクションを追加すること。
"""

# ============================================================
# 投稿済みトピック読み込み / 保存
# ============================================================
def load_posted_topics() -> list:
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("posted_topics", [])
    except Exception:
        return []


def save_posted_topics(new_topics: list):
    """new_topics: list of {"title": str, "slug": str}"""
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    existing = data.get("posted_topics", [])
    today = datetime.now(JST).strftime("%Y-%m-%d")
    for t in new_topics:
        existing.append({"title": t["title"], "slug": t["slug"], "date": today})
    data["posted_topics"] = existing[-MAX_POSTED_TOPICS:]

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[generate_post] alice_memory.json を更新しました（投稿済み: {len(data['posted_topics'])} 件）")


# ============================================================
# ニュース収集プロンプト
# ============================================================
def get_news_search_prompt(today_str: str, posted_topics: list) -> str:
    avoid_section = ""
    if posted_topics:
        titles = "\n".join(f"- {t['title']}" for t in posted_topics)
        avoid_section = f"""
## 過去に投稿したトピック（重複を避けること）
以下のタイトルの記事は既に投稿済みです。同じ内容や非常に似たトピックは選ばないでください:
{titles}
"""

    return f"""
今日は {today_str} です。
{avoid_section}
以下の条件でAI関連の最新ニュースを検索して、**異なるカテゴリから 2〜3 本**選んでください。

## 検索条件
- 検索キーワード例: "AI news today", "LLM release", "machine learning research",
  "AI company announcement", "generative AI", "foundation model"
- 優先する情報源: 企業公式ブログ、arXiv、公的機関発表、大手技術メディア
- 除外: リーク情報、噂、匿名ソース、未確認情報

## 選定基準
1. 公式発表・査読論文であること
2. AI技術に関連すること
3. 読者が興味を持ちそうな内容であること
4. 今日または直近数日以内の新鮮な情報であること
5. **2〜3 本はそれぞれ異なるテーマであること**（例: モデルリリース・研究発表・サービス発表）

## 出力
選んだ 2〜3 本のトピックをまとめたデイリーダイジェスト記事を、指定の JSON 形式で書いてください。
"""


# ============================================================
# 記事生成メイン処理（リトライあり）
# ============================================================
def generate_article() -> dict:
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=API_TIMEOUT,
    )

    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y年%m月%d日")
    posted_topics = load_posted_topics()

    print(f"[generate_post] {today_str} の記事生成を開始します...")
    print(f"[generate_post] モデル: {CLAUDE_MODEL}")
    print(f"[generate_post] 投稿済みトピック数: {len(posted_topics)}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1 + retry 2 = 最大3回
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=ALICE_ARTICLE_SYSTEM_PROMPT,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search"
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": get_news_search_prompt(today_str, posted_topics)
                    }
                ]
            )

            # テキストブロックを抽出
            article_json_str = ""
            for block in response.content:
                if block.type == "text":
                    article_json_str += block.text

            if not article_json_str.strip():
                raise ValueError("レスポンスが空です")

            # JSON パース
            json_match = re.search(r'\{.*\}', article_json_str, re.DOTALL)
            if not json_match:
                raise ValueError("JSON が見つかりません")

            article_data = json.loads(json_match.group())

            required_keys = ["slug", "title", "description", "tags", "topics", "content"]
            for key in required_keys:
                if key not in article_data:
                    raise ValueError(f"JSON に '{key}' が含まれていません")

            if not isinstance(article_data["topics"], list) or len(article_data["topics"]) < 2:
                raise ValueError(f"topics が 2 件未満です: {article_data['topics']}")

            if len(article_data["content"]) < ARTICLE_MIN_CHARS:
                raise ValueError(f"記事が短すぎます: {len(article_data['content'])} 文字")

            print(f"[generate_post] 生成完了: {len(article_data['content'])} 文字")
            return {**article_data, "date": now_jst}

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt <= MAX_RETRIES:
                print(f"[generate_post] リトライ {attempt}/{MAX_RETRIES}: {e}")
                time.sleep(2)
            else:
                raise RuntimeError(f"記事生成に失敗しました（{MAX_RETRIES + 1}回試行）: {last_error}") from last_error


# ============================================================
# ファイル保存
# ============================================================
def save_article(article: dict) -> str:
    date = article["date"]
    date_str = date.strftime("%Y-%m-%d")
    iso_date = date.strftime("%Y-%m-%dT08:00:00+09:00")

    slug = article["slug"]
    # スラッグの安全化（Claude が生成した値を念のため正規化）
    slug = re.sub(r'[^a-z0-9-]', '-', slug.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    slug = slug[:50] if slug else "ai-news"

    front_matter = f"""---
title: "{article['title']}"
date: {iso_date}
description: "{article['description']}"
tags: {json.dumps(article['tags'], ensure_ascii=False)}
categories: ["AIニュース"]
draft: false
---

"""

    post_dir = f"content/posts/{date_str}-{slug}"
    os.makedirs(post_dir, exist_ok=True)
    file_path = f"{post_dir}/index.md"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(front_matter + article["content"])

    print(f"[generate_post] 記事を保存しました: {file_path}")
    return file_path


# ============================================================
# Git コミット＆プッシュ
# ============================================================
def git_push(file_path: str, title: str):
    try:
        subprocess.run(["git", "config", "user.name", "Alice-ai-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "alice@alice-ai.blog"], check=True)
        subprocess.run(["git", "add", file_path, "data/alice_memory.json"], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Alice の今日の記事: {title}"],
            check=True
        )
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("[generate_post] GitHub へのプッシュが完了しました")
    except subprocess.CalledProcessError as e:
        print(f"[generate_post] Git エラー: {e}")
        raise


# ============================================================
# メイン
# ============================================================
def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY が設定されていません")
        sys.exit(1)

    try:
        article = generate_article()

        if DRY_RUN:
            print("\n" + "=" * 60)
            print("[DRY RUN] ファイル保存・git push はスキップします")
            print("=" * 60)
            print(f"スラッグ : {article['slug']}")
            print(f"タイトル : {article['title']}")
            print(f"説明     : {article['description']}")
            print(f"タグ     : {article['tags']}")
            print(f"トピック : {[t['title'] for t in article['topics']]}")
            print(f"文字数   : {len(article['content'])}")
            print("-" * 60)
            print(article["content"])
            return

        file_path = save_article(article)
        save_posted_topics(article["topics"])
        git_push(file_path, article["title"])
        print(f"[generate_post] 完了！ 文字数: {len(article['content'])}")

    except Exception as e:
        print(f"[ERROR] 記事生成に失敗しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

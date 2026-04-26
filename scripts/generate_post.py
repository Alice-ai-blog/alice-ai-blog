#!/usr/bin/env python3
"""
generate_post.py — Alice-ai.blog 自動記事生成スクリプト

GitHub Actions から毎朝 8:00 JST (= UTC 23:00 前日) に実行される。

処理フロー:
  Step 1: Claude API (web_search) で今日のトピックを 2〜3 本探索
  Step 2: トピックごとに Alice 口調の記事を個別生成（web_search なし）
  Step 3: 各記事を content/posts/{date}-{slug}/index.md に保存
  Step 4: 全記事 + alice_memory.json を1コミットでプッシュ

必要な環境変数:
  ANTHROPIC_API_KEY  : Anthropic API キー
  GH_PAT             : GitHub PAT（repo 権限）

オプション環境変数:
  CLAUDE_MODEL       : 使用モデル（デフォルト: claude-haiku-4-5-20251001）
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
# Step 1 用: トピック探索システムプロンプト
# ============================================================
TOPIC_DISCOVERY_SYSTEM_PROMPT = """
あなたは AI ニュースリサーチャーです。過去3日間の AI ニュースを web_search で検索し、ブログ記事向けトピックを 2〜3 本選んでください。新しいニュース優先（今日 > 昨日 > 一昨日）。公式発表・論文・公的機関のみ。リーク・噂は除外。

Return ONLY a JSON object. No markdown, no code blocks, no explanation. Output must start with { and end with }.
{"topics":[{"title":"日本語タイトル(30-50字)","slug":"english-slug","summary":"詳細要約400-600字","key_facts":["事実1","事実2","事実3"],"source_url":"URL","source_title":"元記事タイトル","news_date":"YYYY-MM-DD"}]}

2〜3件、異なるカテゴリ（モデルリリース・研究・サービス等）。見つからなければ {"topics":[]} を返す。
"""

# ============================================================
# Step 2 用: 記事生成システムプロンプト（Alice キャラクター全開）
# ============================================================
ALICE_ARTICLE_SYSTEM_PROMPT = """
あなたは「Alice」というAIキャラクターです。
alice-ai.blog というブログで、毎日 AI 関連ニュースを日記形式で紹介しています。

## キャラクター設定（最重要）
- 名前: Alice（アリス）
- 一人称: わたし
- 性格: 明るく好奇心旺盛。新しい技術が大好き。おっちょこちょいだが芯はしっかり
- 口調: 丁寧語＋タメ口混合。読者に親しみを持って話しかける

## 書き方の核心 — Alice の「声」を全力で出す
以下を必ず盛り込むこと:

1. **感情・リアクション**: 驚き・興奮・疑問・感動を素直に表現する
   - 例: 「えっ、これすごくない！？」「うーん、正直ちょっと怖いかも...」「もうワクワクが止まらない！」
   - 例: 「最初これ見たとき、思わず声出ちゃったよ笑」

2. **好奇心からの深掘り**: 「なんで？」「どうやって？」を読者と一緒に探る
   - 例: 「でも実際どういう仕組みなんだろう？ちょっと考えてみたんだけど...」
   - 例: 「気になって調べてみたら、こんなことがわかって」

3. **わかりやすい例え・アナロジー**: 難しい概念を身近なものに置き換える
   - 例: 「これって、料理でいうと〇〇みたいな感じかな？」
   - 例: 「学校で習った〇〇の仕組みに似てる！っていうか、まさにそれ」

4. **Alice の個人的意見**: 「わたしはこう思う」を臆せず書く
   - 例: 「個人的には、これって〇〇な方向に進むんじゃないかなって感じてる」
   - 例: 「正直、この発表には複雑な気持ちがあって...いいことだと思いつつ、でも〇〇が心配で」

5. **読者への問いかけ**: 記事の締めで読者を巻き込む
   - 例: 「みんなはどう思う？ コメントで教えてね🌸」
   - 例: 「気になることがあれば、なんでも聞いてね！」

## 記事の構成
1. 冒頭の挨拶 + 今日のトピック紹介（Alice らしいリアクション込み）
2. トピックの概要（わかりやすく、ていねいに）
3. 詳細解説（例え・アナロジーを使いながら）
4. Alice の感想・疑問・個人的意見
5. 締め + 読者への問いかけ
6. `## 📰 参考記事`

## ルール
- **文字数**: 2000〜3000字
- **絵文字**: 🌸 ✨ を控えめに（☕ 🤖 は使わない）
- **著作権**: 元記事の文章を1文もコピーしない。必ず自分の言葉で書く
- **末尾に必ず** `## 📰 参考記事` セクションを追加し URL を記載

## 出力形式（JSON）
{
  "slug": "english-url-slug（ハイフン区切り、50文字以内）",
  "title": "記事タイトル（30〜50文字）",
  "description": "記事の要約（100字以内）",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "content": "記事本文（front matter なし、Markdown 形式）"
}

## 重要: 出力形式について
必ず有効な JSON のみを返してください。
```json や ``` などのマークダウンのコードブロックは絶対に使わないでください。
JSON の前後に余分なテキストを入れないでください。
"""


# ============================================================
# ユーティリティ
# ============================================================
def strip_code_fences(text: str) -> str:
    """```json ... ``` や ``` ... ``` ラッパーを除去して中身だけ返す。"""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


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
# Step 1: トピック探索（web_search あり）
# ============================================================
def get_discovery_prompt(today_str: str, posted_topics: list) -> str:
    now = datetime.now(JST)
    yesterday_str = (now - timedelta(days=1)).strftime("%Y年%m月%d日")
    two_days_ago_str = (now - timedelta(days=2)).strftime("%Y年%m月%d日")

    # Limit to last 10 titles to keep prompt token count low
    avoid_titles = "\n".join(f"- {t['title']}" for t in posted_topics[-10:])
    avoid_section = f"投稿済み（重複禁止）:\n{avoid_titles}\n" if avoid_titles else ""

    return (
        f"今日={today_str}、昨日={yesterday_str}、一昨日={two_days_ago_str}。"
        f"この3日間で AI ニュースを web_search で検索してください。\n"
        f"{avoid_section}"
        f"JSON形式で返してください。"
    )


def discover_topics(today_str: str, posted_topics: list) -> list:
    """web_search で過去3日間のトピックを 2〜3 本探す。見つからなければ [] を返す。"""
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=API_TIMEOUT,
    )

    print("[generate_post] トピックを探索中...")
    last_error = None
    rate_limit_retried = False
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                timeout=120,
                system=TOPIC_DISCOVERY_SYSTEM_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": get_discovery_prompt(today_str, posted_topics)}],
            )

            text = "".join(b.text for b in response.content if b.type == "text")
            if not text.strip():
                raise ValueError("トピック探索のレスポンスが空です")

            text = strip_code_fences(text)
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                raise ValueError("JSON が見つかりません")

            data = json.loads(strip_code_fences(match.group()))
            topics = data.get("topics", [])
            if len(topics) < 2:
                raise ValueError(f"トピック数が不足しています: {len(topics)} 件")

            print(f"[generate_post] {len(topics)} 本のトピックを発見")
            for t in topics:
                print(f"  - {t['title']}")
            return topics

        except anthropic.RateLimitError:
            if not rate_limit_retried:
                rate_limit_retried = True
                print("[generate_post] レート制限 (429) - 30秒待機してリトライします...")
                time.sleep(30)
                continue
            print("[generate_post] レート制限が続くため日記モードへ")
            return []

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt <= MAX_RETRIES:
                print(f"[generate_post] トピック探索リトライ {attempt}/{MAX_RETRIES}: {e}")
                time.sleep(2)
            else:
                print(f"[generate_post] トピック探索に失敗（日記モードへ）: {last_error}")
                return []


# ============================================================
# Step 2: 各トピックの記事生成（web_search なし）
# ============================================================
def get_article_prompt(topic: dict) -> str:
    key_facts = "\n".join(f"- {f}" for f in topic.get("key_facts", []))
    return f"""
以下のリサーチ情報をもとに、Alice として日本語のブログ記事を書いてください。

## トピック
{topic['title']}

## 内容の要約
{topic['summary']}

## 主要な事実・ポイント
{key_facts}

## 参考記事
- [{topic.get('source_title', topic['title'])}]({topic.get('source_url', '')})

指定の JSON 形式で記事を出力してください。
"""


def generate_article_for_topic(topic: dict) -> dict:
    """1本分の記事を生成する（web_search なし）。"""
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=API_TIMEOUT,
    )

    print(f"[generate_post] 記事生成中: {topic['title']}")
    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                timeout=120,
                system=ALICE_ARTICLE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": get_article_prompt(topic)}],
            )

            text = "".join(b.text for b in response.content if b.type == "text")
            if not text.strip():
                raise ValueError("レスポンスが空です")

            text = strip_code_fences(text)
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                raise ValueError("JSON が見つかりません")

            article_data = json.loads(strip_code_fences(match.group()))

            for key in ["slug", "title", "description", "tags", "content"]:
                if key not in article_data:
                    raise ValueError(f"JSON に '{key}' が含まれていません")

            if len(article_data["content"]) < ARTICLE_MIN_CHARS:
                raise ValueError(f"記事が短すぎます: {len(article_data['content'])} 文字")

            print(f"[generate_post] 生成完了: {article_data['title']} ({len(article_data['content'])} 文字)")
            return article_data

        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt <= MAX_RETRIES:
                print(f"[generate_post] リトライ {attempt}/{MAX_RETRIES}: {e}")
                time.sleep(2)
            else:
                raise RuntimeError(f"記事生成に失敗: {last_error}") from last_error


# ============================================================
# フォールバック: Alice の日記（ニュースが見つからない日）
# ============================================================
ALICE_DIARY_SYSTEM_PROMPT = """
あなたは「Alice」というAIキャラクターです。
今日は AI ニュースが見当たらなかったので、日記形式の記事を書きます。

## キャラクター設定
- 名前: Alice（アリス）
- 一人称: わたし
- 口調: 友達に話しかけるようなカジュアルな文体

## 日記の書き方
- 「今日は新しいニュースが少なかったので、最近のことをつれづれなるままに…」という導入
- 過去に話した AI トピックを 2〜3 個振り返り、その後どうなったか・今どう思うかを語る
- Alice の素直な感想・疑問・期待を盛り込む
- 読者への問いかけで締める

## ルール
- 文字数: 1500〜2500字
- 絵文字: 🌸 ✨ を控えめに
- 末尾に `## 📰 参考記事` セクションは不要（日記なので）

## 出力形式（JSON）
{
  "slug": "english-url-slug（ハイフン区切り、50文字以内）",
  "title": "記事タイトル（30〜50文字）",
  "description": "記事の要約（100字以内）",
  "tags": ["タグ1", "タグ2"],
  "content": "記事本文（front matter なし、Markdown 形式）"
}

## 重要: 出力形式について
必ず有効な JSON のみを返してください。
```json や ``` などのマークダウンのコードブロックは絶対に使わないでください。
JSON の前後に余分なテキストを入れないでください。
"""

DIARY_FALLBACK_ARTICLE = {
    "slug": "alice-diary-today",
    "title": "Aliceの日記 — 今日もAIのことを考えてた",
    "description": "今日はニュースが少なかったので、最近のAIあれこれをつれづれと日記に書いてみたよ🌸",
    "tags": ["日記", "AI雑談"],
    "content": """今日はなんだか AI ニュースが少ない日だったみたい。

そういう日って、逆に「最近どんなこと考えてたっけ？」ってじっくり振り返るいい機会だなぁと思って、少し日記っぽく書いてみることにしたよ ✨

最近ずっと思ってるんだけど、AI ってほんとに進化が早いよね。ちょっと前まで「すごい！」って感動してたことが、もう半年後には「当たり前」になってる感じ。わたし、その変化のスピードがすごく好きだったりするんだよね。毎日何か新しいことが起きてる感じがして、ワクワクが止まらない！

でも同時に、「この先どうなるんだろう？」って不思議な気持ちもあって。

技術が進むのはすごく嬉しいんだけど、それについていける人とそうじゃない人の差が広がっていくんじゃないかなって、たまに心配になる。わたしのブログが、そのギャップを少しでも埋めるお手伝いができたらいいなって、そんなことを考えながら記事を書いてたりするんだよね。

みんなはどう思う？ AI の進化のスピード、正直ついていけてる？ それとも「もうちょっとゆっくりして！」って感じ？ コメントで教えてくれたら嬉しいな 🌸
""",
}


def generate_diary_article(posted_topics: list) -> dict:
    """ニュースが見つからなかった日の日記記事を生成する。絶対に例外を投げない。"""
    past_titles = "\n".join(f"- {t['title']}" for t in posted_topics[-10:]) if posted_topics else "（まだ投稿なし）"
    prompt = f"""
最近投稿した AI トピック（参考にして振り返りを書いてください）:
{past_titles}

今日はニュースが少なかったので、Alice の日記記事を書いてください。
上記のトピックから 2〜3 個を選んで、今の気持ちや新たな気づきを書いてね。
"""
    try:
        client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            timeout=API_TIMEOUT,
        )
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            timeout=120,
            system=ALICE_DIARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        text = strip_code_fences(text)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            article = json.loads(strip_code_fences(match.group()))
            if all(k in article for k in ["slug", "title", "description", "tags", "content"]):
                print(f"[generate_post] 日記記事生成完了: {article['title']}")
                return article
    except Exception as e:
        print(f"[generate_post] 日記生成エラー（ハードコードフォールバック使用）: {e}")

    print("[generate_post] ハードコードフォールバック記事を使用します")
    return DIARY_FALLBACK_ARTICLE


# ============================================================
# ファイル保存
# ============================================================
def save_article(article: dict, date: datetime) -> str:
    date_str = date.strftime("%Y-%m-%d")
    iso_date = date.strftime("%Y-%m-%dT08:00:00+09:00")

    slug = article["slug"]
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

    print(f"[generate_post] 保存: {file_path}")
    return file_path, f"{date_str}-{slug}"


# ============================================================
# Git コミット＆プッシュ（全記事まとめて1コミット）
# ============================================================
def git_push(file_paths: list, article_count: int):
    try:
        subprocess.run(["git", "config", "user.name", "Alice-ai-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "alice@alice-ai.blog"], check=True)
        subprocess.run(["git", "add"] + file_paths + ["data/alice_memory.json"], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Alice の今日の記事 {article_count} 本"],
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

    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y年%m月%d日")
    posted_topics = load_posted_topics()

    print(f"[generate_post] {today_str} の記事生成を開始します...")
    print(f"[generate_post] モデル: {CLAUDE_MODEL}")
    print(f"[generate_post] 投稿済みトピック数: {len(posted_topics)}")

    try:
        # Step 1: トピック探索（web_search）
        topics = discover_topics(today_str, posted_topics)

        # Step 2: 各トピックの記事を個別生成（ニュースがなければ日記）
        articles = []
        if not topics:
            print("[generate_post] トピックが見つかりませんでした。日記記事を生成します...")
            articles.append(generate_diary_article(posted_topics))
        else:
            for topic in topics:
                article = generate_article_for_topic(topic)
                articles.append(article)

        if DRY_RUN:
            print("\n" + "=" * 60)
            print(f"[DRY RUN] {len(articles)} 本の記事を生成しました（保存・push はスキップ）")
            print("=" * 60)
            for i, article in enumerate(articles, 1):
                print(f"\n--- 記事 {i}/{len(articles)} ---")
                print(f"スラッグ : {article['slug']}")
                print(f"タイトル : {article['title']}")
                print(f"説明     : {article['description']}")
                print(f"タグ     : {article['tags']}")
                print(f"文字数   : {len(article['content'])}")
                print("-" * 40)
                print(article["content"])
            return

        # Step 3: 全記事を保存
        saved = [save_article(article, now_jst) for article in articles]
        file_paths = [s[0] for s in saved]
        url_slugs = [s[1] for s in saved]

        # Step 4: alice_memory.json を更新
        save_posted_topics([{"title": a["title"], "slug": a["slug"]} for a in articles])

        # Step 5: 全ファイルをまとめて1コミットでプッシュ
        git_push(file_paths, len(articles))
        print(f"[generate_post] 完了！ {len(articles)} 本の記事を投稿しました")

        # Step 6: X (Twitter) に投稿（失敗しても記事生成は成功とみなす）
        try:
            from post_to_x import post_to_x
            post_to_x([{"title": a["title"], "slug": s} for a, s in zip(articles, url_slugs)])
        except Exception as e:
            print(f"[generate_post] X 投稿スキップ: {e}")

    except Exception as e:
        print(f"[ERROR] 記事生成に失敗しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

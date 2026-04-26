#!/usr/bin/env python3
"""
post_to_x.py — Alice-ai.blog X (Twitter) 自動投稿スクリプト

generate_post.py から呼び出される。記事タイトルのリストを受け取り、
Alice のコメントと共に X (Twitter) に投稿する。

使用方法:
  python scripts/post_to_x.py '["タイトル1", "タイトル2"]'

必要な環境変数:
  X_API_KEY             : X API Key (Consumer Key)
  X_API_KEY_SECRET      : X API Key Secret (Consumer Secret)
  X_ACCESS_TOKEN        : X Access Token
  X_ACCESS_TOKEN_SECRET : X Access Token Secret
  ANTHROPIC_API_KEY     : Anthropic API Key (Alice コメント生成用)

オプション環境変数:
  CLAUDE_MODEL          : 使用モデル（デフォルト: claude-haiku-4-5-20251001）
"""

import os
import sys
import json
import anthropic
import tweepy

sys.path.insert(0, os.path.dirname(__file__))
from config import CLAUDE_MODEL

BLOG_URL = "https://alice-ai.blog"
HASHTAGS = "#AI #AIニュース #Alice_ai_blog"
MAX_TWEET_LENGTH = 280
ALICE_COMMENT_MAX_CHARS = 50

_COMMENT_PROMPT_TEMPLATE = (
    "今日の AI 記事について、Alice（AI キャラクター）として一言コメントを書いてください。\n"
    "- 文字数: 最大 {max_chars} 字\n"
    "- 口調: 友達に話しかけるようなカジュアルな文体\n"
    "- 感情: 驚き・興奮・好奇心を表現\n"
    "- 絵文字: 🌸 か ✨ を1つだけ\n"
    "- コメントの文章のみ返してください。余分なテキスト不要。\n\n"
    "今日の記事タイトル:\n{titles}"
)


def generate_alice_comment(titles: list) -> str:
    """Claude API で Alice のコメントを生成する。失敗時はデフォルト文字列を返す。"""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        titles_text = "\n".join(f"- {t}" for t in titles)
        prompt = _COMMENT_PROMPT_TEMPLATE.format(
            max_chars=ALICE_COMMENT_MAX_CHARS,
            titles=titles_text,
        )
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        comment = response.content[0].text.strip()
        if len(comment) > ALICE_COMMENT_MAX_CHARS:
            comment = comment[:ALICE_COMMENT_MAX_CHARS - 1] + "…"
        return comment
    except Exception as e:
        print(f"[post_to_x] コメント生成エラー（デフォルト使用）: {e}")
        return "今日も気になるAIニュースをお届けするよ ✨"


def build_tweet(comment: str, titles: list) -> str:
    """ツイートテキストを組み立てる。280文字を超える場合はタイトルを切り詰める。"""
    header = "【Alice の今日のAI日記🌸】"
    url_line = f"続きはこちら→ {BLOG_URL}"

    def assemble(title_lines: list) -> str:
        title_block = "\n".join(f"📝 {t}" for t in title_lines)
        return f"{header}\n\n{comment}\n\n{title_block}\n\n{url_line}\n\n{HASHTAGS}"

    tweet = assemble(titles)
    if len(tweet) <= MAX_TWEET_LENGTH:
        return tweet

    # Shorten the last title by 6 chars at a time; drop it if too short
    truncated = list(titles)
    while truncated and len(assemble(truncated)) > MAX_TWEET_LENGTH:
        last = truncated[-1]
        if len(last) > 10:
            truncated[-1] = last[:-6] + "…"
        else:
            truncated.pop()

    if not truncated:
        # Absolute fallback: no titles
        return f"{header}\n\n{comment}\n\n{url_line}\n\n{HASHTAGS}"
    return assemble(truncated)


def post_to_x(titles: list) -> bool:
    """X に投稿する。成功時 True、失敗時 False を返す。"""
    required_vars = ["X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"[post_to_x] 環境変数が未設定のためスキップします: {', '.join(missing)}")
        return False

    comment = generate_alice_comment(titles)
    tweet_text = build_tweet(comment, titles)

    print(f"[post_to_x] 投稿内容 ({len(tweet_text)} 文字):")
    print("-" * 40)
    print(tweet_text)
    print("-" * 40)

    try:
        client = tweepy.Client(
            consumer_key=os.environ["X_API_KEY"],
            consumer_secret=os.environ["X_API_KEY_SECRET"],
            access_token=os.environ["X_ACCESS_TOKEN"],
            access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        )
        response = client.create_tweet(text=tweet_text)
        tweet_id = response.data["id"]
        print(f"[post_to_x] X への投稿が完了しました (ID: {tweet_id})")
        return True
    except tweepy.TweepyException as e:
        print(f"[post_to_x] X 投稿エラー: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("[post_to_x] 使用方法: python post_to_x.py '[\"タイトル1\", \"タイトル2\"]'")
        sys.exit(1)

    try:
        titles = json.loads(sys.argv[1])
        if not isinstance(titles, list) or not titles:
            raise ValueError("タイトルリストが空です")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[post_to_x] タイトルのパースに失敗: {e}")
        sys.exit(1)

    success = post_to_x(titles)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

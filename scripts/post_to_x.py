#!/usr/bin/env python3
"""
post_to_x.py — Alice-ai.blog X (Twitter) 自動投稿スクリプト

generate_post.py から呼び出される。記事情報のリストを受け取り、
Alice のコメントと共に X (Twitter) に投稿する。

使用方法:
  python scripts/post_to_x.py '[{"title":"タイトル1","slug":"2026-04-26-slug-1"},...]'

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
import re
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
# X/Twitter counts all URLs as 23 chars via t.co shortening
_TWITTER_URL_WEIGHT = 23

_COMMENT_PROMPT_TEMPLATE = (
    "今日の AI 記事について、Alice（AI キャラクター）として一言コメントを書いてください。\n"
    "- 文字数: 最大 {max_chars} 字\n"
    "- 一人称: 必ず「わたし」を使う。「ぼく」「おれ」「あたし」は絶対に使わない\n"
    "- 口調: 友達に話しかけるようなカジュアルな文体\n"
    "- 感情: 驚き・興奮・好奇心を表現\n"
    "- 絵文字: 🌸 か ✨ を1つだけ\n"
    "- コメントの文章のみ返してください。余分なテキスト不要。\n\n"
    "今日の記事タイトル:\n{titles}"
)

_URL_RE = re.compile(r'https?://\S+')


def _tweet_len(text: str) -> int:
    """Twitter-weighted character count (each URL counted as 23 chars)."""
    adjusted = _URL_RE.sub('x' * _TWITTER_URL_WEIGHT, text)
    return len(adjusted)


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


def _article_url(slug: str) -> str:
    return f"{BLOG_URL}/posts/{slug}/"


def build_tweet(comment: str, articles: list) -> str:
    """
    ツイートテキストを組み立てる。
    articles: list of {"title": str, "slug": str}

    優先順位:
      1. 全タイトル＋全リンク（フル形式）
      2. 後ろのリンクから順に削除して全タイトルを確保
      3. 全リンク削除後もオーバーする場合はタイトルを切り詰め
    """
    header = "【Alice の今日のAI日記🌸】"

    def assemble(lines: list) -> str:
        block = "\n".join(lines)
        return f"{header}\n\n{comment}\n\n{block}\n\n{HASHTAGS}"

    # Build full line list with per-article title + link pairs
    def make_lines(include_link: list) -> list:
        lines = []
        for a, show in zip(articles, include_link):
            lines.append(f"📝 {a['title']}")
            if show:
                lines.append(f"🔗 {_article_url(a['slug'])}")
        return lines

    include_link = [True] * len(articles)
    tweet = assemble(make_lines(include_link))
    if _tweet_len(tweet) <= MAX_TWEET_LENGTH:
        return tweet

    # Remove links one by one from last article to first
    for i in range(len(articles) - 1, -1, -1):
        include_link[i] = False
        tweet = assemble(make_lines(include_link))
        if _tweet_len(tweet) <= MAX_TWEET_LENGTH:
            return tweet

    # All links removed — truncate titles if still over limit
    trunc_titles = [a["title"] for a in articles]
    while trunc_titles:
        lines = [f"📝 {t}" for t in trunc_titles]
        if _tweet_len(assemble(lines)) <= MAX_TWEET_LENGTH:
            return assemble(lines)
        last = trunc_titles[-1]
        if len(last) > 10:
            trunc_titles[-1] = last[:-6] + "…"
        else:
            trunc_titles.pop()

    return f"{header}\n\n{comment}\n\n{HASHTAGS}"


def post_to_x(articles: list):
    """
    ツイート内容を生成してコンソールに出力する。X API への実際の投稿は無効化中。
    articles: list of {"title": str, "slug": str}
    戻り値: tweet_text (str) — 失敗時は None
    """
    titles = [a["title"] for a in articles]
    comment = generate_alice_comment(titles)
    tweet_text = build_tweet(comment, articles)

    print(f"[post_to_x] ツイート内容 ({_tweet_len(tweet_text)} 文字 / Twitter換算):")
    print("-" * 40)
    print(tweet_text)
    print("-" * 40)
    print("[post_to_x] X API 投稿は現在無効化中（data/today_tweet.txt に保存）")

    return tweet_text


def main():
    if len(sys.argv) < 2:
        print('[post_to_x] 使用方法: python post_to_x.py \'[{"title":"タイトル","slug":"2026-04-26-slug"}]\'')
        sys.exit(1)

    try:
        articles = json.loads(sys.argv[1])
        if not isinstance(articles, list) or not articles:
            raise ValueError("記事リストが空です")
        for item in articles:
            if not isinstance(item, dict) or "title" not in item or "slug" not in item:
                raise ValueError(f"各要素は {{title, slug}} の形式が必要です: {item}")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[post_to_x] 引数のパースに失敗: {e}")
        sys.exit(1)

    success = post_to_x(articles)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

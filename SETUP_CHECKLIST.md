# 🚀 セットアップチェックリスト

---

## ✅ 実装済み（Claude Code 完了）

- [x] Hugo + PaperMod テーマ構築・Cloudflare Pages デプロイ
- [x] Giscus コメント欄（`layouts/partials/comments.html`）
  - repo-id: `R_kgDOSGJXCQ` / category-id: `DIC_kwDOSGJXCc4C7JO5` 設定済み
- [x] `scripts/generate_post.py`（記事自動生成）
- [x] `scripts/config.py`（モデル設定集中管理）
- [x] `requirements.txt`（`anthropic>=0.49.0`）
- [x] `.github/workflows/daily_post.yml`（毎朝 8:00 JST 自動実行）
- [x] `.github/workflows/test_dry_run.yml`（手動テスト用）
- [x] `workers/comment_reply/src/index.js`（Cloudflare Workers 実装）
- [x] `workers/README.md`（デプロイ手順）

---

## 🔧 あなたが実施する残作業

### 1. GitHub Secrets / Variables を登録

GitHub → リポジトリ → **Settings → Secrets and variables → Actions**

**Secrets（New repository secret）**:

| シークレット名 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API キー |
| `GH_PAT` | GitHub Fine-grained PAT（Contents: Read and write） |

**Variables（New repository variable）**:

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | 記事生成モデル。変更時のみ設定 |

---

### 2. GitHub Actions のテスト実行

1. GitHub → Actions → **「Alice の毎日記事生成」**
2. 「Run workflow」→「Run workflow」をクリック
3. ログに 2000 字以上の記事が生成されれば成功

または **「[TEST] DRY_RUN 記事生成テスト」** ワークフローでも確認可能（ファイル保存・push なし）

---

### 3. Cloudflare Workers デプロイ

詳細は `workers/README.md` を参照。概要:

```bash
cd workers/comment_reply
npm install
wrangler login
wrangler kv:namespace create COMMENT_CACHE   # → 出力IDをwrangler.tomlに記入
wrangler secret put CLAUDE_API_KEY
wrangler secret put GITHUB_TOKEN
wrangler secret put GITHUB_WEBHOOK_SECRET
wrangler secret put BOT_ACCOUNT_NAME         # alice-ai-bot
wrangler secret put REPO_OWNER               # Alice-ai-blog
wrangler secret put REPO_NAME                # alice-ai-blog
wrangler deploy
```

デプロイ後、Workers の URL を GitHub Webhook に登録（Settings → Webhooks）。

---

### 4. 動作確認

- [ ] GitHub Actions 手動実行 → 記事が `content/posts/` に生成・push される
- [ ] Giscus でテストコメント投稿 → Alice が返信する
- [ ] `wrangler tail` で Workers のログを確認

---

## 🔐 セキュリティ注意事項

- シークレット・API キーは絶対にコミットしない（`.gitignore` で除外済み）
- `wrangler.toml` に直接シークレットを書かない
- `data/user_violations.json` はコミットするが中身のユーザー名は個人情報に注意

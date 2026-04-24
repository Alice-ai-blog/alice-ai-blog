# 🚀 セットアップチェックリスト

このフォルダの内容を alice-ai-blog リポジトリに配置して、各ステップを実行してください。

---

## 📁 ファイル配置場所

```
このフォルダの内容         →  配置先（alice-ai-blog/ 直下からの相対パス）
-----------------------       -------------------------------------------------
CLAUDE.md                  →  CLAUDE.md（リポジトリ直下）
scripts/generate_post.py   →  scripts/generate_post.py
.github/workflows/         →  .github/workflows/daily_post.yml
data/user_violations.json  →  data/user_violations.json
data/alice_memory.json     →  data/alice_memory.json
data/affiliate_links.json  →  data/affiliate_links.json
layouts/partials/          →  layouts/partials/comments.html
requirements.txt           →  requirements.txt
workers/                   →  workers/（フォルダごと）
```

---

## ✅ チェックリスト（順番に実施）

### 今日夜（あなたが実施）

- [ ] **Anthropic API キー発行**
  1. https://console.anthropic.com/ でアカウント作成
  2. API Keys → Create Key → コピーして保管（チャットには貼らないこと）
  3. Plans & Billing → Usage Limits → Hard Limit $5 に設定

- [ ] **GitHub PAT（Fine-grained）作成**
  1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
  2. 「Generate new token」
  3. Repository access: alice-ai-blog のみ選択
  4. Permissions:
     - Contents: Read and write（コミット・プッシュ用）
     - Discussions: Read and write（コメント返信用）
  5. トークン文字列をコピーして保管

- [ ] **GitHub Secrets に登録**
  1. GitHub → alice-ai-blog リポジトリ → Settings → Secrets and variables → Actions
  2. 以下を「New repository secret」で追加:

  **必須シークレット（Actions → Secrets）**:
  | シークレット名 | 内容 |
  |---|---|
  | `ANTHROPIC_API_KEY` | Anthropic API キー |
  | `GH_PAT` | GitHub PAT（Contents: Read and write）|

  **オプション変数（Actions → Variables）**:
  | 変数名 | デフォルト値 | 説明 |
  |---|---|---|
  | `CLAUDE_MODEL` | `claude-haiku-4-5` | 使用モデル変更時に設定 |

- [ ] **Giscus コメント欄の設定**
  1. https://giscus.app/ja にアクセス
  2. リポジトリ: `Alice-ai-blog/alice-ai-blog`
  3. ページ↔️ディスカッションの対応: 「パス名」を選択
  4. ディスカッションカテゴリ: 「Announcements」
  5. 生成されたコードの `data-repo-id` と `data-category-id` の値をコピー
  6. `layouts/partials/comments.html` の `REPO_ID_HERE` と `CATEGORY_ID_HERE` を置き換える
  7. `hugo.toml` の `comments = false` を `comments = true` に変更

### Claude Code が実施（コード改善）

- [ ] `scripts/generate_post.py` の動作確認・改善
  - スラッグ生成の改善（Claude API に英語スラッグ生成を依頼する方式）
  - エラーハンドリングの強化
  - テスト実行

- [ ] `workers/comment_reply/src/index.js` の完成
  - user_violations.json の更新処理（GitHub API 経由）
  - GitHub Block API 連携
  - 連投ユーザーのコメント統合処理

- [ ] Cloudflare Workers デプロイ
  1. `cd workers/comment_reply && npm install`
  2. `wrangler login`
  3. シークレット設定（wrangler secret put × 4）
  4. `wrangler deploy`
  5. GitHub Webhook 設定

- [ ] 動作テスト
  1. GitHub Actions を手動実行（daily_post.yml → Run workflow）
  2. Giscus でテストコメント → Workers が返信するか確認

---

## 📝 重要な注意事項

- **シークレット（APIキー等）は絶対にコミットしない**（.gitignore で除外済み）
- **CLAUDE.md はリポジトリにコミットして Claude Code に参照させること**
- **Blowfish テーマには戻らない**（PaperMod で確定）
- テスト時は Claude API のコストに注意（$5上限設定必須）

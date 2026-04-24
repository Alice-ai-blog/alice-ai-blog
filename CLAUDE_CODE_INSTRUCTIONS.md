# Claude Code 指示書 — Alice-ai.blog 自動化実装

## 最初にやること

まず以下のファイルを読んで、プロジェクト全体を把握してください:

```
CLAUDE.md
prompts/alice_persona.md
```

---

## タスク一覧（feature ブランチで順番に実装）

---

### TASK 01: data/ 初期ファイルのリポジトリ配置

**ブランチ**: `feature/data-init`

以下のファイルを `data/` フォルダに作成してコミット:
- `data/user_violations.json`（ブロックリスト・違反履歴）
- `data/alice_memory.json`（読者記憶・リクエスト記録）
- `data/affiliate_links.json`（アフィリエイトリンク）

初期内容は `claude-code-handoff/data/` の各ファイルをそのまま使用。

完了条件: `git push origin feature/data-init` 成功

---

### TASK 02: Giscus コメント欄の設置

**ブランチ**: `feature/giscus-comments`

1. `layouts/partials/comments.html` を作成
   - ベースは `claude-code-handoff/layouts/partials/comments.html`
   - `REPO_ID_HERE` と `CATEGORY_ID_HERE` は環境変数 or プレースホルダーのまま（ユーザーが後で設定）
2. `config/_default/hugo.toml` の `comments = false` を `comments = true` に変更

完了条件: ローカルで `hugo server` を起動し、記事ページにコメント欄のプレースホルダーが表示される

---

### TASK 03: requirements.txt と generate_post.py の配置・改善

**ブランチ**: `feature/article-generation`

1. `requirements.txt` を配置（`claude-code-handoff/requirements.txt` から）
2. `scripts/generate_post.py` を配置（`claude-code-handoff/scripts/generate_post.py` から）
3. 以下の改善を加える:
   - **スラッグ生成の改善**: タイトルから英語スラッグを生成する際に Claude API に依頼する方式に変更
     ```python
     # 記事生成時に以下もClaude APIに生成させる
     # {"slug": "ai-model-release-2026", "title": "...", "content": "..."}
     # → front matter の date + slug でファイルパスを決定
     ```
   - **front matter の date 形式**: Hugo の ISO8601 形式 `2026-04-20T08:00:00+09:00` に修正
   - **エラーハンドリング**: API タイムアウト（30秒）、レスポンスが空の場合のリトライ（最大2回）
   - **ドライラン機能**: 環境変数 `DRY_RUN=true` の時はファイル保存・git push せずに記事内容だけ出力

4. ローカルテスト:
   ```bash
   DRY_RUN=true ANTHROPIC_API_KEY=実際のキー python scripts/generate_post.py
   ```
   記事が標準出力に表示されれば成功

完了条件: ドライランで 2000 字以上の Alice 口調記事が生成される

---

### TASK 04: GitHub Actions ワークフローの配置

**ブランチ**: `feature/github-actions`

1. `.github/workflows/daily_post.yml` を作成（`claude-code-handoff/.github/workflows/daily_post.yml` から）
2. 以下を確認・修正:
   - `cron: '0 23 * * *'` が毎朝 8:00 JST に対応しているか確認
   - `workflow_dispatch` でのテスト実行が可能な設定になっているか確認
   - `submodules: true` が含まれているか確認（PaperMod テーマのため）

3. GitHub Secrets の設定手順を `SETUP_CHECKLIST.md` に追記:
   ```
   必要なシークレット:
   - ANTHROPIC_API_KEY（Anthropic API キー）
   - GH_PAT（GitHub PAT、repo権限）
   オプション:
   - CLAUDE_MODEL（デフォルト: claude-haiku-4-5）
   ```

完了条件: `git push origin feature/github-actions` 後、GitHub Actions の画面で `daily_post.yml` が表示される

---

### TASK 05: Cloudflare Workers コメント返信の完成

**ブランチ**: `feature/workers-comment-reply`

ベースは `claude-code-handoff/workers/comment_reply/src/index.js`

以下の未実装部分を完成させる:

#### 5-1. user_violations.json の更新処理

違反が発生した時に GitHub API 経由でファイルを更新する関数を実装:

```javascript
async function recordViolation(username, violationType, env) {
  // 1. GitHub API で現在の user_violations.json を取得
  // 2. violations[username] にエントリを追加/更新
  // 3. 3回以上違反 → blocked_users に追加
  // 4. GitHub API でファイルを更新（PUT /repos/{owner}/{repo}/contents/{path}）
}
```

#### 5-2. GitHub Block API 連携

ユーザーをブロックする関数:

```javascript
async function blockUser(username, env) {
  // PUT /user/blocks/{username}
  // GITHUB_TOKEN で実行
  // ブロック後 user_violations.json の blocked_users に記録
}
```

#### 5-3. 連投コメント統合処理

同一ユーザーから5分以内に複数コメントが届いた場合の処理:
- Workers の KV Store（またはシンプルなメモリキャッシュ）で直近のコメントを一時保持
- 5分のウィンドウ内に届いたコメントを統合して1回だけ返信

```javascript
// KV Store を使う場合: wrangler.toml に kv_namespaces を追加
// [[kv_namespaces]]
// binding = "COMMENT_CACHE"
// id = "KV_NAMESPACE_ID"
```

#### 5-4. 2回目違反の警告、3回目のブロック処理

```javascript
// violations[username].count に応じて:
// 1回目: パターンA〜Dで返信
// 2回目: パターンEで警告
// 3回目以降: 返信なし + blockUser() 実行
```

完了条件:
- `wrangler deploy` でエラーなくデプロイできる
- `workers/README.md` のデプロイ手順が正確である

---

### TASK 06: 全体テストとマージ

**ブランチ**: `main`（各 feature ブランチを順番にマージ）

1. 各 feature ブランチを `main` にマージ:
   ```
   feature/data-init → main
   feature/giscus-comments → main
   feature/article-generation → main
   feature/github-actions → main
   feature/workers-comment-reply → main
   ```

2. マージ後に Cloudflare Pages が正常にビルドされることを確認

3. GitHub Actions を手動実行してテスト:
   - Actions タブ → 「Alice の毎日記事生成」→ 「Run workflow」

4. Workers の動作確認:
   - GitHub Discussions にテストコメントを投稿
   - Alice が返信するか確認

---

## 注意事項

- シークレット（APIキー等）は絶対にコミットしない
- `.gitignore` に以下が含まれているか確認: `*.env`, `.env.*`, `public/`
- Blowfish テーマは完全に廃棄済み。PaperMod で確定
- モデル名は `scripts/generate_post.py` と環境変数 `CLAUDE_MODEL` で一元管理
- `data/*.json` は git 管理する（読者情報の永続化のため）

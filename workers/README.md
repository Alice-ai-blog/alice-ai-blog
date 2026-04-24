# Cloudflare Workers デプロイ手順

## 前提条件
- Node.js 18+ がインストール済み
- Cloudflare アカウントでログイン済み（`wrangler login`）

## デプロイ手順

### 1. wrangler をインストール
```bash
cd workers/comment_reply
npm install
```

### 2. KV ネームスペースを作成（連投検出用）
```bash
wrangler kv:namespace create COMMENT_CACHE
```

出力された ID を `wrangler.toml` の `kv_namespaces` セクションに設定:
```toml
[[kv_namespaces]]
binding = "COMMENT_CACHE"
id = "ここに出力されたIDを貼る"
```

### 3. シークレットを設定（順番に実行）
```bash
wrangler secret put CLAUDE_API_KEY
# プロンプトが出たら Anthropic API キーを入力

wrangler secret put GITHUB_TOKEN
# プロンプトが出たら GitHub Fine-grained PAT を入力
# 権限: Discussions（Read and write）、Contents（Read and write）

wrangler secret put GITHUB_WEBHOOK_SECRET
# プロンプトが出たら任意のランダム文字列を入力（例: openssl rand -hex 32 で生成）

wrangler secret put BOT_ACCOUNT_NAME
# プロンプトが出たら Bot の GitHub ユーザー名を入力（例: alice-ai-bot）

wrangler secret put REPO_OWNER
# プロンプトが出たら Alice-ai-blog と入力

wrangler secret put REPO_NAME
# プロンプトが出たら alice-ai-blog と入力
```

### 4. Workers をデプロイ
```bash
wrangler deploy
```

デプロイ成功すると `https://alice-comment-reply.YOUR-SUBDOMAIN.workers.dev` のような URL が発行されます。

### 5. GitHub Webhook を設定
1. GitHub リポジトリ → Settings → Webhooks → Add webhook
2. **Payload URL**: wrangler deploy で発行された Workers の URL
3. **Content type**: `application/json`
4. **Secret**: Step 3 で `GITHUB_WEBHOOK_SECRET` に設定した値
5. **Which events**: 「Let me select individual events」→ `Discussion comments` のみチェック
6. **Active**: チェックON
7. 「Add webhook」をクリック

### 6. 動作確認
Webhook の設定後、テスト用コメントを GitHub Discussions に投稿して Alice が返信するか確認してください。

## トラブルシューティング

### 返信が来ない場合
1. Cloudflare Workers のログを確認: `wrangler tail`
2. GitHub → Settings → Webhooks → 該当 Webhook → Recent Deliveries でレスポンスを確認

### 署名検証エラー
`GITHUB_WEBHOOK_SECRET` が Webhook 設定の Secret と一致しているか確認

### Bot ループが発生する場合
`BOT_ACCOUNT_NAME` が Bot の正確な GitHub ユーザー名と一致しているか確認

### KV が使えない場合
`wrangler.toml` の `kv_namespaces` コメントを外して正しい ID を設定する。
KV なしでも動作するが、連投コメント統合機能は無効になる。

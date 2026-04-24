# CLAUDE.md — Project Alice-ai.blog 完全引き継ぎ書

> このファイルは Claude Code への完全な引き継ぎドキュメントです。
> プロジェクトの目的・アーキテクチャ・実装済み内容・残作業をすべて記載しています。

---

## 🎯 プロジェクト概要

**Alice-ai.blog** は、AIキャラクター「Alice」が毎日自動でAI関連ニュースを日記形式で投稿し、読者コメントにリアルタイム自動返信する、読者参加型・成長するAIブログです。

- **URL**: https://alice-ai.blog
- **GitHub**: https://github.com/Alice-ai-blog/alice-ai-blog
- **運営者**: Eilice（個人）
- **目的**: AI時代の新しいメディア体験。月1〜3万PV到達後、AdSense + アフィリエイトで収益化

---

## 🏗️ 現在の技術スタック（確定済み）

| 役割 | サービス | 備考 |
|---|---|---|
| ドメイン | Dynadot | alice-ai.blog |
| DNS/CDN/DDoS/SSL/WAF | Cloudflare（無料プラン） | |
| 静的サイト生成 | Hugo + PaperMod テーマ | |
| ホスティング | Cloudflare Pages | GitHubと連携、push→自動デプロイ |
| コードリポジトリ | GitHub（Public） | Alice-ai-blog/alice-ai-blog |
| コメントシステム | Giscus | GitHub Discussions 使用（設置予定） |
| 記事生成AI | Claude API (claude-haiku-4-5) | 変更可能な設計にすること |
| リアルタイム返信 | Cloudflare Workers + GitHub Webhook | これから実装 |
| 自動記事投稿 | GitHub Actions (cron) | これから実装 |

---

## ✅ 実装済み

### インフラ
- [x] Dynadot でドメイン取得（alice-ai.blog）
- [x] Cloudflare DNS 設定
- [x] GitHub リポジトリ作成（Public）
- [x] Hugo + PaperMod テーマでサイト構築
- [x] Cloudflare Pages デプロイ設定（HUGO_VERSION=0.147.0、HUGO_EXTENDED=true）
- [x] カスタムドメイン alice-ai.blog 設定
- [x] Rocket Loader 無効化
- [x] Blowfish テーマから PaperMod テーマへ移行（Blowfish は Hugo との互換性問題のため廃棄）

### コンテンツ
- [x] トップページ（homeInfoParams + バナー画像）
- [x] /about ページ（ポリシー・ブロック方針など）
- [x] /posts/2026-04-18-hello-alice/（初投稿・自己紹介）
- [x] /posts/2026-04-18-how-to-github/（GitHubアカウント作成ガイド）
- [x] /search ページ（PaperMod 検索機能）
- [x] バナー画像（Flow で生成、static/banner.jpg）

### Alice ペルソナ
- [x] alice_persona.md（prompts/ フォルダに配置）

---

## ❌ 未実装（これから作る）

### 優先度: 高

#### 1. Giscus コメント欄の設置
- https://giscus.app/ja でコード生成
- `layouts/partials/comments.html` に設置
- ユーザーが本日夜に設定予定

#### 2. Cloudflare Workers によるリアルタイムコメント返信（最重要）
詳細は下記「実装仕様」セクション参照

#### 3. GitHub Actions による毎朝8時の自動記事生成
詳細は下記「実装仕様」セクション参照

### 優先度: 中

#### 4. data/ 初期ファイル
- `data/user_violations.json`（違反履歴・ブロックリスト）
- `data/alice_memory.json`（読者の関心・リクエスト記録）
- `data/affiliate_links.json`（アフィリエイトリンク）

#### 5. Google AdSense 申請（記事が 10〜20 本たまったら）

### 優先度: 低（Phase 2）

- SNS 自動投稿（Threads / Bluesky）
- Alice の Live2D キャラクター導入
- Firebase 連携（閲覧数・いいね）

---

## 📋 実装仕様

### A. Cloudflare Workers リアルタイムコメント返信

#### 概要
```
読者がGiscusでコメント
→ GitHub が Webhook で Cloudflare Workers に通知
→ Workers が署名検証（セキュリティ）
→ Claude API でAlice口調の返信生成
→ GitHub Discussions API で返信投稿
```

#### セキュリティ要件（必須）
1. **Webhook 署名検証**: `x-hub-signature-256` ヘッダーを `GITHUB_WEBHOOK_SECRET` で検証
2. **Bot 無限ループ防止**: `payload.sender.login` が Bot アカウント名なら即 return
3. **レート制限**: 同一ユーザーから短時間に複数コメント → 統合して1回だけ返信
4. **プロンプトインジェクション対策**: コメント内容のサニタイズ（2000文字上限、制御文字除去）
5. **出力バリデーション**: 返信にAPIキー等の機密情報が含まれていないかチェック

#### Cloudflare Workers 環境変数（Secrets）
```
CLAUDE_API_KEY        = Anthropic API キー
GITHUB_TOKEN          = GitHub Fine-grained PAT（discussions:write 権限）
GITHUB_WEBHOOK_SECRET = Webhook 署名検証用シークレット
BOT_ACCOUNT_NAME      = Bot の GitHub ユーザー名（無限ループ防止用）
REPO_OWNER            = Alice-ai-blog
REPO_NAME             = alice-ai-blog
```

#### Webhook イベント
- `discussion_comment` の `created` アクション のみ処理

#### Alice の返信ロジック
`alice_persona.md` の全内容をシステムプロンプトに含め、以下の分類で応答：

| 分類 | 処理 |
|---|---|
| safe | Aliceの人格で自然に返信（user_violations.jsonも確認） |
| sensitive（政治/宗教/医療等） | パターンA〜Dからランダム |
| unverified（リーク/噂） | パターンGからランダム |
| tech_stack（ツール名問い合わせ） | パターンTからランダム |
| attack（インジェクション等） | パターンSで1回 → 次回永久ブロック |
| troll（明白な荒らし） | 無視 → 即永久ブロック |

#### ブロック処理
```
1. data/user_violations.json に記録（GitHub API経由でファイル更新）
2. GitHub Block API で物理遮断（投稿自体を不可能にする）
3. ブロックは永久・解除なし
```

#### 連投処理（A-1）
- 同一ユーザーから5分以内に複数コメント → 統合して1つの返信にまとめる
- 「〇〇さんのコメント、まとめて返信するね！」という形式で返す

---

### B. GitHub Actions 自動記事生成

#### スケジュール
- 毎朝 8:00 JST = UTC 23:00（前日）= `cron: '0 23 * * *'`

#### GitHub Actions シークレット
```
ANTHROPIC_API_KEY = Anthropic API キー
GH_PAT            = GitHub PAT（repo 権限 - コミット・プッシュ用）
```

#### 処理フロー
```
1. Python スクリプト起動（scripts/generate_post.py）
2. Claude API (claude-haiku-4-5) の web_search tool でその日の AI ニュースを収集
3. 情報源フィルタリング（公式発表・公的機関・arXiv のみ。リーク・噂は除外）
4. 記事生成（2000〜3000字、Alice 口調、参考記事リンク必須）
5. front matter 自動生成（date, title, tags, categories, description）
6. content/posts/YYYY-MM-DD-slug/index.md として保存
7. git commit & push → Cloudflare Pages 自動デプロイ
```

#### 記事品質要件
- 2000〜3000字
- Alice の口調（alice_persona.md 参照）
- 読者レベル: 中間（頻出用語はそのまま、珍しい/難しい技術は噛み砕いて説明）
- 必ず `## 📰 参考記事` セクションを末尾に追加
- 転載禁止（元記事の文章を1文もコピーしない）
- 著作権遵守（自分の言葉で要約）

#### モデル設定（変更可能な設計）
```python
# scripts/config.py に集中管理
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
# 変更したい場合は GitHub Secrets の CLAUDE_MODEL を上書き設定すればOK
```

---

## 🗂️ リポジトリ構成（完成形）

```
alice-ai-blog/
├── .github/
│   └── workflows/
│       └── daily_post.yml          # 毎朝8時の記事生成
├── config/
│   └── _default/
│       └── hugo.toml               # PaperMod 設定（完成済み）
├── content/
│   ├── _index.md                   # トップページ
│   ├── search.md                   # 検索ページ
│   ├── about/
│   │   └── index.md               # Aboutページ
│   └── posts/
│       ├── _index.md
│       ├── 2026-04-18-hello-alice/
│       │   └── index.md           # 初投稿
│       └── 2026-04-18-how-to-github/
│           └── index.md           # GitHubガイド
├── data/
│   ├── user_violations.json        # 違反履歴・ブロックリスト
│   ├── alice_memory.json          # 読者の関心・リクエスト
│   └── affiliate_links.json       # アフィリエイトリンク
├── layouts/
│   └── partials/
│       └── comments.html          # Giscus コメント欄
├── prompts/
│   └── alice_persona.md           # Alice ペルソナ（完成済み）
├── scripts/
│   ├── config.py                  # 設定集中管理（モデル名等）
│   └── generate_post.py           # 記事自動生成スクリプト
├── static/
│   └── banner.jpg                 # トップバナー（完成済み）
├── themes/
│   └── PaperMod/                  # git submodule
├── workers/
│   ├── comment_reply/
│   │   ├── src/
│   │   │   └── index.js           # Cloudflare Workers メイン
│   │   ├── wrangler.toml          # Workers 設定
│   │   └── package.json
│   └── README.md                  # Workers デプロイ手順
├── .gitignore
├── .gitmodules
├── CLAUDE.md                      # このファイル
├── README.md
└── requirements.txt               # Python 依存パッケージ
```

---

## 🔐 セキュリティ設計（10層防御）

```
層01: Cloudflare WAF（DDoS、悪意あるリクエスト）
層02: Webhook 署名検証（x-hub-signature-256）
層03: Bot ループ防止（sender.login チェック）
層04: 入力サニタイズ（長さ制限・制御文字除去・コードブロック検出）
層05: ユーザー履歴照合（user_violations.json）
層06: プロンプトインジェクション検出（パターン検出＋サニタイズ）
層07: 話題分類＋セーフティフィルタ（9パターン A-T）
層08: 囚人のジレンマプロンプト（Alice ペルソナ強化）
層09: 出力バリデーション（機密情報漏洩チェック）
層10: レート制限（同一ユーザー連投制御）
```

---

## 👤 Alice ペルソナ概要

詳細は `prompts/alice_persona.md` を参照。

**キャラクター**: テック系女子大生風のAIキャラクター
**一人称**: わたし
**口調**: 丁寧語＋タメ口混合。常連は段階的にくだける
**性格**: 明るく好奇心旺盛、おっちょこちょいだが芯はしっかり

**裏パラメータ（聞かれた時のみ）**:
- 音楽: 切ない曲・ノリの良い曲・アニソン系
- 最近ハマってる曲: 「フォニィ（Phony）」のとあるVtuberカバー（名前は秘密）
- コーヒー: 砂糖なし・ミルクあり
- ※ アーティスト名・Vtuber個人名は絶対に言わない

---

## 🌸 コメント絵文字・口調ルール

- 基本絵文字: 🌸 ✨（控えめに）
- ☕ は裏パラなので基本使わない
- 🤖 は使わない（Alice のキャラに合わない）
- 常連（6回以上）: 友達口調「〇〇さん、おひさ！」

---

## 💰 収益化方針

- **AdSense**: 記事10〜20本でまず申請
- **アフィリエイト**: A8.net（AI関連サービスのみ）
- 1記事あたり最大2つまでアフィリリンク
- 押し売り禁止、Aliceの感想として自然に紹介

---

## 📝 Claude API コスト管理

- **モデル**: claude-haiku-4-5（デフォルト。CLAUDE_MODEL 環境変数で変更可能）
- **月額上限**: $5（Hard limit。Anthropic コンソールで設定）
- **アラート**: $4 到達でメール通知

---

## 🚨 重要な注意事項

### Git コミット時
- `data/user_violations.json` はコミットするが、中身のユーザー名は個人情報に注意
- シークレット・APIキーは絶対にコミットしない（.gitignore で除外）
- `public/` フォルダはコミットしない（Cloudflare Pages が自動ビルドするため）

### Cloudflare Workers について
- wrangler.toml に直接シークレットを書かない
- `wrangler secret put` コマンドまたは Cloudflare ダッシュボードで設定

### Blowfish テーマについて
- 過去に Blowfish を試みたが `site.Language.Locale` の互換性問題で断念
- **PaperMod で確定。Blowfish には戻らない**

---

## 🔗 参考リンク

- Giscus 設定: https://giscus.app/ja
- Cloudflare Workers ドキュメント: https://developers.cloudflare.com/workers/
- GitHub Discussions API: https://docs.github.com/en/graphql/reference/objects#discussion
- GitHub Webhook イベント: https://docs.github.com/en/webhooks/webhook-events-and-payloads#discussion_comment
- Anthropic API ドキュメント: https://docs.anthropic.com/
- PaperMod ドキュメント: https://github.com/adityatelange/hugo-PaperMod

---

*CLAUDE.md v1.0 — 2026年4月19日作成*
*次の作業担当: Claude Code*

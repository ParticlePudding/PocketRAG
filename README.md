# PocketRAG（RAG プロンプトビルダー）

社内ChatGPT（APIなし）などに貼り付ける **RAG プロンプト** を、手元の資料から作るツールです。
資料の読み込み・検索（キーワード＋意味のハイブリッド）・ベクトル化はすべてローカルで行い、資料は外部に送信しません。

読み込める資料：PDF・Word（.docx）・Excel（.xlsx）・PowerPoint（.pptx）・テキスト・Markdown・CSV・HTML など。
データシートのスペック表などの表は、行と列の対応を残したまま（タブ区切りで）読み取ります。スキャン画像だけの PDF は読めません。

埋め込みモデル（意味検索）：ruri-v3-30m（日本語特化・軽量）、bge-m3（多言語）、EmbeddingGemma 2（Google・多言語。CLI・デスクトップ版のみ）。
比べた結果は [docs/埋め込みモデルの比較.md](docs/埋め込みモデルの比較.md) を参照。

| 形態 | 中身 | 向いている使い方 |
|---|---|---|
| ブラウザ版（GitHub Pages） | `index.html`（プロンプトビルダー）, `eval.html`（精度テスト） | すぐ試す。モデルは HuggingFace から自動取得、`?offline=1` で通信なし |
| オフライン配布版 | エンジン内蔵の HTML 2つ（ダブルクリックで動く） | ネット接続のない社内PC |
| CLI（`rag.exe`） | 検索・プロンプト生成・評価をコマンドで。ネイティブ版エンジンで高速 | 定型作業・自動化 |
| デスクトップ版 | `rag.exe` を内蔵した Tauri アプリ | 画面で使いたい・速さも欲しい |

## ビルド
```
npm install
python scripts/build.py site offline        # ブラウザ版・オフライン版
python scripts/build.py cli-windows         # CLI（Bun が必要）
```
デスクトップ版は Windows でビルドします（`.github/workflows/release.yml` を参照。Actions の「Release」を手動実行すると zip ができます）。

## 構成
- `src/prompt-builder.html` … プロンプトビルダー（検索・プロンプト生成の中核 `Core` もここ）
- `src/eval-template.html` … 精度テスト（ビルド時に Core とテストセットを埋め込む）
- `src/browser_embed.js` … ブラウザ内ベクトル化（Transformers.js / ONNX Runtime Web）
- `cli/src/` … CLI（Bun）。`rag serve` で画面とベクトル化API（OpenAI 互換 `/v1/embeddings`）も提供
- `desktop/src-tauri/` … デスクトップ版（`rag serve` を起動してウィンドウで開く）
- `src/sample/`・`src/testset.json` … テスト用資料（Wikipedia 6 記事・34 問）
- `src/sample-tech/`・`src/testset-tech.json` … テスト用資料（架空のセンサ基板の技術文書 13 件・48 問。`tests/make_tech_samples.py` と `tests/make_tech_testset.py` で作る）
- `tests/eval_retrieval.mjs` … 埋め込みモデルの検索性能の比較（LLM なし）

## ライセンス
このツールのソースコードは MIT License です（`LICENSE` を参照）。
テスト用資料は Wikipedia 日本語版の抜粋（CC BY-SA 4.0）と、このリポジトリのために作った架空の技術文書（MIT）。同梱する Transformers.js と PDF.js は Apache-2.0、ONNX Runtime は MIT。

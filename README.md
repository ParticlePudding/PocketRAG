# RAG プロンプトビルダー

社内ChatGPT（APIなし）などに貼り付ける **RAG プロンプト** を、手元の資料から作るツールです。
資料の読み込み・検索（キーワード＋意味のハイブリッド）・ベクトル化はすべてローカルで行い、資料は外部に送信しません。

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

## ライセンス
テスト用資料は Wikipedia 日本語版の抜粋（CC BY-SA 4.0）。同梱する Transformers.js は Apache-2.0、ONNX Runtime は MIT。

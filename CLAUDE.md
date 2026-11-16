# CLAUDE.md — RAG プロンプトビルダー（引き継ぎメモ）

このファイルは Claude（claude.ai のチャット）で開発してきた内容を Claude Code に引き継ぐためのメモです。
まず「目的と制約」「今の状態」「次にやること」を読んでください。

## 目的と制約（最重要）
- 利用者の会社では **API のない社内 ChatGPT** しか使えない。このツールは **RAG プロンプトを作ってコピペで渡す** のが本来の目的。
- **社内資料を PC の外に出さない**。資料の読み込み・検索・ベクトル化はすべてローカル。外部通信は「モデルのダウンロード」を明示的に行うときだけ。
- LLM への接続は **任意の機能**（精度評価・自動化用）。接続先は LM Studio / Ollama などのローカル LLM（OpenAI 互換）のみ。無料のクラウド API は使わない方針。
- 利用者は日本語話者。**画面・メッセージ・ドキュメント・コメントは日本語**。分かりやすい言葉で（専門用語には説明を添える）。
- 配布先は主に **Windows 10/11 の社内 PC**（ネット接続が制限される場合あり。署名なし exe は SmartScreen の警告が出る）。

## 構成
```
src/prompt-builder.html   プロンプトビルダー。検索・プロンプト生成の中核 Core（<script id="core">）もここが正本
src/eval-template.html    精度テスト（/*CORE*/ と /*TESTSET*/ をビルド時に埋め込む）
src/browser_embed.js      ブラウザ内ベクトル化 BrowserEmbed（Transformers.js + ONNX Runtime Web）
src/testset.json          評価用テストセット（Wikipedia 6記事・34問）。src/sample/ がその資料
src/offline/              オフライン配布版に同梱する説明書とモデル取得スクリプト（PowerShell）
cli/src/main.js           CLI（Bun）。index / search / prompt / ask / eval / models / rules / serve / app
cli/src/embed.js          CLI のベクトル化（ネイティブ版 onnxruntime-node。無ければ WASM 版に自動で切替）
desktop/src-tauri/        デスクトップ版（Tauri 2）。同じフォルダの rag.exe を「serve --port 0 --print-url」で起動してウィンドウで開くだけ
scripts/build.py          すべてのビルド（site / offline / cli-windows / cli-linux / desktop）
scripts/patch_tjs.py      CLI 用に Transformers.js の minify 済みコードへ手当て（下の「落とし穴」参照）
tests/                    ダミーモデル・速度比較用モデルの生成スクリプト
.github/workflows/        pages.yml（Pages 公開）, release.yml（Windows 向け配布物をビルド）
```
生成物（.gitignore 済み）：`dist/`, `cli/runtime/`, `cli/site/`, `cli/src/core.cjs`, `cli/src/site_files.js`

## ビルド
```
npm install                                   # @huggingface/transformers 4.3.2（固定）と onnxruntime-node/web
python scripts/build.py site offline          # dist/site（Pages 版）, dist/RAG精度テスト.zip（オフライン版）
python scripts/build.py cli-windows           # dist/RAG-CLI-windows.zip（要 Bun。Linux からのクロスビルド可）
python scripts/build.py desktop --app <tauri の exe>   # cli-windows の後。dist/RAG-Desktop.zip
cd desktop/src-tauri && cargo build --release --locked  # Windows でのみ（WebView2）
```
Windows で Python を使うときは `PYTHONUTF8=1` を付ける（日本語のファイル名を表示するため）。

## 4つの配布形態
| 形態 | ベクトル化 | モード |
|---|---|---|
| Pages 版（dist/site） | ブラウザ内（WebGPU / WASM） | http(s) で開くとオンライン（HF から取得・Cache Storage に保存）。`?offline=1` で通信なし |
| オフライン版（HTML 2つ） | 同上。エンジンを HTML に gzip+base64 で内蔵（約9MB） | file:// は常にオフライン。モデルは「モデルフォルダを追加…」で IndexedDB に取り込む |
| CLI（rag.exe） | ネイティブ版（engine フォルダ）。DirectML は `--device dml` | 通信なし（`models download` のみ通信） |
| デスクトップ版 | rag.exe の `/v1/embeddings` を画面から呼ぶ（エンジン選択「このアプリ」） | `window.RAG_APP` が注入され、既定でオフライン |

## 主な仕様・決定事項
- 検索：BM25（日本語は文字バイグラム、索引時はユニグラムも）＋文書名トークン（タイトル一致で1.5倍）。ハイブリッドは RRF（k=60）。
- 埋め込みモデル：**ruri-v3-30m**（名古屋大、日本語特化・軽量。`sirasagi62/ruri-v3-30m-ONNX`）と **bge-m3**（`Xenova/bge-m3`）。
  - 接頭辞は `Core.embedPrefixes(名前)`：ruri は「検索クエリ: / 検索文書: 」、e5 は query:/passage:、bge は無し。
  - プーリング：`1_Pooling/config.json` があれば従う。無ければ名前に bge を含むと cls、それ以外は mean。
  - 量子化形式：CPU/WASM は q8 優先、WebGPU は fp16 優先（無ければ順に代替）。
- プロンプト：基本プロンプト（`Core.DEFAULT_BASE`）＋追加プロンプト（`Core.DEFAULT_EXTRA`：漏れなく答える・日付/数値/区分を含める）。
  利用者が編集でき、localStorage `rag-prompt-rules` に保存（同じ origin の2画面で共有）。CLI は `--base-file/--extra-file/--no-extra`。
- 精度テストの自動判定：`must`（OR の候補を AND）を NFKC・桁区切り除去して照合。資料にない質問は「判断できません」等で正解。CSV は BOM 付き UTF-8、先頭行に条件とプロンプトを記録。
- 配布 zip は Python の zipfile で作る（日本語ファイル名に UTF-8 フラグが付く。Info-ZIP だと Windows で文字化けした実績あり）。

## 落とし穴（ここを壊すと動かなくなる）
1. **Transformers.js の読み込みはすべて `env.fetch` を差し替えて仲介**している（`https://local-model.invalid/` という架空ホストを横取り）。モデルは `local/m0` のような別名で渡す（フォルダ名に日本語が来ても安全にするため）。WASM 本体も `useWasmCache=true` で env.fetch 経由。
2. **Bun で Web 版 Transformers.js を読むとき**は、読み込みの間だけ `process.release` を隠す（Node 判定されるとネイティブ版を探して失敗する）。
3. **CLI のネイティブ版**は `globalThis[Symbol.for('onnxruntime')]` に onnxruntime-node を入れて渡す。この経路ではデバイス一覧が空になるため、`scripts/patch_tjs.py` が minify 済みコードの該当箇所を正規表現で書き換える（`globalThis.__ragDevices`）。**Transformers.js を更新するとパターンがずれる可能性がある**ので、更新時はビルドが「patch point not found」で止まらないか確認。
4. **Bun でコンパイルした exe はパッケージ名で require できない**。そのため onnxruntime-node と onnxruntime-common を `ort-bundle.cjs` に1ファイル化し、`binding.js` と同じ `dist/` に置いている（`../bin/napi-v6/<OS>/x64/onnxruntime_binding.node` の相対パスを保つため）。読み込みは `createRequire(engine/loader.js)` で絶対パス指定。
5. Tauri 側は rag.exe の標準出力の1行目（URL）を待つ。rag 側は `serve --print-url` のとき URL だけを stdout に、ログはすべて stderr に出すこと。

## 今の状態
- 動作確認済み（Linux・ヘッドレス Chrome + Playwright、ダミーモデル／同じ計算量の代用モデル）：
  ブラウザ版の全モード（オンライン取得とキャッシュ、?offline=1 で HF 通信 0 件、file://）、オフライン版、CLI 全コマンド（Linux バイナリ）、`serve`/`app` の画面、精度テスト画面。
- 利用者の実機（Windows、Chrome）で確認済み：オフライン版のブラウザ内ベクトル化（bge-m3・ruri とも WebGPU）と精度テスト。
  - gemma-4-e2b＋ハイブリッド：**ruri-v3-30m で 34/34 正解**、bge-m3 で 32 正解・1 部分正解（Q30）・1 不正解（Q28）。日本語資料では ruri を標準にする方針。
- 速度（2コア環境・51チャンク）：ネイティブ版は WASM 版より ruri 相当で約3〜6倍、bge-m3 相当で約7〜13倍速い（スレッド1〜2本）。
- **Windows 11 実機で確認済み（2026-11-16、Node 26 / Bun 1.4.4 / Rust 1.99）**：
  - `build.py site offline cli-windows desktop` と Tauri の `cargo build --release --locked` が通る。
  - rag.exe：ネイティブ版エンジンの読み込み、本物の ruri-v3-30m で index（51チャンク：CPU 0.9 秒／DirectML 2.2 秒）・search・prompt・eval（根拠が上位5件に 30/30）。
  - デスクトップ版：起動（rag.exe は 127.0.0.1 のみで待ち受け）、通常終了・強制終了のどちらでも rag.exe が残らない（ジョブオブジェクトで道連れにする。`tie_to_app_lifetime`）。
- **未確認**：本物のモデルでの CLI とブラウザ版のベクトル一致、bge-m3 での CLI。

## 次にやること
1. GitHub にリポジトリを作って push。Settings → Pages を「GitHub Actions」にする（pages.yml が公開）。
2. Actions の「Release」を手動実行し、GitHub の Windows 環境でも同じくビルドが通るか確認（ローカルの Windows では通っている）。
3. （済）Windows 実機で `rag.exe models / index / app` と、デスクトップ版の起動・終了を確認。
4. 本物のモデルで、CLI（ネイティブ版）とブラウザ版のベクトルがほぼ一致し、検索結果が同じになるか確認（ダミーでは差が最大 0.0003）。
5. 自動判定の改善：要点の語が含まれていても、答えが「判断できません」なら不正解にする（Q28 の誤判定。精度テスト画面と CLI の両方）。
6. 利用者の宿題：新しい版（追加プロンプトあり）で ruri と bge-m3 をもう一度評価し、CSV を比較。

## テストの仕方
- 作業環境から HuggingFace に届かなかったため、`tests/make_dummy_models.py`（形だけのモデル）と `tests/make_standin_models.py`（本物と同じ層数・幅、重みは乱数）で検証した。
- 画面のテストは Playwright でヘッドレス Chrome を起動し、`ctx.route` で外部通信を記録・遮断して「外部通信 0 件」を確かめる。HuggingFace は route でダミーモデルを返して代用。
- フォルダ選択（webkitdirectory）は `page.set_input_files('#webDir', フォルダのパス)` で再現できる。

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
src/testset-tech.json     評価用テストセット（架空のセンサ基板 SN-200 の技術文書 13件・48問）。src/sample-tech/ がその資料
src/offline/              オフライン配布版に同梱する説明書とモデル取得スクリプト（PowerShell）
cli/src/main.js           CLI（Bun）。index / search / prompt / ask / eval / models / rules / serve / app
cli/src/embed.js          CLI のベクトル化（ネイティブ版 onnxruntime-node。無ければ WASM 版に自動で切替）
desktop/src-tauri/        デスクトップ版（Tauri 2）。同じフォルダの rag.exe を「serve --port 0 --print-url」で起動してウィンドウで開くだけ
scripts/build.py          すべてのビルド（site / offline / cli-windows / cli-linux / desktop）
scripts/patch_tjs.py      CLI 用に Transformers.js の minify 済みコードへ手当て（下の「落とし穴」参照）
tests/                    ダミーモデル・速度比較用モデルの生成、技術文書の資料とテストセットの生成（make_tech_samples.py / make_tech_testset.py）、
                          埋め込みモデルの検索性能の比較（eval_retrieval.mjs）
docs/埋め込みモデルの比較.md   ruri / bge-m3 / EmbeddingGemma 2 の比較結果
.github/workflows/        pages.yml（Pages 公開）, release.yml（Windows 向け配布物をビルド）
```
生成物（.gitignore 済み）：`dist/`, `cli/runtime/`, `cli/site/`, `cli/src/core.cjs`, `cli/src/site_files.js`

## ビルド
```
npm install                                   # @huggingface/transformers 4.3.2（固定）、onnxruntime-node/web、pdfjs-dist 6.5.438（固定）
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
- 資料の読み込み（Core.extractText）：PDF は pdf.js（文字の位置から行を組み立て、離れた文字の間はタブ＝表の列。ヘッダー・フッターの除去、
  折り返しの連結、大きい文字の行を見出しに、ページ先頭に「直前の見出し（p.N）」）。Word の表もタブ区切りの行。
  Excel はセルの列位置（r="C5"）どおりに並べて空欄を保ち、表示形式（styles.xml の numFmt）で日付→2026-07-30・％・通貨・桁区切りにする（excelNumber）。
  縦に結合したセルは下の行にも同じ値を入れる。空の行をはさむと別の表。CSV/TSV も引用符を解釈してタブ区切りの行にする（csvText）。
- 分割（chunkText）：タブ区切りの行が2行以上ある段落を表とみなし、行の途中で切らず、2つ目以降のかたまりの先頭に列名の行（最初のタブ区切りの行）を付け直す。
  どう読み取られたかは `rag text <資料>` で確認できる。スキャン画像だけの PDF はエラー（OCR は非対応）。
- 検索：BM25（日本語は文字バイグラム、索引時はユニグラムも）＋文書名トークン（タイトル一致で1.5倍）。
  - 品番・コード（英字と数字が混ざる語、区切り記号を含む英数字）は重み3倍（SEARCH_OPT.idWeight）。H-21 と H21、FY2025 と 2025年度、異体字（﨑・髙など）を同じ語として扱う。
  - 質問の言い回し（ひらがなだけの2文字：「とは」「ですか」）は、漢字・カナ・英数字の語が3つ以上あれば検索語から外す（SEARCH_OPT.dropHira）。
  - ハイブリッドは RRF（k=60）の **max**（キーワードと意味の順位点の大きい方で並べる）。合計だと、キーワードが当たらない正解（英日をまたぐ質問など）が下に落ちる。
  - 数値はすべて tests/bench_retrieval.mjs と評価者20人のテストセット（552問）で比べて決めた。
- 分割したかたまりの見出しの頭に、文書の題名と「製品名：」の行、版・日付（本文の「Rev.」「第N版」「発行日」など。無ければファイルの更新日）を付ける。
  例：「KD-3410A / KD-3410B［版 D］／電気的特性」。基本プロンプトに「版や日付から新しいと分かる資料を優先する」を追加。
- PDF：表の空欄は、いちばんセルの多い行の列位置に x で割り当てて残す。先頭の空欄は上の行の値で埋める（縦に結合したセル）。2段組みは中央の縦の帯で左→右に読む。
  上付きは 10^-5、下付きは SiO2 の形。PowerPoint は表示順・表（タブ区切り）・自動番号・発表者ノートを読む。Word の自動番号（numbering.xml）も付ける。
- 文字コード：BOM 付き UTF-16、UTF-8、Shift_JIS と EUC-JP（化けの少ない方）を判定。Excel の千円表示（#,##0,）・指数（1.2E-05）も表示どおり。
- 埋め込みモデル：**ruri-v3-30m**（名古屋大、日本語特化・軽量。`sirasagi62/ruri-v3-30m-ONNX`）、**bge-m3**（`Xenova/bge-m3`）、
  **EmbeddingGemma 2**（`onnx-community/embeddinggemma-2-ONNX`。CLI・デスクトップ版のみ。`rag models download gemma`）。
  - 接頭辞は `Core.embedPrefixes(名前)`：ruri は「検索クエリ: / 検索文書: 」、EmbeddingGemma は「task: search result | query: 」/「title: none | text: 」、
    e5 は query:/passage:、bge は無し。
  - EmbeddingGemma 2 はパイプラインを使わず、文章用の部品だけを AutoModel で読み込み sentence_embedding を使う（loadExtractor。画像・音声の部品は読まない）。
  - プーリング：`1_Pooling/config.json` があれば従う。無ければ名前に bge を含むと cls、それ以外は mean。
  - 量子化形式：CPU/WASM は q8 優先、WebGPU は fp16 優先（無ければ順に代替）。
- プロンプト：基本プロンプト（`Core.DEFAULT_BASE`）＋追加プロンプト（`Core.DEFAULT_EXTRA`：漏れなく答える・日付/数値/区分を含める）。
  利用者が編集でき、localStorage `rag-prompt-rules` に保存（同じ origin の2画面で共有）。CLI は `--base-file/--extra-file/--no-extra`。
- 精度テストの自動判定（Core.autoJudge / retrievalScore。画面と CLI で共通）：`must`（OR の候補を AND）を NFKC・桁区切り除去して照合。
  数字だけの語は前後が数字でないときだけ一致。答えの最初の文が「判断できません」などなら不正解。資料にない質問は「判断できません」等で正解。
  検索の当たりは、根拠の資料（sources）のかたまりだけで must がそろったかで判定（別の資料の偶然の一致を数えない）。CSV は BOM 付き UTF-8、先頭行に条件とプロンプトを記録。
- 配布 zip は Python の zipfile で作る（日本語ファイル名に UTF-8 フラグが付く。Info-ZIP だと Windows で文字化けした実績あり）。

## 落とし穴（ここを壊すと動かなくなる）
1. **Transformers.js の読み込みはすべて `env.fetch` を差し替えて仲介**している（`https://local-model.invalid/` という架空ホストを横取り）。モデルは `local/m0` のような別名で渡す（フォルダ名に日本語が来ても安全にするため）。WASM 本体も `useWasmCache=true` で env.fetch 経由。
2. **Bun で Web 版 Transformers.js を読むとき**は、読み込みの間だけ `process.release` を隠す（Node 判定されるとネイティブ版を探して失敗する）。
3. **CLI のネイティブ版**は `globalThis[Symbol.for('onnxruntime')]` に onnxruntime-node を入れて渡す。この経路ではデバイス一覧が空になるため、`scripts/patch_tjs.py` が minify 済みコードの該当箇所を正規表現で書き換える（`globalThis.__ragDevices`）。**Transformers.js を更新するとパターンがずれる可能性がある**ので、更新時はビルドが「patch point not found」で止まらないか確認。
4. **Bun でコンパイルした exe はパッケージ名で require できない**。そのため onnxruntime-node と onnxruntime-common を `ort-bundle.cjs` に1ファイル化し、`binding.js` と同じ `dist/` に置いている（`../bin/napi-v6/<OS>/x64/onnxruntime_binding.node` の相対パスを保つため）。読み込みは `createRequire(engine/loader.js)` で絶対パス指定。
5. Tauri 側は rag.exe の標準出力の1行目（URL）を待つ。rag 側は `serve --print-url` のとき URL だけを stdout に、ログはすべて stderr に出すこと。
6. **pdf.js は worker を別スレッドにせず**、`globalThis.pdfjsWorker` に worker のモジュールを入れて同じスレッドで動かす（file:// と exe で動かすため）。
   CMap は `dist/_gen/cmaps.json`（build.py の make_cmaps）を同梱し、`BinaryDataFactory` で渡す（外部から取らない）。pdf.js 6 では文書オブジェクトに
   destroy が無いので `loadingTask.destroy()` を使う。並びは build.py の RT_FILES と browser_embed.js の RUNTIME を一致させる（HTML 内蔵の rt0〜rt5）。
7. **EmbeddingGemma 2 はブラウザでは動かない**：ONNX の全形式（q8・q4・q4f16・fp16）が GatherBlockQuantized を使い、onnxruntime-web 1.31（Transformers.js 4.3.2〜4.4.0-next）に
   実装がない。ブラウザ側は分かりやすいエラーにしている（`globalThis.RAG_TRY_EG2 = true` で試せる）。ネイティブ版（onnxruntime-node 1.30）では動く。
8. このリポジトリのファイルは **CRLF** で保存されている（core.autocrlf=true）。スクリプトで書き換えるときは改行を CRLF のまま保つ（README.md と新しいファイルは LF）。
   Edit ツールで直すとファイル全体が LF になることがあるので、コミット前に `git diff --stat` が実際の変更行数になっているか確かめる。
   Python の here-doc で `` `
` を書くと制御文字になりやすい（使い方.txt の「.ag.exe」が「.ag.exe」に化けた原因）。
9. `rag serve` は、この PC の中の画面（同じ origin・file:// の null・localhost）からの呼び出しだけを受け付ける。外部サイトの Origin には 403。

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
- **2026-11-16 追加**：PDF の読み込み（全形態）、Word の表をタブ区切りに、`rag text`、EmbeddingGemma 2（CLI・デスクトップ版）、技術文書のテストセット。
  - PDF：CLI（exe）、Pages 版、オフライン版（HTML 内蔵のエンジン）で同じ読み取り結果になることを確認。外部通信 0 件。
  - 埋め込みモデルの比較は `docs/埋め込みモデルの比較.md`。技術文書では EmbeddingGemma 2 が最良（41/48）、bge-m3 40、ruri 37。Wikipedia は 3 つとも 34/34。
  - ruri の CLI とブラウザ版のベクトルが一致することを確認（コサイン 0.999 以上）。EmbeddingGemma 2 はブラウザでは動かない（落とし穴 7）。
  - 以前の「29/34」は、`--llm-model` を付けないと LM Studio の一覧の最初のモデル（phi-4-mini-reasoning）が使われていたためと考えられる（コードと一覧の順から）。gemma-4-e2b を指定すると 34/34。
- **2026-11-17 追加**：Excel の読み取りを作り直し（空欄・表示形式・結合セル）、CSV を表として読む、表を分けたときに列名の行を付け直す。
  技術文書のテストセットに Excel の問題 9 問を追加（計 57 問、`C3-C4_コンデンサ受入評価.xlsx`）。直す前→後（gemma-4-e2b）：
  EmbeddingGemma 2 は 47→50/57、ruri は 44→48/57。Excel の 9 問はどちらも 6→9。元の 48 問は 41→41 と 38→39（下がっていない）。
  直す前は空欄で列がずれ、代替品の空欄に正規品の値（-0.128）を答えていた。Wikipedia の検索結果は変わらない（チャンク数も同じ 51）。
- **2026-11-19：20人の評価と改善**（評価者が職種ごとに作った資料とテストセットは C:/dev/eval/agents/ にある。リポジトリの外。まとめは同じ場所の まとめ.md）
  評価者20人のテストセット（552問）で、検索で答えが根拠の資料から上位5件に入った割合：ruri 80% → 88%、EmbeddingGemma 2 は 93%。
  主な修正：品番・コードの重み、表記ゆれ、ハイブリッドを max に、かたまりに題名・版・日付・列名を残す、PDF の空欄・2段組み・上付き、PowerPoint の表とノート、
  千円表示、文字コード判定、rag eval の判定、使い方.txt の化け、モデルが無いときはキーワード検索で続ける、serve の呼び出し元の制限、知らないオプションの警告。
- **未確認**：bge-m3 の CLI とブラウザ版のベクトル一致、実在のデータシート（フォントや表の形がさまざまな PDF）での読み取り品質。

## 次にやること
1. GitHub にリポジトリを作って push。Settings → Pages を「GitHub Actions」にする（pages.yml が公開）。
2. Actions の「Release」を手動実行し、GitHub の Windows 環境でも同じくビルドが通るか確認（ローカルの Windows では通っている）。
3. （済）Windows 実機で `rag.exe models / index / app` と、デスクトップ版の起動・終了を確認。
4. 本物のモデルで、CLI（ネイティブ版）とブラウザ版のベクトルがほぼ一致し、検索結果が同じになるか確認（ダミーでは差が最大 0.0003）。
5. （済）自動判定の改善（最初の文が「判断できません」なら不正解、数字は前後の数字を見て一致、検索の当たりは sources の資料だけで判定）。
6. 利用者の宿題：新しい版（追加プロンプトあり）で ruri と bge-m3 をもう一度評価し、CSV を比較。
7. （一部済）ハイブリッドを max にして、意味検索だけより悪くなる問題は解消（EmbeddingGemma 2 で 91% → 93%）。ruri は英日をまたぐ質問が弱いままなので、
   英語の資料が多いときは EmbeddingGemma 2 を勧める。質問を資料の言語にも直して検索する、は未着手。
9. 評価者20人の指摘で残っているもの：コマンドのたびにモデルを読み直して遅い（常駐して続けて検索できるモード）、問い合わせ履歴のような大きな CSV は
   1行＝1かたまりにしたい、同じ資料が上位を占めすぎる（資料ごとの上限）、Markdown の | 表、PDF の2段の列見出しの1段目、旧版の資料を検索から外す指定。
8. `rag eval` で `--llm-model` を省いたとき、埋め込み用でないモデルの最初のものが選ばれる。gemma など回答向けのモデルを優先するか、使ったモデル名を必ず表示する。

## テストの仕方
- 作業環境から HuggingFace に届かなかったため、`tests/make_dummy_models.py`（形だけのモデル）と `tests/make_standin_models.py`（本物と同じ層数・幅、重みは乱数）で検証した。
- 画面のテストは Playwright でヘッドレス Chrome を起動し、`ctx.route` で外部通信を記録・遮断して「外部通信 0 件」を確かめる。HuggingFace は route でダミーモデルを返して代用。
- フォルダ選択（webkitdirectory）は `page.set_input_files('#webDir', フォルダのパス)` で再現できる。

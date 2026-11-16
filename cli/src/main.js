// RAG プロンプトビルダー CLI
// 資料のインデックス化（キーワード＋ベクトル）→ 検索 → 社内ChatGPT等に貼るプロンプトの生成までをローカルで行う。
// ローカルLLM（LM Studio / Ollama など OpenAI 互換）を指定したときだけ、回答・評価も行う。
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { embed, findModel, listModels, modelDirs, exeDir, engine, setRunOptions } from './embed.js';
import { SITE } from './site_files.js';
import cmapsFile from '../runtime/cmaps.json' with { type: 'file' };
const Core = require('./core.cjs');

// PDF の読み込み（pdf.js）。Core.extractText が呼ぶ。処理役（worker）は別スレッドにせずこのプロセスの中で動かし、
// 日本語などの文字の対応表（CMap）は exe に同梱したものを使う（外部には読みに行かない）。初めて PDF を読むときだけ読み込む。
let pdfP = null;
globalThis.RAG_PDF = () => pdfP || (pdfP = (async () => {
  // pdf.js は読み込み時に「画面描画用の部品（canvas）がない」と警告を出すが、文字の取り出しには不要なので表示しない
  const log = console.log, warn = console.warn;
  const quiet = f => (...a) => { if (!/^Warning: Cannot (load "@napi-rs\/canvas"|polyfill)/.test(String(a[0]))) f(...a); };
  console.log = quiet(log); console.warn = quiet(warn);
  let pdfjs;
  try {
    globalThis.pdfjsWorker = await import('pdfjs-dist/legacy/build/pdf.worker.mjs');
    pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  } finally { console.log = log; console.warn = warn; }
  const map = JSON.parse(await Bun.file(cmapsFile).text());
  return { pdfjs, cmap: n => map[n] ? new Uint8Array(Buffer.from(map[n], 'base64')) : null };
})());

const VERSION = '1.0.0';
const DEFAULTS = { index: 'rag-index.json', chunk: 600, overlap: 100, k: 5, n: 10, format: 'qa', temp: 0.1, maxTokens: 2048 };

/* ---------- 引数 ---------- */
const ALIAS = { o: 'out', i: 'index', k: 'k', n: 'n', m: 'model', h: 'help', f: 'format', c: 'copy', q: 'quiet' };
const BOOL = new Set(['help', 'json', 'copy', 'quiet', 'no-embed', 'no-extra', 'version', 'keyword', 'gpu', 'no-open', 'print-url']);
function parseArgs(argv) {
  const pos = [], opt = {};
  for (let i = 0; i < argv.length; i++) {
    let a = argv[i];
    if (a === '--') { pos.push(...argv.slice(i + 1)); break; }
    if (/^--?[^\d]/.test(a)) {
      let key = a.replace(/^--?/, ''), val;
      if (key.includes('=')) [key, val] = [key.slice(0, key.indexOf('=')), key.slice(key.indexOf('=') + 1)];
      key = ALIAS[key] || key;
      if (val === undefined) val = BOOL.has(key) ? true : argv[++i];
      if (val === undefined) die(`--${key} の値がありません`);
      opt[key] = val;
    } else pos.push(a);
  }
  return { pos, opt };
}
const log = (...a) => { if (!G.quiet) console.error(...a); };
function die(msg) { console.error('エラー: ' + msg); process.exit(1); }
const G = {};

/* ---------- 設定ファイル（任意） ---------- */
function loadConfig(opt) {
  const cands = [opt.config, path.join(process.cwd(), 'rag.config.json'), path.join(exeDir(), 'rag.config.json')].filter(Boolean);
  for (const p of cands) {
    if (fs.existsSync(p)) {
      try { return { ...JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, '')), _path: p }; }
      catch (e) { die(`設定ファイル ${p} を読めません: ${e.message}`); }
    }
    else if (p === opt.config) die(`設定ファイルが見つかりません: ${p}`);
  }
  return {};
}
// 優先順位：コマンドの引数 > 設定ファイル > 既定値
const get = (opt, cfg, key, def) => opt[key] ?? cfg[key] ?? def;
const num = (v, name) => { const n = Number(v); if (!Number.isFinite(n)) die(`${name} は数値で指定してください: ${v}`); return n; };

function promptRules(opt, cfg) {
  const read = p => fs.readFileSync(p, 'utf8').replace(/^﻿/, '');
  let base = Core.DEFAULT_BASE, extra = Core.DEFAULT_EXTRA;
  if (typeof cfg.base === 'string') base = cfg.base;
  if (typeof cfg.extra === 'string') extra = cfg.extra;
  if (cfg.baseFile) base = read(path.resolve(path.dirname(cfg._path || '.'), cfg.baseFile));
  if (cfg.extraFile) extra = read(path.resolve(path.dirname(cfg._path || '.'), cfg.extraFile));
  if (opt['base-file']) base = read(opt['base-file']);
  if (opt['extra-file']) extra = read(opt['extra-file']);
  if (opt['no-extra']) extra = '';
  return { base, extra };
}

/* ---------- 資料の読み込み ---------- */
const SKIP_DIR = new Set(['node_modules', '.git', 'models', '埋め込みモデル']);
function walk(p, out = []) {
  const st = fs.statSync(p);
  if (st.isFile()) { out.push(p); return out; }
  for (const e of fs.readdirSync(p, { withFileTypes: true })) {
    if (e.name.startsWith('.') || e.name.startsWith('~$')) continue;
    const q = path.join(p, e.name);
    if (e.isDirectory()) { if (!SKIP_DIR.has(e.name)) walk(q, out); } else out.push(q);
  }
  return out;
}
async function readDocs(inputs) {
  const docs = [], skipped = [];
  for (const inp of inputs) {
    if (!fs.existsSync(inp)) die(`見つかりません: ${inp}`);
    const root = fs.statSync(inp).isDirectory() ? inp : path.dirname(inp);
    for (const f of walk(inp)) {
      const rel = path.relative(root, f).split(path.sep).join('/');
      try {
        const b = fs.readFileSync(f);
        const text = await Core.extractText(path.basename(f), b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
        if (text && text.trim()) docs.push({ name: rel, text }); else skipped.push(`${rel}（本文なし）`);
      } catch (e) { skipped.push(`${rel}（${e.message}）`); }
    }
  }
  return { docs, skipped };
}

/* ---------- インデックス ---------- */
function toB64(vecs) {
  const dim = vecs[0].length, all = new Float32Array(vecs.length * dim);
  vecs.forEach((v, i) => all.set(v, i * dim));
  return { dim, data: Buffer.from(all.buffer).toString('base64') };
}
function fromB64(dim, b64) {
  const buf = Buffer.from(b64, 'base64'); const all = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
  const out = []; for (let i = 0; i < all.length; i += dim) out.push(all.slice(i, i + dim));
  return out;
}
function loadIndex(p) {
  if (!fs.existsSync(p)) die(`インデックスが見つかりません: ${p}\n  先に「rag index <資料フォルダ>」で作ってください。`);
  const j = JSON.parse(fs.readFileSync(p, 'utf8'));
  const idx = { ...j, kw: Core.buildIndex(j.chunks), vecs: j.vectors ? fromB64(j.vectors.dim, j.vectors.data) : null };
  return idx;
}
async function embedChunks(chunks, model, label = 'ベクトル化') {
  const pre = Core.embedPrefixes(model.name).d;
  const t0 = Date.now();
  const r = await embed(model, chunks.map(c => pre + Core.chunkEmbedText(c)), { onProgress: (d, t) => progress(`${label}中… ${d} / ${t}`) });
  progress(''); log(`${label}：${chunks.length} 件（${model.name}・${engineLabel(r.device)}・${r.dtype}、${((Date.now() - t0) / 1000).toFixed(1)} 秒）`);
  return r.vectors;
}
const engineLabel = d => d === 'wasm' ? 'WASM（予備・1コア）' : d === 'dml' ? 'ネイティブ・GPU（DirectML）' : 'ネイティブ・CPU';
function progress(s) { if (!G.quiet && process.stderr.isTTY) process.stderr.write('\r' + s.padEnd(40)); if (!s && process.stderr.isTTY) process.stderr.write('\r'); }

async function retrieve(idx, question, extra, topN, opt) {
  if (!idx.vecs || opt.keyword) return { hits: Core.search(idx.kw, question, extra, topN), mode: 'キーワード' };
  const model = findModel(idx.model, opt['models-dir']);
  const q = Core.embedPrefixes(model.name).q + question + (extra ? ' ' + extra : '');
  const { vectors } = await embed(model, [q]);
  return { hits: Core.hybridSearch(idx.kw, question, extra, topN, vectors[0], idx.vecs), mode: `ハイブリッド（${model.name}）` };
}

/* ---------- 出力 ---------- */
function writeOut(text, opt) {
  if (opt.out) { fs.writeFileSync(opt.out, text, 'utf8'); log(`保存しました: ${opt.out}`); }
  if (opt.copy) copyToClipboard(text);
  if (!opt.out && !opt.copy) process.stdout.write(text.endsWith('\n') ? text : text + '\n');
}
function copyToClipboard(text) {
  let r;
  if (process.platform === 'win32') {
    // clip.exe は BOM 付き UTF-16LE を渡すと日本語が化けない
    r = spawnSync('clip', [], { input: Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(text, 'utf16le')]) });
  } else if (process.platform === 'darwin') r = spawnSync('pbcopy', [], { input: text });
  else { r = spawnSync('wl-copy', [], { input: text }); if (r.error) r = spawnSync('xclip', ['-selection', 'clipboard'], { input: text }); }
  if (r.error || r.status) die('クリップボードにコピーできませんでした');
  log('クリップボードにコピーしました（社内ChatGPTに貼り付けてください）');
}

/* ---------- ローカルLLM（OpenAI互換） ---------- */
const stripThink = s => String(s || '').replace(/<think>[\s\S]*?<\/think>/g, '').replace(/^[\s\S]*?<\/think>/, '').trim();
async function llmModelOf(url, name) {
  if (name) return name;
  const r = await fetch(url.replace(/\/+$/, '') + '/models').catch(e => die(`ローカルLLMに接続できません（${url}）: ${e.message}`));
  if (!r.ok) die(`ローカルLLMの一覧を取得できません（HTTP ${r.status}）`);
  const ids = ((await r.json()).data || []).map(m => m.id).filter(id => !Core.isEmbedModel(id));
  if (!ids.length) die('回答用のモデルが読み込まれていません（--llm-model で指定してください）');
  return ids[0];
}
async function chat(url, model, p, { temp, maxTokens }) {
  const t0 = Date.now();
  const r = await fetch(url.replace(/\/+$/, '') + '/chat/completions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, temperature: temp, max_tokens: maxTokens, stream: false,
      messages: [{ role: 'system', content: p.system }, { role: 'user', content: p.user }] })
  });
  if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + (await r.text()).slice(0, 160));
  const j = await r.json();
  return { answer: stripThink(j.choices?.[0]?.message?.content || ''), sec: (Date.now() - t0) / 1000 };
}

/* ---------- 採点（評価ツールと同じ規則） ---------- */
const normA = s => String(s || '').normalize('NFKC').toLowerCase().replace(/(\d),(?=\d)/g, '$1').replace(/\s+/g, '');
const REFUSE = ['判断できません', '判断できない', '記載がありません', '記載されていません', '記載はありません', '記述がありません', '記述はありません',
  '見当たりません', '含まれていません', '書かれていません', 'わかりません', '分かりません', '情報がありません', '情報はありません'];
const isRefusal = a => REFUSE.some(r => normA(a).includes(normA(r)));
const coverage = (text, must) => { const t = normA(text); return must.filter(g => g.some(x => t.includes(normA(x)))).length; };
const autoJudge = (q, a) => !a.trim() ? null : !q.must.length ? isRefusal(a) : coverage(a, q.must) === q.must.length;
const ctxText = cs => cs.map(c => c.source.replace(/\.[^.]+$/, '') + ' ' + (c.heading || '') + '\n' + c.text).join('\n');
const retOf = (q, cs) => q.must.length ? coverage(ctxText(cs), q.must) / q.must.length : null;
const retLabel = r => r === null ? '' : r === 1 ? 'OK' : r > 0 ? 'PARTIAL' : 'NG';

/* =================== コマンド =================== */
const HELP = `RAG プロンプトビルダー CLI ${VERSION}
資料を検索して、社内ChatGPTなどに貼り付けるプロンプトを作ります。処理はすべてこのPCの中で行います。

使い方:
  rag index <資料フォルダ|ファイル...> [-o rag-index.json] [-m ruri-v3-30m] [--no-embed]
      資料を読み込み、検索用のインデックスを作ります（md, txt, csv, json, html, pdf, docx, xlsx, pptx）。
      -m で埋め込みモデルを指定するとハイブリッド検索（キーワード＋意味）になります。
      -m を省略すると、使えるモデルがあれば ruri → bge-m3 の順で自動で使います。
  rag search "<質問>" [-i rag-index.json] [-n 10] [--extra "追加キーワード"]
      検索結果（候補）を一覧表示します。
  rag prompt "<質問>" [-i rag-index.json] [-k 5] [-f qa|summary|extract|compare] [--instr "300字以内で"]
                      [--json] [-o prompt.txt] [-c]
      上位 k 件の資料を入れたプロンプトを出力します。-c でクリップボードにコピー、--json で API 用の形式。
  rag ask "<質問>" --llm http://localhost:1234/v1 [--llm-model 名前]   （プロンプトの指定は prompt と同じ）
      ローカルLLM（LM Studio / Ollama など）に質問して回答を表示します。
  rag eval <testset.json> [--llm URL] [--llm-model 名前] [-m モデル|--keyword] [-k 5] [--csv 結果.csv]
      テストセットで検索の当たり率を測ります。--llm を付けると回答も採点します（評価ツールと同じCSV形式）。
  rag models                      使える埋め込みモデルの一覧
  rag models download ruri|bge|gemma   埋め込みモデルを HuggingFace からダウンロード（ネット接続が必要。ここだけ通信します）
  rag text <資料フォルダ|ファイル...> [--json] [-o 出力]   資料から読み取った文章を表示（PDF などの読み取り結果の確認用）
  rag rules [--base-file F] [--extra-file F]   使われるプロンプトのルール（基本＋追加）を表示
  rag app   [--port 39871]                    画面版（プロンプトビルダー／精度テスト）をアプリとして開く
  rag serve [--port 39871]                    画面とベクトル化API（OpenAI互換 /v1/embeddings）をこのPC内だけで提供

共通のオプション:
  --models-dir DIR      埋め込みモデルの置き場所（既定: exe と同じ場所の models / 埋め込みモデル）
  --base-file F         基本プロンプトをファイルから読む       --extra-file F   追加プロンプトをファイルから読む
  --no-extra            追加プロンプトを使わない                --config F       設定ファイル（既定: rag.config.json）
  --device cpu|dml      ベクトル化に使う装置（dml は Windows の GPU。既定は cpu）  --threads N  CPUのスレッド数
  -q, --quiet           進み具合を表示しない

設定ファイル rag.config.json（任意。カレントフォルダか exe と同じ場所）の例:
  { "index": "rag-index.json", "k": 5, "model": "ruri-v3-30m", "llm": "http://localhost:1234/v1",
    "base": "あなたは…", "extraFile": "追加ルール.txt" }
`;

async function cmdIndex(pos, opt, cfg) {
  if (!pos.length) die('資料のフォルダかファイルを指定してください（例: rag index ./社内資料）');
  const chunk = num(get(opt, cfg, 'chunk', DEFAULTS.chunk), '--chunk'), overlap = num(get(opt, cfg, 'overlap', DEFAULTS.overlap), '--overlap');
  const out = opt.out || cfg.index || DEFAULTS.index;
  const { docs, skipped } = await readDocs(pos);
  if (!docs.length) die('読み込める資料がありませんでした');
  const chunks = [];
  for (const d of docs) for (const c of Core.chunkText(d.text, chunk, overlap)) chunks.push({ source: d.name, heading: c.heading, text: c.text });
  log(`資料 ${docs.length} 件 → チャンク ${chunks.length} 個`);
  if (skipped.length) log(`読み込まなかったファイル ${skipped.length} 件:\n  ` + skipped.slice(0, 20).join('\n  ') + (skipped.length > 20 ? '\n  …' : ''));
  let model = null, vectors = null;
  if (!opt['no-embed']) {
    const want = opt.model || cfg.model;
    if (want) model = findModel(want, opt['models-dir']);
    else {
      const all = listModels(opt['models-dir']);
      model = all.find(m => /ruri/i.test(m.name)) || all.find(m => /bge-m3/i.test(m.name)) || all[0] || null;
      if (!model) log('埋め込みモデルが見つからないため、キーワード検索だけのインデックスを作ります（rag models を参照）');
    }
    if (model) vectors = toB64(await embedChunks(chunks, model));
  }
  const data = { tool: 'rag-cli', version: 1, created: new Date().toISOString(), chunk, overlap, model: model ? model.name : null,
    docs: docs.map(d => d.name), chunks, vectors };
  fs.writeFileSync(out, JSON.stringify(data));
  log(`インデックスを保存しました: ${out}（${model ? 'ハイブリッド検索' : 'キーワード検索'}）`);
}

async function cmdSearch(pos, opt, cfg) {
  const question = pos.join(' ').trim(); if (!question) die('質問を指定してください');
  const idx = loadIndex(opt.index || cfg.index || DEFAULTS.index);
  const n = num(get(opt, cfg, 'n', DEFAULTS.n), '-n');
  const { hits, mode } = await retrieve(idx, question, opt.extra || '', n, opt);
  if (opt.json) return writeOut(JSON.stringify(hits.map(h => ({ ...idx.chunks[h.i], score: h.score, kwRank: h.kwRank, vecRank: h.vecRank })), null, 2), opt);
  const lines = [`検索方式: ${mode}　候補 ${hits.length} 件`, ''];
  hits.forEach((h, r) => {
    const c = idx.chunks[h.i];
    const how = h.kwRank !== undefined || h.vecRank !== undefined
      ? `キーワード ${h.kwRank ? h.kwRank + '位' : '—'}・意味 ${h.vecRank ? h.vecRank + '位' : '—'}${h.vecScore !== undefined ? `（類似度 ${h.vecScore.toFixed(3)}）` : ''}`
      : `スコア ${h.score.toFixed(2)}`;
    lines.push(`[${r + 1}] ${c.source}${c.heading ? '（' + c.heading + '）' : ''}  ${how}`);
    lines.push('    ' + c.text.replace(/\s+/g, ' ').slice(0, 120) + (c.text.length > 120 ? '…' : ''));
  });
  writeOut(lines.join('\n'), opt);
}

async function buildPromptFor(question, opt, cfg) {
  const idx = loadIndex(opt.index || cfg.index || DEFAULTS.index);
  const k = num(get(opt, cfg, 'k', DEFAULTS.k), '-k');
  const { hits, mode } = await retrieve(idx, question, opt.extra || '', k, opt);
  const rules = promptRules(opt, cfg);
  const p = Core.buildPrompt({ question, chunks: hits.map(h => idx.chunks[h.i]), format: opt.format || cfg.format || DEFAULTS.format,
    customFormat: opt.instr || cfg.instr || '', budget: num(get(opt, cfg, 'budget', 0), '--budget'), base: rules.base, extra: rules.extra });
  log(`検索方式: ${mode}　参考資料 ${p.used} 件${p.dropped ? `（上限文字数のため ${p.dropped} 件省略）` : ''}・${p.full.length.toLocaleString()} 文字`);
  return p;
}
async function cmdPrompt(pos, opt, cfg) {
  const question = pos.join(' ').trim(); if (!question) die('質問を指定してください');
  const p = await buildPromptFor(question, opt, cfg);
  writeOut(opt.json ? JSON.stringify({ model: opt['api-model'] || cfg.apiModel || 'gpt-4o', temperature: 0.2,
    messages: [{ role: 'system', content: p.system }, { role: 'user', content: p.user }] }, null, 2) : p.full, opt);
}
async function cmdAsk(pos, opt, cfg) {
  const question = pos.join(' ').trim(); if (!question) die('質問を指定してください');
  const url = opt.llm || cfg.llm; if (!url) die('--llm でローカルLLMのURLを指定してください（例: http://localhost:1234/v1）');
  const p = await buildPromptFor(question, opt, cfg);
  const model = await llmModelOf(url, opt['llm-model'] || cfg.llmModel);
  log(`回答中…（${model}）`);
  const r = await chat(url, model, p, { temp: num(get(opt, cfg, 'temp', DEFAULTS.temp), '--temp'), maxTokens: num(get(opt, cfg, 'max-tokens', DEFAULTS.maxTokens), '--max-tokens') });
  log(`（${r.sec.toFixed(1)} 秒）`);
  writeOut(r.answer, opt);
}

async function cmdEval(pos, opt, cfg) {
  const file = pos[0]; if (!file) die('テストセット（testset.json）を指定してください');
  const set = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
  if (!Array.isArray(set.docs) || !Array.isArray(set.questions)) die('テストセットの形式が正しくありません（docs と questions が必要です）');
  set.questions.forEach((q, i) => { q.id ??= i + 1; q.type ??= '未分類'; q.must ??= []; q.expected ??= ''; });
  const chunkSize = num(get(opt, cfg, 'chunk', DEFAULTS.chunk), '--chunk'), overlap = num(get(opt, cfg, 'overlap', DEFAULTS.overlap), '--overlap');
  const k = num(get(opt, cfg, 'k', DEFAULTS.k), '-k');
  const flat = [];
  for (const d of set.docs) for (const c of Core.chunkText(d.text, chunkSize, overlap)) flat.push({ source: d.name, heading: c.heading, text: c.text });
  const kw = Core.buildIndex(flat);
  log(`${set.title || 'テストセット'}：資料 ${set.docs.length} 件（チャンク ${flat.length} 個）・質問 ${set.questions.length} 問`);
  // 検索（キーワードと、モデルがあればハイブリッド）
  let model = null;
  if (!opt.keyword) {
    const want = opt.model || cfg.model;
    model = want ? findModel(want, opt['models-dir']) : (listModels(opt['models-dir']).find(m => /ruri/i.test(m.name)) || listModels(opt['models-dir'])[0] || null);
    if (!model) log('埋め込みモデルが見つからないため、キーワード検索だけで評価します');
  }
  const state = set.questions.map(q => {
    const kwChunks = Core.search(kw, q.question, '', k).map(h => flat[h.i]);
    return { q, chunks: kwChunks, kwRet: retOf(q, kwChunks), ret: retOf(q, kwChunks), answer: '', sec: null, err: '' };
  });
  let dtype = '', evalDevice = '';
  if (model) {
    const pre = Core.embedPrefixes(model.name);
    const vecs = await embedChunks(flat, model, '資料のベクトル化');
    const r = await embed(model, state.map(s => pre.q + s.q.question), { onProgress: (d, t) => progress(`質問のベクトル化中… ${d} / ${t}`) });
    progress(''); dtype = r.dtype; evalDevice = r.device;
    state.forEach((s, i) => { s.chunks = Core.hybridSearch(kw, s.q.question, '', k, r.vectors[i], vecs).map(h => flat[h.i]); s.ret = retOf(s.q, s.chunks); });
  }
  const answerable = state.filter(s => s.q.must.length);
  const hit = ss => ss.filter(s => s.ret === 1).length, hitKw = ss => ss.filter(s => s.kwRet === 1).length;
  console.error(`\n検索で根拠が上位${k}件に入った割合: ${hit(answerable)} / ${answerable.length}` + (model ? `（キーワードのみ: ${hitKw(answerable)} / ${answerable.length}）` : ''));
  // 回答（--llm があるときだけ）
  const url = opt.llm || cfg.llm;
  const rules = promptRules(opt, cfg);
  let llmModel = '';
  if (url) {
    llmModel = await llmModelOf(url, opt['llm-model'] || cfg.llmModel);
    const temp = num(get(opt, cfg, 'temp', DEFAULTS.temp), '--temp'), maxTokens = num(get(opt, cfg, 'max-tokens', DEFAULTS.maxTokens), '--max-tokens');
    for (let i = 0; i < state.length; i++) {
      const s = state[i];
      progress(`回答中 ${i + 1} / ${state.length}（${llmModel}）`);
      const p = Core.buildPrompt({ question: s.q.question, chunks: s.chunks, format: 'qa', base: rules.base, extra: rules.extra });
      try { const r = await chat(url, llmModel, p, { temp, maxTokens }); s.answer = r.answer; s.sec = r.sec; }
      catch (e) { s.err = e.message; }
    }
    progress('');
    const judged = state.map(s => autoJudge(s.q, s.answer));
    const ok = judged.filter(Boolean).length;
    const unans = state.filter(s => !s.q.must.length);
    console.error(`回答の正解（自動判定）: ${ok} / ${state.length}`);
    if (unans.length) console.error(`資料にない質問で「判断できません」と答えた割合: ${unans.filter(s => isRefusal(s.answer)).length} / ${unans.length}`);
    console.error(`根拠番号 [n] を付けた割合: ${answerable.filter(s => /\[\d+\]/.test(s.answer)).length} / ${answerable.length}`);
    const errs = state.filter(s => s.err); if (errs.length) console.error(`エラー ${errs.length} 件（例: ${errs[0].err}）`);
    const secs = state.filter(s => s.sec).map(s => s.sec); if (secs.length) console.error(`平均 ${(secs.reduce((a, b) => a + b, 0) / secs.length).toFixed(2)} 秒/問`);
  }
  // 種類別
  const types = [...new Set(state.map(s => s.q.type))];
  console.error('\n種類別（検索で根拠あり' + (url ? '／回答の正解' : '') + '）:');
  for (const t of types) {
    const ss = state.filter(s => s.q.type === t), a = ss.filter(s => s.q.must.length);
    console.error(`  ${t}: ${a.length ? hit(a) + '/' + a.length : '—'}` + (url ? `／${ss.filter(s => autoJudge(s.q, s.answer)).length}/${ss.length}` : ''));
  }
  // CSV（評価ツールと同じ列）
  const csvPath = opt.csv || (opt.out && opt.out.endsWith('.csv') ? opt.out : null);
  if (csvPath) {
    const rows = state.map(s => {
      const j = autoJudge(s.q, s.answer);
      return { id: s.q.id, type: s.q.type, question: s.q.question, expected: s.q.expected, retrieval: retLabel(s.ret), retrieval_kw: retLabel(s.kwRet),
        sources: s.chunks.map(c => c.source).join(' / '), answer: s.answer || s.err, judge: j === null ? '' : j ? '正解' : '不正解', manual: '', seconds: s.sec ? s.sec.toFixed(2) : '' };
    });
    const head = Object.keys(rows[0]), q = v => '"' + String(v).replace(/"/g, '""') + '"';
    const st = { base: rules.base.trim() === Core.DEFAULT_BASE.trim() ? '既定' : '変更あり', extra: !rules.extra.trim() ? 'なし' : rules.extra.trim() === Core.DEFAULT_EXTRA.trim() ? '既定' : '変更あり' };
    const csv = '﻿' + [
      `# tool=rag-cli ${VERSION} model=${llmModel || '(回答なし)'} mode=rag search=${model ? 'hybrid' : 'kw'}${model ? ` emb=${model.name} (${engineLabel(evalDevice)}・${dtype})` : ''} topk=${k} chunk=${chunkSize} overlap=${overlap} prompt_base=${st.base} prompt_extra=${st.extra}`,
      `# 基本プロンプト: ${rules.base.trim().replace(/\r?\n/g, ' / ')}`, `# 追加プロンプト: ${rules.extra.trim().replace(/\r?\n/g, ' / ') || '（なし）'}`,
      head.join(','), ...rows.map(r => head.map(h => q(r[h])).join(','))].join('\r\n');
    fs.writeFileSync(csvPath, csv, 'utf8');
    console.error(`\nCSVを保存しました: ${csvPath}`);
  }
}

async function cmdModels(pos, opt) {
  if (pos[0] === 'download') return downloadModel(pos[1], opt);
  const ms = listModels(opt['models-dir']);
  const roots = modelDirs(opt['models-dir']);
  const E = engine();
  console.log(`計算エンジン: ${E.kind === 'native' ? 'ネイティブ版（' + E.note + '）' : 'WASM版（予備） … ' + E.note}`);
  console.log(`モデルを探した場所: ${roots.length ? roots.join(' , ') : '（なし）'}`);
  if (!ms.length) { console.log('埋め込みモデルが見つかりません。「rag models download ruri」でダウンロードするか、models フォルダにモデルのフォルダを置いてください。'); return; }
  for (const m of ms) {
    const onnx = fs.readdirSync(path.join(m.dir, 'onnx')).filter(f => f.endsWith('.onnx'));
    const size = onnx.reduce((s, f) => s + fs.statSync(path.join(m.dir, 'onnx', f)).size, 0);
    console.log(`  ${m.name.padEnd(20)} ${(size / 1048576).toFixed(0).padStart(5)} MB  ${onnx.join(', ')}  (${m.dir})`);
  }
}
const CATALOG = { ruri: { repo: 'sirasagi62/ruri-v3-30m-ONNX', dir: 'ruri-v3-30m' }, bge: { repo: 'Xenova/bge-m3', dir: 'bge-m3' },
  gemma: { repo: 'onnx-community/embeddinggemma-2-ONNX', dir: 'embeddinggemma-2' } };   // gemma は文章用の部品（model_*.onnx）だけを取る
async function downloadModel(which, opt) {
  const keys = which === 'all' ? Object.keys(CATALOG) : [which];
  if (!which || keys.some(k => !CATALOG[k])) die('ダウンロードするモデルを指定してください: ruri / bge / gemma / all');
  const root = path.resolve(opt['models-dir'] || path.join(exeDir(), 'models'));
  const base = ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', '1_Pooling/config.json'];
  const pref = ['onnx/model_quantized.onnx', 'onnx/model_int8.onnx', 'onnx/model_uint8.onnx', 'onnx/model.onnx'];
  for (const k of keys) {
    const { repo, dir } = CATALOG[k];
    console.error(`== ${dir}（${repo}）→ ${path.join(root, dir)}`);
    const r = await fetch(`https://huggingface.co/api/models/${repo}`).catch(e => die(`HuggingFace に接続できません: ${e.message}`));
    if (!r.ok) die(`モデル情報を取得できません（HTTP ${r.status}）`);
    const names = ((await r.json()).siblings || []).map(s => s.rfilename);
    const files = base.filter(f => names.includes(f));
    const onnx = pref.find(f => names.includes(f)); if (!onnx) die('ONNXファイルが見つかりません');
    files.push(onnx, ...names.filter(n => n.startsWith(onnx + '_data')));
    for (const f of files) {
      const dest = path.join(root, dir, ...f.split('/'));
      if (fs.existsSync(dest)) { console.error(`  （取得済み）${f}`); continue; }
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      const res = await fetch(`https://huggingface.co/${repo}/resolve/main/${f}`);
      if (!res.ok) die(`ダウンロードに失敗しました: ${f}（HTTP ${res.status}）`);
      const total = +res.headers.get('content-length') || 0; let got = 0;
      const tmp = dest + '.part', w = fs.createWriteStream(tmp);
      for await (const chunk of res.body) { w.write(chunk); got += chunk.length; if (total > 2e6) progress(`  ${f} ${(got / 1048576).toFixed(0)} / ${(total / 1048576).toFixed(0)} MB`); }
      await new Promise(ok => w.end(ok)); fs.renameSync(tmp, dest); progress('');
      console.error(`  取得しました: ${f}`);
    }
  }
  console.error('完了しました。社内PCで使うときは、models フォルダを rag.exe と同じ場所にコピーしてください。');
}

// 資料から取り出した文章を表示する（PDF や Excel がどう読み取られるかの確認用）
async function cmdText(pos, opt) {
  if (!pos.length) die('資料のファイルかフォルダを指定してください');
  const { docs, skipped } = await readDocs(pos);
  for (const s of skipped) console.error(`読み込めませんでした: ${s}`);
  writeOut(opt.json ? JSON.stringify(docs, null, 1) + '\n' : docs.map(d => `===== ${d.name} =====\n${d.text.trim()}\n`).join('\n'), opt);
}

function cmdRules(pos, opt, cfg) {
  const r = promptRules(opt, cfg);
  writeOut(`# 基本プロンプト\n${r.base.trim()}\n\n# 追加プロンプト\n${r.extra.trim() || '（なし）'}\n`, opt);
}

/* ---------- 画面版とAPI（このPC内だけ） ---------- */
const MIME = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', mjs: 'text/javascript; charset=utf-8', wasm: 'application/wasm',
  json: 'application/json; charset=utf-8', md: 'text/markdown; charset=utf-8', txt: 'text/plain; charset=utf-8' };
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Private-Network': 'true' };
function startServer(opt) {
  const port = num(opt.port ?? 39871, '--port'), host = opt.host || '127.0.0.1';
  const appTag = `<script>window.RAG_APP = { embedUrl: location.origin + '/v1', offline: true, engine: ${JSON.stringify(engine().kind)} };</script>\n`;
  const server = Bun.serve({ port, hostname: host, async fetch(req) {
    const u = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    try {
      if (u.pathname === '/v1/models') return Response.json({ object: 'list', data: listModels(opt['models-dir']).map(m => ({ id: m.name, object: 'model', owned_by: 'local' })) }, { headers: CORS });
      if (u.pathname === '/v1/embeddings' && req.method === 'POST') {
        const j = await req.json();
        const input = Array.isArray(j.input) ? j.input : [j.input];
        const m = findModel(String(j.model || '').replace(/^(app|web):/, ''), opt['models-dir']);
        const r = await embed(m, input.map(String));
        return Response.json({ object: 'list', model: m.name, data: r.vectors.map((v, i) => ({ object: 'embedding', index: i, embedding: Array.from(v) })),
          usage: { prompt_tokens: 0, total_tokens: 0 } }, { headers: { ...CORS, 'X-Rag-Engine': `${r.device}/${r.dtype}` } });
      }
      let p = decodeURIComponent(u.pathname.replace(/\/$/, '/index.html')).replace(/^\//, '');
      if (p === 'sample' || p === 'sample/') p = 'sample/index.html';
      const f = SITE[p];
      if (!f) return new Response('Not Found', { status: 404 });
      const ext = p.split('.').pop();
      if (ext === 'html') {
        const html = (await Bun.file(f).text()).replace('<script id="bembed">', appTag + '<script id="bembed">');
        return new Response(html, { headers: { 'Content-Type': MIME.html, 'Cache-Control': 'no-store' } });
      }
      return new Response(Bun.file(f), { headers: { 'Content-Type': MIME[ext] || 'application/octet-stream' } });
    } catch (e) { return Response.json({ error: { message: e.message } }, { status: 500, headers: CORS }); }
  } });
  const url = `http://${host === '0.0.0.0' ? '127.0.0.1' : host}:${server.port}/`;
  const E = engine();
  console.error(`RAG プロンプトビルダーを起動しました: ${url}`);
  console.error(`  計算エンジン: ${E.kind === 'native' ? 'ネイティブ版' : 'WASM版（予備）… ' + E.note}`);
  console.error(`  埋め込みモデル: ${listModels(opt['models-dir']).map(m => m.name).join(', ') || '（なし）'}`);
  console.error('  このウィンドウを閉じると終了します。');
  if (opt['print-url']) console.log(url);
  return url;
}
function openWindow(url) {
  if (process.platform === 'win32') {
    // Edge のアプリモード（アドレスバーなしのウィンドウ）で開く。無ければ既定のブラウザ
    const r = spawnSync('cmd', ['/c', 'start', '""', 'msedge', `--app=${url}`], { windowsHide: true });
    if (r.status) spawnSync('cmd', ['/c', 'start', '""', url], { windowsHide: true });
  } else if (process.platform === 'darwin') spawnSync('open', [url]);
  else spawnSync('xdg-open', [url]);
}
async function cmdServe(pos, opt) { startServer(opt); await new Promise(() => {}); }
async function cmdApp(pos, opt) { const url = startServer(opt); if (!opt['no-open']) openWindow(url); await new Promise(() => {}); }

/* ---------- 入口 ---------- */
async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const { pos, opt } = parseArgs(rest);
  G.quiet = !!opt.quiet;
  if (!cmd || cmd === 'help' || cmd === '--help' || cmd === '-h' || opt.help) { process.stdout.write(HELP); return; }
  if (cmd === '--version' || cmd === 'version') { console.log(VERSION); return; }
  const cfg = loadConfig(opt);
  setRunOptions({ device: opt.device || cfg.device || 'cpu', threads: num(opt.threads ?? cfg.threads ?? 0, '--threads') });
  const table = { index: cmdIndex, search: cmdSearch, prompt: cmdPrompt, ask: cmdAsk, eval: cmdEval, models: cmdModels, rules: cmdRules, text: cmdText, serve: cmdServe, app: cmdApp };
  if (!table[cmd]) die(`不明なコマンドです: ${cmd}（rag help で使い方を表示）`);
  await table[cmd](pos, opt, cfg);
}
main().catch(e => die(e && e.message ? e.message : String(e)));

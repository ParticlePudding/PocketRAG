// CLI 用のベクトル化（Transformers.js + ONNX Runtime）
// ・ネイティブ版：exe と同じ場所の engine フォルダにある onnxruntime-node（DLL）を使う。CPU の全コア／DirectML が使えて速い
// ・WASM 版：engine が無い・読めないときの予備（exe に同梱。1コアのみで遅い）
// 外部通信はしない（モデルはローカルのフォルダから読む）。
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import wasmFile from '../runtime/ort-wasm-simd-threaded.asyncify.wasm' with { type: 'file' };
import mjsFile from '../runtime/ort-wasm-simd-threaded.asyncify.mjs' with { type: 'file' };

const BASE = 'https://local-model.invalid/';
const DTYPE_SUFFIX = { '': 'fp32', '_fp16': 'fp16', '_quantized': 'q8', '_int8': 'int8', '_uint8': 'uint8', '_q4': 'q4', '_q4f16': 'q4f16', '_bnb4': 'bnb4' };
const CPU_PREF = ['q8', 'int8', 'uint8', 'fp32', 'q4', 'bnb4', 'fp16', 'q4f16'];

/* ---- モデルの置き場所 ---- */
export function exeDir() {
  const compiled = /\$bunfs|~BUN/.test(import.meta.url) || /\$bunfs|~BUN/.test(Bun.main || '');
  return compiled ? path.dirname(process.execPath) : path.resolve(import.meta.dir, '..');
}
export function modelDirs(extra) {
  const c = [extra, process.env.RAG_MODELS_DIR,
    path.join(exeDir(), 'models'), path.join(exeDir(), '埋め込みモデル'),
    path.join(process.cwd(), 'models'), path.join(process.cwd(), '埋め込みモデル')].filter(Boolean);
  return [...new Set(c.map(p => path.resolve(p)))].filter(p => fs.existsSync(p) && fs.statSync(p).isDirectory());
}
const isModelDir = d => fs.existsSync(path.join(d, 'config.json')) && fs.existsSync(path.join(d, 'tokenizer.json'))
  && fs.existsSync(path.join(d, 'onnx')) && fs.readdirSync(path.join(d, 'onnx')).some(f => f.endsWith('.onnx'));
export function listModels(extra) {
  const out = [];
  for (const root of modelDirs(extra)) {
    if (isModelDir(root)) out.push({ name: path.basename(root), dir: root });
    for (const e of fs.readdirSync(root, { withFileTypes: true })) {
      const d = path.join(root, e.name);
      if (e.isDirectory() && isModelDir(d) && !out.some(m => m.name === e.name)) out.push({ name: e.name, dir: d });
    }
  }
  return out;
}
export function findModel(name, extra) {
  if (name && fs.existsSync(name) && isModelDir(path.resolve(name))) return { name: path.basename(path.resolve(name)), dir: path.resolve(name) };
  const all = listModels(extra);
  const m = all.find(x => x.name === name) || all.find(x => x.name.toLowerCase().includes(String(name).toLowerCase()));
  if (!m) throw new Error(`埋め込みモデル「${name}」が見つかりません。見つかったモデル: ${all.map(x => x.name).join(', ') || 'なし'}\n` +
    `  exe と同じ場所の models フォルダ（または --models-dir）に、モデルのフォルダ（config.json・tokenizer.json・onnx/ を含む）を置いてください。`);
  return m;
}
function dtypesOf(dir) {
  return fs.readdirSync(path.join(dir, 'onnx')).map(f => (f.match(/^model(.*)\.onnx$/) || [])[1]).filter(s => s !== undefined && DTYPE_SUFFIX[s] !== undefined).map(s => DTYPE_SUFFIX[s]);
}
function poolingOf(m) {
  const p = path.join(m.dir, '1_Pooling', 'config.json');
  if (fs.existsSync(p)) {
    try {
      const j = JSON.parse(fs.readFileSync(p, 'utf8'));
      if (j.pooling_mode_cls_token) return 'cls';
      if (j.pooling_mode_lasttoken) return 'last_token';
      if (j.pooling_mode_mean_tokens) return 'mean';
    } catch {}
  }
  return /bge|gte-base-en|snowflake/i.test(m.name) ? 'cls' : 'mean';
}

/* ---- ネイティブ版エンジン（engine/node_modules/onnxruntime-node） ---- */
let engineInfo = null;   // { kind: 'native'|'wasm', note }
function loadNative() {
  if (process.env.RAG_ENGINE === 'wasm') return { kind: 'wasm', note: 'RAG_ENGINE=wasm が指定されています' };
  const cands = [process.env.RAG_ENGINE_DIR, path.join(exeDir(), 'engine'), path.join(process.cwd(), 'engine')].filter(Boolean);
  for (const dir of cands) {
    const pkg = path.join(dir, 'node_modules', 'onnxruntime-node', 'dist', 'ort-bundle.cjs');
    if (!fs.existsSync(pkg)) continue;
    try {
      const req = createRequire(path.join(dir, 'loader.js'));   // 実行時にディスクから読み込む（exe に取り込まない）
      const ort = req(pkg);
      return { kind: 'native', ort, note: pkg };
    } catch (e) { return { kind: 'wasm', note: `ネイティブ版を読み込めませんでした（${e.message.split('\n')[0]}）` }; }
  }
  return { kind: 'wasm', note: 'engine フォルダが見つかりません' };
}
export function engine() { if (!engineInfo) engineInfo = loadNative(); return engineInfo; }

/* ---- ライブラリ ---- */
let lib = null;
const dirs = new Map();   // 'm0' → モデルのフォルダ
async function getLib() {
  if (lib) return lib;
  // Node 判定のままだとネイティブ版の ONNX Runtime を探してしまうので、読み込みの間だけ隠す
  const rel = process.release;
  Object.defineProperty(process, 'release', { value: { name: 'rag-cli' }, configurable: true });
  let L;
  const E = engine();
  if (E.kind === 'native') {
    globalThis[Symbol.for('onnxruntime')] = E.ort;
    globalThis.__ragDevices = process.platform === 'win32' ? ['dml', 'cpu'] : ['cpu'];
  }
  try { L = await import('../runtime/transformers.native.js'); }
  finally { Object.defineProperty(process, 'release', { value: rel, configurable: true }); }
  const env = L.env;
  Object.assign(env, { allowLocalModels: false, allowRemoteModels: true, remoteHost: BASE, remotePathTemplate: '{model}/',
    useBrowserCache: false, useFSCache: false, useCustomCache: false, useWasmCache: true });
  env.fetch = async url => {
    const u = String((url && url.href) || url);
    if (!u.startsWith(BASE)) return new Response('', { status: 404, statusText: 'blocked' });   // 外部には出ない
    const rel = decodeURIComponent(u.slice(BASE.length).split(/[?#]/)[0]);
    let file = null;
    if (rel === '_rt/ort.wasm') file = wasmFile;
    else if (rel === '_rt/ort.mjs') file = mjsFile;
    else { const m = rel.match(/^local\/(m\d+)\/(.*)$/); if (m && dirs.has(m[1])) file = path.join(dirs.get(m[1]), ...m[2].split('/')); }
    if (!file) return new Response('', { status: 404 });
    const f = Bun.file(file);
    if (!(await f.exists())) return new Response('', { status: 404 });
    const buf = await f.arrayBuffer();
    return new Response(buf, { status: 200, headers: { 'Content-Length': String(buf.byteLength) } });
  };
  if (E.kind === 'wasm') {
    env.backends.onnx.wasm.wasmPaths = { wasm: BASE + '_rt/ort.wasm', mjs: BASE + '_rt/ort.mjs' };
    env.backends.onnx.wasm.proxy = false;
  }
  lib = L; return L;
}

// ベクトル化の関数を用意する。普通のモデルは feature-extraction パイプライン。
// EmbeddingGemma 2 はパイプラインだと画像・音声の部品まで読み込むので、文章用の部品だけを読み込み、
// モデルが出す sentence_embedding（平均＋512→768 の変換済み）を使う。呼び方はパイプラインと同じにそろえる。
// （src/browser_embed.js にも同じ処理がある）
async function loadExtractor(L, id, opts) {
  let cfg = null;
  try { cfg = await L.AutoConfig.from_pretrained(id); } catch {}
  if (!cfg || !(cfg.architectures || []).includes('EmbeddingGemma2Model')) return L.pipeline('feature-extraction', id, opts);
  cfg.vision_config = cfg.audio_config = null;
  const tok = await L.AutoTokenizer.from_pretrained(id);
  const model = await L.AutoModel.from_pretrained(id, { ...opts, config: cfg });
  return async texts => (await model(await tok(texts, { padding: true, truncation: true, max_length: 2048 }))).sentence_embedding;
}
// 長さ1にそろえる（モデルを直接呼んだときにもパイプラインと同じ扱いにするため）
function unit(v) {
  let s = 0; for (let i = 0; i < v.length; i++) s += v[i] * v[i];
  s = Math.sqrt(s); if (s > 0 && Math.abs(s - 1) > 1e-4) for (let i = 0; i < v.length; i++) v[i] /= s;
  return v;
}

const pipes = new Map();
let runOpts = { device: 'auto', threads: 0 };
export function setRunOptions(o) { runOpts = { ...runOpts, ...o }; }
async function getPipe(m) {
  if (pipes.has(m.dir)) return pipes.get(m.dir);
  const E = engine();
  // 計算に使う装置：ネイティブ版は CPU（既定）か DirectML（Windows の GPU）。WASM 版は wasm のみ
  const devices = E.kind === 'wasm' ? ['wasm'] : runOpts.device === 'dml' ? ['dml', 'cpu'] : ['cpu'];
  const L = await getLib();
  const id = 'm' + dirs.size; dirs.set(id, m.dir);
  const have = dtypesOf(m.dir);
  const order = CPU_PREF.filter(d => have.includes(d));
  let lastErr;
  for (const device of devices) for (const dtype of order.length ? order : ['fp32']) {
    try {
      const suf = Object.keys(DTYPE_SUFFIX).find(k => DTYPE_SUFFIX[k] === dtype);
      const opts = { device, dtype };
      if (device !== 'wasm' && runOpts.threads > 0) opts.session_options = { intraOpNumThreads: runOpts.threads };
      if (fs.existsSync(path.join(m.dir, 'onnx', `model${suf}.onnx_data`))) opts.use_external_data_format = true;
      const pipe = await loadExtractor(L, 'local/' + id, opts);
      const P = { pipe, dtype, device, pooling: poolingOf(m) };
      pipes.set(m.dir, P); return P;
    } catch (e) { lastErr = e; }
  }
  throw lastErr;
}

/* texts をベクトル化（正規化済み Float32Array の配列） */
export async function embed(m, texts, { batch = 8, onProgress } = {}) {
  const P = await getPipe(m);
  const order = texts.map((t, i) => i).sort((a, b) => texts[a].length - texts[b].length);
  const out = new Array(texts.length);
  for (let s = 0; s < order.length; s += batch) {
    const idx = order.slice(s, s + batch);
    const t = await P.pipe(idx.map(i => texts[i]), { pooling: P.pooling, normalize: true });
    const d = t.dims[t.dims.length - 1];
    idx.forEach((i, n) => { out[i] = unit(Float32Array.from(t.data.subarray(n * d, (n + 1) * d))); });
    if (t.dispose) t.dispose();
    onProgress && onProgress(Math.min(s + batch, texts.length), texts.length);
  }
  return { vectors: out, dtype: P.dtype, pooling: P.pooling, device: P.device };
}

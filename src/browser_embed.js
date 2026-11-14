/* ブラウザ内ベクトル化（Transformers.js + ONNX Runtime Web）
 * モード
 *  - オフライン … file:// で開いたとき、または URL に ?offline=1 を付けたとき。外部（HuggingFace）には一切アクセスしない。
 *                 モデルは「モデルフォルダを追加…」で取り込んだもの（IndexedDB に保存）だけを使う。
 *  - オンライン … http(s) で開いたとき（GitHub Pages など）。取り込んだモデルに加え、既定のモデルを HuggingFace から
 *                 取得できる。取得したファイルはブラウザのキャッシュ（Cache Storage）に保存し、2回目からは通信しない。
 * 計算エンジン（Transformers.js / ONNX Runtime の WASM）は、HTML 内蔵 → 取り込み済み → 同じサーバーの runtime/ の順に探す。
 * Transformers.js の env.fetch を差し替え、ライブラリからの読み込みをすべてこのモジュールが仲介する。
 */
const BrowserEmbed = (() => {
  const BASE = 'https://local-model.invalid/';          // 実在しないホスト。すべて localFetch で横取りする
  const HF = 'https://huggingface.co/';
  const RT = '_runtime/';
  const RUNTIME = ['transformers.min.js', 'ort-wasm-simd-threaded.asyncify.mjs', 'ort-wasm-simd-threaded.asyncify.wasm'];
  const MODEL_FILES = /^(config\.json|tokenizer\.json|tokenizer_config\.json|special_tokens_map\.json|1_Pooling\/config\.json|onnx\/[^/]+\.onnx(_data(_\d+)?)?)$/;
  const DTYPE_SUFFIX = { '': 'fp32', '_fp16': 'fp16', '_quantized': 'q8', '_int8': 'int8', '_uint8': 'uint8', '_q4': 'q4', '_q4f16': 'q4f16', '_bnb4': 'bnb4' };
  const PREF = { webgpu: ['fp16', 'fp32', 'q4f16', 'q8', 'int8', 'uint8', 'q4', 'bnb4'], wasm: ['q8', 'int8', 'uint8', 'fp32', 'q4', 'bnb4', 'fp16', 'q4f16'] };
  // オンラインで取得できるモデル（ダウンロード量を抑えるため量子化版を優先）
  const CATALOG = [
    { name: 'ruri-v3-30m', repo: 'sirasagi62/ruri-v3-30m-ONNX', size: '数十MB', dtypes: ['q8', 'fp32'] },
    { name: 'bge-m3', repo: 'Xenova/bge-m3', size: '約570MB', dtypes: ['q8', 'fp16'] }
  ];
  const HF_CACHE = 'rag-hf-models';

  // ?offline / ?offline=1 でオフライン。?offline=0 なら明示的にオンライン。file:// は常にオフライン
  const params = new URLSearchParams(typeof location !== 'undefined' ? location.search : '');
  const ov = params.get('offline');
  const isHttp = typeof location !== 'undefined' && /^https?:$/.test(location.protocol);
  const appOffline = typeof window !== 'undefined' && window.RAG_APP && window.RAG_APP.offline;   // デスクトップ版（rag app）は既定でオフライン
  const OFFLINE = !isHttp || (ov !== null ? !/^(0|false|no|off)$/i.test(ov) : !!appOffline);

  let files = new Map();      // 'ruri-v3-30m/config.json' → Blob（取り込んだもの）
  let cachedRepos = new Set(); // オンラインで取得済みのリポジトリ
  let loaded = null;
  let lib = null, libP = null;
  const pipes = new Map();    // 'モデル|device' → Promise<{pipe, device, dtype, pooling}>
  const alias = new Map();    // 'm0' → モデル名（モデルIDに日本語などが来ても安全にするため）
  let lastRun = '';
  let onDownload = null;      // ダウンロードの進み具合を受け取る関数

  /* ---- 計算エンジン ---- */
  const rtCache = new Map();
  async function runtimeBlob(f) {
    if (rtCache.has(f)) return rtCache.get(f);
    let blob = null;
    const el = document.getElementById('rt' + RUNTIME.indexOf(f));
    if (el) {   // HTML 内蔵（gzip＋base64）
      const bin = atob(el.textContent.trim()); const u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      blob = await new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'))).blob();
    } else if (files.has(RT + f)) {
      blob = files.get(RT + f);
    } else if (isHttp) {   // 同じサーバーの runtime/ フォルダ（GitHub Pages 版）
      const r = await fetch(new URL('runtime/' + f, location.href));
      if (r.ok) blob = await r.blob();
    }
    if (blob) rtCache.set(f, blob);
    return blob;
  }

  /* ---- IndexedDB ---- */
  const idb = {
    open() { return new Promise((res, rej) => { const r = indexedDB.open('rag-browser-embed', 1); r.onupgradeneeded = () => r.result.createObjectStore('files'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); },
    async tx(mode, fn) { const db = await this.open(); return new Promise((res, rej) => { const t = db.transaction('files', mode); fn(t.objectStore('files')); t.oncomplete = () => { db.close(); res(); }; t.onerror = () => { db.close(); rej(t.error); }; t.onabort = () => { db.close(); rej(t.error || new Error('保存に失敗しました（ディスク容量を確認してください）')); }; }); },
    async all() {
      const db = await this.open();
      return new Promise((res, rej) => {
        const out = new Map(); const r = db.transaction('files').objectStore('files').openCursor();
        r.onsuccess = () => { const c = r.result; if (c) { out.set(c.key, c.value); c.continue(); } else { db.close(); res(out); } };
        r.onerror = () => { db.close(); rej(r.error); };
      });
    },
    put(key, blob) { return this.tx('readwrite', s => { s.put(blob, key); }); },
    del(keys) { return this.tx('readwrite', s => { for (const k of keys) s.delete(k); }); }
  };
  async function openHfCache() { try { return (isHttp && self.caches) ? await caches.open(HF_CACHE) : null; } catch { return null; } }

  async function load() {
    if (!loaded) loaded = (async () => {
      try { files = await idb.all(); } catch { files = new Map(); }
      cachedRepos = new Set();
      const c = await openHfCache();
      if (c) { try { for (const req of await c.keys()) { const m = req.url.match(/^https:\/\/huggingface\.co\/(.+?)\/resolve\//); if (m && /\.onnx$/.test(req.url)) cachedRepos.add(m[1]); } } catch {} }
      refreshAlias();
    })();
    return loaded;
  }
  function refreshAlias() { alias.clear(); models().forEach((n, i) => alias.set('m' + i, n)); }

  /* ---- 使えるモデル ---- */
  function localModels() {
    const names = new Set();
    for (const p of files.keys()) { const m = p.match(/^([^/]+)\/config\.json$/); if (m && m[1] + '/' !== RT) names.add(m[1]); }
    return [...names].filter(n => files.has(n + '/tokenizer.json') && onnxFiles(n).length).sort();
  }
  const catalogOf = name => CATALOG.find(c => c.name === name);
  const isOnlineModel = name => !OFFLINE && !localModels().includes(name) && !!catalogOf(name);
  function models() {
    const local = localModels();
    return OFFLINE ? local : [...local, ...CATALOG.map(c => c.name).filter(n => !local.includes(n))];
  }
  function onnxFiles(name) { return [...files.keys()].filter(p => p.startsWith(name + '/onnx/') && /\.onnx$/.test(p)).map(p => p.slice(name.length + 6)); }
  function sizeOf(prefix) { let s = 0; for (const [k, b] of files) if (k.startsWith(prefix)) s += b.size || 0; return s; }
  function info() {
    return {
      offline: OFFLINE, lastRun,
      models: models().map(n => isOnlineModel(n)
        ? { name: n, online: true, cached: cachedRepos.has(catalogOf(n).repo), size: catalogOf(n).size }
        : { name: n, online: false, bytes: sizeOf(n + '/'), dtypes: dtypesOf(n) })
    };
  }
  function dtypesOf(name) {
    const out = [];
    for (const f of onnxFiles(name)) { const m = f.match(/^model(.*)\.onnx$/); if (m && DTYPE_SUFFIX[m[1]]) out.push(DTYPE_SUFFIX[m[1]]); }
    return out;
  }
  function label(name) {
    const n = name.toLowerCase();
    if (/ruri/.test(n)) return name + '（日本語特化・名古屋大）';
    if (/bge-m3/.test(n)) return name + '（高精度・多言語）';
    if (/e5/.test(n)) return name + '（多言語）';
    return name;
  }

  /* ---- フォルダの取り込み ----
   * モデル単体のフォルダでも、複数のモデルが入ったフォルダでも受け付ける。
   * config.json と tokenizer.json が並んでいる場所をモデルのフォルダとみなす。 */
  async function importFiles(fileList, onProgress) {
    await load();
    const arr = [...fileList].map(f => ({ f, p: (f.webkitRelativePath || f.name).replace(/\\/g, '/') }));
    const byPath = new Map(arr.map(x => [x.p, x.f]));
    const plan = [];
    const modelDirs = arr.filter(x => /(^|\/)config\.json$/.test(x.p)).map(x => x.p.slice(0, -'config.json'.length))
      .filter(dir => byPath.has(dir + 'tokenizer.json') && !/(^|\/)1_Pooling\/$/.test(dir));
    const names = [];
    for (const dir of modelDirs) {
      const name = dir.replace(/\/$/, '').split('/').pop() || 'model';
      const parts = arr.filter(x => x.p.startsWith(dir) && MODEL_FILES.test(x.p.slice(dir.length)));
      if (!parts.some(x => /^onnx\/.+\.onnx$/.test(x.p.slice(dir.length)))) continue;
      names.push(name);
      for (const x of parts) plan.push([name + '/' + x.p.slice(dir.length), x.f]);
    }
    if (!names.length) throw new Error('モデルが見つかりません。config.json・tokenizer.json・onnx フォルダが入っているモデルのフォルダ（例：ruri-v3-30m）を選んでください。');
    const old = [...files.keys()].filter(k => names.some(n => k.startsWith(n + '/')));   // 同名モデルは入れ替える
    if (old.length) await idb.del(old);
    const total = plan.reduce((s, [, f]) => s + f.size, 0); let done = 0;
    for (const [key, f] of plan) {
      await idb.put(key, f);
      done += f.size; onProgress && onProgress(done, total);
    }
    loaded = null; await load(); pipes.clear();
    return { models: names, bytes: total };
  }
  async function removeAll() {
    await load();
    await idb.del([...files.keys()]);
    try { if (isHttp && self.caches) await caches.delete(HF_CACHE); } catch {}
    loaded = null; await load(); pipes.clear();
  }

  /* ---- オンライン取得（HuggingFace → Cache Storage） ---- */
  async function onlineFetch(repo, path) {
    if (OFFLINE) return new Response('', { status: 404, statusText: 'offline' });
    const url = HF + repo + '/resolve/main/' + path;
    const cache = await openHfCache();
    if (cache) { const hit = await cache.match(url); if (hit) return hit; }
    const r = await fetch(url);
    if (!r.ok) return new Response('', { status: r.status, statusText: r.statusText });
    const total = +r.headers.get('content-length') || 0;
    let blob;
    if (r.body && total > 2e6) {   // 大きいファイルは進み具合を知らせる
      const reader = r.body.getReader(); const parts = []; let got = 0;
      for (;;) {
        const { done, value } = await reader.read(); if (done) break;
        parts.push(value); got += value.length;
        onDownload && onDownload(path, got, total);
      }
      blob = new Blob(parts);
    } else blob = await r.blob();
    const resp = new Response(blob, { status: 200, headers: { 'Content-Length': String(blob.size) } });
    if (cache) { try { await cache.put(url, resp.clone()); if (/\.onnx$/.test(path)) cachedRepos.add(repo); } catch {} }
    return resp;
  }

  /* ---- Transformers.js からの読み込みをすべてここで受ける ---- */
  async function localFetch(url) {
    const u = typeof url === 'string' ? url : (url && url.href) || String(url);
    if (!u.startsWith(BASE)) return new Response('', { status: 404, statusText: 'blocked' });   // 想定外の外部通信はしない
    let rel = decodeURIComponent(u.slice(BASE.length).split(/[?#]/)[0]);
    if (rel.startsWith(RT)) {
      const b = await runtimeBlob(rel.slice(RT.length));
      return b ? new Response(b, { status: 200, headers: { 'Content-Length': String(b.size) } }) : new Response('', { status: 404 });
    }
    const m = rel.match(/^local\/(m\d+)\/(.*)$/);
    if (!m) return new Response('', { status: 404 });
    const name = alias.get(m[1]), path = m[2];
    if (isOnlineModel(name)) return onlineFetch(catalogOf(name).repo, path);
    const b = files.get(name + '/' + path);
    return b ? new Response(b, { status: 200, headers: { 'Content-Length': String(b.size) } }) : new Response('', { status: 404, statusText: 'Not Found' });
  }

  async function getLib() {
    if (lib) return lib;
    if (libP) return libP;
    libP = (async () => {
      await load();
      const js = await runtimeBlob(RUNTIME[0]);
      if (!js) throw new Error('計算エンジンが見つかりません（HTMLと同じ場所に runtime フォルダがあるか確認してください）');
      const url = URL.createObjectURL(new Blob([js], { type: 'text/javascript' }));
      const L = await import(url);
      const env = L.env;
      env.allowLocalModels = false;
      env.allowRemoteModels = true;
      env.remoteHost = BASE;
      env.remotePathTemplate = '{model}/';
      env.useBrowserCache = false;
      env.useFSCache = false;
      env.useCustomCache = false;
      env.useWasmCache = true;          // WASM 本体も env.fetch 経由で読む
      env.fetch = localFetch;
      const w = env.backends.onnx.wasm;
      w.wasmPaths = { mjs: BASE + RT + RUNTIME[1], wasm: BASE + RT + RUNTIME[2] };
      w.proxy = false;
      lib = L; return L;
    })();
    try { return await libP; } finally { libP = null; }
  }

  let gpuOk = null;
  async function hasWebGPU() {
    if (gpuOk !== null) return gpuOk;
    try { gpuOk = !!(navigator.gpu && await navigator.gpu.requestAdapter()); } catch { gpuOk = false; }
    return gpuOk;
  }

  async function poolingOf(name) {
    const b = files.get(name + '/1_Pooling/config.json');
    if (b) {
      try {
        const j = JSON.parse(await b.text());
        if (j.pooling_mode_cls_token) return 'cls';
        if (j.pooling_mode_lasttoken) return 'last_token';
        if (j.pooling_mode_mean_tokens) return 'mean';
      } catch {}
    }
    return /bge|gte-base-en|snowflake/i.test(name) ? 'cls' : 'mean';
  }
  function dtypeCandidates(name, device) {
    if (isOnlineModel(name)) return catalogOf(name).dtypes;
    const have = dtypesOf(name);
    const order = PREF[device].filter(d => have.includes(d));
    return order.length ? order : [have[0] || 'fp32'];
  }

  async function getPipe(name, devicePref = 'auto') {
    await load();
    if (!models().includes(name)) throw new Error(OFFLINE ? `モデル「${name}」が取り込まれていません（オフラインモード）` : `モデル「${name}」が見つかりません`);
    const dev = devicePref === 'auto' ? (await hasWebGPU() ? 'webgpu' : 'wasm') : devicePref;
    const key = name + '|' + dev;
    if (pipes.has(key)) return pipes.get(key);
    const p = (async () => {
      const L = await getLib();
      const id = 'local/' + [...alias].find(([, n]) => n === name)[0];
      let lastErr;
      for (const dtype of dtypeCandidates(name, dev)) {   // 無い形式は飛ばして次を試す
        try {
          const ext = !isOnlineModel(name) && files.has(`${name}/onnx/model${Object.keys(DTYPE_SUFFIX).find(k => DTYPE_SUFFIX[k] === dtype)}.onnx_data`);
          const opts = { device: dev, dtype };
          if (ext) opts.use_external_data_format = true;
          const pipe = await L.pipeline('feature-extraction', id, opts);
          return { pipe, device: dev, dtype, pooling: await poolingOf(name) };
        } catch (e) { lastErr = e; }
      }
      throw lastErr;
    })();
    pipes.set(key, p);
    try { return await p; }
    catch (err) {
      pipes.delete(key);
      if (dev === 'webgpu' && devicePref === 'auto') { gpuOk = false; return getPipe(name, 'wasm'); }   // GPU で失敗したら CPU で再挑戦
      throw err;
    }
  }

  /* texts をベクトル化（正規化済み Float32Array の配列） */
  async function embed(name, texts, opts = {}) {
    onDownload = opts.onDownload || null;
    try { return await embedOnce(name, texts, opts); }
    catch (err) {
      // GPU（WebGPU）の計算で失敗したときは CPU でやり直す（GPUドライバや fp16 非対応など）
      if ((opts.device || 'auto') === 'auto' && gpuOk) {
        gpuOk = false; for (const k of [...pipes.keys()]) if (k.endsWith('|webgpu')) pipes.delete(k);
        return embedOnce(name, texts, { ...opts, device: 'wasm' });
      }
      throw err;
    } finally { onDownload = null; }
  }
  async function embedOnce(name, texts, { device = 'auto', batch = 8, onProgress, signal } = {}) {
    const P = await getPipe(name, device);
    lastRun = `${name} を ${P.device === 'webgpu' ? 'GPU（WebGPU）' : 'CPU（WASM）'}・${P.dtype} で実行`;
    const order = texts.map((t, i) => i).sort((a, b) => texts[a].length - texts[b].length);   // 長さ順に束ねて無駄な詰め物を減らす
    const out = new Array(texts.length);
    for (let s = 0; s < order.length; s += batch) {
      if (signal && signal.aborted) throw new Error('中止しました');
      const idx = order.slice(s, s + batch);
      const t = await P.pipe(idx.map(i => texts[i]), { pooling: P.pooling, normalize: true });
      const d = t.dims[t.dims.length - 1], data = t.data;
      idx.forEach((i, n) => { out[i] = Float32Array.from(data.subarray(n * d, (n + 1) * d)); });
      if (t.dispose) t.dispose();
      onProgress && onProgress(Math.min(s + batch, texts.length), texts.length);
      await new Promise(r => setTimeout(r, 0));   // 画面が固まらないよう一息つく
    }
    return out;
  }

  // モード切替用のURL（今のページの ?offline を付け外しする）
  function switchUrl(toOffline) {
    const u = new URL(location.href);
    if (toOffline) u.searchParams.set('offline', '1'); else u.searchParams.delete('offline');
    return u.href;
  }

  return { load, info, models, label, importFiles, removeAll, embed, hasWebGPU, switchUrl,
    get offline() { return OFFLINE; }, get canGoOnline() { return isHttp; }, get lastRun() { return lastRun; } };
})();

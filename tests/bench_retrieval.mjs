// 複数のテストセットで検索の性能をまとめて測る（LLM は使わない）。CLI と同じ Core とネイティブ版エンジンを使う。
//   RAG_ENGINE_DIR=dist/cli-windows/RAG-CLI/engine bun tests/bench_retrieval.mjs <モデル置き場> <モデル名> <testset.json...>
// 指標：上位 n 件のうち「根拠の資料（sources）」のかたまりだけで、正解の語（must）がすべてそろったか（厳しい基準）。
//   R@1・R@5 … 上位 1・5 件でそろった割合　MRR … そろった順位の逆数の平均
// 環境変数 RAG_VARIANTS に JSON の配列で、ハイブリッドの設定（Core.hybridSearch の第 7 引数）を並べると、まとめて比べられる。
//   例：RAG_VARIANTS='[{"name":"既定"},{"name":"上位30","cap":30}]'
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { embed, findModel } from '../cli/src/embed.js';
const Core = createRequire(import.meta.url)('../cli/src/core.cjs');

const [modelsDir, modelName, ...files] = process.argv.slice(2);
if (!files.length) { console.error('使い方: bun tests/bench_retrieval.mjs <モデル置き場> <モデル名> <testset.json...>'); process.exit(1); }
const variants = JSON.parse(process.env.RAG_VARIANTS || '[{"name":"既定"}]');
if (process.env.RAG_SEARCH) Core.setSearchOptions(JSON.parse(process.env.RAG_SEARCH));   // 例：RAG_SEARCH='{"idWeight":1,"dropHira":false}'
const normA = s => String(s || '').normalize('NFKC').toLowerCase().replace(/(\d),(?=\d)/g, '$1').replace(/\s+/g, '');
const m = modelName === 'none' ? null : findModel(modelName, modelsDir);

function rankOf(q, order, flat, ctx) {
  const src = new Set(q.sources || []);
  let acc = '';
  for (let r = 0; r < order.length; r++) {
    const i = order[r];
    if (src.size && !src.has(flat[i].source)) continue;
    acc += ctx[i] + '\n';
    if (q.must.every(g => g.some(x => acc.includes(normA(x))))) return r + 1;
  }
  return Infinity;
}
const stat = rs => ({ n: rs.length, r1: rs.filter(r => r <= 1).length, r5: rs.filter(r => r <= 5).length, mrr: rs.reduce((s, r) => s + (r === Infinity ? 0 : 1 / r), 0) });
const add = (a, b) => ({ n: a.n + b.n, r1: a.r1 + b.r1, r5: a.r5 + b.r5, mrr: a.mrr + b.mrr });
const fmt = s => `R@1 ${String(Math.round(100 * s.r1 / s.n)).padStart(3)}%  R@5 ${String(Math.round(100 * s.r5 / s.n)).padStart(3)}%  MRR ${(s.mrr / s.n).toFixed(3)}`;

const total = {}; const zero = { n: 0, r1: 0, r5: 0, mrr: 0 };
const misses = {};
for (const file of files) {
  const set = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
  const flat = [];
  for (const d of set.docs) for (const c of Core.chunkText(d.text, 600, 100)) flat.push({ source: d.name, heading: c.heading, text: c.text, title: c.title });
  const ctx = flat.map(c => normA(c.source.replace(/\.[^.]+$/, '') + ' ' + (c.heading || '') + '\n' + c.text));
  const kw = Core.buildIndex(flat);
  const qs = set.questions.filter(q => q.must && q.must.length && q.sources && q.sources.length);
  const res = {};
  res['キーワード'] = qs.map(q => rankOf(q, Core.search(kw, q.question, '', 0).map(h => h.i), flat, ctx));
  if (m) {
    const pre = Core.embedPrefixes(m.name);
    const dv = (await embed(m, flat.map(c => pre.d + Core.chunkEmbedText(c)))).vectors;
    const qv = (await embed(m, qs.map(q => pre.q + q.question))).vectors;
    res['意味のみ'] = qs.map((q, i) => rankOf(q, dv.map((v, j) => [j, Core.cosine(qv[i], v)]).sort((a, b) => b[1] - a[1]).map(x => x[0]), flat, ctx));
    for (const v of variants) res['ハイブリッド:' + v.name] = qs.map((q, i) => rankOf(q, Core.hybridSearch(kw, q.question, '', flat.length, qv[i], dv, v).map(h => h.i), flat, ctx));
  }
  const name = path.basename(file, '.json');
  console.log(`\n# ${name}（質問 ${qs.length}・チャンク ${flat.length}）`);
  for (const [k, rs] of Object.entries(res)) {
    const s = stat(rs); total[k] = add(total[k] || zero, s);
    console.log(`  ${k.padEnd(22)} ${fmt(s)}`);
    (misses[k] ||= []).push(...qs.filter((q, i) => rs[i] > 5).map(q => `${name.slice(0, 2)}-Q${q.id}`));
  }
}
console.log(`\n## 合計（モデル ${m ? m.name : 'なし'}）`);
for (const [k, s] of Object.entries(total)) console.log(`  ${k.padEnd(22)} ${fmt(s)}  （${s.n} 問）`);
if (process.env.RAG_BENCH_MISSES) fs.writeFileSync(process.env.RAG_BENCH_MISSES, JSON.stringify(misses, null, 1));

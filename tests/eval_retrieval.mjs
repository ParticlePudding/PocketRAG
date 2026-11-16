// 埋め込みモデルの検索性能を比べる（LLM は使わない）。CLI と同じ Core（分割・BM25・ハイブリッド）とネイティブ版エンジンを使う。
//   先に python scripts/build.py cli-windows（cli/src/core.cjs と cli/runtime/ を作る）
//   RAG_ENGINE_DIR=dist/cli-windows/RAG-CLI/engine bun tests/eval_retrieval.mjs <testset.json> <モデル置き場> <モデル名...>
// 指標は2通り（どちらも R@1・R@3・R@5 … 上位 1・3・5 件でそろった割合、MRR … そろった順位の逆数の平均。1 に近いほど上位）：
//   答え … 上位の文章に正解の語（must）がすべて含まれたか。rag eval・精度テストの「検索で根拠が入った割合」と同じ基準（主な指標）
//   資料 … 上位の文章に根拠の資料（sources）のチャンクがすべて入ったか（答えの箇所でなくてもよい、ゆるい基準）
// 環境変数 RAG_WVEC でハイブリッドの意味検索の重み（既定 1）、RAG_EVAL_JSON で結果の保存先を指定できる。
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { embed, findModel } from '../cli/src/embed.js';
const Core = createRequire(import.meta.url)('../cli/src/core.cjs');

const [file, modelsDir, ...names] = process.argv.slice(2);
if (!file || !modelsDir) { console.error('使い方: bun tests/eval_retrieval.mjs <testset.json> <モデル置き場> <モデル名...>'); process.exit(1); }
const set = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
const flat = [];
for (const d of set.docs) for (const c of Core.chunkText(d.text, 600, 100)) flat.push({ source: d.name, heading: c.heading, text: c.text });
const kw = Core.buildIndex(flat);
const qs = set.questions.filter(q => q.must && q.must.length);
const wVec = +(process.env.RAG_WVEC || 1);

// rag eval と同じ正規化（NFKC・小文字・桁区切りと空白を除く）
const normA = s => String(s || '').normalize('NFKC').toLowerCase().replace(/(\d),(?=\d)/g, '$1').replace(/\s+/g, '');
const chunkCtx = flat.map(c => normA(c.source.replace(/\.[^.]+$/, '') + ' ' + (c.heading || '') + '\n' + c.text));
// 正解の語がすべてそろう順位（そろわなければ Infinity）
function answerRank(q, order) {
  let ctx = '';
  for (let r = 0; r < order.length; r++) {
    ctx += chunkCtx[order[r]] + '\n';
    if (q.must.every(g => g.some(x => ctx.includes(normA(x))))) return r + 1;
  }
  return Infinity;
}
// 根拠の資料がすべてそろう順位
function docRank(q, order) {
  const need = new Set(q.sources || []);
  if (!need.size) return Infinity;
  for (let r = 0; r < order.length; r++) { need.delete(flat[order[r]].source); if (!need.size) return r + 1; }
  return Infinity;
}
function stats(ranks) {
  const n = ranks.length, at = k => ranks.filter(r => r <= k).length / n;
  return { r1: at(1), r3: at(3), r5: at(5), mrr: ranks.reduce((s, r) => s + (r === Infinity ? 0 : 1 / r), 0) / n };
}
const pct = x => (x * 100).toFixed(0).padStart(3) + '%';
const row = (label, s) => `${label.padEnd(24)} R@1 ${pct(s.r1)}  R@3 ${pct(s.r3)}  R@5 ${pct(s.r5)}  MRR ${s.mrr.toFixed(3)}`;
function both(label, orders) {
  const a = qs.map((q, i) => answerRank(q, orders[i])), d = qs.map((q, i) => docRank(q, orders[i]));
  console.log(row(label + '（答え）', stats(a)));
  console.log(row(label + '（資料）', stats(d)));
  return { a, d, sa: stats(a), sd: stats(d) };
}

console.log(`# ${path.basename(file)}：資料 ${set.docs.length} 件・チャンク ${flat.length} 個・答えのある質問 ${qs.length} 問` + (wVec !== 1 ? `（意味検索の重み ${wVec}）` : '') + '\n');
const results = { keyword: both('キーワードのみ', qs.map(q => Core.search(kw, q.question, '', 0).map(h => h.i))) };

for (const name of names) {
  const m = findModel(name, modelsDir), pre = Core.embedPrefixes(m.name);
  const t0 = performance.now();
  const dv = await embed(m, flat.map(c => pre.d + Core.chunkEmbedText(c)));
  const tDoc = (performance.now() - t0) / 1000;
  const qv = await embed(m, qs.map(q => pre.q + q.question));
  console.log(`\n## ${m.name}（${dv.device}・${dv.dtype}・次元 ${dv.vectors[0].length}・資料のベクトル化 ${tDoc.toFixed(1)} 秒）`);
  const V = both('  意味のみ', qs.map((q, i) => dv.vectors.map((v, j) => [j, Core.cosine(qv.vectors[i], v)]).sort((a, b) => b[1] - a[1]).map(x => x[0])));
  const H = both('  ハイブリッド', qs.map((q, i) => Core.hybridSearch(kw, q.question, '', flat.length, qv.vectors[i], dv.vectors, { wVec }).map(h => h.i)));
  results[m.name] = { vec: V, hyb: H, sec: tDoc, dim: dv.vectors[0].length };
}

// 種類別（答えの基準の R@5。意味のみ／ハイブリッド）
const types = [...new Set(qs.map(q => q.type))];
console.log('\n種類別 R@5・答えの基準（意味のみ／ハイブリッド）');
console.log('種類'.padEnd(10) + '問数  キーワード  ' + names.map(n => n.padEnd(18)).join(''));
for (const t of types) {
  const idx = qs.map((q, i) => q.type === t ? i : -1).filter(i => i >= 0);
  const r5 = rs => idx.filter(i => rs[i] <= 5).length;
  console.log(t.padEnd(10) + String(idx.length).padStart(4) + '  ' + String(r5(results.keyword.a)).padStart(6) + '      ' +
    names.map(n => { const r = results[findModel(n, modelsDir).name]; return `${r5(r.vec.a)}／${r5(r.hyb.a)}`.padEnd(18); }).join(''));
}
console.log('\n上位 5 件に答えがそろわなかった質問（意味のみ ／ ハイブリッド）');
console.log(`  キーワードのみ: ${qs.filter((q, i) => results.keyword.a[i] > 5).map(q => 'Q' + q.id).join(' ') || 'なし'}`);
for (const n of names) {
  const r = results[findModel(n, modelsDir).name];
  const miss = rs => qs.filter((q, i) => rs[i] > 5).map(q => 'Q' + q.id).join(' ') || 'なし';
  console.log(`  ${n}: ${miss(r.vec.a)} ／ ${miss(r.hyb.a)}`);
}
if (process.env.RAG_EVAL_JSON) fs.writeFileSync(process.env.RAG_EVAL_JSON, JSON.stringify(results));

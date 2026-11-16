# 使い方: python tests/make_standin_models.py <名前> <層数> <幅> <ヘッド数> <FFN幅>   … 速度比較用（本物と同じ計算量・重みは乱数）
# 例: python tests/make_standin_models.py ruri-like 10 256 4 1024 / bge-like 8 1024 16 4096（先に make_dummy_models.py でトークナイザを用意）
# 本物と同じ大きさ（層数・幅）のエンコーダを乱数の重みで作る（計算量の比較用。精度は無意味）
import sys, os, shutil, numpy as np, onnx
from onnx import helper as H, TensorProto as T, numpy_helper as NH
from onnxruntime.quantization import quantize_dynamic, QuantType
name, L, D, NH_, F = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
VOCAB = 1028; dh = D // NH_
rng = np.random.default_rng(0); inits = []; nodes = []
def W(n, *shape, s=0.02): inits.append(NH.from_array((rng.standard_normal(shape) * s).astype(np.float32), n)); return n
def C(n, arr): inits.append(NH.from_array(np.array(arr), n)); return n
def N(op, ins, out, **kw): nodes.append(H.make_node(op, ins, [out], **kw)); return out
C('shape_split', np.array([0, 0, NH_, dh], dtype=np.int64)); C('shape_merge', np.array([0, 0, D], dtype=np.int64))
C('one', np.array(1.0, dtype=np.float32)); C('neg', np.array(-1e4, dtype=np.float32)); C('scale', np.array(1 / np.sqrt(dh), dtype=np.float32))
C('half', np.array(0.5, dtype=np.float32)); C('isq2', np.array(1 / np.sqrt(2), dtype=np.float32)); C('axes12', np.array([1, 2], dtype=np.int64))
x = N('Gather', [W('emb', VOCAB, D), 'input_ids'], 'x0', axis=0)
mf = N('Cast', ['attention_mask'], 'mf', to=T.FLOAT)
mb = N('Mul', [N('Sub', ['one', mf], 'inv'), 'neg'], 'mb0'); mb = N('Unsqueeze', [mb, 'axes12'], 'mb')
for i in range(L):
    p = f'l{i}_'
    def proj(t, o): return N('Add', [N('MatMul', [x, W(p + t + 'W', D, D)], p + t + 'm'), W(p + t + 'b', D)], p + t)
    q = N('Transpose', [N('Reshape', [proj('q', 0), 'shape_split'], p + 'qr')], p + 'qt', perm=[0, 2, 1, 3])
    k = N('Transpose', [N('Reshape', [proj('k', 0), 'shape_split'], p + 'kr')], p + 'kt', perm=[0, 2, 3, 1])
    v = N('Transpose', [N('Reshape', [proj('v', 0), 'shape_split'], p + 'vr')], p + 'vt', perm=[0, 2, 1, 3])
    s = N('Add', [N('Mul', [N('MatMul', [q, k], p + 's0'), 'scale'], p + 's1'), 'mb'], p + 's2')
    a = N('Softmax', [s], p + 'a', axis=-1)
    c = N('Reshape', [N('Transpose', [N('MatMul', [a, v], p + 'c0')], p + 'c1', perm=[0, 2, 1, 3]), 'shape_merge'], p + 'c')
    o = N('Add', [N('MatMul', [c, W(p + 'oW', D, D)], p + 'om'), W(p + 'ob', D)], p + 'o')
    x = N('LayerNormalization', [N('Add', [x, o], p + 'r1'), C(p + 'ln1g', np.ones(D, np.float32)), C(p + 'ln1b', np.zeros(D, np.float32))], p + 'n1', axis=-1)
    h = N('Add', [N('MatMul', [x, W(p + 'f1', D, F)], p + 'h0'), W(p + 'f1b', F)], p + 'h1')
    g = N('Mul', [N('Mul', [h, 'half'], p + 'g0'), N('Add', ['one', N('Erf', [N('Mul', [h, 'isq2'], p + 'g1')], p + 'g2')], p + 'g3')], p + 'g')
    f = N('Add', [N('MatMul', [g, W(p + 'f2', F, D)], p + 'f2m'), W(p + 'f2b', D)], p + 'f')
    x = N('LayerNormalization', [N('Add', [x, f], p + 'r2'), C(p + 'ln2g', np.ones(D, np.float32)), C(p + 'ln2b', np.zeros(D, np.float32))], p + 'n2' if i < L - 1 else 'last_hidden_state', axis=-1)
g = H.make_graph(nodes, name, [H.make_tensor_value_info('input_ids', T.INT64, ['b', 's']), H.make_tensor_value_info('attention_mask', T.INT64, ['b', 's'])],
                 [H.make_tensor_value_info('last_hidden_state', T.FLOAT, ['b', 's', D])], inits)
m = H.make_model(g, opset_imports=[H.make_opsetid('', 17)]); m.ir_version = 8
d = f'tests/models/{name}'; os.makedirs(d + '/onnx', exist_ok=True)
onnx.save(m, d + '/onnx/model.onnx', save_as_external_data=False)
quantize_dynamic(d + '/onnx/model.onnx', d + '/onnx/model_quantized.onnx', weight_type=QuantType.QInt8, extra_options={'DefaultTensorType': T.FLOAT})
src = sys.argv[6] if len(sys.argv) > 6 else 'tests/models/ruri-v3-30m/'
for f in ['tokenizer.json', 'tokenizer_config.json']: shutil.copy(src + f, d)
import json; json.dump({"model_type": "bert", "hidden_size": D, "vocab_size": VOCAB, "num_attention_heads": NH_, "num_hidden_layers": L}, open(d + '/config.json', 'w'))
print(name, {f: os.path.getsize(d + '/onnx/' + f) // 1048576 for f in os.listdir(d + '/onnx')}, 'MB')

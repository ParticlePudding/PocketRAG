# 使い方: python tests/make_dummy_models.py tests/models   … 形だけのダミー（ruri-v3-30m / bge-m3 という名前。数KB。動作確認用）
import json, os, sys, numpy as np, onnx
from onnx import helper, TensorProto, numpy_helper
from tokenizers import Tokenizer, models, pre_tokenizers, processors, normalizers
root = sys.argv[1]
chars = set()
for fn in os.listdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sample')):
    chars |= set(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'sample', fn), encoding='utf-8').read())
chars |= set("検索クエリ文書: query passage寒い気温")
vocab = ["[PAD]","[UNK]","[CLS]","[SEP]"] + sorted(c for c in chars if not c.isspace())
v = {t:i for i,t in enumerate(vocab)}
tok = Tokenizer(models.WordPiece(v, unk_token="[UNK]", max_input_chars_per_word=100))
tok.normalizer = normalizers.BertNormalizer(lowercase=False)
tok.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
tok.post_processor = processors.BertProcessing(("[SEP]",3),("[CLS]",2))
H=16
rng=np.random.default_rng(0)
emb=rng.standard_normal((len(vocab),H)).astype(np.float32)
for name in ["ruri-v3-30m","bge-m3"]:
    d=f"{root}/{name}"; os.makedirs(d+"/onnx",exist_ok=True)
    tok.save(d+"/tokenizer.json")
    json.dump({"model_type":"bert","hidden_size":H,"vocab_size":len(vocab),"num_attention_heads":1,"num_hidden_layers":1},open(d+"/config.json","w"))
    json.dump({"tokenizer_class":"BertTokenizer","model_max_length":512,"do_lower_case":False,"cls_token":"[CLS]","sep_token":"[SEP]","pad_token":"[PAD]","unk_token":"[UNK]"},open(d+"/tokenizer_config.json","w"))
    g=helper.make_graph([helper.make_node("Gather",["E","input_ids"],["last_hidden_state"],axis=0)],"g",
      [helper.make_tensor_value_info("input_ids",TensorProto.INT64,["b","s"]),helper.make_tensor_value_info("attention_mask",TensorProto.INT64,["b","s"])],
      [helper.make_tensor_value_info("last_hidden_state",TensorProto.FLOAT,["b","s",H])],[numpy_helper.from_array(emb,"E")])
    m=helper.make_model(g,opset_imports=[helper.make_opsetid("",17)]); m.ir_version=8
    onnx.checker.check_model(m)
    onnx.save(m, d+"/onnx/model_quantized.onnx")
print(len(vocab))

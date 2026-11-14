# CLI 用：外部から渡したネイティブ ONNX Runtime（onnxruntime-node）を使えるよう、デバイス一覧を補う
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding='utf-8').read()
m = re.search(r'if\((\w+) in globalThis\)(\w+)=globalThis\[\1\];else if\(\w+\.IS_NODE_ENV\)\{switch\(\2=\w+,process\.platform\)\{case"win32":(\w+)\.push\("dml"\)', s)
if not m: sys.exit('patch point not found')
sym, onnx, devs = m.groups()
dflt = re.search(r'\b' + devs + r'\.push\("cpu"\),(\w+)=\["cpu"\]', s).group(1)
old = f'if({sym} in globalThis){onnx}=globalThis[{sym}];'
new = f'if({sym} in globalThis){{{onnx}=globalThis[{sym}];{devs}.push(...(globalThis.__ragDevices||["cpu"]));{dflt}=["cpu"]}}'
assert s.count(old) == 1
open(dst, 'w', encoding='utf-8').write(s.replace(old, new))
print('patched', sym, onnx, devs, dflt)

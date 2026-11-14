#!/usr/bin/env python3
"""ビルドスクリプト（リポジトリのルートで実行。先に npm install が必要）

  python scripts/build.py site           GitHub Pages 版        → dist/site/
  python scripts/build.py offline        オフライン配布版（HTML 2つ＋エンジン内蔵） → dist/RAG精度テスト.zip
  python scripts/build.py cli-windows    CLI（Windows）        → dist/cli-windows/ , dist/RAG-CLI-windows.zip
  python scripts/build.py cli-linux      CLI（Linux）
  python scripts/build.py desktop --app <tauriでビルドしたexe>   デスクトップ版 → dist/RAG-Desktop.zip（cli-windows の後に実行）
"""
import base64, gzip, json, os, re, shutil, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, DIST, CLI = os.path.join(ROOT, 'src'), os.path.join(ROOT, 'dist'), os.path.join(ROOT, 'cli')
NM = os.path.join(ROOT, 'node_modules')
RT_FILES = [os.path.join(NM, '@huggingface', 'transformers', 'dist', 'transformers.min.js'),
            os.path.join(NM, 'onnxruntime-web', 'dist', 'ort-wasm-simd-threaded.asyncify.mjs'),
            os.path.join(NM, 'onnxruntime-web', 'dist', 'ort-wasm-simd-threaded.asyncify.wasm')]
read = lambda p: open(p, encoding='utf-8').read()
def write(p, s, bom=False):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8-sig' if bom else 'utf-8', newline='').write(s)

def zipdir(folder, zpath, root_name=None):
    """日本語のファイル名が Windows で化けないよう UTF-8 フラグ付きで zip にする（Python の zipfile は自動で付ける）"""
    if os.path.exists(zpath): os.remove(zpath)
    base = os.path.dirname(folder)
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, ds, fs in os.walk(folder):
            ds.sort()
            arc = os.path.relpath(r, base)
            if root_name: arc = os.path.join(root_name, os.path.relpath(r, folder)) if r != folder else root_name
            z.write(r, arc.replace(os.sep, '/') + '/')
            for f in sorted(fs): z.write(os.path.join(r, f), (os.path.join(arc, f)).replace(os.sep, '/'))
    print('  ->', os.path.relpath(zpath, ROOT), os.path.getsize(zpath) // 1048576, 'MB')

# ---------- 画面 ----------
def pages():
    pb = read(os.path.join(SRC, 'prompt-builder.html'))
    core = re.search(r'<script id="core">([\s\S]*?)</script>', pb).group(1)
    ts = json.dumps(json.load(open(os.path.join(SRC, 'testset.json'), encoding='utf-8')), ensure_ascii=False).replace('</', '<\\/')
    ev = read(os.path.join(SRC, 'eval-template.html')).replace('/*CORE*/', core).replace('/*TESTSET*/', ts)
    return pb, ev, core

def inject(html, inline):
    be = read(os.path.join(SRC, 'browser_embed.js')).replace('</', '<\\/')
    rt = ''
    if inline:
        rt = '<!-- 内蔵の計算エンジン: Transformers.js (Apache-2.0) / ONNX Runtime Web (MIT) -->\n' + ''.join(
            f'<script type="application/octet-stream" id="rt{i}">{base64.b64encode(gzip.compress(open(f, "rb").read(), 9, mtime=0)).decode()}</script>\n'
            for i, f in enumerate(RT_FILES))
    return html.replace('<script id="core">', rt + '<script id="bembed">\n' + be + '</script>\n\n<script id="core">', 1)

def build_site():
    print('[site]')
    pb, ev, _ = pages()
    site = os.path.join(DIST, 'site')
    shutil.rmtree(site, ignore_errors=True)
    nav = ('<nav style="font-size:12px;margin:0 0 4px"><a href="./">プロンプトビルダー</a> ｜ <a href="eval.html">RAG精度テスト</a> ｜ '
           '<a href="sample/">テスト用資料</a></nav>\n')
    write(os.path.join(site, 'index.html'), inject(pb, False).replace('<header>\n', '<header>\n' + nav, 1))
    write(os.path.join(site, 'eval.html'), inject(ev, False).replace('<header>\n', '<header>\n' + nav, 1))
    os.makedirs(os.path.join(site, 'runtime'))
    for f in RT_FILES: shutil.copy(f, os.path.join(site, 'runtime'))
    shutil.copy(os.path.join(NM, '@huggingface', 'transformers', 'LICENSE'), os.path.join(site, 'runtime', 'LICENSE-transformers.js.txt'))
    write(os.path.join(site, 'runtime', 'LICENSE-onnxruntime-web.txt'), 'onnxruntime-web (https://github.com/microsoft/onnxruntime)\nCopyright (c) Microsoft Corporation.\nLicensed under the MIT License.\n')
    shutil.copytree(os.path.join(SRC, 'sample'), os.path.join(site, 'sample'))
    shutil.copy(os.path.join(SRC, 'testset.json'), os.path.join(site, 'sample'))
    items = ''.join(f'<li><a href="{f}" download>{f}</a></li>' for f in sorted(os.listdir(os.path.join(site, 'sample'))))
    write(os.path.join(site, 'sample', 'index.html'), '<!doctype html><meta charset="utf-8"><title>テスト用資料</title><body style="font-family:sans-serif">'
          '<h1>テスト用資料</h1><p>Wikipedia日本語版の記事の抜粋（CC BY-SA 4.0）と、評価用のテストセットです。</p><ul>' + items + '</ul><p><a href="../">戻る</a></p>')
    write(os.path.join(site, '.nojekyll'), '')

def build_offline():
    print('[offline]')
    pb, ev, _ = pages()
    out = os.path.join(DIST, 'offline', 'RAG精度テスト')
    shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    write(os.path.join(out, 'rag-prompt-builder.html'), inject(pb, True))
    write(os.path.join(out, 'rag-eval.html'), inject(ev, True))
    shutil.copy(os.path.join(SRC, 'testset.json'), out)
    shutil.copytree(os.path.join(SRC, 'sample'), os.path.join(out, 'テスト用資料'))
    shutil.copytree(os.path.join(SRC, 'offline'), out, dirs_exist_ok=True)
    zipdir(out, os.path.join(DIST, 'RAG精度テスト.zip'))

# ---------- CLI ----------
def prepare_cli():
    """exe に取り込むもの（Core・画面・Transformers.js）を cli/ の下に用意する"""
    _, _, core = pages()
    write(os.path.join(CLI, 'src', 'core.cjs'), '// 自動生成（src/prompt-builder.html の Core と同じもの）\n' + core)
    rt = os.path.join(CLI, 'runtime'); os.makedirs(rt, exist_ok=True)
    for f in RT_FILES: shutil.copy(f, rt)
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'patch_tjs.py'), os.path.join(rt, 'transformers.min.js'), os.path.join(rt, 'transformers.native.js')], check=True)
    build_site()
    site = os.path.join(CLI, 'site')
    shutil.rmtree(site, ignore_errors=True)
    shutil.copytree(os.path.join(DIST, 'site'), site, ignore=shutil.ignore_patterns('runtime', '.nojekyll'))
    lines, entries, n = ['// 自動生成：exe に埋め込む画面ファイル'], [], 0
    for r, _, fs in os.walk(site):
        for f in sorted(fs):
            rel = os.path.relpath(os.path.join(r, f), site).replace(os.sep, '/')
            lines.append(f"import f{n} from '../site/{rel}' with {{ type: 'file' }};"); entries.append(f"  '{rel}': f{n},"); n += 1
    for f in RT_FILES:
        b = os.path.basename(f)
        lines.append(f"import f{n} from '../runtime/{b}' with {{ type: 'file' }};"); entries.append(f"  'runtime/{b}': f{n},"); n += 1
    write(os.path.join(CLI, 'src', 'site_files.js'), '\n'.join(lines) + '\nexport const SITE = {\n' + '\n'.join(entries) + '\n};\n')

def build_cli(target):
    print(f'[cli-{target}]')
    prepare_cli()
    out = os.path.join(DIST, f'cli-{target}', 'RAG-CLI')
    shutil.rmtree(os.path.dirname(out), ignore_errors=True); os.makedirs(out)
    exe = 'rag.exe' if target == 'windows' else 'rag'
    bun = shutil.which('bun') or 'bun'
    subprocess.run([bun, 'build', '--compile', '--minify', f'--target=bun-{target}-x64', 'src/main.js', '--outfile', os.path.join(out, exe)], cwd=CLI, check=True)
    # ネイティブ版エンジン：onnxruntime-node（該当OSのバイナリだけ）と、exe から読めるよう1ファイルにまとめた JS
    plat = 'win32' if target == 'windows' else 'linux'
    eng = os.path.join(out, 'engine', 'node_modules')
    for pkg in ['onnxruntime-node', 'onnxruntime-common']:
        os.makedirs(os.path.join(eng, pkg))
        shutil.copy(os.path.join(NM, pkg, 'package.json'), os.path.join(eng, pkg))
        shutil.copytree(os.path.join(NM, pkg, 'dist'), os.path.join(eng, pkg, 'dist'))
    shutil.copytree(os.path.join(NM, 'onnxruntime-node', 'bin', 'napi-v6', plat, 'x64'), os.path.join(eng, 'onnxruntime-node', 'bin', 'napi-v6', plat, 'x64'))
    subprocess.run([bun, 'build', os.path.join(NM, 'onnxruntime-node', 'dist', 'index.js'), '--target=node', '--format=cjs',
                    '--outfile', os.path.join(eng, 'onnxruntime-node', 'dist', 'ort-bundle.cjs')], check=True)
    write(os.path.join(out, 'engine', 'LICENSE.txt'), 'ONNX Runtime (https://github.com/microsoft/onnxruntime)\nCopyright (c) Microsoft Corporation. Licensed under the MIT License.\n'
          'DirectML / DirectX Shader Compiler: Microsoft のライセンスに従います。\n')
    os.makedirs(os.path.join(out, 'models'))
    shutil.copy(os.path.join(CLI, 'ここにモデルを置く.txt'), os.path.join(out, 'models'))
    for f in ['使い方.txt', 'rag.config.json']: shutil.copy(os.path.join(CLI, f), out)
    shutil.copy(os.path.join(SRC, 'testset.json'), out)
    shutil.copytree(os.path.join(SRC, 'sample'), os.path.join(out, 'テスト用資料'))
    zipdir(out, os.path.join(DIST, f'RAG-CLI-{target}.zip'))

def build_desktop(app_exe):
    print('[desktop]')
    cli = os.path.join(DIST, 'cli-windows', 'RAG-CLI')
    if not os.path.exists(cli): sys.exit('先に cli-windows をビルドしてください')
    out = os.path.join(DIST, 'desktop', 'RAG-Desktop')
    shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    shutil.copytree(cli, out)
    shutil.copy(app_exe, os.path.join(out, 'RAGプロンプトビルダー.exe'))
    shutil.copy(os.path.join(ROOT, 'desktop', 'はじめに.txt'), out)
    zipdir(out, os.path.join(DIST, 'RAG-Desktop.zip'))

if __name__ == '__main__':
    args = sys.argv[1:] or ['site', 'offline']
    i = 0
    while i < len(args):
        a = args[i]
        if a == 'site': build_site()
        elif a == 'offline': build_offline()
        elif a.startswith('cli-'): build_cli(a[4:])
        elif a == 'desktop': build_desktop(args[i + 2] if args[i + 1] == '--app' else args[i + 1]); i += 2
        else: sys.exit('不明なターゲット: ' + a)
        i += 1

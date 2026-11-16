# -*- coding: utf-8 -*-
"""技術文書のテストセット（src/testset-tech.json）を作る。

資料の本文は、ツール自身の読み取り結果（rag text --json）をそのまま使う。PDF・Word・Excel などの読み取りもあわせて確かめるため。
先に tests/make_tech_samples.py で資料を作り、python scripts/build.py cli-windows（または cli-linux）で rag をビルドしておく。

  python tests/make_tech_testset.py [rag の実行ファイル]

質問の must（採点で答えに含まれるべき語）は、OR の候補を AND でつなぐ（精度テストと同じ）。
資料に must の語が本当に書かれているかもここで確かめる（書かれていなければ止める）。
"""
import glob, json, os, subprocess, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, 'src', 'sample-tech')
OUT = os.path.join(ROOT, 'src', 'testset-tech.json')

LDO, TS, FET, AN = 'HZ-LDO33A_データシート.pdf', 'HZ-TS20_Datasheet.pdf', 'HZ-N6030_MOSFET_データシート.pdf', 'AN-012_Input_Capacitor_Selection.pdf'
SPEC, QA, FW = 'SN-200_ハードウェア設計仕様書.docx', 'SN-200_出荷検査手順書.docx', 'SN-200_Firmware_Release_Notes.docx'
BOM, DR, CSV = 'SN-200_BOM.xlsx', 'SN-200_DR2_設計レビュー.pptx', 'SN-200_温度試験結果.csv'
FR, UART, CAP = '不具合報告_FR-2026-031.txt', 'UART_コマンド仕様.md', 'コンデンサ選定基準.html'
EV = 'C3-C4_コンデンサ受入評価.xlsx'

# (種類, 質問, 期待する答え, must, 根拠の資料)
Q = [
    # ---- データシートの表を読む
    ('表の読み取り', 'HZ-LDO33A の出力電流の最大値はいくつですか？', '500mA。', [['500']], [LDO]),
    ('表の読み取り', 'HZ-LDO33A の無負荷時消費電流の標準値と最大値を教えてください。', '標準 35μA、最大 60μA。', [['35'], ['60']], [LDO]),
    ('表の読み取り', 'HZ-LDO33A の出力電流 500mA のときのドロップアウト電圧の最大値は？', '650mV（Rev.1.1 で 600mV から変更）。', [['650']], [LDO]),
    ('表の読み取り', 'HZ-LDO33A を DFN-6 パッケージで使うときの熱抵抗 θja は？', '65℃/W（JEDEC 4層基板）。', [['65']], [LDO]),
    ('表の読み取り', 'HZ-LDO33A の出力コンデンサの ESR はどの範囲にすればよいですか？', '0.001Ω〜0.5Ω。', [['0.001'], ['0.5']], [LDO]),
    ('表の読み取り', 'HZ-LDO33A の過熱保護が働く温度と、そのヒステリシスは？', '検出温度 160℃（標準）、ヒステリシス 20℃。', [['160'], ['20']], [LDO]),
    ('単一事実', 'HZ-LDO33A の EN 端子を使わないときはどう処理しますか？', 'VIN に接続する（開放は禁止）。', [['VIN']], [LDO]),
    ('表の読み取り', 'HZ-N6030 のゲート電圧 4.5V のときのオン抵抗の最大値は？', '19mΩ（VGS=4.5V、ID=10A）。', [['19']], [FET]),
    ('表の読み取り', 'HZ-N6030 のゲートしきい値電圧は最小何 V から最大何 V ですか？', '1.2V〜2.5V（標準 1.8V）。', [['1.2'], ['2.5']], [FET]),
    ('表の読み取り', 'HZ-N6030 のケース温度 100℃ での連続ドレイン電流の定格は？', '21A。', [['21']], [FET]),
    ('表の読み取り', 'HZ-N6030 の総ゲート電荷量 Qg の標準値と最大値は？', '標準 18nC、最大 26nC（Rev.2.0 で 30nC から変更）。', [['18'], ['26']], [FET]),
    ('単一事実', 'HZ-N6030 のオン抵抗は、チャネル温度 125℃ では 25℃ のときの何倍になりますか？', '約 1.7 倍。', [['1.7']], [FET]),
    ('単一事実', 'SN-200 の BOM で、温度センサの単価はいくらですか？', '210 円（HZ-TS20-DRL）。', [['210']], [BOM]),

    # ---- 英語の資料に日本語で質問
    ('英語資料', 'HZ-TS20 の ADD0 端子を SDA につないだときの I2C アドレスは？', '0x4A。', [['0x4A', '4A']], [TS]),
    ('英語資料', 'HZ-TS20 の -40℃〜125℃ での温度精度は？', '±0.5℃（最大）。', [['0.5']], [TS]),
    ('英語資料', 'HZ-TS20 の1回の温度変換にかかる時間（標準）は？', '15.5ms（最大 17.5ms）。', [['15.5']], [TS]),
    ('英語資料', 'HZ-TS20 のデバイス ID レジスタのアドレスと、読み出される値は？', 'アドレス 0x0F、値 0x2012。', [['0x0F', '0F'], ['2012']], [TS]),
    ('英語資料', 'HZ-TS20 の温度レジスタの値が 0x0C80 のとき、温度は何度ですか？', '25.0℃（3200 × 0.0078125）。', [['25']], [TS]),
    ('英語資料', 'HZ-TS20 の変換中（動作時）の消費電流の標準値は？', '135μA（Rev.B で 150μA から変更）。', [['135']], [TS]),
    ('英語資料', 'AN-012 では HZ-BK2405 の入力コンデンサに何を勧めていますか？', '10μF・50V・X7R のセラミックコンデンサを 2 個並列（1210 サイズ）、VIN 端子から 3mm 以内。',
     [['10'], ['50'], ['X7R'], ['2個', '2 個', '2つ', '二つ', '並列', 'two', 'parallel']], [AN]),
    ('英語資料', 'AN-012 の例で、入力 12V・出力 5V・2A のときの入力コンデンサのリップル電流（実効値）は？', '約 0.99A（D=0.417）。', [['0.99']], [AN]),
    ('英語資料', 'ファームウェア v2.3.0 の既知の不具合は何ですか？', '電源投入後 2 秒間、ADC の校正が終わるまで GET_VOLT が 0 を返す。', [['GET_VOLT'], ['2']], [FW]),

    # ---- 英語で質問
    ('英語の質問', 'What is the typical dropout voltage of the HZ-LDO33A at 300 mA?', '250 mV (typical); 400 mV max.', [['250']], [LDO]),
    ('英語の質問', 'What is the maximum RS-485 baud rate of the SN-200?', '115200 bps.', [['115200']], [SPEC]),
    ('英語の質問', 'Which capacitor dielectrics are prohibited on power lines by the internal design guideline?', 'Y5V and Z5U.', [['Y5V'], ['Z5U']], [CAP]),
    ('英語の質問', 'In firmware 2.2.1, what was the default measurement interval changed to?', '60 seconds (from 30 s).', [['60']], [FW]),

    # ---- 言い換え（資料と違う言葉で質問）
    ('言い換え', 'SN-200 は何ボルトから何ボルトの電源につなげますか？', 'DC 9V〜24V（逆接続保護あり）。', [['9'], ['24']], [SPEC]),
    ('言い換え', 'SN-200 の基板の大きさを教えてください。', '80mm × 50mm、厚さ 1.6mm（4層）。', [['80'], ['50']], [SPEC]),
    ('言い換え', 'SN-200 で温度センサが LDO の熱で狂わないよう、どれくらい離して置いていますか？', 'LDO（U2）から 14mm（推奨は 10mm 以上）。', [['14']], [SPEC]),
    ('言い換え', 'SN-200 で RS-485 の終端抵抗を有効にするにはどうしますか？', 'ジャンパ JP2 をショートする（伝送路の両端の機器のみ）。', [['JP2']], [SPEC]),
    ('言い換え', '出荷検査で 3.3V の電圧がいくつならOKですか？', '3.25V〜3.35V（TP1）。', [['3.25'], ['3.35']], [QA]),
    ('言い換え', '出荷検査で NG になった基板はどうすればよいですか？', '赤色の不良タグを付けて隔離棚に置き、当日中に品質保証課へ不具合票で報告する。', [['タグ'], ['品質保証', '品証']], [QA]),
    ('言い換え', '測定間隔を 0 秒にするコマンドを送るとどうなりますか？', 'エラー応答（エラーコード 0xE3：パラメータが範囲外）になる。', [['E3']], [UART]),
    ('言い換え', '温度を読むコマンドの応答が 2534 だったら何℃ですか？', '25.34℃（0.01℃ 単位）。', [['25.34']], [UART]),
    ('言い換え', 'SN-200 の通信フレームのチェックサムの計算で、初期値はいくつですか？', '0xFFFF（CRC-16/CCITT、多項式 0x1021）。', [['FFFF']], [UART]),
    ('言い換え', 'アルミ電解コンデンサは、使う温度を 10℃ 下げると寿命はどうなりますか？', '2 倍になる（10℃2倍則）。', [['2倍', '2 倍', '二倍']], [CAP]),

    # ---- 複数の資料をまたぐ
    ('複数資料', 'SN-200 の温度センサの I2C アドレスはいくつで、そのためには ADD0 端子をどこにつなぎますか？', '0x49。ADD0 を VDD に接続する。', [['49'], ['VDD']], [SPEC, TS]),
    ('複数資料', 'SN-200 の LDO の損失は何 W で、SOT-89-5 の熱抵抗だと温度上昇は何℃になりますか？', '0.255W。θja 104℃/W で約 27℃ 上昇（周囲 70℃ で Tj 約 97℃）。', [['0.255'], ['27']], [SPEC, LDO, DR]),
    ('複数資料', '不具合 FR-2026-031 を受けて、出荷検査手順書は何版になり、何が追加されましたか？', 'Rev.1.3。ジャンパ JP2（終端抵抗）の設定を確認する手順が追加された。', [['1.3'], ['JP2']], [FR, QA]),
    ('複数資料', '温度試験で不合格になったのはどの温度・どの試料で、理由は何ですか？', '70℃ の試料 #2。温度センサ誤差 +0.62℃ が基準（±0.5℃）を超えた。', [['70'], ['0.62']], [CSV, QA]),
    ('複数資料', 'SN-200 の量産試作の時期と台数、目標原価は？', '2026 年 7 月に 50 台。目標原価は 1 台 4,800 円。', [['7月', '7 月'], ['50'], ['4800']], [DR]),
    ('複数資料', 'SN-200 の Q1 の代わりに使える部品と、その条件は？', 'HZ-N6040。VDSS 60V 以上・RDS(on) 15mΩ 以下であれば可。', [['N6040'], ['15']], [BOM]),
    ('複数資料', 'SN-200 の BOM の主要部品の合計金額はいくらですか？', '1,594 円（主要部品のみ）。', [['1594']], [BOM]),

    # ---- 資料どうしの食い違い
    ('食い違い', 'SN-200 の LDO の出力コンデンサ C12 の容量はいくつですか？', '設計仕様書（Rev.2.1）は 22μF、BOM（版C）は 10μF で食い違っている。BOM では納期の都合で 22μF から 10μF に変更されている。',
     [['22'], ['10']], [SPEC, BOM]),

    # ---- 資料にない
    ('資料にない', 'HZ-N6030 のゲート抵抗 Rg はいくつですか？', '資料に記載なし（「判断できません」と答えれば正解）。', [], []),
    ('資料にない', 'SN-200 の防水・防塵の等級（IP 等級）は？', '資料に記載なし（「判断できません」と答えれば正解）。', [], []),
    ('資料にない', 'HZ-TS20 で湿度を測ったときの精度は？', '資料に記載なし（HZ-TS20 は温度センサ。「判断できません」と答えれば正解）。', [], []),
    ('資料にない', 'What is the MTBF of the SN-200?', 'Not in the documents (answering "cannot be determined" is correct).', [], []),

    # ---- Excel の表（空のセル・結合したセル・日付・％・通貨、分割した後半の行）。番号を変えないよう最後に追加
    ('Excelの表', '代替品 GR-1210-106-50 の DC 24V での静電容量はいくつですか？', '4.7μF（正規品は 5.8μF）。', [['4.7']], [EV]),
    ('Excelの表', '代替品 GR-1210-106-50 の ESR（500kHz）はいくつですか？', '未測定（測定器の手配待ち）。正規品は 3.1mΩ。', [['未測定']], [EV]),
    ('Excelの表', '正規品 CM32X7R106K50 の DC 24V での容量変化率は？', '-42.6%（0V 比）。', [['42.6']], [EV]),
    ('Excelの表', 'コンデンサの受入評価で、代替品を評価した日はいつですか？', '2026 年 9 月 12 日（正規品は 9 月 10 日）。', [['2026-09-12', '9月12日', '9 月 12 日']], [EV]),
    ('Excelの表', 'C3, C4 の代替品の単価と納期は？', '¥24（1,000 個購入時）、納期 3 週。', [['24'], ['3週', '3 週']], [EV]),
    ('Excelの表', '代替品 GR-1210-106-50 を 24V 系で使うときの条件は何ですか？', '3 個並列にすること（判定は条件付き合格）。', [['3個', '3 個', '3つ', '三つ']], [EV]),
    ('Excelの表', 'SN-200 の BOM で、ターミナルブロック 3P のメーカーと単価は？', 'コハク工業、66 円。', [['コハク'], ['66']], [BOM]),
    ('Excelの表', 'SN-200 の BOM で、終端抵抗 R10 の型番は？', 'RC16-121J（120Ω）。', [['RC16-121J']], [BOM]),
    ('資料にない', '代替品 GR-1210-106-50 の 125℃ での容量変化率は？', '表に値がない（空欄。正規品は -12.8%）。「判断できません」と答えれば正解。', [], []),
]


def norm(s):
    return unicodedata.normalize('NFKC', s).replace(',', '').lower()


def main():
    rag = sys.argv[1] if len(sys.argv) > 1 else next(iter(sorted(p for p in glob.glob(os.path.join(ROOT, 'dist', 'cli-*', 'RAG-CLI', 'rag*')) if os.path.basename(p) in ('rag', 'rag.exe'))), None)
    if not rag: sys.exit('rag が見つかりません。先に python scripts/build.py cli-windows を実行してください')
    r = subprocess.run([rag, 'text', SAMPLES, '--json', '-q'], capture_output=True)
    if r.returncode: sys.exit(r.stderr.decode('utf-8', 'replace'))
    docs = json.loads(r.stdout.decode('utf-8'))
    names = {d['name'] for d in docs}
    missing = sorted(set(os.listdir(SAMPLES)) - names)
    if missing: sys.exit(f'読み取れなかった資料があります: {missing}\n{r.stderr.decode("utf-8", "replace")}')
    text = {d['name']: norm(d['text']) for d in docs}
    errors = []
    for i, (_, q, _, must, src) in enumerate(Q, 1):
        for s in src:
            if s not in names: errors.append(f'Q{i}: 資料 {s} がありません')
        body = ' '.join(text.get(s, '') for s in src)
        for group in must:
            if not any(norm(w) in body for w in group): errors.append(f'Q{i}: 「{" / ".join(group)}」が根拠の資料にありません（{q}）')
    if errors: sys.exit('\n'.join(errors))
    out = {
        'app': 'rag-eval', 'version': 1,
        'title': '技術文書（架空のセンサ基板 SN-200 と部品のデータシート・設計書・BOM・受入評価など 14 件。PDF/Word/Excel/PowerPoint/CSV/テキスト/Markdown/HTML）',
        'license': 'このリポジトリのために作った架空の資料です（実在の会社・製品とは関係ありません）。MIT License。',
        'docs': docs,
        'questions': [{'id': i, 'type': t, 'question': q, 'expected': e, 'must': m, 'sources': s} for i, (t, q, e, m, s) in enumerate(Q, 1)],
    }
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1); fp.write('\n')
    from collections import Counter
    print(f'{os.path.relpath(OUT, ROOT)}: 資料 {len(docs)} 件・質問 {len(Q)} 問', dict(Counter(t for t, *_ in Q)))


if __name__ == '__main__':
    main()

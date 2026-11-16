# -*- coding: utf-8 -*-
"""技術文書のテスト用資料（src/sample-tech/）を作る。

架空の会社「ホシゾラ電子（Hoshizora Electronics）」のセンサノード基板 SN-200 と、その部品のデータシート・
設計書・BOM・試験結果など。日本語が主で一部英語。形式は PDF / Word / Excel / PowerPoint / CSV / テキスト / Markdown / HTML。
実在の製品・会社とは関係ない（実在のデータシートは著作物なので使わない）。

  python -m venv .venv && .venv\\Scripts\\pip install python-docx openpyxl reportlab python-pptx
  .venv\\Scripts\\python tests\\make_tech_samples.py

PDF は2種類の作り方を混ぜている（どちらも実在のデータシートでよくある形）：
  ・日本語標準フォント（HeiseiKakuGo-W5、埋め込みなし）… 読み取りに CMap（UniJIS-UCS2-H）が必要
  ・TrueType 埋め込み（BIZ UDゴシック。Windows に標準で入っている。SIL OFL）… ToUnicode で読める
  ・英語の標準フォント（Helvetica）
同じ内容を何度作っても同じファイルになるよう、作成日時などは固定している。
"""
import csv, datetime, os, sys

from docx import Document
from docx.shared import Pt
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Pt as PPt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'src', 'sample-tech')
FIXED = datetime.datetime(2026, 11, 1, 9, 0, 0)

pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
BIZ = r'C:\Windows\Fonts\BIZ-UDGothicR.ttc'
if os.path.exists(BIZ):
    pdfmetrics.registerFont(TTFont('BIZUD', BIZ, subfontIndex=0))
    TTF = 'BIZUD'
else:
    print('BIZ UDゴシックが見つからないため、MOSFET のデータシートも HeiseiKakuGo-W5 で作ります', file=sys.stderr)
    TTF = 'HeiseiKakuGo-W5'


# ---------------------------------------------------------------- PDF の共通部品
def styles(font):
    return {
        'title': ParagraphStyle('t', fontName=font, fontSize=17, leading=22, spaceAfter=4),
        'sub': ParagraphStyle('s', fontName=font, fontSize=10, leading=14, textColor=colors.HexColor('#444444'), spaceAfter=10),
        'h1': ParagraphStyle('h1', fontName=font, fontSize=12.5, leading=17, spaceBefore=10, spaceAfter=5),
        'body': ParagraphStyle('b', fontName=font, fontSize=9, leading=13.5, spaceAfter=4),
        'cell': ParagraphStyle('c', fontName=font, fontSize=8, leading=10.5),
        'note': ParagraphStyle('n', fontName=font, fontSize=7.5, leading=10, textColor=colors.HexColor('#555555'), spaceAfter=4),
    }


def table(rows, widths, font, head=1):
    t = Table(rows, colWidths=[w * mm for w in widths], repeatRows=head)
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), font, 8),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#888888')),
        ('BACKGROUND', (0, 0), (-1, head - 1), colors.HexColor('#e6ecf3')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


def build_pdf(name, story, font, footer, title, author='Hoshizora Electronics'):
    path = os.path.join(OUT, name)

    def deco(c, d):
        c.saveState()
        c.setFont(font, 7.5)
        c.setFillColor(colors.HexColor('#666666'))
        c.drawString(18 * mm, 10 * mm, footer)
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, f'{d.page}')
        c.restoreState()

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=title, author=author, creator='make_tech_samples.py', invariant=1)
    doc.build(story, onFirstPage=deco, onLaterPages=deco)


# ---------------------------------------------------------------- 1. LDO データシート（日本語・CID フォント）
def ldo_pdf():
    f = 'HeiseiKakuGo-W5'; S = styles(f)
    st = [
        Paragraph('HZ-LDO33A', S['title']),
        Paragraph('低損失 3.3V 出力 リニアレギュレータ（500mA）　データシート Rev.1.1', S['sub']),
        Paragraph('概要', S['h1']),
        Paragraph('HZ-LDO33A は、最大 500mA を出力できる低損失（低ドロップアウト）の 3.3V 固定出力リニアレギュレータです。'
                  '無負荷時の消費電流が 35μA（標準）と小さく、電池駆動や常時通電のセンサ機器に適しています。'
                  '出力コンデンサにはセラミックコンデンサ（2.2μF 以上）を使用できます。過電流保護と過熱保護を内蔵しています。', S['body']),
        Paragraph('特長', S['h1']),
        Paragraph('・入力電圧範囲：3.6V〜16V　・出力電圧精度：±1%（Ta=25℃）　・ドロップアウト電圧：250mV（標準、IOUT=300mA）<br/>'
                  '・無負荷時消費電流：35μA（標準）　・スタンバイ電流：0.1μA（標準、EN=0V）<br/>'
                  '・パッケージ：SOT-89-5、DFN-6（2mm×2mm）　・動作周囲温度：-40℃〜105℃', S['body']),
        Paragraph('用途', S['h1']),
        Paragraph('産業用センサノード、スマートメータ、電池駆動機器、マイコンの電源。', S['body']),
        Paragraph('絶対最大定格', S['h1']),
        Paragraph('絶対最大定格を超える条件では、一瞬でも IC が破壊するおそれがあります。（Ta=25℃）', S['note']),
        table([['項目', '記号', '定格', '単位'],
               ['入力電圧', 'VIN', '-0.3〜18', 'V'],
               ['EN 端子電圧', 'VEN', '-0.3〜VIN+0.3（最大 18）', 'V'],
               ['出力電圧', 'VOUT', '-0.3〜6.0', 'V'],
               ['許容損失（SOT-89-5）', 'Pd', '1.2', 'W'],
               ['許容損失（DFN-6）', 'Pd', '1.9', 'W'],
               ['接合部温度', 'Tj', '150', '℃'],
               ['保存温度', 'Tstg', '-55〜150', '℃']], [62, 22, 60, 20], f),
        Paragraph('推奨動作条件', S['h1']),
        table([['項目', '記号', '最小', '最大', '単位'],
               ['入力電圧', 'VIN', '3.6', '16', 'V'],
               ['出力電流', 'IOUT', '0', '500', 'mA'],
               ['動作周囲温度', 'Ta', '-40', '105', '℃'],
               ['出力コンデンサ容量', 'COUT', '2.2', '－', 'μF'],
               ['出力コンデンサの ESR', 'ESR', '0.001', '0.5', 'Ω']], [62, 22, 25, 25, 20], f),
        PageBreak(),
        Paragraph('電気的特性', S['h1']),
        Paragraph('特に指定のない限り Ta=25℃、VIN=5.0V、IOUT=1mA、CIN=COUT=2.2μF（セラミック）。', S['note']),
        table([['項目', '記号', '条件', '最小', '標準', '最大', '単位'],
               ['出力電圧', 'VOUT', 'IOUT=1mA', '3.267', '3.300', '3.333', 'V'],
               ['入力安定度', 'ΔVOUT/ΔVIN', 'VIN=4.0V〜16V', '－', '0.02', '0.1', '%/V'],
               ['負荷安定度', 'ΔVOUT', 'IOUT=1mA〜500mA', '－', '10', '30', 'mV'],
               ['ドロップアウト電圧', 'VDO', 'IOUT=300mA', '－', '250', '400', 'mV'],
               ['ドロップアウト電圧', 'VDO', 'IOUT=500mA', '－', '420', '650', 'mV'],
               ['無負荷時消費電流', 'IQ', 'IOUT=0mA', '－', '35', '60', 'μA'],
               ['スタンバイ電流', 'ISTB', 'EN=0V', '－', '0.1', '1.0', 'μA'],
               ['電流制限', 'ILIM', 'VOUT=3.0V', '550', '800', '－', 'mA'],
               ['短絡電流', 'ISC', 'VOUT=0V', '－', '150', '－', 'mA'],
               ['リップル除去率', 'PSRR', 'f=1kHz、IOUT=50mA', '－', '70', '－', 'dB'],
               ['出力雑音電圧', 'VN', 'f=10Hz〜100kHz', '－', '45', '－', 'μVrms'],
               ['EN 端子 H しきい値', 'VENH', '', '1.2', '－', '－', 'V'],
               ['EN 端子 L しきい値', 'VENL', '', '－', '－', '0.4', 'V'],
               ['過熱保護 検出温度', 'TSD', 'Tj', '－', '160', '－', '℃'],
               ['過熱保護 ヒステリシス', 'TSDH', 'Tj', '－', '20', '－', '℃']], [34, 22, 36, 16, 16, 16, 16], f),
        Paragraph('熱特性', S['h1']),
        table([['パッケージ', '熱抵抗 θja（接合部−周囲）', '条件'],
               ['SOT-89-5', '104 ℃/W', 'JEDEC 4層基板'],
               ['DFN-6（2mm×2mm）', '65 ℃/W', 'JEDEC 4層基板、裏面パッドをはんだ付け']], [40, 50, 74], f),
        Paragraph('損失の計算：Pd =（VIN − VOUT）× IOUT。例えば VIN=5.0V、IOUT=150mA のとき Pd = 1.7V × 0.15A = 0.255W となり、'
                  'SOT-89-5 では接合部温度の上昇は約 27℃ です（θja=104℃/W）。周囲温度 70℃ でも Tj は約 97℃ で、過熱保護（160℃）には達しません。', S['body']),
        Paragraph('使用上の注意', S['h1']),
        Paragraph('・出力コンデンサは IC の出力端子の近く（5mm 以内）に配置してください。2.2μF 未満では発振するおそれがあります。<br/>'
                  '・入力側にも 1μF 以上のコンデンサを配置してください。入力配線が 10cm を超える場合は 2.2μF 以上を推奨します。<br/>'
                  '・EN 端子を使わない場合は VIN に接続してください（開放禁止）。', S['body']),
        Paragraph('型番の構成', S['h1']),
        table([['型番', 'パッケージ', '梱包', '最小発注単位'],
               ['HZ-LDO33A-S5', 'SOT-89-5', 'テープ＆リール', '3,000 個'],
               ['HZ-LDO33A-D6', 'DFN-6（2mm×2mm）', 'テープ＆リール', '5,000 個']], [45, 45, 40, 34], f),
        Paragraph('改版履歴', S['h1']),
        table([['版', '日付', '内容'],
               ['Rev.1.0', '2024-03-15', '初版'],
               ['Rev.1.1', '2025-06-02', 'ドロップアウト電圧（IOUT=500mA）の最大値を 600mV から 650mV に変更。DFN-6 の熱抵抗を追記。']], [20, 28, 116], f),
    ]
    build_pdf('HZ-LDO33A_データシート.pdf', st, f, 'ホシゾラ電子株式会社　HZ-LDO33A データシート Rev.1.1', 'HZ-LDO33A データシート')


# ---------------------------------------------------------------- 2. 温度センサ データシート（英語・Helvetica）
def ts_pdf():
    f = 'Helvetica'; S = styles(f)
    S['title'].fontName = 'Helvetica-Bold'; S['h1'].fontName = 'Helvetica-Bold'
    st = [
        Paragraph('HZ-TS20', S['title']),
        Paragraph('Digital Temperature Sensor with I2C Interface, +/-0.2 &deg;C Accuracy - Datasheet Rev. B', S['sub']),
        Paragraph('1 Features', S['h1']),
        Paragraph('- Accuracy: +/-0.2 &deg;C (max) from -10 &deg;C to +85 &deg;C; +/-0.5 &deg;C (max) from -40 &deg;C to +125 &deg;C<br/>'
                  '- 16-bit resolution: 0.0078125 &deg;C (1 LSB)<br/>'
                  '- Supply voltage: 1.7 V to 5.5 V<br/>'
                  '- Low power: 3.5 &micro;A average at 1 Hz conversion rate; 0.15 &micro;A in shutdown<br/>'
                  '- I2C / SMBus compatible interface, up to 1 MHz (Fast-mode Plus)<br/>'
                  '- Four selectable addresses (ADD0 pin)<br/>'
                  '- Programmable ALERT output (open-drain)<br/>'
                  '- Packages: SOT-563 (1.6 mm x 1.6 mm), WSON-6 (2 mm x 2 mm)', S['body']),
        Paragraph('2 Applications', S['h1']),
        Paragraph('Industrial sensor nodes, cold-chain loggers, battery thermal monitoring, PC and server thermal management.', S['body']),
        Paragraph('3 Description', S['h1']),
        Paragraph('The HZ-TS20 is a digital temperature sensor that converts the die temperature into a 16-bit two\'s-complement value. '
                  'Each conversion takes 15.5 ms (typical). Between conversions the device enters a low-power standby state. '
                  'Place the sensor away from heat sources such as linear regulators; a distance of at least 10 mm is recommended '
                  'to keep the self-heating error from nearby components below 0.1 &deg;C.', S['body']),
        Paragraph('4 Electrical Characteristics', S['h1']),
        Paragraph('TA = 25 &deg;C, VDD = 3.3 V, unless otherwise noted.', S['note']),
        table([['Parameter', 'Test conditions', 'Min', 'Typ', 'Max', 'Unit'],
               ['Temperature accuracy', '-10 to +85 C', '-0.2', '+/-0.1', '0.2', 'C'],
               ['Temperature accuracy', '-40 to +125 C', '-0.5', '+/-0.25', '0.5', 'C'],
               ['Resolution', '', '', '0.0078125', '', 'C'],
               ['Supply voltage (VDD)', '', '1.7', '3.3', '5.5', 'V'],
               ['Average supply current', '1 Hz conversion', '', '3.5', '5.0', 'uA'],
               ['Active current', 'During conversion', '', '135', '200', 'uA'],
               ['Shutdown current', '', '', '0.15', '0.5', 'uA'],
               ['Conversion time', '', '', '15.5', '17.5', 'ms'],
               ['I2C clock frequency', '', '0.001', '', '1000', 'kHz'],
               ['ALERT output low voltage', 'IOL = 3 mA', '', '', '0.4', 'V']], [44, 38, 18, 22, 18, 14], f),
        Paragraph('5 I2C Address Selection', S['h1']),
        table([['ADD0 pin connection', '7-bit address'],
               ['GND', '0x48'], ['VDD', '0x49'], ['SDA', '0x4A'], ['SCL', '0x4B']], [60, 40], f),
        PageBreak(),
        Paragraph('6 Register Map', S['h1']),
        table([['Address', 'Name', 'Reset value', 'Description'],
               ['0x00', 'TEMP_RESULT', '0x8000', 'Latest conversion result (16-bit, two\'s complement)'],
               ['0x01', 'CONFIG', '0x0220', 'Conversion mode, averaging, alert mode'],
               ['0x02', 'T_HIGH', '0x6000', 'High limit (192 C)'],
               ['0x03', 'T_LOW', '0x8000', 'Low limit (-256 C)'],
               ['0x0F', 'DEVICE_ID', '0x2012', 'Device identification']], [20, 30, 25, 85], f),
        Paragraph('7 Temperature Data Format', S['h1']),
        Paragraph('The temperature in degrees Celsius is TEMP_RESULT x 0.0078125. For example, 0x0C80 (3200) corresponds to 25.0 &deg;C, '
                  'and 0xFF80 (-128) corresponds to -1.0 &deg;C. The value 0x8000 is returned before the first conversion completes.', S['body']),
        Paragraph('8 Configuration Register (0x01)', S['h1']),
        table([['Bits', 'Field', 'Description'],
               ['11:10', 'MOD', '00 = continuous conversion, 01 = shutdown, 11 = one-shot'],
               ['9:7', 'CONV', 'Conversion cycle: 000 = 15.5 ms ... 100 = 1 s (default) ... 111 = 16 s'],
               ['6:5', 'AVG', 'Averaging: 00 = none, 01 = 8 (default), 10 = 32, 11 = 64'],
               ['4', 'T/nA', '0 = alert mode, 1 = therm (comparator) mode']], [20, 25, 115], f),
        Paragraph('9 Layout Guidelines', S['h1']),
        Paragraph('Place a 0.1 &micro;F decoupling capacitor as close as possible to the VDD pin. Connect the exposed pad (WSON-6 only) to GND. '
                  'Use 10 k&Omega; pull-up resistors on SDA, SCL and ALERT when the bus capacitance is below 100 pF.', S['body']),
        Paragraph('10 Ordering Information', S['h1']),
        table([['Part number', 'Package', 'Packing', 'MOQ'],
               ['HZ-TS20-DRL', 'SOT-563', 'Tape and reel', '4,000'],
               ['HZ-TS20-DSG', 'WSON-6', 'Tape and reel', '3,000']], [40, 35, 40, 30], f),
        Paragraph('11 Revision History', S['h1']),
        Paragraph('Rev. A (2025-01-20): Initial release. Rev. B (2025-11-04): Added WSON-6 package; changed typical active current from 150 uA to 135 uA.', S['body']),
    ]
    build_pdf('HZ-TS20_Datasheet.pdf', st, f, 'Hoshizora Electronics  HZ-TS20 Datasheet Rev. B', 'HZ-TS20 Datasheet')


# ---------------------------------------------------------------- 3. MOSFET データシート（日英併記・TrueType 埋め込み）
def mosfet_pdf():
    f = TTF; S = styles(f)
    st = [
        Paragraph('HZ-N6030', S['title']),
        Paragraph('Nチャネル パワーMOSFET　60V / 30A　（N-channel Power MOSFET）　データシート Rev.2.0', S['sub']),
        Paragraph('特長 Features', S['h1']),
        Paragraph('・低オン抵抗：RDS(on) = 9.5mΩ（標準、VGS=10V）<br/>・4.5V ゲート駆動に対応（ロジックレベル）<br/>'
                  '・アバランシェ耐量保証：EAS = 45mJ<br/>・パッケージ：TO-252（DPAK）、鉛フリー・RoHS 対応', S['body']),
        Paragraph('用途 Applications', S['h1']),
        Paragraph('DC-DC コンバータ、モータ駆動、電源の逆接続保護、負荷スイッチ。', S['body']),
        Paragraph('絶対最大定格 Absolute Maximum Ratings（Tc=25℃）', S['h1']),
        table([['項目 Parameter', '記号', '定格', '単位'],
               ['ドレイン・ソース間電圧', 'VDSS', '60', 'V'],
               ['ゲート・ソース間電圧', 'VGSS', '±20', 'V'],
               ['ドレイン電流（連続）Tc=25℃', 'ID', '30', 'A'],
               ['ドレイン電流（連続）Tc=100℃', 'ID', '21', 'A'],
               ['ドレイン電流（パルス）', 'IDP', '120', 'A'],
               ['アバランシェエネルギー（単発）', 'EAS', '45', 'mJ'],
               ['許容損失 Tc=25℃', 'PD', '50', 'W'],
               ['チャネル温度', 'Tch', '175', '℃'],
               ['保存温度', 'Tstg', '-55〜175', '℃']], [70, 22, 40, 20], f),
        Paragraph('熱抵抗 Thermal Resistance', S['h1']),
        table([['項目', '記号', '最大', '単位'],
               ['チャネル−ケース間', 'Rθjc', '2.5', '℃/W'],
               ['チャネル−周囲間（基板実装）', 'Rθja', '50', '℃/W']], [70, 22, 40, 20], f),
        PageBreak(),
        Paragraph('電気的特性 Electrical Characteristics（Tc=25℃）', S['h1']),
        table([['項目', '記号', '条件', '最小', '標準', '最大', '単位'],
               ['ドレイン・ソース間降伏電圧', 'V(BR)DSS', 'ID=250μA, VGS=0V', '60', '—', '—', 'V'],
               ['ゲートしきい値電圧', 'VGS(th)', 'VDS=VGS, ID=250μA', '1.2', '1.8', '2.5', 'V'],
               ['ドレイン遮断電流', 'IDSS', 'VDS=60V, VGS=0V', '—', '—', '1', 'μA'],
               ['ゲート漏れ電流', 'IGSS', 'VGS=±20V', '—', '—', '±100', 'nA'],
               ['オン抵抗', 'RDS(on)', 'VGS=10V, ID=15A', '—', '9.5', '12', 'mΩ'],
               ['オン抵抗', 'RDS(on)', 'VGS=4.5V, ID=10A', '—', '14', '19', 'mΩ'],
               ['入力容量', 'Ciss', 'VDS=30V, f=1MHz', '—', '1050', '—', 'pF'],
               ['出力容量', 'Coss', 'VDS=30V, f=1MHz', '—', '210', '—', 'pF'],
               ['総ゲート電荷量', 'Qg', 'VGS=10V, VDS=30V, ID=15A', '—', '18', '26', 'nC'],
               ['ターンオン遅延時間', 'td(on)', 'VDD=30V, ID=15A', '—', '9', '—', 'ns'],
               ['ターンオフ遅延時間', 'td(off)', 'VDD=30V, ID=15A', '—', '22', '—', 'ns'],
               ['ダイオード順電圧', 'VSD', 'IS=15A, VGS=0V', '—', '0.88', '1.2', 'V'],
               ['逆回復時間', 'trr', 'IS=15A, di/dt=100A/μs', '—', '28', '—', 'ns']], [38, 18, 46, 13, 13, 13, 13], f),
        Paragraph('注記 Notes', S['h1']),
        Paragraph('1. パルス幅 300μs 以下、デューティ 2% 以下で測定。<br/>2. RDS(on) は温度とともに増加し、Tch=125℃ では 25℃ のときの約 1.7 倍になります。<br/>'
                  '3. Rθja は 40mm×40mm、銅箔厚 70μm の FR-4 基板に実装した場合の値です。', S['body']),
        Paragraph('改版履歴 Revision History', S['h1']),
        table([['版', '日付', '内容'],
               ['Rev.1.0', '2023-09-01', '初版'],
               ['Rev.2.0', '2025-02-10', '製造拠点の変更に伴い Qg の最大値を 30nC から 26nC に変更。EAS を 40mJ から 45mJ に変更。']], [20, 28, 104], f),
    ]
    build_pdf('HZ-N6030_MOSFET_データシート.pdf', st, f, 'ホシゾラ電子株式会社 / Hoshizora Electronics　HZ-N6030 Rev.2.0', 'HZ-N6030 データシート')


# ---------------------------------------------------------------- 4. アプリケーションノート（英語の文章）
def an_pdf():
    f = 'Helvetica'; S = styles(f)
    S['title'].fontName = 'Helvetica-Bold'; S['h1'].fontName = 'Helvetica-Bold'
    st = [
        Paragraph('AN-012: Input Capacitor Selection for the HZ-BK2405 Buck Converter', S['title']),
        Paragraph('Application Note - Hoshizora Electronics - 2026-04', S['sub']),
        Paragraph('1 Introduction', S['h1']),
        Paragraph('The HZ-BK2405 is a synchronous buck converter with an input range of 4.5 V to 28 V, an output current of up to 3 A '
                  'and a fixed switching frequency of 500 kHz. Because a buck converter draws pulsed current from its input, the input capacitor '
                  'must handle a large RMS ripple current. An undersized input capacitor causes excessive input voltage ripple, EMI problems '
                  'and, in the worst case, overheating of the capacitor.', S['body']),
        Paragraph('2 Input RMS Ripple Current', S['h1']),
        Paragraph('The RMS current in the input capacitor is approximately I_RMS = I_OUT x sqrt(D x (1 - D)), where D = V_OUT / V_IN is the duty cycle. '
                  'The ripple current is largest at D = 0.5, where I_RMS = I_OUT / 2.', S['body']),
        Paragraph('Example: V_IN = 12 V, V_OUT = 5.0 V, I_OUT = 2 A gives D = 0.417 and I_RMS = 2 x sqrt(0.417 x 0.583) = 0.99 A. '
                  'Choose capacitors whose combined ripple current rating exceeds 1.0 A at the switching frequency.', S['body']),
        Paragraph('3 Recommended Capacitors', S['h1']),
        Paragraph('We recommend two 10 uF, 50 V, X7R ceramic capacitors in parallel (1210 size) placed within 3 mm of the VIN pin. '
                  'Do not use Y5V or Z5U dielectrics: their capacitance drops by more than 80 % under DC bias and at temperature extremes. '
                  'Note that the effective capacitance of X7R capacitors also decreases with DC bias: a 10 uF, 50 V, 1210 capacitor retains only '
                  'about 60 % of its nominal value at 24 V.', S['body']),
        Paragraph('4 Input Filter Damping', S['h1']),
        Paragraph('When the converter is supplied through a long cable (more than 1 m), the cable inductance and the low-ESR ceramic capacitors form '
                  'a resonant circuit. A hot-plug event can then produce an input voltage spike of up to twice the supply voltage. To damp the '
                  'resonance, add a 47 uF aluminium electrolytic capacitor with an ESR of about 0.3 ohm in parallel with the ceramic capacitors. '
                  'For 24 V systems, use a TVS diode with a standoff voltage of 26 V or higher at the input connector.', S['body']),
        Paragraph('5 Layout Checklist', S['h1']),
        Paragraph('- Place the ceramic input capacitors within 3 mm of the VIN and PGND pins.<br/>'
                  '- Keep the loop formed by the input capacitor, the high-side switch and PGND as small as possible.<br/>'
                  '- Use at least four thermal vias under the exposed pad.<br/>'
                  '- Keep the feedback trace away from the switch node (SW).', S['body']),
        Paragraph('6 Summary', S['h1']),
        Paragraph('Use at least 20 uF of X7R ceramic capacitance rated for 50 V, check the RMS ripple current, and add a damped electrolytic capacitor '
                  'when long input cables are used.', S['body']),
    ]
    build_pdf('AN-012_Input_Capacitor_Selection.pdf', st, f, 'Hoshizora Electronics  AN-012 Rev.1', 'AN-012')


# ---------------------------------------------------------------- Word
def set_jp_font(doc):
    for s in ['Normal', 'Heading 1', 'Heading 2', 'Title']:
        st = doc.styles[s]; st.font.name = 'Yu Gothic'
        rpr = st.element.get_or_add_rPr(); rf = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts')
        if rf is None: rf = rpr.makeelement('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts', {}); rpr.append(rf)
        rf.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia', 'Yu Gothic')


def add_table(doc, rows):
    t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = 'Table Grid'
    for i, r in enumerate(rows):
        for j, v in enumerate(r): t.cell(i, j).text = v
    return t


def save_docx(doc, name, title):
    cp = doc.core_properties; cp.title = title; cp.author = 'ホシゾラ電子'; cp.created = FIXED; cp.modified = FIXED; cp.last_modified_by = 'ホシゾラ電子'
    doc.save(os.path.join(OUT, name))


def spec_docx():
    d = Document(); set_jp_font(d)
    d.add_heading('SN-200 ハードウェア設計仕様書', 0)
    d.add_paragraph('文書番号：HZ-SN200-HW-001　版：Rev.2.1　発行日：2026-08-20　作成：第二設計部 佐藤')
    d.add_heading('1. 概要', 1)
    d.add_paragraph('SN-200 は工場設備の温度を監視するセンサノード基板である。温度センサの値を RS-485 で上位の収集装置に送る。'
                    '設置場所は制御盤の中を想定し、DC 24V または DC 12V の盤内電源から給電する。')
    d.add_heading('2. 主な仕様', 1)
    add_table(d, [['項目', '仕様'],
                  ['入力電圧', 'DC 9V〜24V（逆接続保護あり）'],
                  ['消費電流', '平均 18mA 以下（DC 12V 入力、送信間隔 60 秒）'],
                  ['動作温度範囲', '-20℃〜70℃'],
                  ['保存温度範囲', '-40℃〜85℃'],
                  ['通信', 'RS-485（半二重）、最大 115200bps、最大 32 台をマルチドロップ接続'],
                  ['温度測定範囲', '-20℃〜70℃（基板上の温度センサ）'],
                  ['温度測定精度', '±0.5℃（-20℃〜70℃）'],
                  ['外形寸法', '80mm × 50mm、厚さ 1.6mm（4層基板）']])
    d.add_heading('3. 電源構成', 1)
    d.add_paragraph('入力（CN1）から逆接続保護用の MOSFET（Q1：HZ-N6030）を通し、降圧 DC-DC コンバータ（U3：HZ-BK2405）で 5.0V を作る。'
                    '5.0V から LDO（U2：HZ-LDO33A）で 3.3V を作り、マイコン・温度センサ・RS-485 トランシーバに供給する。'
                    '3.3V 系の最大負荷電流は 150mA と見積もった。このとき LDO の損失は (5.0V − 3.3V) × 0.15A = 0.255W である。')
    d.add_paragraph('LDO の出力コンデンサ C12 は 22μF（セラミック、X7R、10V）とする。データシートの最小値 2.2μF に対し、'
                    'マイコンの起動時の突入電流による電圧降下を抑えるために大きめの値とした。')
    d.add_paragraph('DC-DC コンバータの入力コンデンサは、アプリケーションノート AN-012 に従い 10μF / 50V / X7R を 2 個並列とする（C3、C4）。'
                    'さらに盤内の長い電源配線を考慮し、47μF のアルミ電解コンデンサ（C5）を追加する。')
    d.add_heading('4. 主要部品', 1)
    add_table(d, [['部品番号', '機能', '型番', '備考'],
                  ['U1', 'マイコン', 'HZ-M4F128', 'Cortex-M4、Flash 128KB、RAM 32KB'],
                  ['U2', '3.3V LDO', 'HZ-LDO33A-S5', 'SOT-89-5'],
                  ['U3', '降圧 DC-DC', 'HZ-BK2405', '500kHz、最大 3A'],
                  ['U4', '温度センサ', 'HZ-TS20-DRL', 'I2C アドレス 0x49（ADD0 を VDD に接続）'],
                  ['U5', 'RS-485 トランシーバ', 'HZ-RS485H', '3.3V 動作、ESD ±15kV'],
                  ['Q1', '逆接続保護', 'HZ-N6030', 'Nch MOSFET、ローサイドに配置']])
    d.add_heading('5. 温度センサの配置', 1)
    d.add_paragraph('温度センサ U4 は、LDO（U2）など発熱する部品から 10mm 以上離して配置する（HZ-TS20 データシートの推奨による）。'
                    'SN-200 では U2 から 14mm の位置に配置した。基板の縁にスリットを設け、基板の熱が伝わりにくくしている。')
    d.add_heading('6. 通信', 1)
    d.add_paragraph('RS-485 の終端抵抗 120Ω（R10）はジャンパ JP2 で接続・切り離しを切り替える。伝送路の両端の機器のみ JP2 をショートする。'
                    '既定の通信速度は 115200bps、データ形式は 8N1 とする。コマンドの詳細は「UART コマンド仕様」を参照。')
    d.add_heading('7. コネクタ', 1)
    add_table(d, [['コネクタ', '用途', 'ピン配置'],
                  ['CN1', '電源入力', '1: +V（9〜24V）、2: GND'],
                  ['CN2', 'RS-485', '1: A（+）、2: B（−）、3: GND'],
                  ['CN3', 'デバッグ（SWD）', '1: 3.3V、2: SWDIO、3: SWCLK、4: GND、5: NRST']])
    d.add_heading('8. 改版履歴', 1)
    add_table(d, [['版', '日付', '内容'],
                  ['Rev.1.0', '2026-04-10', '初版'],
                  ['Rev.2.0', '2026-06-20', 'DR2 の指摘を反映（TVS ダイオード D5 の追加、温度センサの配置変更）'],
                  ['Rev.2.1', '2026-08-20', '消費電流の目標を 20mA から 18mA に変更']])
    save_docx(d, 'SN-200_ハードウェア設計仕様書.docx', 'SN-200 ハードウェア設計仕様書')


def inspect_docx():
    d = Document(); set_jp_font(d)
    d.add_heading('SN-200 出荷検査手順書', 0)
    d.add_paragraph('文書番号：HZ-SN200-QA-003　版：Rev.1.3　発行日：2026-10-01　品質保証課')
    d.add_heading('1. 目的', 1)
    d.add_paragraph('SN-200 の出荷前に、全数に対して電気的な機能を確認する手順を定める。')
    d.add_heading('2. 使用機材', 1)
    d.add_paragraph('直流安定化電源（12V 設定、電流制限 200mA）、デジタルマルチメータ、RS-485 ループバック治具（JIG-485-02）、'
                    '基準温度計（校正済み、精度 ±0.1℃）、検査用 PC（検査ソフト SN-TEST v1.4）')
    d.add_heading('3. 手順', 1)
    for s in ['外観を確認する（はんだブリッジ、部品の欠品・向き）。',
              'ジャンパ JP2（終端抵抗）の設定が出荷指示書のとおりか確認する。指示がない場合はオープン（終端なし）とする。',
              'CN1 に 12V を加え、入力電流を測定する（待機時）。',
              '3.3V と 5V のテストポイント（TP1、TP2）の電圧を測定する。',
              '検査ソフトで RS-485 ループバック試験を行う（115200bps、1000 フレーム）。',
              '温度センサの読み値を基準温度計と比較する（室温、5 分以上なじませてから）。',
              '結果を検査記録に入力し、合格品に検査済みシールを貼る。']:
        d.add_paragraph(s, style='List Number')
    d.add_heading('4. 判定基準', 1)
    add_table(d, [['検査項目', '判定基準'],
                  ['3.3V 出力（TP1）', '3.25V〜3.35V'],
                  ['5V 出力（TP2）', '4.85V〜5.15V'],
                  ['待機時の入力電流（12V 入力）', '25mA 以下'],
                  ['RS-485 ループバック', '1000 フレームでエラー 0'],
                  ['温度センサの誤差', '基準温度計との差が ±0.5℃ 以内']])
    d.add_heading('5. 不合格時の処置', 1)
    d.add_paragraph('不合格品には赤色の不良タグを付けて隔離棚に置き、当日中に品質保証課へ不具合票で報告する。再検査は修理後に全項目を行う。')
    d.add_heading('6. 改版履歴', 1)
    add_table(d, [['版', '日付', '内容'],
                  ['Rev.1.2', '2026-07-01', '温度センサの比較手順を追加'],
                  ['Rev.1.3', '2026-10-01', '不具合報告 FR-2026-031 を受け、手順 2（JP2 の確認）を追加']])
    save_docx(d, 'SN-200_出荷検査手順書.docx', 'SN-200 出荷検査手順書')


def release_docx():
    d = Document()
    d.add_heading('SN-200 Firmware Release Notes', 0)
    d.add_paragraph('Hoshizora Electronics - Embedded Software Team')
    d.add_heading('Version 2.3.0 (2026-10-02)', 1)
    d.add_paragraph('New features', style='List Bullet')
    d.add_paragraph('SET_INTERVAL now accepts intervals from 1 s to 3600 s (previously 10 s to 3600 s).')
    d.add_paragraph('Added the GET_VERSION response field "build date".')
    d.add_paragraph('Bug fixes', style='List Bullet')
    d.add_paragraph('Fixed a CRC error that occurred when a frame contained exactly 256 bytes of payload.')
    d.add_paragraph('Fixed incorrect negative temperatures below -10 C (sign extension error).')
    d.add_paragraph('Known issues', style='List Bullet')
    d.add_paragraph('GET_VOLT returns 0 during the first 2 seconds after power-on, until the ADC calibration completes.')
    d.add_heading('Version 2.2.1 (2026-07-15)', 1)
    d.add_paragraph('Reduced the average current consumption by 1.5 mA by putting the RS-485 transceiver into standby between transmissions.')
    d.add_paragraph('Changed the default measurement interval from 30 s to 60 s.')
    d.add_heading('Upgrade procedure', 1)
    d.add_paragraph('Connect the SWD debugger to CN3 and write the firmware image sn200_fw_v2.3.0.hex. '
                    'Settings stored in flash (address, interval, baud rate) are kept. Firmware version 2.0 or later is required before updating; '
                    'devices with version 1.x must first be updated to 2.0.')
    save_docx(d, 'SN-200_Firmware_Release_Notes.docx', 'SN-200 Firmware Release Notes')


# ---------------------------------------------------------------- Excel
def bom_xlsx():
    wb = Workbook(); ws = wb.active; ws.title = 'BOM'
    ws.append(['SN-200 部品表（BOM）　版：C　更新日：2026-07-30'])
    ws.append([])
    ws.append(['No', '部品番号', '品名', '型番', 'メーカー', '数量', '単価（円）', '備考'])
    rows = [
        [1, 'U1', 'マイコン', 'HZ-M4F128', 'ホシゾラ電子', 1, 420, ''],
        [2, 'U2', '3.3V LDO', 'HZ-LDO33A-S5', 'ホシゾラ電子', 1, 38, 'SOT-89-5'],
        [3, 'U3', '降圧 DC-DC', 'HZ-BK2405', 'ホシゾラ電子', 1, 165, ''],
        [4, 'U4', '温度センサ', 'HZ-TS20-DRL', 'ホシゾラ電子', 1, 210, 'I2C 0x49'],
        [5, 'U5', 'RS-485 トランシーバ', 'HZ-RS485H', 'ホシゾラ電子', 1, 95, ''],
        [6, 'Q1', 'Nch MOSFET', 'HZ-N6030', 'ホシゾラ電子', 1, 48, '逆接続保護'],
        [7, 'D5', 'TVS ダイオード', 'HZ-TVS712', 'ホシゾラ電子', 1, 22, 'RS-485 ESD 対策（DR2 で追加）'],
        [8, 'C3, C4', 'セラミックコンデンサ', 'CM32X7R106K50', 'アオイ電子部品', 2, 31, '10μF 50V X7R 1210'],
        [9, 'C5', 'アルミ電解コンデンサ', 'AE-47U35V', 'アオイ電子部品', 1, 18, '47μF 35V 低 ESR'],
        [10, 'C12', 'セラミックコンデンサ', 'CM21X5R106M16', 'アオイ電子部品', 1, 9, '10μF 16V X5R 0805'],
        [11, 'R10', 'チップ抵抗', 'RC16-121J', 'アオイ電子部品', 1, 1, '120Ω 終端抵抗'],
        [12, 'JP2', 'ジャンパピン', 'JP-2P-254', 'コハク工業', 1, 6, '終端抵抗の切替'],
        [13, 'CN1', 'ターミナルブロック 2P', 'TB-508-2P', 'コハク工業', 1, 54, '電源入力'],
        [14, 'CN2', 'ターミナルブロック 3P', 'TB-508-3P', 'コハク工業', 1, 66, 'RS-485'],
        [15, 'PCB', 'プリント基板', 'HZ-SN200-PCB-C', '共栄プリント', 1, 380, '4層 80×50mm'],
    ]
    for r in rows: ws.append([None if v == '' else v for v in r])   # 空欄は本当に空のセルにする（Excel で入力しなかったのと同じ）
    ws.append([]); ws.append([None] * 5 + ['合計', sum(r[5] * r[6] for r in rows), '主要部品のみ（受動部品の一部は省略）'])
    for row in ws.iter_rows(min_row=4, min_col=7, max_col=7):
        for c in row: c.number_format = '#,##0'
    h = wb.create_sheet('変更履歴')
    h.append(['版', '日付', '変更内容', '理由'])
    h.append(['A', datetime.date(2026, 4, 12), '初版', None])
    h.append(['B', datetime.date(2026, 6, 25), 'D5（HZ-TVS712）を追加', 'DR2 指摘 #2（RS-485 の ESD 対策）'])
    h.append(['C', datetime.date(2026, 7, 30), 'C12 を 22μF（CM21X7R226M10）から 10μF（CM21X5R106M16）に変更', '22μF の部品の納期が 26 週と長いため'])
    for row in h.iter_rows(min_row=2, min_col=2, max_col=2):   # 日付のセル（表示は 2026/4/12。中身は日付の通し番号）
        for c in row: c.number_format = 'yyyy/m/d'
    a = wb.create_sheet('代替部品')
    a.append(['部品番号', '正規品', '代替品', '条件'])
    a.append(['Q1', 'HZ-N6030', 'HZ-N6040', 'VDSS 60V 以上・RDS(on) 15mΩ 以下であれば可'])
    a.append(['C3, C4', 'CM32X7R106K50', 'GR-1210-106-50', '50V・X7R に限る'])
    a.append(['U4', 'HZ-TS20-DRL', '（なし）', '代替品なし。精度の要求を満たす品がないため'])
    for w in wb.worksheets:
        for col in 'ABCDEFGH': w.column_dimensions[col].width = 18
    wb.properties.created = FIXED; wb.properties.modified = FIXED; wb.properties.creator = 'ホシゾラ電子'
    wb.save(os.path.join(OUT, 'SN-200_BOM.xlsx'))


def eval_xlsx():
    """受入評価の比較表。空のセル・結合したセル・日付・％・通貨の表示形式・1つのシートに2つの表、を含む（Excel の読み取りの確認用）"""
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = '比較'
    ws['A1'] = 'C3, C4 用 積層セラミックコンデンサ 受入評価'; ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = '評価者：鈴木（製造技術）　目的：代替品 GR-1210-106-50 を正規品の代わりに使えるか確認する'
    ws.append([])
    ws.append(['区分', '項目', '条件', 'CM32X7R106K50（正規品）', 'GR-1210-106-50（代替品）', '単位', '備考'])   # 4 行目
    data = [
        ['静電容量', '静電容量', 'DC 0V、25℃', 10.1, 9.8, 'μF', None],
        [None, '静電容量', 'DC 12V', 6.9, 6.1, 'μF', None],
        [None, '静電容量', 'DC 24V', 5.8, 4.7, 'μF', '代替品は 24V で実効容量が 5μF を下回る'],
        [None, '容量変化率', 'DC 24V（0V 比）', -0.426, -0.520, None, None],
        ['損失', 'ESR', '500kHz', 3.1, None, 'mΩ', '代替品は未測定（測定器の手配待ち）'],
        [None, '許容リップル電流', '500kHz、温度上昇 20℃', 4.2, 3.6, 'Arms', None],
        ['調達', '単価', '1,000 個購入時', 31, 24, None, None],
        [None, '納期', None, '8 週', '3 週', None, None],
        ['評価', '評価日', None, datetime.date(2026, 9, 10), datetime.date(2026, 9, 12), None, None],
        [None, '判定', None, '合格', '条件付き合格', None, '24V 系で使う場合は 3 個並列にすること'],
    ]
    for r in data: ws.append(r)
    # 区分の列は縦に結合（実際の表でよくある形）
    for a, b in [('A5', 'A8'), ('A9', 'A10'), ('A11', 'A12'), ('A13', 'A14')]: ws.merge_cells(f'{a}:{b}')
    for r in range(5, 15):
        if ws[f'B{r}'].value == '容量変化率':
            ws[f'D{r}'].number_format = ws[f'E{r}'].number_format = '0.0%'
        if ws[f'B{r}'].value == '単価':
            ws[f'D{r}'].number_format = ws[f'E{r}'].number_format = '"¥"#,##0'
        if ws[f'B{r}'].value == '評価日':
            ws[f'D{r}'].number_format = ws[f'E{r}'].number_format = '[$-411]ggge"年"m"月"d"日"'
        if ws[f'B{r}'].value in ('静電容量', 'ESR', '許容リップル電流'):
            for c in 'DE':
                if ws[f'{c}{r}'].value is not None: ws[f'{c}{r}'].number_format = '0.0'
    # 2つ目の表（空の行をはさむ）：温度特性。代替品の 125℃ は未測定で空欄
    ws.append([]); ws.append([])
    ws.append(['温度特性（DC 0V、25℃ 比の容量変化率）'])
    ws.append(['温度（℃）', '正規品', '代替品'])
    for t, a, b in [(-40, -0.081, -0.093), (-20, -0.042, -0.049), (25, 0, 0), (85, -0.067, -0.094), (125, -0.128, None)]:
        ws.append([t, a, b])
        for c in 'BC': ws[f'{c}{ws.max_row}'].number_format = '0.0%'
    for col, w in zip('ABCDEFG', [10, 18, 22, 24, 24, 8, 40]): ws.column_dimensions[col].width = w
    wb.properties.created = FIXED; wb.properties.modified = FIXED; wb.properties.creator = 'ホシゾラ電子'
    wb.save(os.path.join(OUT, 'C3-C4_コンデンサ受入評価.xlsx'))


# ---------------------------------------------------------------- PowerPoint
def dr_pptx():
    p = Presentation()
    def slide(title, lines):
        s = p.slides.add_slide(p.slide_layouts[1]); s.shapes.title.text = title
        tf = s.placeholders[1].text_frame; tf.text = lines[0]
        for l in lines[1:]: tf.add_paragraph().text = l
        for para in tf.paragraphs:
            for r in para.runs: r.font.size = PPt(18)
    t = p.slides.add_slide(p.slide_layouts[0]); t.shapes.title.text = 'SN-200 設計レビュー（DR2）'
    t.placeholders[1].text = '2026-06-12　第二設計部　出席：佐藤（設計）、田中（品証）、鈴木（製造技術）、山本（購買）'
    slide('指摘事項 #1：LDO の発熱', ['3.3V 系の最大負荷 150mA で LDO の損失は 0.255W',
                                   'SOT-89-5（θja 104℃/W）で温度上昇は約 27℃。周囲 70℃ でも Tj 約 97℃',
                                   '判定：問題なし（対策不要）'])
    slide('指摘事項 #2：RS-485 の ESD 対策', ['盤内配線は長く、静電気・サージが入りやすい',
                                       '対策：CN2 の近くに TVS ダイオード D5（HZ-TVS712）を追加する',
                                       '担当：佐藤　期限：2026-06-26'])
    slide('指摘事項 #3：温度センサの配置', ['DR1 の配置では U4 が LDO（U2）から 6mm で、自己発熱の影響を受ける',
                                     'データシートの推奨は 10mm 以上',
                                     '対策：U4 を基板の端に移動し、スリットを入れる（担当：佐藤）'])
    slide('決定事項', ['量産試作は 2026 年 7 月に 50 台で行う',
                     '目標原価は 1 台あたり 4,800 円（基板・部品・実装を含む）',
                     '次回 DR3 は量産試作の評価後（2026 年 9 月予定）'])
    slide('宿題', ['購買（山本）：C12（22μF）の納期を確認する',
                 '品証（田中）：出荷検査の判定基準案を作成する（7 月末まで）',
                 '製造技術（鈴木）：検査治具 JIG-485-02 を手配する'])
    p.core_properties.created = FIXED; p.core_properties.modified = FIXED; p.core_properties.author = 'ホシゾラ電子'
    p.save(os.path.join(OUT, 'SN-200_DR2_設計レビュー.pptx'))


# ---------------------------------------------------------------- CSV / テキスト / Markdown / HTML
def results_csv():
    rows = [['温度(℃)', '試料', '3.3V出力(V)', '5V出力(V)', '消費電流(mA)', '温度センサ誤差(℃)', '判定']]
    data = {
        -20: [(3.302, 5.01, 17.2, -0.21), (3.299, 5.00, 17.5, -0.18), (3.301, 5.02, 17.1, -0.25)],
        0:   [(3.301, 5.01, 16.8, -0.08), (3.300, 5.00, 17.0, -0.05), (3.300, 5.01, 16.9, -0.11)],
        25:  [(3.300, 5.00, 16.5, 0.03), (3.299, 4.99, 16.6, 0.06), (3.300, 5.00, 16.4, 0.02)],
        50:  [(3.298, 4.99, 16.9, 0.18), (3.297, 4.99, 17.1, 0.31), (3.298, 5.00, 16.8, 0.15)],
        70:  [(3.296, 4.98, 17.6, 0.34), (3.295, 4.98, 17.9, 0.62), (3.297, 4.99, 17.4, 0.29)],
    }
    for t, ss in data.items():
        for i, (v33, v5, cur, err) in enumerate(ss, 1):
            ok = abs(err) <= 0.5 and 3.25 <= v33 <= 3.35 and cur <= 18.0
            rows.append([t, f'#{i}', f'{v33:.3f}', f'{v5:.2f}', f'{cur:.1f}', f'{err:+.2f}', '合格' if ok else '不合格'])
    with open(os.path.join(OUT, 'SN-200_温度試験結果.csv'), 'w', encoding='utf-8-sig', newline='') as fp:
        csv.writer(fp, lineterminator='\r\n').writerows(rows)


def write(name, text, enc='utf-8'):
    with open(os.path.join(OUT, name), 'w', encoding=enc, newline='\r\n' if name.endswith('.txt') else '\n') as fp: fp.write(text)


FR = """不具合報告書　FR-2026-031

件名：高温試験で RS-485 の通信エラーが発生する
発生日：2026-09-18
報告者：品質保証課 田中
対象：SN-200 量産試作品（ロット 2607、シリアル 0012〜0019）
重要度：B（出荷前に対策が必要）

■ 現象
恒温槽 70℃ での連続通信試験（ケーブル長 50m、115200bps）で、通信エラー率が約 2% になった。
25℃ ではエラーは発生しなかった。8 台中 3 台で発生。

■ 調査結果
1. エラーが出た 3 台は、ジャンパ JP2（終端抵抗 120Ω）がショートされていなかった（終端なし）。
2. 伝送路の末端の機器で終端がないため信号が反射し、高温でトランシーバのしきい値がずれてエラーになったと考えられる。
3. JP2 をショートすると、70℃・50m・115200bps でエラー 0（1 万フレーム）になった。
4. 回路・部品の不良はなかった。

■ 原因
出荷時の JP2 の設定が作業者任せになっており、出荷検査で確認していなかった。

■ 対策
・出荷検査手順書を Rev.1.3 に改訂し、JP2 の設定を確認する手順を追加した（2026-10-01）。
・取扱説明書に「伝送路の両端の機器のみ JP2 をショートする」ことを明記する（2026-10 末まで、担当：技術サポート）。
・ケーブルが 30m を超える場合は 57600bps 以下で使うことを推奨する。

■ 状態：対策済み（2026-10-08 に効果を確認）
"""

UART = """# SN-200 UART コマンド仕様

SN-200 と上位の収集装置は、RS-485 上で次のフレーム形式のコマンドをやりとりする。
文書番号：HZ-SN200-FW-010　版：1.2（ファームウェア v2.3.0 に対応）

## 通信設定

- 通信速度：115200bps（既定）。SET_BAUD で 9600 / 19200 / 57600 / 115200bps に変更できる
- データ形式：8 ビット、パリティなし、ストップビット 1（8N1）
- 応答待ち時間：上位装置は 100ms 以内に応答がなければ再送する（最大 3 回）

## フレーム形式

| 項目 | 長さ | 内容 |
|---|---|---|
| STX | 1 バイト | 0x02 |
| ADDR | 1 バイト | 機器アドレス（1〜32。0 は全機器あて） |
| LEN | 1 バイト | CMD と DATA の合計バイト数 |
| CMD | 1 バイト | コマンド番号 |
| DATA | 0〜250 バイト | コマンドごとのデータ |
| CRC | 2 バイト | CRC-16/CCITT（多項式 0x1021、初期値 0xFFFF）。ADDR から DATA までを計算。上位バイトが先 |
| ETX | 1 バイト | 0x03 |

## コマンド一覧

| CMD | 名前 | 要求データ | 応答データ |
|---|---|---|---|
| 0x10 | GET_TEMP | なし | 温度（int16、0.01℃ 単位。例：2534 → 25.34℃） |
| 0x11 | GET_VOLT | なし | 入力電圧（uint16、mV 単位） |
| 0x20 | SET_INTERVAL | 測定間隔（uint16、秒。1〜3600、既定 60） | なし |
| 0x21 | SET_BAUD | 0=9600、1=19200、2=57600、3=115200 | なし（応答後に切り替え） |
| 0x30 | RESET | なし | なし（応答後に再起動） |
| 0x7F | GET_VERSION | なし | ファームウェアの版（例："2.3.0"）とビルド日 |

## エラー応答

エラーのときは CMD に 0xEE を入れ、DATA の 1 バイト目にエラーコードを入れて返す。

| エラーコード | 意味 |
|---|---|
| 0xE1 | CRC エラー |
| 0xE2 | 未対応のコマンド |
| 0xE3 | パラメータが範囲外（例：SET_INTERVAL に 0 や 3601 を指定） |
| 0xE4 | 処理中（測定中のため受け付けられない） |

## 注意

- 全機器あて（ADDR=0）のコマンドには応答しない。
- ファームウェア v2.2 以前では SET_INTERVAL の最小値は 10 秒。
"""

HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>コンデンサ選定基準</title></head>
<body>
<h1>社内設計基準：コンデンサの選定</h1>
<p>基準番号：DS-CAP-002　改訂：2025-12-01　設計標準化委員会</p>
<h2>1. 定格電圧のディレーティング</h2>
<p>セラミックコンデンサは、定格電圧が使用電圧の 2 倍以上のものを選ぶ。電源の入力など、サージが入るおそれのある箇所では 2.5 倍以上とする。</p>
<p>アルミ電解コンデンサは、定格電圧が使用電圧の 1.25 倍以上のものを選ぶ。</p>
<h2>2. 誘電体の種類</h2>
<ul>
<li>電源ラインには X7R または X5R を使う。Y5V・Z5U は使用禁止（温度と DC バイアスで容量が大きく減るため）。</li>
<li>周囲温度が 70℃ を超える場所、または 85℃ を超えて使う部品には X7R を使う（X5R の上限は 85℃）。</li>
<li>タンタルコンデンサは、突入電流で短絡故障するおそれがあるため、電源の入力側には使わない。</li>
</ul>
<h2>3. DC バイアス特性の確認</h2>
<p>セラミックコンデンサは直流電圧をかけると実効容量が減る。メーカーのシミュレーションツールで実効容量を確認し、必要な容量の 1.5 倍以上の実効容量を確保すること。</p>
<h2>4. アルミ電解コンデンサの寿命</h2>
<table border="1">
<tr><th>項目</th><th>基準</th></tr>
<tr><td>寿命の計算</td><td>周囲温度が 10℃ 下がるごとに寿命は 2 倍になる（10℃2倍則）</td></tr>
<tr><td>必要な寿命</td><td>製品の設計寿命（SN-200 は 10 年）以上</td></tr>
<tr><td>推奨品</td><td>105℃・2000 時間品以上</td></tr>
</table>
<p>例：105℃・2000 時間品を周囲 65℃ で使う場合、寿命は 2000 × 2<sup>4</sup> = 32000 時間（約 3.7 年）。10 年が必要な場合は 105℃・10000 時間品を選ぶか、温度を下げる。</p>
<h2>5. 承認</h2>
<p>この基準から外れる部品を使う場合は、設計審査（DR）で承認を得ること。</p>
</body></html>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    ldo_pdf(); ts_pdf(); mosfet_pdf(); an_pdf()
    spec_docx(); inspect_docx(); release_docx()
    bom_xlsx(); eval_xlsx(); dr_pptx(); results_csv()
    write('不具合報告_FR-2026-031.txt', FR, enc='cp932')   # 古い社内文書によくある Shift_JIS
    write('UART_コマンド仕様.md', UART)
    write('コンデンサ選定基準.html', HTML)
    for f in sorted(os.listdir(OUT)): print(f'{os.path.getsize(os.path.join(OUT, f)):>8,}  {f}')


if __name__ == '__main__':
    main()

"""地元の会・PMDAの医療機器回収・造影剤の供給状況のテスト。実ページの構造を写した最小の例で確かめる。"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import update_news as u  # noqa: E402


KART_TOP_HTML = '''
<ul class="news">
<li><span class="data">2026.10.24</span><span class="category">お知らせ</span><p><a href="article/data.php?nid=509">第3回 消化管部会 研修会のご案内</a></p></li>
<li><span class="data">2026.10.02</span><span class="category">会員</span><p><a href="article/data.php?nid=505">会費納入についてのお願い</a></p></li>
</ul>
<a href="https://example.com/banner">バナー広告のリンクです</a>
'''

KART_SCHEDULE_HTML = '''
<ul><li><span class="data">2026.11.14</span><p><a href="schedule.php?nid=307">少人数施設ミーティング</a></p></li>
<li><span class="data">2026.11.21</span><p><a href="schedule.php?nid=310">消化管部会 胃透視読影会</a></p></li></ul>
'''


def test_kart_notices():
    items = u.parse_dated_links(KART_TOP_HTML, u.KART_TOP, r'data\.php\?nid=')
    assert [x['title'] for x in items] == ['第3回 消化管部会 研修会のご案内', '会費納入についてのお願い']
    assert items[0]['url'] == 'https://kagawart.jp/article/data.php?nid=509'
    assert items[0]['published'].startswith('2026-10-24')


def test_kart_schedule(monkeypatch):
    monkeypatch.setattr(u, 'fetch', lambda url: KART_SCHEDULE_HTML if 'm=11' in url else '<ul></ul>')
    ev = u.update_kart_schedule()
    assert {x['title'] for x in ev} >= {'少人数施設ミーティング', '消化管部会 胃透視読影会'}
    x = next(x for x in ev if x['title'] == '少人数施設ミーティング')
    assert x['event_start'] == '2026-11-14' and x['place'] == '香川'
    assert x['url'] == 'https://kagawart.jp/article/schedule.php?nid=307'


def test_local_societies_are_official_and_relevant():
    x = {'headline': '会費納入についてのお願い', 'summary': '', 'source': '香川県診療放射線技師会',
         'url': 'https://kagawart.jp/article/data.php?nid=505'}
    assert u.is_official(x['url']) and u.relevant(x)
    assert u.relevant({'headline': '支部だより', 'summary': '', 'source': '', 'url': 'https://jsrt-chushi.jp/?p=1'})


RECALL_HTML = '''
<table>
<tr><th>番号</th><th>掲載年月日</th><th>種類</th><th>一般名</th><th>販売名</th><th>製造販売業者等名称</th><th>備考</th></tr>
<tr><td>2-13015</td><td>2026/10/27</td><td>医療機器</td><td>放射線治療計画プログラム</td><td><a href="/rgo/MainServlet?recallno=2-13015">RayStation</a></td><td>レイサーチ・ジャパン株式会社</td><td></td></tr>
<tr><td>2-13012</td><td>2026/10/26</td><td>医療機器</td><td>単回使用注射針</td><td><a href="/rgo/MainServlet?recallno=2-13012">注射針A</a></td><td>某社</td><td></td></tr>
<tr><td>2-13009</td><td>2026/10/23</td><td>医療機器</td><td>据置型デジタル式循環器用X線透視診断装置</td><td><a href="/rgo/MainServlet?recallno=2-13009">アーティス</a></td><td>シーメンスヘルスケア株式会社</td><td></td></tr>
</table>'''


def test_pmda_recalls_keep_only_imaging_devices():
    items = u.parse_pmda_recalls(RECALL_HTML, 2)
    assert [x['title'] for x in items] == [
        '医療機器の回収(クラスII)：RayStation(放射線治療計画プログラム)',
        '医療機器の回収(クラスII)：アーティス(据置型デジタル式循環器用X線透視診断装置)',
    ]
    assert items[0]['url'] == 'https://www.info.pmda.go.jp/rgo/MainServlet?recallno=2-13015'


def test_recall_is_high_and_safety():
    t = '医療機器の回収(クラスII)：アーティス(据置型デジタル式循環器用X線透視診断装置)'
    x = {'headline': t, 'summary': '', 'source': 'PMDA', 'url': 'https://www.info.pmda.go.jp/rgo/MainServlet?recallno=2-13009'}
    assert u.relevant(x)
    assert u.importance(x, u.is_official(x['url'])) == '高'
    assert u.category(x) == '安全管理'


def test_fetch_decodes_euc_jp(monkeypatch):
    raw = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=EUC-JP"></head>回収</html>'.encode('euc_jp')
    monkeypatch.setattr(u, 'fetch_bytes', lambda url: (raw, None))
    assert '回収' in u.fetch('https://example.com')


HEAD = ['薬剤区分', '薬効分類', '成分名', '規格単位', 'YJコード', '品名', '製造販売業者名', '7', '8', '9', '10',
        '⑪製造販売業者の出荷対応の状況', '⑫の情報を更新した日', '13', '14', '15', '16', '17', '18', '19', '今回掲載時の更新有無']


def row(cls, ing, name, status, new='', changed=46320):
    r = [''] * len(HEAD)
    r[0], r[1], r[2], r[3], r[4], r[5], r[6] = '内用薬', cls, ing, '100%1g', '7212', name, '某社'
    r[11], r[12], r[20] = status, changed, new
    return r


def test_supply_rows_pick_imaging_agents():
    rows = [['医療用医薬品供給状況'], HEAD,
            row('Ｘ線造影剤', '硫酸バリウム', 'バリコンミール', '②限定出荷（自社の事情）', 'New'),
            row('Ｘ線造影剤', 'イオヘキソール', 'オムニパーク300', '⑤供給停止'),
            row('その他の診断用薬（体外診断用医薬品を除く。）', 'ガドテリドール', 'プロハンス', '①通常出荷', 'New'),
            row('解熱鎮痛消炎剤', 'アセトアミノフェン', 'カロナール', '②限定出荷（自社の事情）', 'New')]
    out = u.parse_supply_rows(rows)
    assert [x['product'] for x in out] == ['バリコンミール', 'オムニパーク300', 'プロハンス']
    assert [x['category'] for x in out] == ['検診', 'CT', 'MRI']
    assert out[0]['status'] == '限定出荷（自社の事情）' and out[0]['new']
    assert out[2]['changed'] == (datetime(1899, 12, 30) + timedelta(days=46320)).date().isoformat()


def test_supply_news_titles(monkeypatch, tmp_path):
    page = '<a href="/content/10800000/261026iyakuhinkyoukyu.xlsx">医療用医薬品供給状況（10月26日現在）</a>'
    monkeypatch.setattr(u, 'fetch', lambda url: page)
    monkeypatch.setattr(u, 'fetch_bytes', lambda url: (b'', None))
    monkeypatch.setattr(u, 'SUPPLY_JSON', tmp_path / 'supply.json')
    rows = [HEAD, row('Ｘ線造影剤', '硫酸バリウム', 'バリコンミール', '②限定出荷（自社の事情）', 'New'),
            row('Ｘ線造影剤', 'アミドトリゾ酸', 'ガストログラフイン', '①通常出荷', 'New'),
            row('Ｘ線造影剤', 'イオヘキソール', 'オムニパーク300', '⑤供給停止')]

    class WB:
        worksheets = [type('S', (), {'iter_rows': lambda self, values_only: iter(rows)})()]
    import openpyxl
    monkeypatch.setattr(openpyxl, 'load_workbook', lambda *a, **k: WB())
    news = u.update_supply()
    assert [x['title'] for x in news] == ['造影剤の限定出荷（自社の事情）：バリコンミール(硫酸バリウム)',
                                         '造影剤の供給回復：ガストログラフイン(アミドトリゾ酸)']
    import json
    saved = json.loads((tmp_path / 'supply.json').read_text())
    assert saved['as_of'] == '10月26日現在'
    assert [x['product'] for x in saved['items']] == ['オムニパーク300', 'バリコンミール']   # 供給停止が先
    x = {'headline': news[0]['title'], 'summary': '', 'source': news[0]['source'], 'url': news[0]['url']}
    assert u.importance(x, True) == '高' and u.category(x) == '安全管理'

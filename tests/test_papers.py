"""学会誌の新着論文(J-STAGE RSS)のテスト。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import update_news as u  # noqa: E402

RSS = '''<?xml version="1.0" encoding="UTF-8"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<item rdf:about="https://www.jstage.jst.go.jp/article/jsgcs/64/5/64_1/_article/-char/ja"><title>胃X線検診における撮影体位の検討</title>
<link>https://www.jstage.jst.go.jp/article/jsgcs/64/5/64_1/_article/-char/ja</link><dc:date>2026-10-20</dc:date></item>
<item><title>大腸内視鏡の受診率</title><link>https://www.jstage.jst.go.jp/article/jsgcs/64/5/64_2/_article/-char/ja</link><dc:date>2026-10-20</dc:date></item>
</rdf:RDF>'''


def test_papers_are_saved_and_kept(monkeypatch, tmp_path):
    monkeypatch.setattr(u, 'PAPERS_JSON', tmp_path / 'papers.json')
    monkeypatch.setattr(u, 'JOURNALS', (('日本消化器がん検診学会雑誌', 'jsgcs', '検診'),))
    monkeypatch.setattr(u, 'fetch', lambda url: RSS)
    out = u.update_papers()
    assert [x['title'] for x in out] == ['胃X線検診における撮影体位の検討', '大腸内視鏡の受診率']
    assert out[0]['journal'] == '日本消化器がん検診学会雑誌' and out[0]['published'] == '2026-10-20'
    assert {x['category'] for x in out} == {'検診'}
    # 次の回にフィードから消えても、前回分は残る
    monkeypatch.setattr(u, 'fetch', lambda url: '<rss></rss>')
    out2 = u.update_papers()
    assert len(out2) == 2
    assert json.loads((tmp_path / 'papers.json').read_text())['items'][0]['url'].startswith('https://www.jstage.jst.go.jp/')

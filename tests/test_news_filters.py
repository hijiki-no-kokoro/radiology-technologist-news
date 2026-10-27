"""ノイズ記事の除外とカテゴリ分類のテスト (python -m pytest tests/test_news_filters.py)。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import update_news as u  # noqa: E402


def item(headline, source=''):
    return {'headline': headline, 'summary': headline, 'source': source, 'url': 'https://news.google.com/x'}


@pytest.mark.parametrize('headline, source', [
    ('フォトンカウンティングCT市場、2035年に89億4,000万米ドルへ拡大予測｜SNS Insider調査', 'ニコニコニュース'),
    ('核医学機器市場の最新動向：力強い成長と競争、2026年から2033年にかけて予測CAGR', 'pando.life'),
    ('グローバル核医学ソフトウェア市場におけるトップ10企業', 'Spherical Insights'),
    ('PET核医学イメージングメーカーランキング', 'pando.life'),
    ('Untitled - 日本診療放射線技師会', '日本診療放射線技師会'),
])
def test_noise_is_excluded(headline, source):
    assert not u.is_news_item(item(headline, source))


@pytest.mark.parametrize('headline, source', [
    ('ガストログラフィン®経口・注腸用「限定出荷」継続のお知らせ', '日本診療放射線技師会'),
    ('EIZO、医用画像表示モニター2機種を発売へ 24.1型と27型', 'Dellows News'),
    ('病院のCT・MRI画像を受診者のスマートフォンへ。検査画像転送サービス「スマぞう」販売開始', 'news.infoseek.co.jp'),
])
def test_real_news_is_kept(headline, source):
    assert u.is_news_item(item(headline, source))


@pytest.mark.parametrize('headline, expected', [
    ('局所進行直腸癌の術前療法で短期放射線療法＋抗PD-1抗体が有意に延長', '放射線治療'),
    ('計画用 CT は放射線治療の出発点', '放射線治療'),
    ('試薬不足のためPET/CT装置が稼働していない', '核医学'),
    ('α線放出核種Ac225を用いる放射線リガンド療法薬', '核医学'),
    ('【画像】レントゲン画像に写ったハート形の物体', '一般撮影'),
    ('告示研修（実技研修）大阪府2026/12/13', '職能'),
    ('ガストログラフィン®経口・注腸用「限定出荷」継続のお知らせ', '安全管理'),
    ('fcuro、キヤノンメディカルと提携 救急CT読影AIなどの認知を拡大', 'CT'),
    ('国産2nm半導体を医療AIに活用へ', 'AI'),
])
def test_category(headline, expected):
    assert u.category(item(headline)) == expected


@pytest.mark.parametrize('headline', [
    'Mayo Clinic director comments on project',   # 「director」「project」の ct は CT ではない
    'Siemens Healthineers Detector Update',       # 「Detector」の ct
    'Primary care trial',                          # 「Primary」「trial」の ri / ai
])
def test_ascii_terms_match_whole_words_only(headline):
    assert u.category(item(headline)) == 'その他'


def test_source_name_is_not_used_for_category():
    # 配信元「日本放射線技術学会」の「学会」で学術に入れない
    assert u.category(item('動画視聴システム更新に伴う一時休止のお知らせ', '日本放射線技術学会')) == 'その他'

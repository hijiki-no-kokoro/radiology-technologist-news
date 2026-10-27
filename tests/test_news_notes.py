"""「技師長目線」の一言と要約整理のテスト (python -m pytest tests/test_news_notes.py)。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import update_news as u  # noqa: E402


def note(headline, importance='中'):
    return u.technologist_note({'headline': headline, 'summary': '', 'importance': importance})


@pytest.mark.parametrize('headline, expected', [
    ('ガストログラフィン®経口・注腸用「限定出荷」継続のお知らせ', '在庫量と代替品'),
    ('画像診断ガイドライン2026年度版の全記事の公開について', '撮影プロトコル'),
    ('股関節撮影時の生殖腺遮蔽の見直しについて（声明）', '撮影手技の見直し'),
    ('診療報酬改定による現場影響度調査に関するアンケート', '医事課'),
    ('告示研修（実技研修）大阪府2026/12/13', '告示研修'),
    ('2026年度 第3回単純X線撮影における品質管理セミナー', '申込期限'),
    ('「放射線治療」特集号の原稿募集について', '応募条件'),
    ('「画像診断ガイドライン」パブリックコメント募集', '意見募集'),
])
def test_note_matches_reason(headline, expected):
    assert expected in note(headline)


@pytest.mark.parametrize('headline', [
    '第62回秋季臨床大会 JRS-NEXT企画 開催報告',           # 終わった催しの報告
    '更新講習会の開催遅延について',                         # 申込を促す案内ではない
    '日本医学放射線学会賞',                                   # 当てはまる理由がない
])
def test_no_note_when_nothing_specific(headline):
    assert note(headline) == ''


def test_low_importance_gets_no_note():
    assert note('ガストログラフィン「限定出荷」', importance='低') == ''


@pytest.mark.parametrize('headline, summary, source', [
    ('停職処分 公立病院の29歳放射線技師 - FNNプライムオンライン', '停職処分 公立病院の29歳放射線技師 FNNプライムオンライン', 'FNNプライムオンライン'),
    ('［お知らせ］専門部会誌-秋号（電子版）閲覧のご案内 - 公益社団法人 日本放射線技術学会',
     '［お知らせ］専門部会誌-秋号（電子版）閲覧のご案内 公益社団法人 日本放射線技術学会', '公益社団法人 日本放射線技術学会'),
])
def test_summary_repeating_headline_is_cleared(headline, summary, source):
    assert u.clean_summary({'headline': headline, 'summary': summary, 'source': source}) == ''


def test_real_summary_is_kept():
    s = 'IGRTを支える教育体制、運用の基礎、臨床上の注意点や工夫を扱うWebセミナー。'
    assert u.clean_summary({'headline': '第66回放射線治療セミナー', 'summary': s, 'source': 'jsrt.or.jp'}) == s

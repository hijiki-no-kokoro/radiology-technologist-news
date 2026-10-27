"""月別アーカイブのテスト (python -m pytest tests/test_news_archive.py)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import update_news as u  # noqa: E402


def test_overflow_items_are_archived_by_month_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(u, 'ARCHIVE_DIR', tmp_path)
    a = {'date': '2026-09-03', 'headline': 'A', 'url': 'https://e/a'}
    b = {'date': '2026-09-20', 'headline': 'B', 'url': 'https://e/b'}
    c = {'date': '2026-08-31', 'headline': 'C', 'url': 'https://e/c'}
    u.archive_items([a, b, c])
    u.archive_items([a])                                    # 2回目でも重複しない
    sep = json.loads((tmp_path / '2026-09.json').read_text(encoding='utf-8'))
    assert [x['url'] for x in sep] == ['https://e/b', 'https://e/a']   # 新しい順
    idx = json.loads((tmp_path / 'index.json').read_text(encoding='utf-8'))
    assert idx['months'] == [{'month': '2026-09', 'count': 2}, {'month': '2026-08', 'count': 1}]


def test_nothing_happens_without_overflow(tmp_path, monkeypatch):
    monkeypatch.setattr(u, 'ARCHIVE_DIR', tmp_path / 'archive')
    u.archive_items([])
    assert not (tmp_path / 'archive').exists()

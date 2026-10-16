import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/update_beer_catalog.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
TODAY = dt.date(2026, 10, 16)


class CatalogUpdateTests(unittest.TestCase):
    def setUp(self):
        self.old = u.read_catalog(ROOT / 'beer-save/beer-catalog.js')['products']
        self.p = {'manufacturer': 'アサヒビール', 'productName': '検証用 季節限定ビール 350ml缶',
                  'volumeMl': 350, 'alcoholPercent': 5, 'caloriesKcal': None,
                  'janCode': '4901004006714', 'category': 'beer',
                  'source': 'https://www.asahibeer.co.jp/products/beer/superdry/1F105.html'}

    def test_real_manufacturer_fixtures(self):
        fs = json.loads((ROOT / 'tests/beer-catalog-source-fixtures.json').read_text())
        for f in fs:
            with self.subTest(source=f['source']):
                expected = f['expected']
                if f['collector'] == 'kirin':
                    args = (expected['productName'], 'ビール', TODAY)
                else:
                    args = (TODAY,)
                ps = getattr(u, 'parse_' + f['collector'])(f['html'], f['source'], *args)
                match = [p for p in ps if p['janCode'] == expected['janCode']]
                self.assertEqual(len(match), 1)
                for k in ['volumeMl', 'alcoholPercent', 'caloriesKcal']:
                    self.assertEqual(match[0][k], expected[k])
                self.assertTrue(u.validate(match[0]))

    def test_case_jan_is_never_single_can(self):
        html = '<h2 class="product-info-head">商品</h2>アルコール分5% 容器:缶 内容量:350ml JANコード ケース:4901004006714'
        self.assertEqual(u.parse_asahi(html, self.p['source'], TODAY), [])

    def test_kirin_pagination_uses_named_index_without_an_id(self):
        class FakeFetcher:
            def __init__(self):
                self.posts = []

            def get(self, url, data=None):
                if data is None:
                    return '<a name="ビール"></a><a href="javascript:toSearch(\'BRAND\')">ブランド</a>'
                self.posts.append(u.urllib.parse.parse_qs(data.decode()))
                if len(self.posts) == 1:
                    return '<input type="hidden" name="index" value="20"><input id="cnt" name="status.count" type="hidden" value="0"><input id="kbn" name="searchResult.kbn" type="hidden"><a href="javascript:toBackNext(\'next\')">次へ</a><a href="javascript:dspDatail(\'A\',\'x\',\'1\')">試験ビール350ml缶</a>'
                return '<a href="javascript:dspDatail(\'B\',\'x\',\'2\')">試験ビール500ml缶</a>'

            def batch(self, urls):
                self.urls = set(urls)
                return []

        f = FakeFetcher()
        u.kirin(f, TODAY)
        self.assertEqual(len(f.posts), 2)
        self.assertEqual(f.posts[1]['status.count'], ['20'])
        self.assertEqual(f.urls, {'https://outer1.kirin.co.jp/kirin/detail/A_1', 'https://outer1.kirin.co.jp/kirin/detail/B_2'})

    def test_future_release_is_held(self):
        html = '<h2 class="product-info-head">商品</h2>アルコール分5% 発売日2026年11月1日 容器:缶 内容量:350ml JANコード 単品:4901004006714'
        self.assertEqual(u.parse_asahi(html, self.p['source'], TODAY), [])
        self.assertFalse(u.future_release('発売日2026年10月16日', TODAY))

    def test_required_values_and_checksum(self):
        for key, value in [('janCode', '4901004006715'), ('volumeMl', None), ('alcoholPercent', 0),
                           ('alcoholPercent', float('nan')), ('productName', '')]:
            with self.subTest(key=key, value=value):
                self.assertFalse(u.validate({**self.p, key: value}))
        self.assertTrue(u.validate(self.p))

    def test_add_new_can_without_inventing_calories(self):
        ps, added, held, _ = u.merge([], [self.p], TODAY)
        self.assertEqual(len(added), 1)
        self.assertFalse(held)
        self.assertIsNone(ps[0]['caloriesKcal'])
        self.assertEqual(ps[0]['productName'], '検証用 季節限定ビール')

    def test_source_failure_cannot_erase_existing_478(self):
        original = copy.deepcopy(self.old)
        ps, added, held, _ = u.merge(self.old, [], TODAY)
        self.assertEqual(ps, sorted(original, key=lambda p: p['janCode']))
        self.assertEqual(self.old, original)
        self.assertEqual(len(ps), len(original))
        self.assertGreaterEqual(len(ps), 478)
        self.assertEqual(added, [])

    def test_repeat_collection_preserves_saved_copy_identity(self):
        prior = next(p for p in self.old if p['janCode'] == self.p['janCode'])
        p = {**self.p, 'productName': '新しい表示名', 'caloriesKcal': 999}
        ps, added, _, _ = u.merge(self.old, [p, p], TODAY)
        self.assertEqual(next(x for x in ps if x['janCode'] == p['janCode']), prior)
        self.assertFalse(added)

    def test_same_jan_new_abv_requires_confirmation_without_overwrite(self):
        prior = next(p for p in self.old if p['janCode'] == self.p['janCode'])
        ps, added, held, _ = u.merge(self.old, [{**self.p, 'alcoholPercent': 6}], TODAY)
        revised = next(p for p in ps if p['janCode'] == prior['janCode'])
        self.assertTrue(revised['requiresConfirmation'])
        self.assertEqual(revised['alcoholPercent'], prior['alcoholPercent'])
        self.assertEqual(len(held), 1)
        self.assertFalse(added)

    def test_conflicting_new_jan_not_added(self):
        ps, added, held, _ = u.merge([], [self.p, {**self.p, 'volumeMl': 500}], TODAY)
        self.assertEqual(ps, [])
        self.assertEqual(added, [])
        self.assertEqual(len(held), 1)

    def test_duplicate_guard_and_batch_anomaly(self):
        with self.assertRaises(ValueError):
            u.merge([self.old[0], self.old[0]], [], TODAY)
        with self.assertRaises(ValueError):
            u.allowed('https://malicious.example/product')
        with self.assertRaises(ValueError):
            u.allowed('http://www.asahibeer.co.jp/product')

    def test_atomic_prevalidation_preserves_files_when_hook_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = root / 'beer-save'
            app.mkdir()
            for name in ['beer-catalog.js', 'log.html', 'sw.js']:
                (app / name).write_text('original')
            with self.assertRaises(ValueError):
                u.write_outputs(root, {'version': 'test', 'products': self.old})
            self.assertTrue(all(p.read_text() == 'original' for p in app.iterdir()))

    def test_generated_assets_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = root / 'beer-save'
            app.mkdir()
            for name in ['beer-catalog.js', 'log.html', 'sw.js']:
                (app / name).write_bytes((ROOT / 'beer-save' / name).read_bytes())
            payload = {'version': 'catalog-auto-test', 'products': self.old}
            u.write_outputs(root, payload)
            self.assertEqual(u.read_catalog(app / 'beer-catalog.js'), payload)
            self.assertIn("const CACHE='beer-save-catalog-auto-test';", (app / 'sw.js').read_text())
            self.assertNotIn('?v=catalog-auto-setup-1', (app / 'log.html').read_text())


if __name__ == '__main__':
    unittest.main()

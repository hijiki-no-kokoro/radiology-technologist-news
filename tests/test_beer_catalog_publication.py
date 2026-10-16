import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish', ROOT / 'scripts/publish_beer_catalog.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PublicationTests(unittest.TestCase):
    def exercise(self, wrong=False, config_changed=False):
        calls = []
        env = {'GITHUB_REPOSITORY': 'example/beer-test', 'GH_TOKEN': 'test-token'}
        initial = Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                Path('beer-save').mkdir()
                bodies = {'beer-save/beer-catalog.js': b'catalog', 'beer-save/log.html': b'page', 'beer-save/sw.js': b'cache'}
                for name, data in bodies.items():
                    Path(name).write_bytes(data)

                def opened(req, timeout):
                    calls.append((req.full_url, req.get_method()))
                    if req.full_url.endswith('/pages'):
                        body = json.dumps({'html_url': 'https://example.github.io/beer-test/',
                                           'source': {'branch': 'other' if config_changed else 'main', 'path': '/'}}).encode()
                    elif req.full_url.endswith('/pages/builds'):
                        body = b'{"status":"queued"}'
                    else:
                        name = req.full_url.split('/beer-test/')[1].split('?')[0]
                        body = b'old-content' if wrong else bodies[name]
                    return io.BytesIO(body)

                with patch.dict(os.environ, env), patch.object(p.urllib.request, 'urlopen', opened), patch.object(p.time, 'sleep'):
                    if wrong or config_changed:
                        with self.assertRaises(RuntimeError):
                            p.main()
                    else:
                        p.main()
                report = Path('work/beer-catalog-publication.json')
                result = json.loads(report.read_text()) if report.exists() else None
            finally:
                os.chdir(initial)
        return calls, result

    def test_explicit_build_and_all_three_served_hashes(self):
        calls, r = self.exercise()
        self.assertIn(('https://api.github.com/repos/example/beer-test/pages/builds', 'POST'), calls)
        self.assertTrue(r['verified'])
        self.assertEqual(len(r['actual']), 3)

    def test_deployment_failure_is_not_reported_as_success(self):
        _, r = self.exercise(wrong=True)
        self.assertFalse(r['verified'])
        self.assertEqual(len(r['errors']), 3)

    def test_changed_pages_settings_are_preserved(self):
        calls, r = self.exercise(config_changed=True)
        self.assertIsNone(r)
        self.assertTrue(all(method == 'GET' for _, method in calls))

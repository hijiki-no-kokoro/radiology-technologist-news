#!/usr/bin/env python3
"""Request existing branch-based Pages build; verify the 3 generated assets.

Requires a short-lived Actions token with Pages write, not a personal API key.
Does not change Pages settings or unrelated repository files.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository')
    token = os.environ['GH_TOKEN']
    api = 'https://api.github.com/repos/' + repo

    def request(path, method='GET'):
        req = urllib.request.Request(api + path, method=method, data=b'' if method == 'POST' else None,
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Accept': 'application/vnd.github+json',
                                              'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    paths = ['beer-save/beer-catalog.js', 'beer-save/log.html', 'beer-save/sw.js']
    expected = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    site = request('/pages')
    if site.get('build_type') == 'workflow' or site.get('source', {}).get('branch') != 'main' or site.get('source', {}).get('path') != '/':
        raise RuntimeError('Pages publishing configuration changed; explicit review required')
    public = site['html_url'].rstrip('/') + '/'
    if not public.startswith('https://'):
        raise ValueError('Public Pages URL must use HTTPS')
    request('/pages/builds', 'POST')
    errors, hashes = {}, {}
    for attempt in range(40):
        if attempt:
            time.sleep(15)
        for p, h in expected.items():
            try:
                req = urllib.request.Request(public + p + '?catalog-verify=' + h[:16], headers={'Cache-Control': 'no-cache'})
                with urllib.request.urlopen(req, timeout=20) as r:
                    actual = hashlib.sha256(r.read(4_000_001)).hexdigest()
                hashes[p] = actual
                if actual != h:
                    errors[p] = 'Published content differs'
                else:
                    errors.pop(p, None)
            except Exception as e:
                errors[p] = str(e)[:200]
        if not errors:
            break
    report = {'publicUrl': public, 'expected': expected, 'actual': hashes, 'errors': errors,
              'verified': not errors}
    Path('work').mkdir(exist_ok=True)
    Path('work/beer-catalog-publication.json').write_text(json.dumps(report, indent=2))
    if errors:
        raise RuntimeError('Pages verification failed; preserved dictionary will be republished on next run')
    print('Published dictionary, page and service worker match generated files.')


if __name__ == '__main__':
    main()

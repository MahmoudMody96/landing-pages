#!/usr/bin/env python3
"""Inject (or remove) the analytics snippet in landing pages.

Reads templates/tracking.json. Does NOTHING unless enabled=true with a
non-empty src + website_id. Idempotent via TRACKING-START/END markers.

  python tools/inject_tracking.py            # inject per tracking.json
  python tools/inject_tracking.py --remove   # strip snippet from all pages
  python tools/inject_tracking.py --check    # report state, no writes

    NOTE: since the pages became template-generated, the snippet is rendered
    into every page by python tools/gen_pages.py (pagekit.tracking_block reads
    the same templates/tracking.json). This script stays for verification and
    for stripping legacy injections -- what it writes is byte-identical to the
    rendered block, so running both in either order is safe.

"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagekit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(ROOT, 'src', 'cities', 'sa-riyadh')

START = pagekit.TRACKING_START
END = pagekit.TRACKING_END
PATTERN = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)
# Removal consumes the block plus every newline between it and </head>, so
# inject -> remove round-trips to the byte-identical original -- and a block
# that was ever injected with an extra blank line gets fully cleaned.
REM_PATTERN = re.compile(
    re.escape(START) + r'.*?' + re.escape(END) + r'\n*', re.S)
# The update path must consume the same newlines: the replacement block carries
# one trailing newline of its own, and anything left behind would turn an
# injected page different from the template's rendering (a blank line before
# </head> is exactly the difference that makes gen_pages.py --check mismatch).
UPDATE_PATTERN = REM_PATTERN


def snippet(cfg):
    """The block the template renders. Single source of truth is
    pagekit.tracking_block() -- kept here so the markers and the exact bytes
    cannot drift between the two paths."""
    return pagekit.tracking_block()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--inject'
    cfg = json.load(open(os.path.join(ROOT, 'templates', 'tracking.json'),
                         encoding='utf-8'))
    active = bool(cfg.get('enabled')) and bool(cfg.get('src')) \
        and bool(cfg.get('website_id'))
    pages = sorted(f for f in os.listdir(PAGES_DIR) if f.endswith('.html'))

    if mode == '--check':
        with_tag = 0
        for fname in pages:
            html = open(os.path.join(PAGES_DIR, fname), encoding='utf-8').read()
            with_tag += 1 if PATTERN.search(html) else 0
        print('tracking config: %s' % ('ACTIVE' if active else 'inactive'))
        print('pages with snippet: %d / %d' % (with_tag, len(pages)))
        return

    if mode == '--remove':
        n = 0
        for fname in pages:
            path = os.path.join(PAGES_DIR, fname)
            html = open(path, encoding='utf-8').read()
            new_html = REM_PATTERN.sub('', html)
            if new_html == html:  # tolerate blocks without trailing newline
                new_html = PATTERN.sub('', html)
            if new_html != html:
                open(path, 'w', encoding='utf-8', newline='\n').write(new_html)
                n += 1
        print('removed snippet from %d pages' % n)
        return

    if not active:
        print('tracking.json is not enabled (need enabled=true + src + '
              'website_id) — pages left untouched.')
        print('Steps: deploy Umami on Coolify -> add a website -> fill '
              'templates/tracking.json -> rerun this script.')
        return

    block = snippet(cfg)
    n = 0
    for fname in pages:
        path = os.path.join(PAGES_DIR, fname)
        html = open(path, encoding='utf-8').read()
        assert html.count('</head>') == 1, fname
        # block already ends with '\n', so it goes right before '</head>'
        new_html = (UPDATE_PATTERN.sub(lambda _: block, html) if PATTERN.search(html)
                    else html.replace('</head>', block + '</head>'))
        if new_html != html:
            open(path, 'w', encoding='utf-8', newline='\n').write(new_html)
            n += 1
    print('tracking injected/updated in %d pages (0 = already current)' % n)


if __name__ == '__main__':
    main()

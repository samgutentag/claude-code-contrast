#!/usr/bin/env python3
"""Embed the before/after screenshots into setup-guide.html as data URIs.

The guide has to stay self-contained: no external assets, so it prints clean and
works offline. This replaces the IMG:BEFORE / IMG:AFTER markers (or a previously
embedded <img>) with fresh base64. Idempotent, so re-run it after retaking a shot.

  python3 embed-images.py
"""

import base64
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
GUIDE = HERE / 'setup-guide.html'
SHOTS = {
    'BEFORE': HERE / 'screenshots' / 'high-contrast-cb-before.png',
    'AFTER': HERE / 'screenshots' / 'high-contrast-cb-after.png',
}
ALT = {
    'BEFORE': 'Claude Code before: the block behind the user message is barely visible',
    'AFTER': 'Claude Code after: a clearly filled slate blue bar behind the user message',
}
MAX_MB = 8


def main():
    if not GUIDE.exists():
        raise SystemExit(f'no guide at {GUIDE}')

    html = GUIDE.read_text()
    total = 0

    for key, path in SHOTS.items():
        if not path.exists():
            raise SystemExit(f'missing screenshot: {path}\nrun ./add-screenshots.sh first')

        raw = path.read_bytes()
        total += len(raw)
        b64 = base64.b64encode(raw).decode('ascii')
        tag = f'<img alt="{ALT[key]}" src="data:image/png;base64,{b64}">'

        marker = f'<!-- IMG:{key} -->'
        # Match the marker plus every embedded tag already following it, so a
        # re-run replaces rather than appends. The trailing * also cleans up
        # duplicates left by an earlier buggy run.
        pattern = re.compile(
            re.escape(marker)
            + rf'(?:\s*<img alt="{re.escape(ALT[key])}" src="data:image/png;base64,[^"]*">)*'
        )
        html, count = pattern.subn(lambda _: f'{marker}\n{tag}', html, count=1)
        if not count:
            raise SystemExit(f'could not find {marker} for {key}')
        print(f'embedded {key.lower():7s} {path.name}  {len(raw) // 1024}KB'
              f' -> {len(b64) // 1024}KB base64')

    GUIDE.write_text(html)
    size_mb = GUIDE.stat().st_size / 1_000_000
    print(f'\n{GUIDE.name} is now {size_mb:.2f}MB')
    if size_mb > MAX_MB:
        print(f'warning: over {MAX_MB}MB, consider downscaling the screenshots', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

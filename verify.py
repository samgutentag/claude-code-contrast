#!/usr/bin/env python3
"""Measure a Claude Code custom theme instead of eyeballing it.

Claude Code discards unrecognized theme override keys silently, so a typo
degrades contrast without any warning. This reads the theme file itself and
checks the tokens that actually carry the user/assistant distinction.

  python3 verify.py                          # default theme, black background
  python3 verify.py --bg '#282c34'           # measure against another terminal bg
  python3 verify.py --theme path/to.json     # a different theme file
  python3 verify.py --dichromat              # also simulate color blindness

Exits non-zero if any check fails, so it works in CI or a pre-commit hook.
"""

import argparse
import json
import pathlib
import sys

DEFAULT_THEME = pathlib.Path.home() / '.claude' / 'themes' / 'high-contrast-cb.json'
DEFAULT_BG = '#000000'

# Floors. userMessageBackground is a background, so WCAG's 3:1 non-text floor
# applies; the rest are text and use 4.5:1, with 7:1 where we can afford it.
TARGETS = {
    'userMessageBackground': 4.0,
    'briefLabelYou': 7.0,
    'briefLabelClaude': 7.0,
    'subtle': 4.5,
    'inactive': 7.0,
}

# The block's foreground is the global `text` token, so brightening the block
# costs legibility of the user's own typed text. Both sides must stay readable.
TEXT_ON_BLOCK_FLOOR = 4.5
BLOCK_TOKEN = 'userMessageBackground'
LABEL_PAIR = ('briefLabelYou', 'briefLabelClaude')

# Vienot 1999 dichromat simulation. Enough to rank candidate pairs; not a
# substitute for testing with actual colorblind readers.
RGB2LMS = ((0.31399, 0.63951, 0.04649),
           (0.15537, 0.75789, 0.08670),
           (0.01776, 0.10945, 0.87247))
LMS2RGB = ((5.47221206, -4.6419601, 0.16963708),
           (-1.1252419, 2.29317094, -0.1678952),
           (0.02980165, -0.19318073, 1.16364789))
DICHROMAT = {
    'protan': ((0, 1.05118294, -0.05116099), (0, 1, 0), (0, 0, 1)),
    'deutan': ((1, 0, 0), (0.9513092, 0, 0.04866992), (0, 0, 1)),
    'tritan': ((1, 0, 0), (0, 1, 0), (-0.86744736, 1.86727089, 0)),
}
# Below roughly this CIELAB distance a pair stops being reliably separable.
DELTA_E_FLOOR = 25.0


def srgb(color):
    h = color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f'not a hex color: {color}')
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def to_linear(channels):
    return [(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in channels]


def luminance(color):
    r, g, b = to_linear(srgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mul(matrix, vector):
    return [sum(matrix[i][j] * vector[j] for j in range(3)) for i in range(3)]


def simulate(color, kind):
    linear = to_linear(srgb(color))
    lms = _mul(DICHROMAT[kind], _mul(RGB2LMS, linear))
    rgb = [max(0.0, min(1.0, v)) for v in _mul(LMS2RGB, lms)]
    out = [(12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055) for v in rgb]
    return '#%02x%02x%02x' % tuple(round(v * 255) for v in out)


def _lab(color):
    r, g, b = to_linear(srgb(color))
    x = 0.4124 * r + 0.3576 * g + 0.1805 * b
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = 0.0193 * r + 0.1192 * g + 0.9505 * b

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x / 0.95047), f(y / 1.0), f(z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b):
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b))) ** 0.5


def load(path):
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(f'no theme file at {path}')
    except json.JSONDecodeError as err:
        raise SystemExit(f'{path} is not valid JSON: {err}')
    overrides = data.get('overrides')
    if not isinstance(overrides, dict):
        raise SystemExit(f'{path} has no "overrides" object')
    return overrides


def check_contrast(overrides, background):
    failures = 0
    for token, floor in TARGETS.items():
        value = overrides.get(token)
        if value is None:
            print(f'MISSING  {token}  (typo, or not overridden)')
            failures += 1
            continue
        try:
            ratio = contrast(value, background)
        except ValueError as err:
            print(f'BADCOLOR {token:26s} {err}')
            failures += 1
            continue
        ok = ratio >= floor
        failures += 0 if ok else 1
        print(f'{"PASS" if ok else "FAIL"}  {token:26s} {value}  {ratio:5.2f}:1  (floor {floor})')

    block = overrides.get(BLOCK_TOKEN)
    if block:
        ratio = contrast('#ffffff', block)
        ok = ratio >= TEXT_ON_BLOCK_FLOOR
        failures += 0 if ok else 1
        print(f'{"PASS" if ok else "FAIL"}  {"your text on block":26s} #ffffff  {ratio:5.2f}:1  '
              f'(floor {TEXT_ON_BLOCK_FLOOR})')
        if not ok:
            print('      the block is too bright; step it down, see README')
    return failures


def check_dichromat(overrides):
    you, claude = (overrides.get(t) for t in LABEL_PAIR)
    if not (you and claude):
        print(f'\nSKIP  dichromat check needs both {" and ".join(LABEL_PAIR)}')
        return 0
    print(f'\nlabel pair {you} / {claude} under simulated color blindness:')
    failures = 0
    for kind in DICHROMAT:
        a, b = simulate(you, kind), simulate(claude, kind)
        dist = delta_e(a, b)
        ok = dist >= DELTA_E_FLOOR
        failures += 0 if ok else 1
        print(f'  {"PASS" if ok else "FAIL"}  {kind:8s} {a} / {b}  deltaE {dist:5.1f}  '
              f'(floor {DELTA_E_FLOOR})')
    print(f'  normal    {you} / {claude}  deltaE {delta_e(you, claude):5.1f}')
    return failures


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--theme', type=pathlib.Path, default=DEFAULT_THEME,
                        help=f'theme JSON to measure (default: {DEFAULT_THEME})')
    parser.add_argument('--bg', default=DEFAULT_BG,
                        help=f'terminal background color (default: {DEFAULT_BG})')
    parser.add_argument('--dichromat', action='store_true',
                        help='also simulate protanopia, deuteranopia and tritanopia')
    args = parser.parse_args()

    try:
        luminance(args.bg)
    except ValueError as err:
        raise SystemExit(f'--bg: {err}')

    overrides = load(args.theme)
    print(f'theme: {args.theme}')
    print(f'background: {args.bg}\n')

    failures = check_contrast(overrides, args.bg)
    if args.dichromat:
        failures += check_dichromat(overrides)

    print('\nall checks passed' if not failures else f'\n{failures} problem(s)')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())

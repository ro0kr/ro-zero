"""Subset Ro Zero TTFs to Korean + English + punctuation."""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from glyph_coverage import keep_code

TTF_DIR = ROOT / "fonts" / "ttf"


def subset_font(path: Path) -> Path:
    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=False)
    cmap = font.getBestCmap() or {}
    unicodes = {code for code in cmap if keep_code(code)}
    options = Options()
    options.layout_features = []
    options.hinting = False
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.drop_tables += ["DSIG"]
    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)
    font.save(path)
    print(f"{path.name}: {len(unicodes)} chars -> {path.stat().st_size} bytes")
    return path


def main() -> None:
    paths = sorted(TTF_DIR.glob("RoZero-*.ttf"))
    if not paths:
        raise SystemExit(f"No RoZero TTFs in {TTF_DIR}")
    for path in paths:
        subset_font(path)


if __name__ == "__main__":
    main()

# Sources

Ro Zero is a **fork of Noto Sans**, not a from-scratch drawing.

This folder is the font source. There are no UFO or Glyphs masters.
The starting outlines are the unmodified Noto Sans TTFs in `../fonts/noto/`.
The Modified Version is built here:

- `fetch_fonts.py` — download unmodified Noto Sans / KR / Symbols
- `type_shatter.py` — shatter each glyph (seed = character code)
- `svg_pattern.py` — crack mesh
- `glyph_coverage.py` — Korean + English + punctuation keep-list
- `build_font.py` — compile Ro Zero TTFs
- `subset_kr_en.py` — subset shipped fonts
- `config.yaml` — family recipe
- `build.sh` — one-command build

```bash
./build.sh
```

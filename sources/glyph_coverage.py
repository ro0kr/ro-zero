"""Korean + English + punctuation coverage for shipped Ro Zero fonts."""

from __future__ import annotations

# Hangul, Latin (English / GF Latin Core-ish), and punctuation/symbols.
# Not CJK ideographs, kana, Arabic, Hebrew, Thai, or Indic.
_RANGES: tuple[tuple[int, int], ...] = (
    (0x0020, 0x007E),  # ASCII
    (0x00A0, 0x017F),  # Latin-1 + Latin Extended-A
    (0x02B0, 0x02FF),  # modifier letters
    (0x0300, 0x036F),  # combining marks
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x2000, 0x206F),  # general punctuation
    (0x2070, 0x209F),  # super/subscripts
    (0x20A0, 0x20CF),  # currency
    (0x2100, 0x23FF),  # letterlike, arrows, math, technical
    (0x2460, 0x27BF),  # enclosed, box, geometric, dingbats
    (0x2B00, 0x2BFF),  # misc symbols and arrows
    (0x3000, 0x303F),  # CJK punctuation (Korean)
    (0x3130, 0x318F),  # Hangul compatibility jamo
    (0xA960, 0xA97F),  # Hangul Jamo Extended-A
    (0xAC00, 0xD7A3),  # Hangul syllables
    (0xD7B0, 0xD7FF),  # Hangul Jamo Extended-B
    (0xFF00, 0xFF65),  # fullwidth ASCII / punct (not halfwidth kana)
    (0xFFA0, 0xFFDC),  # halfwidth Hangul
    (0xFFE0, 0xFFEF),  # fullwidth symbols
)


def keep_code(code: int) -> bool:
    for start, end in _RANGES:
        if start <= code <= end:
            return True
    return False

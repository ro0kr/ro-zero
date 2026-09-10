"""Download unmodified Noto Sans sources. Ro Zero is a fork of these fonts."""

from __future__ import annotations

import urllib.request
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts" / "noto"
FILES = {
    "NotoSans-Variable.ttf": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf",
    "NotoSansKR[wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
    "NotoSansJP[wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
    "NotoSansSC[wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
    "NotoSansSymbols-Variable.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf",
    "NotoSansSymbols2-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
    "NotoSansArabic[wdth,wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosansarabic/NotoSansArabic%5Bwdth%2Cwght%5D.ttf",
    "NotoSansHebrew[wdth,wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosanshebrew/NotoSansHebrew%5Bwdth%2Cwght%5D.ttf",
    "NotoSansThai[wdth,wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosansthai/NotoSansThai%5Bwdth%2Cwght%5D.ttf",
    "NotoSansDevanagari[wdth,wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf",
}


def ensure_fonts() -> None:
    FONTS.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        path = FONTS / name
        if path.exists() and path.stat().st_size > 10000:
            continue
        print(f"Downloading {name}")
        try:
            urllib.request.urlretrieve(url, path)
        except Exception as exc:
            print(f"Skip {name}: {exc}")
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    ensure_fonts()

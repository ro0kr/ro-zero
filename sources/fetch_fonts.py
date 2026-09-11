"""Download unmodified Noto Sans sources used by this fork."""

from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts" / "noto"
FILES = {
    "NotoSans-Variable.ttf": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf",
    "NotoSansKR[wght].ttf": "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
    "NotoSansSymbols-Variable.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf",
    "NotoSansSymbols2-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
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

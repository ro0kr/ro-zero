#!/usr/bin/env bash
# Rebuild Ro Zero from the Noto Sans fork sources.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -r requirements.txt
python3 fetch_fonts.py
python3 build_font.py --family
python3 sources/subset_kr_en.py
echo "Built fonts/ttf/RoZero-*.ttf (Korean + English + punctuation)"

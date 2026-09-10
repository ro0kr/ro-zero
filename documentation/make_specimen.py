"""Render documentation/ro-zero-specimen.png from Ro Zero Bold."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "fonts" / "ttf" / "RoZero-Bold.ttf"
OUT = Path(__file__).resolve().parent / "ro-zero-specimen.png"


def main() -> None:
    font_title = ImageFont.truetype(str(FONT), 168)
    font_line = ImageFont.truetype(str(FONT), 88)
    font_caption = ImageFont.truetype(str(FONT), 28)
    width, height = 1600, 720
    image = Image.new("RGB", (width, height), "#f7f3ea")
    draw = ImageDraw.Draw(image)
    draw.text((72, 88), "Ro Zero", font=font_title, fill="#111111")
    draw.text((72, 320), "가나다라 abcd 1234", font=font_line, fill="#111111")
    draw.text(
        (72, 500),
        "A fork of Noto Sans  ·  Noto Sans 포크  ·  Bold 700",
        font=font_caption,
        fill="#5c584f",
    )
    draw.rectangle((72, 640, 280, 644), fill="#111111")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

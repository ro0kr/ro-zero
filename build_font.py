"""Build Ro Zero: shattered Noto Sans as a TrueType file named ro-zero.ttf."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.timeTools import timestampNow
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from shapely.geometry import Polygon
from shapely.geometry.polygon import LinearRing

from type_shatter import (
    FONT_KINDS,
    UPM,
    _instance,
    black900_radius,
    shatter_glyph_em,
)

ROOT = Path(__file__).resolve().parent
DOWNLOADS = ROOT / "downloads"
USER_DOWNLOADS = Path.home() / "Downloads"
USER_DESKTOP = Path.home() / "Desktop"
ARTIFACTS = Path("/opt/cursor/artifacts")
FONT_NAME = "ro-zero.ttf"
ZIP_NAME = "ro-zero-100-900.zip"
STATUS_NAME = "ro-zero.status.json"
WEIGHT = 500
_BUILD_WEIGHT = 500
FAMILY = "Ro Zero"
STYLE = "Medium"
PS_NAME = "RoZero-Medium"
SIMPLIFY = 2.0
FAMILY_WEIGHTS: tuple[tuple[int, str], ...] = (
    (100, "Thin"),
    (200, "ExtraLight"),
    (300, "Light"),
    (400, "Regular"),
    (500, "Medium"),
    (600, "SemiBold"),
    (700, "Bold"),
    (800, "ExtraBold"),
    (900, "Black"),
)


def glyph_name(code: int) -> str:
    if code < 0x10000:
        return f"uni{code:04X}"
    return f"u{code:05X}"


def usable_code(code: int) -> bool:
    if code < 0x20:
        return False
    if 0x7F <= code <= 0x9F:
        return False
    if 0xD800 <= code <= 0xDFFF:
        return False
    if 0xFE00 <= code <= 0xFE0F:
        return False
    if 0xE0100 <= code <= 0xE01EF:
        return False
    if code in (0xFEFF, 0xFFFE, 0xFFFF):
        return False
    return True


def collect_codepoints() -> list[int]:
    codes: set[int] = set()
    for kind in FONT_KINDS:
        try:
            font = _instance(kind, WEIGHT)
        except Exception:
            continue
        cmap = font.getBestCmap() or {}
        codes.update(cmap.keys())
    return sorted(code for code in codes if usable_code(code))


def _signed_area(points: list[tuple[int, int]]) -> float:
    total = 0.0
    count = len(points)
    for i, (x, y) in enumerate(points):
        nx, ny = points[(i + 1) % count]
        total += x * ny - nx * y
    return total * 0.5


def _ring_points(ring: LinearRing, clockwise: bool) -> list[tuple[int, int]]:
    raw = [(int(round(x)), int(round(y))) for x, y in ring.coords]
    cleaned: list[tuple[int, int]] = []
    for point in raw:
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    if len(cleaned) < 3:
        return []
    ccw = _signed_area(cleaned) > 0
    if clockwise == ccw:
        cleaned.reverse()
    return cleaned


def contours_from_polys(polys: list[Polygon]) -> list[list[tuple[int, int]]]:
    contours: list[list[tuple[int, int]]] = []
    for poly in polys:
        try:
            simple = poly.simplify(SIMPLIFY, preserve_topology=True)
        except Exception:
            simple = poly
        if simple.is_empty:
            continue
        if simple.geom_type == "Polygon":
            parts = [simple]
        elif simple.geom_type == "MultiPolygon":
            parts = [item for item in simple.geoms if item.geom_type == "Polygon"]
        else:
            continue
        for part in parts:
            outer = _ring_points(part.exterior, clockwise=True)
            if len(outer) >= 3:
                contours.append(outer)
            for hole in part.interiors:
                inner = _ring_points(hole, clockwise=False)
                if len(inner) >= 3:
                    contours.append(inner)
    return contours


def _glyph_from_contours(contours: list[list[tuple[int, int]]]):
    pen = TTGlyphPen(None)
    for contour in contours:
        pen.moveTo(contour[0])
        for point in contour[1:]:
            pen.lineTo(point)
        pen.closePath()
    return pen.glyph()


def _worker(code: int) -> tuple[int, float, list[list[tuple[int, int]]]]:
    char = chr(code)
    try:
        polys, advance = shatter_glyph_em(char, _BUILD_WEIGHT, persist_mesh=True)
    except Exception:
        return code, 0.0, []
    return code, float(advance), contours_from_polys(polys)


def write_status(payload: dict) -> None:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    path = DOWNLOADS / STATUS_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def output_paths(dest: Path | None = None) -> list[Path]:
    paths = [dest] if dest else [DOWNLOADS / FONT_NAME]
    extras = [USER_DOWNLOADS / FONT_NAME, USER_DESKTOP / FONT_NAME]
    if ARTIFACTS.is_dir():
        extras.append(ARTIFACTS / FONT_NAME)
    for extra in extras:
        if extra not in paths:
            paths.append(extra)
    return [path for path in paths if path is not None]


def _copy_outputs(master: Path) -> list[str]:
    written = [str(master)]
    for path in output_paths(master):
        if path.resolve() == master.resolve():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(master, path)
        written.append(str(path))
    return written


def _source_metrics() -> dict:
    font = _instance("lgc", WEIGHT)
    os2 = font["OS/2"]
    hhea = font["hhea"]
    return {
        "ascent": int(hhea.ascent),
        "descent": int(hhea.descent),
        "lineGap": int(hhea.lineGap),
        "typoAscender": int(os2.sTypoAscender),
        "typoDescender": int(os2.sTypoDescender),
        "typoLineGap": int(os2.sTypoLineGap),
        "winAscent": int(os2.usWinAscent),
        "winDescent": int(os2.usWinDescent),
        "sCapHeight": int(getattr(os2, "sCapHeight", 714) or 714),
        "sxHeight": int(getattr(os2, "sxHeight", 536) or 536),
        "ySubscriptXSize": int(os2.ySubscriptXSize or 650),
        "ySubscriptYSize": int(os2.ySubscriptYSize or 600),
        "ySubscriptXOffset": int(os2.ySubscriptXOffset or 0),
        "ySubscriptYOffset": int(os2.ySubscriptYOffset or 75),
        "ySuperscriptXSize": int(os2.ySuperscriptXSize or 650),
        "ySuperscriptYSize": int(os2.ySuperscriptYSize or 600),
        "ySuperscriptXOffset": int(os2.ySuperscriptXOffset or 0),
        "ySuperscriptYOffset": int(os2.ySuperscriptYOffset or 350),
        "yStrikeoutSize": int(os2.yStrikeoutSize or 50),
        "yStrikeoutPosition": int(os2.yStrikeoutPosition or 300),
        "underlinePosition": int(font["post"].underlinePosition or -100),
        "underlineThickness": int(font["post"].underlineThickness or 50),
        "panose": os2.panose,
    }


def _style_for_weight(weight: int) -> str:
    for value, name in FAMILY_WEIGHTS:
        if value == weight:
            return name
    return "Medium"


def _fs_selection(weight: int) -> int:
    if weight >= 700:
        return 0x0020  # BOLD
    if weight == 400:
        return 0x0040  # REGULAR
    return 0


def assemble_font(
    rows: list[tuple[int, float, list[list[tuple[int, int]]]]],
    dest: Path,
    weight: int = 500,
) -> None:
    style = _style_for_weight(weight)
    ps_name = f"RoZero-{style}"
    metrics_src = _source_metrics()
    cmap: dict[int, str] = {}
    glyphs: dict = {}
    advances: dict[str, float] = {}

    notdef = _glyph_from_contours(
        contours_from_polys(shatter_glyph_em("?", weight, persist_mesh=True)[0])
    )
    glyphs[".notdef"] = notdef
    advances[".notdef"] = 600
    glyphs[".null"] = _glyph_from_contours([])
    advances[".null"] = 0
    glyphs["space"] = _glyph_from_contours([])
    advances["space"] = 250
    cmap[0x20] = "space"
    cmap[0xA0] = "space"

    for code, advance, contours in rows:
        if code in (0x20, 0xA0):
            advances["space"] = max(advances["space"], advance if advance > 0 else 250)
            continue
        name = glyph_name(code)
        glyphs[name] = _glyph_from_contours(contours)
        advances[name] = advance if advance > 0 else 250
        cmap[code] = name

    order = [".notdef", ".null", "space"] + [
        glyph_name(code) for code, _, _ in sorted(rows, key=lambda item: item[0]) if code not in (0x20, 0xA0)
    ]
    # Keep only names we actually created.
    order = [name for name in order if name in glyphs]

    fb = FontBuilder(int(UPM), isTTF=True)
    now = timestampNow()
    fb.setupHead(
        fontRevision=1.0,
        lowestRecPPEM=8,
        created=now,
        modified=now,
        macStyle=1 if weight >= 700 else 0,
    )
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap, allowFallback=True)
    fb.setupGlyf(glyphs)
    hmtx = {}
    glyf = fb.font["glyf"]
    for name, width in advances.items():
        glyph = glyf[name]
        lsb = int(getattr(glyph, "xMin", 0) or 0)
        hmtx[name] = (max(int(round(width)), 0), lsb)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(
        ascent=metrics_src["ascent"],
        descent=metrics_src["descent"],
        lineGap=metrics_src["lineGap"],
    )
    fb.setupNameTable(
        {
            "copyright": "Ro Zero is derived from Noto Sans under the SIL Open Font License 1.1.",
            "familyName": FAMILY,
            "styleName": style,
            "uniqueFontIdentifier": f"Ro Zero {style}; {weight}; roughness 0; 100 shards; 30% gaps",
            "fullName": f"{FAMILY} {style}",
            "psName": ps_name,
            "version": "Version 1.000",
            "manufacturer": "Ro Zero",
            "description": (
                "Shattered Noto Sans. 100 pieces, 30% crack gaps, roughness 0. "
                "Seed is the character code. Corner radius from Noto Sans Black 900."
            ),
            "licenseDescription": (
                "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
                "This license is available with a FAQ at: https://openfontlicense.org"
            ),
            "licenseInfoURL": "https://openfontlicense.org",
            "typographicFamily": FAMILY,
            "typographicSubfamily": style,
            "sampleText": "가나다라 abcd 1234",
        }
    )
    fb.setupOS2(
        sTypoAscender=metrics_src["typoAscender"],
        sTypoDescender=metrics_src["typoDescender"],
        sTypoLineGap=metrics_src["typoLineGap"],
        usWinAscent=metrics_src["winAscent"],
        usWinDescent=metrics_src["winDescent"],
        usWeightClass=weight,
        usWidthClass=5,
        fsSelection=_fs_selection(weight),
        achVendID="ROZR",
        sCapHeight=metrics_src["sCapHeight"],
        sxHeight=metrics_src["sxHeight"],
        fsType=0,
        ySubscriptXSize=metrics_src["ySubscriptXSize"],
        ySubscriptYSize=metrics_src["ySubscriptYSize"],
        ySubscriptXOffset=metrics_src["ySubscriptXOffset"],
        ySubscriptYOffset=metrics_src["ySubscriptYOffset"],
        ySuperscriptXSize=metrics_src["ySuperscriptXSize"],
        ySuperscriptYSize=metrics_src["ySuperscriptYSize"],
        ySuperscriptXOffset=metrics_src["ySuperscriptXOffset"],
        ySuperscriptYOffset=metrics_src["ySuperscriptYOffset"],
        yStrikeoutSize=metrics_src["yStrikeoutSize"],
        yStrikeoutPosition=metrics_src["yStrikeoutPosition"],
    )
    fb.setupPost(
        keepGlyphNames=False,
        underlinePosition=metrics_src["underlinePosition"],
        underlineThickness=metrics_src["underlineThickness"],
    )
    fb.setupDummyDSIG()
    fb.font["OS/2"].panose = metrics_src["panose"]
    fb.font["OS/2"].recalcCodePageRanges(fb.font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fb.save(dest)


def build_ro_zero_font(
    dest: Path | None = None,
    codes: list[int] | None = None,
    workers: int | None = None,
    install: bool = True,
    weight: int = 500,
) -> Path:
    global _BUILD_WEIGHT
    _BUILD_WEIGHT = weight
    dest = dest or (DOWNLOADS / FONT_NAME)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if install:
        USER_DOWNLOADS.mkdir(parents=True, exist_ok=True)
        USER_DESKTOP.mkdir(parents=True, exist_ok=True)
    codes = list(codes) if codes is not None else collect_codepoints()
    workers = max(1, workers or (os.cpu_count() or 2))
    started = time.time()
    if install:
        write_status(
        {
            "state": "building",
            "done": 0,
            "total": len(codes),
            "weight": weight,
            "style": _style_for_weight(weight),
            "workers": workers,
            "radius": round(black900_radius(UPM), 3),
        }
    )
    rows: list[tuple[int, float, list[list[tuple[int, int]]]]] = []
    if workers == 1 or len(codes) < 8:
        for i, code in enumerate(codes, start=1):
            rows.append(_worker(code))
            if i == 1 or i % 25 == 0 or i == len(codes):
                if install:
                    write_status(
                        {
                            "state": "building",
                            "done": i,
                            "total": len(codes),
                            "workers": 1,
                            "elapsed": round(time.time() - started, 1),
                        }
                    )
                print(f"shatter {i}/{len(codes)}", flush=True)
    else:
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=workers) as pool:
            for i, row in enumerate(pool.imap(_worker, codes, chunksize=8), start=1):
                rows.append(row)
                if i == 1 or i % 50 == 0 or i == len(codes):
                    if install:
                        write_status(
                            {
                                "state": "building",
                                "done": i,
                                "total": len(codes),
                                "workers": workers,
                                "elapsed": round(time.time() - started, 1),
                            }
                        )
                    print(f"shatter {i}/{len(codes)}", flush=True)
    if install:
        write_status(
            {
                "state": "compiling",
                "done": len(rows),
                "total": len(codes),
                "elapsed": round(time.time() - started, 1),
            }
        )
    print(f"compiling TrueType {_style_for_weight(weight)} {weight}", flush=True)
    assemble_font(rows, dest, weight=weight)
    copies = _copy_outputs(dest) if install else [str(dest)]
    payload = {
        "state": "ready",
        "done": len(rows),
        "total": len(codes),
        "glyphs": len(rows),
        "bytes": dest.stat().st_size,
        "path": str(dest),
        "copies": copies,
        "elapsed": round(time.time() - started, 1),
        "download": "/download/ro-zero.ttf",
    }
    if install:
        write_status(payload)
    print(f"wrote {dest} ({dest.stat().st_size} bytes)", flush=True)
    return dest


def repair_empty_glyphs(path: Path, workers: int | None = None) -> Path:
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    cmap = font.getBestCmap() or {}
    empty = []
    for code, name in cmap.items():
        if name in (".notdef", ".null", "space"):
            continue
        if font["glyf"][name].numberOfContours == 0:
            empty.append(code)
    workers = max(1, workers or (os.cpu_count() or 2))
    print(f"repair {len(empty)} empty glyphs", flush=True)
    if not empty:
        return path
    write_status({"state": "building", "done": 0, "total": len(empty), "repair": True})
    rows: dict[int, tuple[float, list[list[tuple[int, int]]]]] = {}
    if workers == 1:
        done_rows = [_worker(code) for code in empty]
    else:
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=workers) as pool:
            done_rows = list(pool.imap(_worker, empty, chunksize=8))
    for code, advance, contours in done_rows:
        rows[code] = (advance, contours)
    filled = 0
    for code, (advance, contours) in rows.items():
        if not contours:
            continue
        name = cmap[code]
        glyph = _glyph_from_contours(contours)
        font["glyf"][name] = glyph
        glyph.recalcBounds(font["glyf"])
        font["hmtx"][name] = (max(int(round(advance)), 0), int(getattr(glyph, "xMin", 0) or 0))
        filled += 1
    font.save(path)
    copies = _copy_outputs(path)
    write_status(
        {
            "state": "ready",
            "done": len(empty),
            "total": len(empty),
            "glyphs": len(cmap),
            "repaired": filled,
            "bytes": path.stat().st_size,
            "path": str(path),
            "copies": copies,
            "download": "/download/ro-zero.ttf",
        }
    )
    print(f"repaired {filled}/{len(empty)} -> {path.stat().st_size} bytes", flush=True)
    return path


def sanitize_installed_font(path: Path, weight: int | None = None) -> Path:
    """Rewrite tables so Windows/Chrome OTS will accept the TTF."""
    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=True)
    if "ltag" in font:
        del font["ltag"]
    metrics = _source_metrics()
    os2 = font["OS/2"]
    if weight is None:
        weight = int(os2.usWeightClass or 500)
    os2.ySubscriptXSize = metrics["ySubscriptXSize"]
    os2.ySubscriptYSize = metrics["ySubscriptYSize"]
    os2.ySubscriptXOffset = metrics["ySubscriptXOffset"]
    os2.ySubscriptYOffset = metrics["ySubscriptYOffset"]
    os2.ySuperscriptXSize = metrics["ySuperscriptXSize"]
    os2.ySuperscriptYSize = metrics["ySuperscriptYSize"]
    os2.ySuperscriptXOffset = metrics["ySuperscriptXOffset"]
    os2.ySuperscriptYOffset = metrics["ySuperscriptYOffset"]
    os2.yStrikeoutSize = metrics["yStrikeoutSize"]
    os2.yStrikeoutPosition = metrics["yStrikeoutPosition"]
    os2.panose = metrics["panose"]
    os2.usWeightClass = weight
    os2.fsSelection = _fs_selection(weight)
    os2.achVendID = "ROZR"
    os2.fsType = 0
    os2.recalcCodePageRanges(font)
    os2.updateFirstAndLastCharIndex(font)
    post = font["post"]
    post.formatType = 3.0
    post.extraNames = []
    post.mapping = {}
    post.underlinePosition = metrics["underlinePosition"]
    post.underlineThickness = metrics["underlineThickness"]
    gasp = newTable("gasp")
    gasp.gaspRange = {8: 10, 65535: 15}
    font["gasp"] = gasp
    dsig = newTable("DSIG")
    dsig.ulVersion = 1
    dsig.usFlag = 0
    dsig.usNumSigs = 0
    dsig.signatureRecords = []
    font["DSIG"] = dsig
    font["head"].lowestRecPPEM = 8
    font["head"].macStyle = 1 if weight >= 700 else 0
    font["head"].modified = timestampNow()
    font.save(path)
    return path


def write_preview_subset(src: Path, dest: Path, text: str) -> Path:
    from fontTools.subset import Options, Subsetter

    font = TTFont(src, recalcBBoxes=False, recalcTimestamp=False)
    options = Options()
    options.layout_features = []
    options.hinting = False
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.drop_tables += ["DSIG"]
    subsetter = Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    font.save(dest)
    return dest


OFL_TEXT = """This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is available with a FAQ at: https://openfontlicense.org

Ro Zero is derived from Noto Sans (Copyright 2015-2022 Google LLC).
"""


def build_family_zip(
    codes: list[int] | None = None,
    workers: int | None = None,
    out_dir: Path | None = None,
    report: bool = True,
) -> Path:
    codes = list(codes) if codes is not None else collect_codepoints()
    workers = workers or None
    root = out_dir or DOWNLOADS
    family_dir = root / "family"
    family_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    ttf_paths: list[Path] = []
    for index, (weight, style) in enumerate(FAMILY_WEIGHTS, start=1):
        dest = family_dir / f"RoZero-{style}.ttf"
        print(f"=== {style} {weight} ({index}/{len(FAMILY_WEIGHTS)}) ===", flush=True)
        if report:
            write_status(
                {
                    "state": "building",
                    "weight": weight,
                    "style": style,
                    "weights_done": index - 1,
                    "weights_total": len(FAMILY_WEIGHTS),
                    "done": 0,
                    "total": len(codes),
                    "download": "/download/ro-zero-100-900.zip",
                }
            )
        build_ro_zero_font(dest=dest, codes=codes, workers=workers, install=False, weight=weight)
        sanitize_installed_font(dest, weight=weight)
        ttf_paths.append(dest)
    ofl = family_dir / "OFL.txt"
    repo_ofl = ROOT / "OFL.txt"
    if repo_ofl.exists():
        shutil.copy2(repo_ofl, ofl)
    else:
        ofl.write_text(OFL_TEXT, encoding="utf-8")
    if root.resolve() == DOWNLOADS.resolve():
        ttf_dir = ROOT / "fonts" / "ttf"
        ttf_dir.mkdir(parents=True, exist_ok=True)
        for path in ttf_paths:
            shutil.copy2(path, ttf_dir / path.name)
    zip_path = root / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in ttf_paths:
            archive.write(path, arcname=path.name)
        archive.write(ofl, arcname="OFL.txt")
    copies = [str(zip_path)]
    if report:
        for extra in (USER_DOWNLOADS / ZIP_NAME, ARTIFACTS / ZIP_NAME):
            try:
                extra.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(zip_path, extra)
                copies.append(str(extra))
            except OSError as exc:
                print(f"skip copy {extra}: {exc}", flush=True)
        write_status(
            {
                "state": "ready",
                "download": "/download/ro-zero-100-900.zip",
                "bytes": zip_path.stat().st_size,
                "fonts": [path.name for path in ttf_paths],
                "glyphs": len(codes),
                "copies": copies,
                "elapsed": round(time.time() - started, 1),
            }
        )
    print(f"wrote {zip_path} ({zip_path.stat().st_size} bytes)", flush=True)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build downloads/ro-zero.ttf")
    parser.add_argument("--limit", type=int, default=0, help="Build only the first N codepoints")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--repair", action="store_true", help="Refill empty glyphs in an existing font")
    parser.add_argument("--sanitize", action="store_true", help="Fix tables on an existing TTF")
    parser.add_argument("--family", action="store_true", help="Build Thin–Black TTFs and zip them")
    args = parser.parse_args()
    dest = args.out or (DOWNLOADS / FONT_NAME)
    if args.family:
        codes = collect_codepoints()
        if args.limit:
            codes = codes[: args.limit]
        build_family_zip(codes=codes, workers=args.workers or None)
        return
    if args.sanitize:
        sanitize_installed_font(dest)
        copies = _copy_outputs(dest)
        write_status(
            {
                "state": "ready",
                "glyphs": len(TTFont(dest).getGlyphOrder()),
                "bytes": dest.stat().st_size,
                "path": str(dest),
                "copies": copies,
                "download": "/download/ro-zero.ttf",
            }
        )
        print(f"sanitized {dest} ({dest.stat().st_size} bytes)", flush=True)
        return
    if args.repair:
        repair_empty_glyphs(dest, workers=args.workers or None)
        return
    codes = collect_codepoints()
    if args.limit:
        codes = codes[: args.limit]
    workers = args.workers or None
    build_ro_zero_font(dest=dest, codes=codes, workers=workers)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        write_status({"state": "error", "error": "interrupted"})
        sys.exit(130)

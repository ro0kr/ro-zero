"""Shatter Noto Sans glyphs. Seed is the character code, never the weight."""

from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree
from shapely.validation import make_valid

from fetch_fonts import ensure_fonts
from svg_pattern import (
    DEFAULT_PIECES,
    DEFAULT_ROUGHNESS,
    DEFAULT_WHITE_RATIO,
    MESH_SIZE,
    PatternConfig,
    build_fracture,
    char_seed,
)

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "fonts" / "noto"
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)
ensure_fonts()
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)
FONT_KINDS = ("lgc", "kr", "sym", "sym2")
QUAD_SEGS = 2  # coarse corner rounding, not a 36-gon
FONT_SIZE = 96.0
UPM = 1000.0
MIN_AREA_EM = 15.6

SPECIMEN_ROWS: tuple[tuple[str, str], ...] = (
    ("Test", "가나다라 abcd 1234"),
)


class FlattenPen(BasePen):
    def __init__(self, glyph_set, steps: int = 5) -> None:
        super().__init__(glyph_set)
        self.steps = steps
        self.contours: list[list[tuple[float, float]]] = []
        self._current: list[tuple[float, float]] = []

    def _moveTo(self, pt) -> None:
        self._flush()
        self._current = [pt]

    def _lineTo(self, pt) -> None:
        self._current.append(pt)

    def _curveToOne(self, p1, p2, p3) -> None:
        p0 = self._current[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1.0 - t
            x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
            self._current.append((x, y))

    def _qCurveToOne(self, p1, p2) -> None:
        p0 = self._current[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1.0 - t
            x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
            y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
            self._current.append((x, y))

    def _closePath(self) -> None:
        self._flush()

    def _endPath(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if len(self._current) >= 3:
            self.contours.append(self._current)
        self._current = []


def _font_file(name: str) -> Path:
    matches = list(FONTS.glob(name))
    if not matches:
        raise FileNotFoundError(f"Missing font {name} in {FONTS}")
    return matches[0]


@lru_cache(maxsize=16)
def _base_font(kind: str) -> TTFont:
    mapping = {
        "lgc": "NotoSans-Variable.ttf",
        "kr": "NotoSansKR*.ttf",
        "sym": "NotoSansSymbols-Variable.ttf",
        "sym2": "NotoSansSymbols2-Regular.ttf",
    }
    return TTFont(_font_file(mapping[kind]), lazy=True)


def _pick_kind(char: str) -> str:
    code = ord(char)
    if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "kr"
    if code >= 0x1F000 or 0x2600 <= code <= 0x27BF or 0x2B00 <= code <= 0x2BFF:
        return "sym2"
    if 0x2190 <= code <= 0x22FF or 0x20A0 <= code <= 0x20CF or 0x2100 <= code <= 0x23FF:
        return "sym"
    return "lgc"


@lru_cache(maxsize=64)
def _instance(kind: str, weight: int) -> TTFont:
    try:
        font = _base_font(kind)
    except FileNotFoundError:
        font = _base_font("lgc")
    axes = {axis.axisTag for axis in font["fvar"].axes} if "fvar" in font else set()
    if not axes:
        return font
    location = {}
    if "wght" in axes:
        location["wght"] = float(weight)
    if "wdth" in axes:
        location["wdth"] = 100.0
    return instantiateVariableFont(font, location, inplace=False)


def _glyph_name(font: TTFont, char: str) -> str | None:
    cmap = font.getBestCmap() or {}
    return cmap.get(ord(char))


def glyph_geometry(char: str, weight: int) -> tuple[BaseGeometry | None, float]:
    kind = _pick_kind(char)
    try:
        font = _instance(kind, weight)
    except Exception:
        font = _instance("lgc", weight)
    name = _glyph_name(font, char)
    if name is None and kind != "lgc":
        font = _instance("lgc", weight)
        name = _glyph_name(font, char)
    if name is None:
        for fallback in ("sym", "sym2"):
            try:
                font = _instance(fallback, weight)
            except Exception:
                continue
            name = _glyph_name(font, char)
            if name:
                break
    if name is None:
        return None, 0.0
    glyph_set = font.getGlyphSet()
    pen = FlattenPen(glyph_set, steps=5)
    glyph_set[name].draw(pen)
    advance = float(glyph_set[name].width)
    rings = []
    for contour in pen.contours:
        try:
            poly = make_valid(Polygon(contour))
        except Exception:
            continue
        if not poly.is_empty and poly.area > 1e-4:
            rings.append(poly)
    if not rings:
        return None, advance
    rings.sort(key=lambda item: item.area, reverse=True)
    geom: BaseGeometry = rings[0]
    for ring in rings[1:]:
        if geom.contains(ring.representative_point()):
            geom = geom.difference(ring)
        else:
            geom = geom.union(ring)
    geom = make_valid(geom)
    if geom.is_empty:
        return None, advance
    return geom, advance


def fillet(geom: BaseGeometry, radius: float) -> BaseGeometry | None:
    if geom is None or geom.is_empty or radius <= 0:
        return None
    try:
        shrunk = geom.buffer(-radius, quad_segs=QUAD_SEGS, join_style=1)
        if shrunk.is_empty:
            return None
        rounded = shrunk.buffer(radius, quad_segs=QUAD_SEGS, join_style=1)
    except Exception:
        return None
    if rounded.is_empty or rounded.area < 1e-3:
        return None
    return make_valid(rounded)


@lru_cache(maxsize=1)
def black900_radius(font_size: float = FONT_SIZE) -> float:
    """Corner radius taken from Noto Sans Black 900, then reused for every weight."""
    geom, _ = glyph_geometry("I", 900)
    if geom is None or geom.is_empty:
        return font_size * 0.08
    minx, _, maxx, _ = geom.bounds
    stem = max(maxx - minx, 1.0)
    # Small enough that 160 shards can keep an R, taken from Black 900 stem.
    radius_em = min(max(stem * 0.03, 4.0), 12.0)
    return radius_em * (font_size / 1000.0)


def _iter_polys(geom: BaseGeometry) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        out: list[Polygon] = []
        for item in geom.geoms:
            out.extend(_iter_polys(item))
        return out
    return []


def _mesh_cache_path(seed: int) -> Path:
    rough = f"{DEFAULT_ROUGHNESS:.2f}"
    ratio = f"{DEFAULT_WHITE_RATIO:.2f}"
    return CACHE / f"mesh-{seed}-{DEFAULT_PIECES}-{MESH_SIZE}-r{rough}-g{ratio}.pkl"


def _build_mesh_polys(seed: int) -> list[Polygon]:
    fracture = build_fracture(
        PatternConfig(
            pieces=DEFAULT_PIECES,
            white_ratio=DEFAULT_WHITE_RATIO,
            seed=seed,
            size=MESH_SIZE,
            roughness=DEFAULT_ROUGHNESS,
        )
    )
    scale = UPM / MESH_SIZE
    polys: list[Polygon] = []
    for shard in fracture.shards:
        scaled = [(x * scale, y * scale) for x, y in shard]
        poly = Polygon(scaled)
        if poly.is_valid and not poly.is_empty:
            polys.append(poly)
    return polys


def _mesh_polys(seed: int, persist: bool) -> list[Polygon]:
    cache_file = _mesh_cache_path(seed)
    if persist and cache_file.exists():
        with cache_file.open("rb") as handle:
            coords = pickle.load(handle)
        return [Polygon(item) for item in coords if len(item) >= 3]
    polys = _build_mesh_polys(seed)
    if persist:
        stored = [list(poly.exterior.coords) for poly in polys]
        with cache_file.open("wb") as handle:
            pickle.dump(stored, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return polys


@lru_cache(maxsize=256)
def _mesh_tree(seed: int) -> tuple[STRtree, tuple[Polygon, ...]]:
    polys = _mesh_polys(seed, persist=True)
    return STRtree(polys), tuple(polys)


def _cover_square(bounds: tuple[float, float, float, float]) -> tuple[float, float, float]:
    minx, miny, maxx, maxy = bounds
    pad = 12.0
    width = max(maxx - minx, 1.0)
    height = max(maxy - miny, 1.0)
    side = max(width, height) + pad * 2
    cx = (minx + maxx) * 0.5
    cy = (miny + maxy) * 0.5
    return cx - side * 0.5, cy - side * 0.5, side


def _to_font(geom: BaseGeometry, ox: float, oy: float, factor: float) -> BaseGeometry:
    return affinity.translate(affinity.scale(geom, 1.0 / factor, 1.0 / factor, origin=(0.0, 0.0)), ox, oy)


def shatter_glyph_em(
    char: str,
    weight: int,
    *,
    persist_mesh: bool = True,
) -> tuple[list[Polygon], float]:
    """Shatter a glyph in font units (1000 UPM, y-up, baseline origin)."""
    seed = char_seed(char)
    glyph, advance = glyph_geometry(char, weight)
    if glyph is None or glyph.is_empty:
        return [], advance
    ox, oy, side = _cover_square(glyph.bounds)
    factor = UPM / side
    mapped = affinity.scale(affinity.translate(glyph, -ox, -oy), factor, factor, origin=(0.0, 0.0))
    radius = black900_radius(UPM) * factor
    if persist_mesh:
        tree, shards = _mesh_tree(seed)
    else:
        shards_list = _mesh_polys(seed, persist=False)
        tree, shards = STRtree(shards_list), tuple(shards_list)
    hits = tree.query(mapped)
    kept: list[Polygon] = []
    raw_kept: list[Polygon] = []
    geoms = getattr(tree, "geometries", shards)
    for index in hits:
        shard = geoms[int(index)]
        try:
            piece = shard.intersection(mapped)
        except Exception:
            continue
        for poly in _iter_polys(_to_font(piece, ox, oy, factor)):
            if not poly.is_empty and poly.area >= 1.0:
                raw_kept.append(poly)
        rounded = fillet(piece, radius)
        if rounded is None:
            continue
        for poly in _iter_polys(_to_font(rounded, ox, oy, factor)):
            if poly.is_empty or poly.area < MIN_AREA_EM:
                continue
            kept.append(poly)
    return (kept or raw_kept), advance


def shatter_glyph(char: str, weight: int, font_size: float = FONT_SIZE) -> tuple[list[Polygon], float]:
    pieces, advance = shatter_glyph_em(char, weight)
    scale = font_size / UPM
    kept: list[Polygon] = []
    for poly in pieces:
        moved = [(x * scale, -y * scale + font_size) for x, y in poly.exterior.coords]
        if len(moved) < 4:
            continue
        try:
            placed = Polygon(moved)
        except Exception:
            continue
        if placed.is_empty or placed.area < 0.4:
            continue
        kept.append(placed)
    return kept, advance * scale


def _fmt(value: float) -> str:
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _path(poly: Polygon) -> str:
    coords = list(poly.exterior.coords)
    parts = [f"M {_fmt(coords[0][0])} {_fmt(coords[0][1])}"]
    for x, y in coords[1:]:
        parts.append(f"L {_fmt(x)} {_fmt(y)}")
    parts.append("Z")
    return " ".join(parts)


def render_line(text: str, weight: int, origin_x: float, origin_y: float, font_size: float = FONT_SIZE) -> tuple[list[str], float]:
    paths: list[str] = []
    x = origin_x
    for char in text:
        if char == " ":
            x += font_size * 0.33
            continue
        pieces, advance = shatter_glyph(char, weight, font_size)
        for poly in pieces:
            shifted = Polygon([(px + x, py + origin_y) for px, py in poly.exterior.coords])
            if not shifted.is_empty:
                paths.append(_path(shifted))
        x += max(advance, font_size * 0.22)
    return paths, x - origin_x


def render_weight_svg(weight: int, font_size: float = FONT_SIZE) -> str:
    margin = 28.0
    row_h = font_size * 1.55
    paths: list[str] = []
    width = margin
    y = margin
    for _label, text in SPECIMEN_ROWS:
        row_paths, row_w = render_line(text, weight, margin, y, font_size)
        paths.extend(row_paths)
        width = max(width, margin + row_w + margin)
        y += row_h
    height = y + margin * 0.4
    body = "\n  ".join(f'<path d="{d}" fill="#000000"/>' for d in paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(width)} {_fmt(height)}" '
        f'width="{_fmt(width)}" height="{_fmt(height)}">\n'
        f"  {body}\n"
        f"</svg>\n"
    )


def render_specimen_svg(font_size: float = 56.0) -> str:
    margin = 36.0
    row_h = font_size * 1.5
    block_gap = font_size * 0.9
    paths: list[str] = []
    width = margin
    y = margin
    for weight in WEIGHTS:
        for _label, text in SPECIMEN_ROWS:
            row_paths, row_w = render_line(text, weight, margin, y, font_size)
            paths.extend(row_paths)
            width = max(width, margin + row_w + margin)
            y += row_h
        y += block_gap
    height = y + margin * 0.2
    body = "\n  ".join(f'<path d="{d}" fill="#000000"/>' for d in paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(width)} {_fmt(height)}" '
        f'width="{_fmt(width)}" height="{_fmt(height)}">\n'
        f"  {body}\n"
        f"</svg>\n"
    )

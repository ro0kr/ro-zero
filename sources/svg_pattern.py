"""Previous jagged shatter: impact cracks, then inset gaps."""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from shapely.geometry import Polygon
from shapely.validation import make_valid

Point = tuple[float, float]
Poly = list[Point]

DEFAULT_PIECES = 100
DEFAULT_WHITE_RATIO = 0.30
DEFAULT_ROUGHNESS = 0.0
MESH_SIZE = 420


@dataclass(frozen=True)
class PatternConfig:
    pieces: int = DEFAULT_PIECES
    white_ratio: float = DEFAULT_WHITE_RATIO
    seed: int = 65
    size: int = MESH_SIZE
    roughness: float = DEFAULT_ROUGHNESS

    def __post_init__(self) -> None:
        if self.pieces < 2:
            raise ValueError("pieces must be at least 2")
        if self.pieces > 3000:
            raise ValueError("pieces must be at most 3000")
        if not 0.0 <= self.white_ratio <= 0.6:
            raise ValueError("white_ratio must be between 0 and 0.6")
        if self.size < 32:
            raise ValueError("size must be at least 32")
        if not 0.0 <= self.roughness <= 1.0:
            raise ValueError("roughness must be between 0 and 1")


@dataclass(frozen=True)
class Fracture:
    shards: list[Poly]
    crack_width: float
    white_ratio: float
    black_area: float
    piece_count: int
    size: int
    seed: int


def char_seed(char: str) -> int:
    """Shatter seed is the character code point. Weight does not change it."""
    if not char:
        raise ValueError("char is required")
    return ord(char[0])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, scalar: float) -> Point:
    return (a[0] * scalar, a[1] * scalar)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _hypot(a: Point) -> float:
    return math.hypot(a[0], a[1])


def _norm(a: Point) -> Point:
    length = _hypot(a)
    if length < 1e-12:
        return (0.0, 0.0)
    return (a[0] / length, a[1] / length)


def polygon_area(poly: Poly) -> float:
    return abs(_signed_area(poly))


def _signed_area(poly: Poly) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return total * 0.5


def ensure_ccw(poly: Poly) -> Poly:
    return list(poly) if _signed_area(poly) >= 0 else list(reversed(poly))


def centroid(poly: Poly) -> Point:
    acc = 0.0
    cx = 0.0
    cy = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        cross = x1 * y2 - x2 * y1
        acc += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    acc *= 0.5
    if abs(acc) < 1e-12:
        return poly[0]
    return (cx / (6.0 * acc), cy / (6.0 * acc))


def _line_hit(p: Point, q: Point, origin: Point, normal: Point) -> Point:
    direction = _sub(q, p)
    denom = _dot(direction, normal)
    if abs(denom) < 1e-14:
        return p
    t = _dot(_sub(origin, p), normal) / denom
    t = min(1.0, max(0.0, t))
    return _add(p, _mul(direction, t))


def clip_halfplane(poly: Poly, origin: Point, normal: Point) -> Poly:
    if len(poly) < 3:
        return []
    out: Poly = []
    prev = poly[-1]
    prev_in = _dot(_sub(prev, origin), normal) <= 1e-10
    for curr in poly:
        curr_in = _dot(_sub(curr, origin), normal) <= 1e-10
        if curr_in:
            if not prev_in:
                out.append(_line_hit(prev, curr, origin, normal))
            out.append(curr)
        elif prev_in:
            out.append(_line_hit(prev, curr, origin, normal))
        prev = curr
        prev_in = curr_in
    return out if len(out) >= 3 else []


def inset_polygon(poly: Poly, distance: float) -> Poly:
    if distance <= 1e-9 or len(poly) < 3:
        return list(poly)
    poly = ensure_ccw(poly)
    out: Poly = []
    count = len(poly)
    for i, curr in enumerate(poly):
        prev = poly[i - 1]
        nxt = poly[(i + 1) % count]
        incoming = _norm(_sub(curr, prev))
        outgoing = _norm(_sub(nxt, curr))
        n1 = (-incoming[1], incoming[0])
        n2 = (-outgoing[1], outgoing[0])
        combined = (n1[0] + n2[0], n1[1] + n2[1])
        if _hypot(combined) < 1e-9:
            combined = n1
        normal = _norm(combined)
        miter = distance / max(_dot(normal, n1), 0.22)
        miter = min(miter, 3.2 * distance)
        out.append((curr[0] + normal[0] * miter, curr[1] + normal[1] * miter))
    return out if len(out) >= 3 else []


def _try_split(poly: Poly, rng: random.Random, min_area: float) -> tuple[Poly, Poly] | None:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width < 1e-6 or height < 1e-6:
        return None
    cx, cy = centroid(poly)
    base = math.pi / 2 if width >= height else 0.0
    for _ in range(12):
        angle = base + rng.uniform(-0.95, 0.95)
        normal = (-math.sin(angle), math.cos(angle))
        extent = max(width, height)
        flake = rng.random() < 0.34
        scale = rng.uniform(0.26, 0.44) if flake else rng.uniform(0.04, 0.18)
        origin = (
            cx + normal[0] * rng.choice((-1.0, 1.0)) * scale * extent,
            cy + normal[1] * rng.choice((-1.0, 1.0)) * scale * extent,
        )
        left = clip_halfplane(poly, origin, normal)
        right = clip_halfplane(poly, origin, (-normal[0], -normal[1]))
        if polygon_area(left) < min_area or polygon_area(right) < min_area:
            continue
        return left, right
    return None


def _perimeter_param(p: Point, size: float) -> float:
    x, y = p
    eps = 1e-6
    if abs(y) <= eps and x < size - eps:
        return x / size
    if abs(x - size) <= eps and y < size - eps:
        return 1.0 + y / size
    if abs(y - size) <= eps and x > eps:
        return 2.0 + (size - x) / size
    return 3.0 + (size - y) / size


def _ray_hit_square(origin: Point, angle: float, size: float) -> Point:
    dx, dy = math.cos(angle), math.sin(angle)
    hits: list[tuple[float, Point]] = []
    if abs(dx) > 1e-12:
        for wall_x in (0.0, size):
            t = (wall_x - origin[0]) / dx
            if t > 1e-8:
                y = origin[1] + t * dy
                if -1e-6 <= y <= size + 1e-6:
                    hits.append((t, (wall_x, min(size, max(0.0, y)))))
    if abs(dy) > 1e-12:
        for wall_y in (0.0, size):
            t = (wall_y - origin[1]) / dy
            if t > 1e-8:
                x = origin[0] + t * dx
                if -1e-6 <= x <= size + 1e-6:
                    hits.append((t, (min(size, max(0.0, x)), wall_y)))
    if not hits:
        return (size, origin[1])
    hits.sort(key=lambda item: item[0])
    return hits[0][1]


def _corners_between(pa: float, pb: float, size: float) -> Poly:
    corners = (
        (1.0, (size, 0.0)),
        (2.0, (size, size)),
        (3.0, (0.0, size)),
        (4.0, (0.0, 0.0)),
    )
    pts: Poly = []
    if pb > pa + 1e-12:
        for param, corner in corners:
            if pa + 1e-9 < param < pb - 1e-9:
                pts.append(corner)
        return pts
    for param, corner in corners:
        if param > pa + 1e-9:
            pts.append(corner)
    for param, corner in corners:
        if param < pb - 1e-9:
            pts.append(corner)
    return pts


def _impact_sectors(size: float, rng: random.Random, piece_budget: int) -> list[Poly]:
    margin = size * 0.18
    impact = (rng.uniform(margin, size - margin), rng.uniform(margin, size - margin))
    ray_count = min(max(6, piece_budget // 80), 10)
    weights = [rng.random() + 0.28 for _ in range(ray_count)]
    total = sum(weights)
    angle = rng.uniform(0.0, math.tau)
    hits: list[tuple[float, Point]] = []
    for weight in weights:
        angle += math.tau * weight / total
        hit = _ray_hit_square(impact, angle, size)
        hits.append((_perimeter_param(hit, size), hit))
    hits.sort(key=lambda item: item[0])
    sectors: list[Poly] = []
    for i, (param_a, hit_a) in enumerate(hits):
        param_b, hit_b = hits[(i + 1) % len(hits)]
        poly = [impact, hit_a, *_corners_between(param_a, param_b, size), hit_b]
        cleaned: Poly = []
        for point in poly:
            if not cleaned or math.hypot(point[0] - cleaned[-1][0], point[1] - cleaned[-1][1]) > 1e-6:
                cleaned.append(point)
        if len(cleaned) >= 3 and polygon_area(cleaned) > size * size * 0.0008:
            sectors.append(ensure_ccw(cleaned))
    return sectors or [[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]]


def fracture_square(config: PatternConfig) -> list[Poly]:
    size = float(config.size)
    rng = random.Random(config.seed)
    pieces = _impact_sectors(size, rng, config.pieces)
    min_area = (size * size) / (config.pieces * 14)
    while len(pieces) < config.pieces:
        if rng.random() < 0.7:
            idx = max(range(len(pieces)), key=lambda i: polygon_area(pieces[i]))
        else:
            idx = rng.randrange(len(pieces))
        split = _try_split(pieces[idx], rng, min_area)
        if split is None:
            chosen = None
            for candidate in sorted(range(len(pieces)), key=lambda i: polygon_area(pieces[i]), reverse=True):
                split = _try_split(pieces[candidate], rng, min_area)
                if split is not None:
                    chosen = candidate
                    break
            if split is None:
                break
            idx = chosen
        left, right = split
        pieces.pop(idx)
        pieces.append(ensure_ccw(left))
        pieces.append(ensure_ccw(right))
    return pieces


def _key(point: Point) -> tuple[float, float]:
    return (round(point[0], 5), round(point[1], 5))


def _signed_unit(seed: int, a: Point, b: Point) -> float:
    payload = f"{seed}:{a[0]:.5f}:{a[1]:.5f}:{b[0]:.5f}:{b[1]:.5f}".encode()
    value = int.from_bytes(hashlib.md5(payload).digest()[:4], "big")
    return (value / 0xFFFFFFFF) * 2.0 - 1.0


def _keep_inside(a: Point, b: Point, mid: Point, size: float) -> Point:
    mx, my = mid
    ox, oy = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
    lo, hi = 0.8, size - 0.8
    for _ in range(8):
        if lo <= mx <= hi and lo <= my <= hi:
            return (mx, my)
        mx = (mx + ox) * 0.5
        my = (my + oy) * 0.5
    return (ox, oy)


def _displace_segment(a: Point, b: Point, seed: int, depth: int, amp: float, size: float) -> Poly:
    if depth <= 0 or math.hypot(b[0] - a[0], b[1] - a[1]) < 18:
        return [a, b]
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    nx, ny = _norm((-(b[1] - a[1]), b[0] - a[0]))
    wobble = _signed_unit(seed, a, b) * length * amp
    mid = _keep_inside(a, b, ((a[0] + b[0]) * 0.5 + nx * wobble, (a[1] + b[1]) * 0.5 + ny * wobble), size)
    left = _displace_segment(a, mid, seed, depth - 1, amp, size)
    right = _displace_segment(mid, b, seed, depth - 1, amp, size)
    return left[:-1] + right


def jagged_edge(a: Point, b: Point, seed: int, depth: int, amp: float, size: float) -> Poly:
    if _key(a) < _key(b):
        return _displace_segment(a, b, seed, depth, amp, size)
    return list(reversed(_displace_segment(b, a, seed, depth, amp, size)))


def jagged_polygons(polys: list[Poly], size: float, seed: int, roughness: float) -> list[Poly]:
    if roughness <= 0:
        return [ensure_ccw(poly) for poly in polys if len(poly) >= 3]
    edge_count: Counter[tuple[tuple[float, float], tuple[float, float]]] = Counter()
    for poly in polys:
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            edge = tuple(sorted((_key(a), _key(b))))
            if edge[0] != edge[1]:
                edge_count[edge] += 1
    amp = 0.05 + 0.16 * roughness
    depth = 2 if roughness <= 0.55 else 3
    out: list[Poly] = []
    for poly in polys:
        rebuilt: Poly = []
        for i, a in enumerate(poly):
            b = poly[(i + 1) % len(poly)]
            edge = tuple(sorted((_key(a), _key(b))))
            if edge_count[edge] >= 2:
                rebuilt.extend(jagged_edge(a, b, seed, depth, amp, size)[:-1])
            else:
                rebuilt.append(a)
        if len(rebuilt) >= 3:
            out.append(ensure_ccw(rebuilt))
    return out


def _black_area(shards: list[Poly]) -> float:
    return sum(polygon_area(p) for p in shards if len(p) >= 3)


def _perimeter(poly: Poly) -> float:
    total = 0.0
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    return total


def _as_polygon(poly: Poly) -> Polygon | None:
    try:
        geom = make_valid(Polygon(poly))
    except Exception:
        return None
    if geom.is_empty or geom.area <= 1e-8:
        return None
    if geom.geom_type == "Polygon":
        return geom
    if geom.geom_type == "MultiPolygon":
        parts = [item for item in geom.geoms if item.geom_type == "Polygon"]
        if not parts:
            return None
        return max(parts, key=lambda item: item.area)
    return None


def shrink_shards(raw: list[Poly], distance: float) -> list[Poly]:
    out: list[Poly] = []
    for poly in raw:
        geom = _as_polygon(poly)
        if geom is None:
            continue
        try:
            inset = geom.buffer(-distance, quad_segs=1, join_style=1)
        except Exception:
            continue
        if inset.is_empty or inset.area <= 1e-8 or inset.area > geom.area * 1.05:
            continue
        if inset.geom_type == "Polygon":
            parts = [inset]
        elif inset.geom_type == "MultiPolygon":
            parts = [item for item in inset.geoms if item.geom_type == "Polygon"]
        else:
            continue
        for part in parts:
            coords = list(part.exterior.coords)
            if len(coords) >= 4:
                out.append([(x, y) for x, y in coords[:-1]])
    return out


def fit_crack_inset(raw: list[Poly], size: float, white_ratio: float) -> float:
    if white_ratio <= 0:
        return 0.0
    peri = sum(_perimeter(p) for p in raw)
    guess = (white_ratio * size * size) / max(peri, 1.0)
    return min(max(guess, size * 0.002), size * 0.02)


def _build_fracture_uncached(config: PatternConfig) -> Fracture:
    size = float(config.size)
    raw = jagged_polygons(fracture_square(config), size, config.seed, config.roughness)
    distance = fit_crack_inset(raw, size, config.white_ratio)
    shards = shrink_shards(raw, distance)
    black = _black_area(shards)
    total = size * size
    return Fracture(
        shards=shards,
        crack_width=distance * 2.0,
        white_ratio=max(0.0, (total - black) / total) if total else 0.0,
        black_area=black,
        piece_count=len(shards),
        size=config.size,
        seed=config.seed,
    )


@lru_cache(maxsize=512)
def build_fracture(config: PatternConfig) -> Fracture:
    return _build_fracture_uncached(config)

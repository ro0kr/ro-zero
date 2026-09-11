"""Sequential 2D discrete fracture network, after GeoDFN (MIT).

Kamel Targhi et al., Geoenergy 2025, DOI 10.1144/geoenergy2025-028
https://github.com/kamelelahe/GeoDFN

Rewritten in the stdlib for this SVG tool. Same hybrid rule: sample
length/orientation, insert longest first, reject near-parallel traces
that sit inside another fracture's stress shadow. Crossing conjugate
sets are kept, and shorter joints can stop on older cracks.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Point = tuple[float, float]
Poly = list[Point]


@dataclass(frozen=True)
class Fracture:
    a: Point
    b: Point
    length: float
    theta: float
    set_id: int
    spacing: float


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polygon_area(poly: Poly) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


def _near(a: Point, b: Point, eps: float = 1e-6) -> bool:
    return _dist(a, b) <= eps


def von_mises(rng: random.Random, mu: float, kappa: float) -> float:
    """Best-Fisher rejection sampler, radians."""
    if kappa < 1e-6:
        return rng.uniform(0.0, math.tau)
    aa = 1.0 + math.sqrt(1.0 + 4.0 * kappa * kappa)
    bb = (aa - math.sqrt(2.0 * aa)) / (2.0 * kappa)
    r = (1.0 + bb * bb) / (2.0 * bb)
    while True:
        z = math.cos(math.pi * rng.random())
        f = (1.0 + r * z) / (r + z)
        c = kappa * (r - f)
        u = rng.random()
        if u < c * (2.0 - c) or (c > 0.0 and math.log(u) <= math.log(c) + 1.0 - c):
            break
    sign = 1.0 if rng.random() > 0.5 else -1.0
    return (mu + sign * math.acos(max(-1.0, min(1.0, f)))) % math.tau


def log_normal_clamped(rng: random.Random, mu: float, sigma: float, lo: float, hi: float) -> float:
    for _ in range(40):
        value = math.exp(rng.gauss(mu, sigma))
        if lo <= value <= hi:
            return value
    return min(hi, max(lo, math.exp(mu)))


def power_law_length(rng: random.Random, alpha: float, lo: float, hi: float) -> float:
    u = rng.random()
    expo = 1.0 / max(alpha - 1.0, 1e-6)
    cdf_lo = 1.0 - lo ** (1.0 - alpha)
    cdf_hi = 1.0 - hi ** (1.0 - alpha)
    u = cdf_lo + u * (cdf_hi - cdf_lo)
    return min(hi, max(lo, lo / max(1.0 - u, 1e-12) ** expo))


def clip_to_square(a: Point, b: Point, size: float) -> tuple[Point, Point] | None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    p = (-dx, dx, -dy, dy)
    q = (a[0], size - a[0], a[1], size - a[1])
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-14:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 > u2:
            return None
    return (a[0] + u1 * dx, a[1] + u1 * dy), (a[0] + u2 * dx, a[1] + u2 * dy)


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    length2 = vx * vx + vy * vy
    if length2 < 1e-18:
        return _dist(p, a)
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / length2
    t = min(1.0, max(0.0, t))
    return math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy))


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if seg_intersect(a, b, c, d) is not None:
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def seg_intersect(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    r = _sub(b, a)
    s = _sub(d, c)
    den = _cross(r, s)
    if abs(den) < 1e-12:
        return None
    q = _sub(c, a)
    t = _cross(q, s) / den
    u = _cross(q, r) / den
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return _add(a, _mul(r, t))
    return None


def acute_angle(t1: float, t2: float) -> float:
    delta = abs((t1 - t2 + math.pi / 2) % math.pi - math.pi / 2)
    return delta


def _too_close(candidate: Fracture, existing: list[Fracture]) -> bool:
    for other in existing:
        parallel = acute_angle(candidate.theta, other.theta) < math.radians(26)
        same_set = candidate.set_id == other.set_id
        if not (parallel or same_set):
            continue
        gap = candidate.spacing + other.spacing
        if segment_distance(candidate.a, candidate.b, other.a, other.b) < gap:
            return True
    return False


def _along(origin: Point, direction: Point, point: Point) -> float:
    return (point[0] - origin[0]) * direction[0] + (point[1] - origin[1]) * direction[1]


def _ray_hit(
    origin: Point,
    direction: Point,
    reach: float,
    existing: list[Fracture],
    size: float,
    stop_on_cracks: bool,
) -> Point:
    far = (origin[0] + direction[0] * reach, origin[1] + direction[1] * reach)
    clipped = clip_to_square(origin, far, size)
    if clipped is None:
        return origin
    start, end = clipped
    tip = end if _along(origin, direction, end) >= _along(origin, direction, start) else start
    if _along(origin, direction, tip) <= 1e-8:
        return origin
    if not stop_on_cracks:
        return tip
    best_t = 1.0
    vec = _sub(tip, origin)
    length = math.hypot(vec[0], vec[1])
    if length < 1e-9:
        return tip
    for other in existing:
        hit = seg_intersect(origin, tip, other.a, other.b)
        if hit is None or _near(hit, origin, 1.5):
            continue
        t = _dist(origin, hit) / length
        if 1e-4 < t < best_t:
            best_t = t
    return _add(origin, _mul(vec, best_t))


def _place_one(
    theta: float,
    set_id: int,
    spacing: float,
    size: float,
    rng: random.Random,
    existing: list[Fracture],
    stop_on_cracks: bool,
) -> Fracture | None:
    dx, dy = math.cos(theta), math.sin(theta)
    reach = size * 3.0
    for _ in range(120):
        mid = (rng.uniform(size * 0.04, size * 0.96), rng.uniform(size * 0.04, size * 0.96))
        a = _ray_hit(mid, (-dx, -dy), reach, existing, size, stop_on_cracks)
        b = _ray_hit(mid, (dx, dy), reach, existing, size, stop_on_cracks)
        if _dist(a, b) < max(12.0, size * 0.05):
            continue
        candidate = Fracture(a=a, b=b, length=_dist(a, b), theta=theta, set_id=set_id, spacing=spacing)
        if _too_close(candidate, existing):
            continue
        return candidate
    return None


def generate_dfn(size: float, target_pieces: int, rng: random.Random) -> list[Fracture]:
    """Build two conjugate joint sets, longest first, with stress shadows."""
    lmin = size * 0.08
    lmax = size * 1.4
    sets = (
        (0, 0.32, 8.5, 0.016),
        (1, 1.92, 7.0, 0.014),
    )
    drafts: list[tuple[float, float, int, float]] = []
    scale = max(0.7, min(1.8, target_pieces / 40))
    for set_id, mu, kappa, intensity in sets:
        acc = 0.0
        goal = intensity * size * size * scale
        while acc < goal and len(drafts) < max(28, target_pieces * 2):
            length = log_normal_clamped(rng, math.log(size * 0.34), 0.5, lmin, lmax)
            if rng.random() < 0.4:
                length = power_law_length(rng, 2.05, lmin, lmax)
            theta = von_mises(rng, mu, kappa)
            spacing = max(size * 0.01, 0.045 * length)
            drafts.append((length, theta, set_id, spacing))
            acc += length

    drafts.sort(key=lambda item: item[0], reverse=True)
    placed: list[Fracture] = []
    through_count = max(8, min(len(drafts), int(target_pieces * 0.45)))
    for i, (length, theta, set_id, spacing) in enumerate(drafts):
        stop = i >= through_count
        frac = _place_one(theta, set_id, spacing, size, rng, placed, stop)
        if frac is not None:
            placed.append(frac)
        if len(placed) >= target_pieces + 12:
            break
    extra = 0
    while len(placed) < target_pieces and extra < target_pieces * 2:
        set_id, mu, kappa, _ = sets[extra % 2]
        theta = von_mises(rng, mu, kappa)
        spacing = size * 0.012
        frac = _place_one(theta, set_id, spacing, size, rng, placed, True)
        if frac is not None:
            placed.append(frac)
        extra += 1
    return placed


def _hit_param(a: Point, b: Point, p: Point) -> float:
    return _dot(_sub(p, a), _sub(b, a))


def split_convex(poly: Poly, a: Point, b: Point) -> list[Poly]:
    if len(poly) < 3:
        return [poly]
    hits: list[tuple[float, int, Point]] = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        inter = seg_intersect(a, b, p, q)
        if inter is None:
            continue
        hits.append((_hit_param(a, b, inter), i, inter))
    hits.sort(key=lambda item: item[0])
    cleaned: list[tuple[int, Point]] = []
    for _, edge, point in hits:
        if cleaned and (_near(point, cleaned[-1][1]) or edge == cleaned[-1][0]):
            continue
        cleaned.append((edge, point))
    if len(cleaned) < 2:
        return [poly]
    (e1, p1), (e2, p2) = cleaned[0], cleaned[-1]
    if e1 == e2 or _near(p1, p2):
        return [poly]

    def walk(start_edge: int, start: Point, end_edge: int, end: Point) -> Poly:
        chain: Poly = [start]
        idx = (start_edge + 1) % len(poly)
        while True:
            vertex = poly[idx]
            if not _near(chain[-1], vertex):
                chain.append(vertex)
            if idx == end_edge:
                break
            idx = (idx + 1) % len(poly)
            if idx == (start_edge + 1) % len(poly):
                break
        if not _near(chain[-1], end):
            chain.append(end)
        return chain

    left = walk(e1, p1, e2, p2)
    right = walk(e2, p2, e1, p1)
    out = []
    for piece in (left, right):
        trimmed: Poly = []
        for point in piece:
            if not trimmed or not _near(trimmed[-1], point):
                trimmed.append(point)
        if len(trimmed) >= 3 and polygon_area(trimmed) > 1e-4:
            out.append(trimmed)
    return out or [poly]


def split_by_fractures(size: float, fractures: list[Fracture], target: int) -> list[Poly]:
    pieces: list[Poly] = [[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]]
    for frac in fractures:
        nxt: list[Poly] = []
        for poly in pieces:
            nxt.extend(split_convex(poly, frac.a, frac.b))
        pieces = nxt
        if len(pieces) >= target:
            break
    return pieces

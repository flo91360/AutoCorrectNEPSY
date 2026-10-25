"""Item 21 : deux roues qui se chevauchent, six cordes (diamètres) dans
chacune et un essieu qui relie leurs centres.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Les roues sont les deux grandes ellipses retrouvées parmi les traits. Les
rayons d'une roue sont repérés depuis son moyeu, direction par direction : un
rayon couvre presque toute la distance du moyeu à la jante dans sa direction.
Chacun est ensuite suivi de proche en proche (un rayon tracé à main levée se
courbe). Deux rayons opposés forment une corde ; le moyeu est le point où les
rayons se croisent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from . import polygons
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from .ellipses import TOLERANCE_MM, Ellipse, coverage, crosses, find_ellipses, fit, tangents
from .shapes import separate_extras

CHORDS = 6
MIN_WHEEL_MM = 15.0  # petit diamètre minimal d'une roue
OTHER_WHEEL_COVERAGE = 0.8  # autre cercle (rapport ≤ 1,5) bien tracé : roue en trop
RIM_NEAR_FRACTION = 0.25  # contour extérieur à moins de 25 % du rayon : la jante
MIN_RIM_COVERAGE = 0.4  # part de la jante visible sur le contour extérieur
HUB_FRACTION = 0.2  # rayons cherchés entre 20 % et 85 % de la distance à la jante
RIM_FRACTION = 0.85
TRACK_FROM_FRACTION = 0.15  # un rayon est suivi jusqu'à 15 % de la distance au moyeu
# Direction d'un rayon : droite ajustée loin du moyeu, où les rayons se mêlent.
LINE_FRACTION = (0.3, 0.9)
LINE_TOLERANCE_MM = 1.0
HUB_LINE_MM = 1.5  # droite d'un rayon qui passe au moyeu
SPOKE_WINDOW_DEG = 3.0
SPOKE_STEP_MM = 0.5
SPOKE_MIN_COVER = 0.5  # part de la distance moyeu-jante tracée dans une direction
SPOKE_SEPARATION_DEG = 8.0
# Écart toléré d'un pas au suivant en suivant un rayon : faible, pour ne pas
# passer sur un trait croisé, plus large après des pas sans point du tracé.
TRACK_MM = 0.5
TRACK_MAX_MM = 2.0
TRACK_STEP_MM = 0.25
INK_STEP_MM = 0.1  # pas des échantillons d'encre en travers du rayon
CROSSING_MM = 1.5  # tache d'encre plus large : croisement d'un autre trait
SPOKE_CONTINUES_MM = 2.0  # le rayon reprend après une interruption
RIM_STOP_MM = 1.0  # un rayon est suivi jusqu'à 1 mm de la jante
AXLE_NEAR_MM = 1.5
AXLE_MIN_COVER = 0.8  # part de la distance entre les moyeux couverte par l'essieu
OPPOSITE_DEG = 15.0  # deux rayons opposés forment une corde
CIRCLE_LOOSE_RATIO = 1.5  # Général, Motricité A
CIRCLE_RATIO = 1.3  # Global C
DISTORTION_MAX_SPREAD = 0.08  # irrégularité du rayon d'une roue (bosses, angles)
GAP_MM = 1.0  # Motricité B
# La jante tracée à main levée s'écarte de l'ellipse ajustée : elle est
# cherchée entre 70 % et 140 % de la distance du centre à l'ellipse.
RIM_BAND = (0.7, 1.4)
AXIS_LOOSE_DEG = 10.0  # corde horizontale ou verticale « ou presque »
SIZE_RATIO = (1.1, 1.4)  # Global D : roue gauche / roue droite
LEFT_CHORD_MAX_MM = 58.0  # Local E
RIGHT_CHORD_MAX_MM = 48.0
CHORD_RATIO_MAX = 1.1  # Local F : roue droite


@dataclass
class Spoke:
    angle: float  # direction depuis le moyeu (degrés, sens trigonométrique, 0 à droite)
    points: np.ndarray  # tracé suivi, du moyeu vers la jante
    gap: float  # plus grande interruption (mm)
    end: np.ndarray  # rencontre avec la jante
    line: tuple[np.ndarray, np.ndarray] | None  # droite ajustée (point, direction)


@dataclass
class Wheel:
    ellipse: Ellipse
    hub: np.ndarray
    spokes: list[Spoke]
    chords: list[tuple[int, int]]

    def chord_length(self, pair: tuple[int, int]) -> float:
        a, b = pair
        return float(np.linalg.norm(self.spokes[a].end - self.spokes[b].end))

    def chord_angle(self, pair: tuple[int, int]) -> float:
        """Direction de la corde (degrés, 0 à 180)."""
        a, b = (self.spokes[k].angle for k in pair)
        return float((a + _difference(b + 180.0, a) / 2) % 180)

    @property
    def unpaired(self) -> list[int]:
        paired = {k for pair in self.chords for k in pair}
        return [k for k in range(len(self.spokes)) if k not in paired]


def score(drawing: Drawing, item: int = 21) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {}
    marks: list = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, marks=marks)

    found = _wheel_ellipses(drawing)
    if found is None:
        for code in codes:
            checks[code].fail("roues non reconnues (deux cercles qui se chevauchent)")
        return result()
    (left_e, right_e), extra_wheels = found
    left, right = _wheels(drawing, left_e, right_e)
    names = {"gauche": left, "droite": right}
    axle = _axle_cover(drawing, left.hub, right.hub)
    measures["essieu_couvert"] = axle

    for color, (name, wheel) in enumerate(names.items()):
        e = wheel.ellipse
        marks.append(mk.trace(e.at(np.linspace(0, 2 * np.pi, 120)),
                              f"roue {name} {fmt(e.major, '')} × {fmt(e.minor)}", color))
        for pair in wheel.chords:
            a, b = (wheel.spokes[k].end for k in pair)
            marks.append(mk.segment(a, b, fmt(wheel.chord_length(pair), "")))
        for k in wheel.unpaired:
            marks.append(mk.segment(wheel.hub, wheel.spokes[k].end, "rayon seul"))
        measures[f"{name}_grand_mm"] = e.major
        measures[f"{name}_petit_mm"] = e.minor
        measures[f"{name}_cordes"] = float(len(wheel.chords))
        measures[f"{name}_rayons"] = float(len(wheel.spokes))
    marks.append(mk.segment(left.hub, right.hub, f"essieu {axle:.0%}".replace("%", " %")))

    overlap = crosses(left_e, right_e)
    distorted = [n for n, w in names.items() if w.ellipse.spread > DISTORTION_MAX_SPREAD]
    loose = [n for n, w in names.items() if w.ellipse.ratio > CIRCLE_LOOSE_RATIO]
    small_right = right_e.major < left_e.major and right_e.center[1] < left_e.center[1]
    axles = axle >= AXLE_MIN_COVER
    inside = bool(left_e.contains(right_e.center[None])[0]) if small_right else bool(
        right_e.contains(left_e.center[None])[0])

    general = checks["G"]
    general.add(overlap, "les deux roues se chevauchent" if overlap
                else "les deux roues ne se chevauchent pas")
    general.add(not distorted and not loose, "roues sans distorsion" if not (distorted or loose)
                else f"roue(s) déformée(s) : {', '.join(sorted(set(distorted + loose)))}")
    general.add(small_right, "la petite roue est à droite et au-dessus de la grande" if small_right
                else "la petite roue n'est pas à droite et au-dessus de la grande")
    for name, wheel in names.items():
        segmented = _segmented(wheel)
        general.add(len(wheel.chords) == CHORDS and len(wheel.spokes) == 2 * CHORDS,
                    f"roue {name} : {len(wheel.chords)} corde(s), {len(wheel.spokes)} rayon(s) "
                    "(six cordes seulement)")
        general.add(not segmented, f"roue {name} : cordes d'un seul trait" if not segmented
                    else f"roue {name} : {segmented} corde(s) segmentée(s)")
        axes = _axes(wheel)
        general.add(None not in axes, f"roue {name} : une corde horizontale et une verticale"
                    if None not in axes else f"roue {name} : pas de corde horizontale et verticale")
    general.limit(axle, f"essieu entre les moyeux tracé sur {axle:.0%} de leur distance"
                  .replace("%", " %") + " (≥ 80 %)", low=AXLE_MIN_COVER, unit="part")
    general.add(inside, "centre de la petite roue dans la grande" if inside
                else "centre de la petite roue hors de la grande")

    checks["A"].add(not distorted and not loose, "roues identifiables, sans distorsion majeure"
                    if not (distorted or loose)
                    else f"roue(s) déformée(s) : {', '.join(sorted(set(distorted + loose)))}")

    rim_gaps = {n: _rim_gap(drawing, w.ellipse, o.ellipse)
                for (n, w), o in zip(names.items(), (right, left))}
    spoke_gap = max((s.gap for w in names.values() for s in w.spokes), default=0.0)
    measures.update({"jante_intervalle_max_mm": max(rim_gaps.values()),
                     "rayon_intervalle_max_mm": spoke_gap})
    for name, gap in rim_gaps.items():
        checks["B"].limit(gap, f"jante {name} : plus grand intervalle {fmt(gap)} ≤ 1 mm",
                          high=GAP_MM)
    checks["B"].limit(spoke_gap, f"plus grand intervalle dans un rayon {fmt(spoke_gap)} ≤ 1 mm",
                      high=GAP_MM)

    for name, wheel in names.items():
        ratio = wheel.ellipse.ratio
        checks["C"].limit(ratio, f"roue {name} : cercle, diamètres {fmt_ratio(ratio)} ≤ 1,3:1",
                          high=CIRCLE_RATIO, unit="ratio")
    checks["C"].add(not extra_wheels and axles, "deux roues seulement, reliées par un essieu"
                    if not extra_wheels and axles else
                    f"{2 + extra_wheels} roue(s), essieu tracé sur {axle:.0%}".replace("%", " %"))

    size = left_e.major / max(right_e.major, 1e-6)
    measures["rapport_roues"] = size
    checks["D"].add(overlap, "les roues se chevauchent" if overlap
                    else "les roues ne se chevauchent pas")
    checks["D"].limit(size, f"grand diamètre roue gauche {fmt(left_e.major)} / roue droite "
                      f"{fmt(right_e.major)} : {fmt_ratio(size)} entre 1,1:1 et 1,4:1",
                      low=SIZE_RATIO[0], high=SIZE_RATIO[1], unit="ratio")

    for name, wheel, limit in (("gauche", left, LEFT_CHORD_MAX_MM),
                               ("droite", right, RIGHT_CHORD_MAX_MM)):
        lengths = [wheel.chord_length(p) for p in wheel.chords] or [wheel.ellipse.major]
        checks["E"].limit(max(lengths), f"roue {name} : plus longue corde {fmt(max(lengths))} "
                          f"≤ {limit:.0f} mm", high=limit)

    figure = np.vstack([w.ellipse.at(np.linspace(0, 2 * np.pi, 180)) for w in names.values()]
                       + [s.points for w in names.values() for s in w.spokes]
                       + [np.linspace(left.hub, right.hub, 50)])
    extras = len(separate_extras(drawing, figure))
    added = sum(max(len(w.spokes) - 2 * CHORDS, 0) for w in names.values())
    checks["F"].add(not extras and not added and not extra_wheels, "aucun autre élément"
                    if not (extras or added or extra_wheels)
                    else f"{added} rayon(s) ajouté(s), {extras + extra_wheels} autre(s) élément(s)")
    for name, wheel in names.items():
        counts = _quadrants(wheel)
        checks["F"].add(counts == [2, 2, 2, 2], f"roue {name} : deux rayons par quadrant" if
                        counts == [2, 2, 2, 2] else f"roue {name} : rayons par quadrant "
                        + ("non délimités (corde horizontale ou verticale absente)"
                           if counts is None else ", ".join(map(str, counts))))
    lengths = [right.chord_length(p) for p in right.chords]
    spread = max(lengths) / max(min(lengths), 1e-6) if len(lengths) >= 2 else float("inf")
    measures["cordes_droite_rapport"] = spread
    checks["F"].limit(spread, f"roue droite : plus longue / plus courte corde "
                      f"{fmt_ratio(spread)} ≤ 1,1:1", high=CHORD_RATIO_MAX, unit="ratio")
    return result()


def _wheel_ellipses(drawing: Drawing) -> tuple[tuple[Ellipse, Ellipse], int] | None:
    """Roue gauche et roue droite, et nombre d'autres cercles bien tracés."""
    found = [e for e in find_ellipses(drawing, 4) if e.minor >= MIN_WHEEL_MM]
    found.sort(key=lambda e: -e.coverage)
    wheels: list[Ellipse] = []
    others = 0
    for e in found:
        if any(np.linalg.norm(e.center - w.center) < 0.2 * w.minor for w in wheels):
            continue
        if len(wheels) < 2:
            wheels.append(e)
        elif e.coverage >= OTHER_WHEEL_COVERAGE and e.ratio <= CIRCLE_LOOSE_RATIO:
            others += 1
    if len(wheels) < 2:
        return None
    outline = polygons.silhouette(drawing)
    for _ in range(3 if outline is not None else 0):  # jusqu'à ce que les jantes bougent peu
        wheels = [_rim(drawing, outline, wheels[0], wheels[1]),
                  _rim(drawing, outline, wheels[1], wheels[0])]
    left, right = sorted(wheels, key=lambda e: e.center[0])
    return (left, right), others


def _rim(drawing: Drawing, outline: np.ndarray, wheel: Ellipse, other: Ellipse) -> Ellipse:
    """Ellipse réajustée sur la jante visible de la roue : la partie du contour
    extérieur du dessin qui la longe. Les rayons et l'autre roue, qui croisent
    la jante, n'y entrent pas : une jante irrégulière est ainsi lue de la même
    façon quels que soient les petits détails du tracé. Elle est ensuite
    recalée sur le milieu du trait (le contour en longe le bord extérieur)."""
    radius = (wheel.major + wheel.minor) / 4
    near, near_other = wheel.distance(outline), other.distance(outline)
    rim = outline[(near <= RIM_NEAR_FRACTION * radius) & (near < near_other)]
    refit = fit(rim)
    if refit is None or coverage(wheel, rim) < MIN_RIM_COVERAGE:
        return wheel
    points = drawing.points
    centered = fit(points[refit.traced(points, tangents(drawing))])
    if centered is not None and np.linalg.norm(centered.center - refit.center) < 0.1 * radius:
        refit = centered
    refit.points = points[refit.distance(points) <= TOLERANCE_MM]
    refit.coverage = coverage(refit, refit.points)
    return refit


def _wheels(drawing: Drawing, left: Ellipse, right: Ellipse) -> tuple[Wheel, Wheel]:
    hubs = [left.center, right.center]
    wheels = []
    for _ in range(2):  # moyeux recalculés au croisement des rayons
        wheels = []
        for k, (e, other) in enumerate(((left, right), (right, left))):
            points = _spoke_points(drawing, e, other, hubs[k], hubs[1 - k])
            spokes = [_track(drawing, hubs[k], a, e) for a in _directions(points, hubs[k], e)]
            wheels.append(Wheel(e, hubs[k], spokes, _pairs(spokes)))
        hubs = [_hub(w.spokes, w.ellipse) for w in wheels]
    return wheels[0], wheels[1]


def _rim_distance(e: Ellipse, hub: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """Distance (mm) du moyeu à la jante (ellipse) dans chaque direction (radians)."""
    u = np.column_stack([np.cos(angles), -np.sin(angles)])
    q0 = e.local(hub)[0]
    q1 = np.column_stack([(u @ e.major_axis) / (e.major / 2), (u @ e.minor_axis) / (e.minor / 2)])
    a = (q1 ** 2).sum(axis=1)
    b = 2 * q1 @ q0
    c = float(q0 @ q0) - 1
    return (-b + np.sqrt(np.maximum(b ** 2 - 4 * a * c, 0))) / (2 * a)


def _spoke_points(drawing: Drawing, e: Ellipse, other: Ellipse, hub: np.ndarray,
                  other_hub: np.ndarray) -> np.ndarray:
    """Points du dessin qui peuvent appartenir aux rayons de la roue : dans la
    roue, hors de la jante de l'autre roue et de l'essieu."""
    points = drawing.points
    ab = other_hub - hub
    t = np.clip(((points - hub) @ ab) / max(float(ab @ ab), 1e-9), 0, 1)
    keep = ((e.radial(points) < 1) & (other.distance(points) > AXLE_NEAR_MM)
            & (np.linalg.norm(points - (hub + np.outer(t, ab)), axis=1) > AXLE_NEAR_MM))
    return points[keep]


def _polar(points: np.ndarray, hub: np.ndarray, e: Ellipse) -> tuple[np.ndarray, np.ndarray,
                                                                     np.ndarray]:
    """Distance au moyeu, direction (degrés) et distance à la jante de chaque point."""
    rel = points - hub
    radius = np.linalg.norm(rel, axis=1)
    angle = np.degrees(np.arctan2(-rel[:, 1], rel[:, 0])) % 360
    return radius, angle, _rim_distance(e, hub, np.radians(angle))


def _directions(points: np.ndarray, hub: np.ndarray, e: Ellipse) -> list[float]:
    """Directions (degrés) des rayons : la distance du moyeu à la jante y est
    presque entièrement tracée."""
    if not len(points):
        return []
    radius, angle, rim = _polar(points, hub, e)
    fraction = radius / np.maximum(rim, 1e-6)
    keep = (fraction > HUB_FRACTION) & (fraction < RIM_FRACTION)
    reach = float(np.median(rim)) if len(rim) else 1.0
    bins = max(1, int((RIM_FRACTION - HUB_FRACTION) * reach / SPOKE_STEP_MM))
    step = (RIM_FRACTION - HUB_FRACTION) / bins
    slot = ((fraction[keep] - HUB_FRACTION) / step).astype(int)
    angle = angle[keep]
    cover = np.zeros(360)
    for deg in range(360):
        near = np.abs((angle - deg + 180) % 360 - 180) <= SPOKE_WINDOW_DEG
        cover[deg] = len(np.unique(slot[near])) / bins
    window = int(SPOKE_SEPARATION_DEG)
    peaks = [deg for deg in range(360) if cover[deg] >= SPOKE_MIN_COVER
             and cover[deg] >= max(cover[(deg + j) % 360] for j in range(-window, window + 1))]
    found: list[list[int]] = []  # plateaux regroupés
    for deg in peaks:
        if found and deg - found[-1][-1] <= window:
            found[-1].append(deg)
        else:
            found.append([deg])
    if len(found) > 1 and found[0][0] + 360 - found[-1][-1] <= window:
        found[0] = [d - 360 for d in found.pop()] + found[0]
    return [float(np.mean(group)) % 360 for group in found]


def _track(drawing: Drawing, hub: np.ndarray, start: float, e: Ellipse) -> Spoke:
    """Suit un rayon sur l'encre, de proche en proche, du milieu vers la jante
    puis vers le moyeu : à chaque distance du moyeu, la tache d'encre la plus
    proche de la direction courante (un rayon tracé à main levée se courbe).
    Une tache bien plus large que le trait est un croisement : la direction
    n'y change pas."""
    rim = float(_rim_distance(e, hub, np.radians([start]))[0])
    found: dict[float, np.ndarray] = {}
    traced: dict[float, bool] = {}  # rayon tracé ou non, pas à pas
    for direction, stop in ((1, rim - RIM_STOP_MM), (-1, TRACK_FROM_FRACTION * rim)):
        theta, r, lost = np.radians(start), 0.5 * rim, 0
        while (r <= stop) if direction > 0 else (r >= stop):
            reach = min(TRACK_MM + lost * TRACK_STEP_MM, TRACK_MAX_MM)
            lateral = np.arange(-reach, reach + 1e-9, INK_STEP_MM)
            angles = theta + lateral / r
            ink = drawing.on_ink(hub + r * np.column_stack([np.cos(angles), -np.sin(angles)]))
            run = _nearest_run(ink)
            if run is None:
                lost += 1
            else:
                lost = 0
                low, high = run
                if (high - low) * INK_STEP_MM <= CROSSING_MM:
                    theta = float(angles[(low + high) // 2])
                found[r] = hub + r * np.array([np.cos(theta), -np.sin(theta)])
            traced[r] = run is not None
            r += direction * TRACK_STEP_MM
            if direction > 0:
                stop = float(_rim_distance(e, hub, np.array([theta]))[0]) - RIM_STOP_MM
        if direction > 0:
            outer = theta
    ordered = np.array([found[r] for r in sorted(found)]) if found else hub[None]
    end = hub + _rim_distance(e, hub, np.array([outer]))[0] * np.array(
        [np.cos(outer), -np.sin(outer)])
    middle_part = np.array([found[r] for r in sorted(found)
                            if LINE_FRACTION[0] * rim <= r <= LINE_FRACTION[1] * rim])
    return Spoke(start, ordered, _gap(traced), end, _line(middle_part))


def _nearest_run(ink: np.ndarray) -> tuple[int, int] | None:
    """Tache d'encre (premier et dernier indice) la plus proche du milieu."""
    middle = len(ink) // 2
    best = None
    k = 0
    while k < len(ink):
        if not ink[k]:
            k += 1
            continue
        low = k
        while k + 1 < len(ink) and ink[k + 1]:
            k += 1
        distance = 0 if low <= middle <= k else min(abs(low - middle), abs(k - middle))
        if best is None or distance < best[0]:
            best = (distance, low, k)
        k += 1
    return None if best is None else (best[1], best[2])


def _line(points: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Droite ajustée sur les points d'un rayon, sans ceux d'un trait croisé
    rattrapés en chemin."""
    if len(points) < 3:
        return None
    center, direction = geo.principal_axis(points)
    rel = points - center
    off = np.abs(rel[:, 0] * direction[1] - rel[:, 1] * direction[0])
    kept = points[off <= LINE_TOLERANCE_MM]
    return geo.principal_axis(kept) if len(kept) >= 3 else (center, direction)


def _gap(traced: dict[float, bool]) -> float:
    """Plus grande interruption (mm) d'un rayon tracé de part et d'autre sur
    au moins 2 mm : un rayon qui n'arrive pas tout à fait à la jante ou au
    moyeu, ou un autre trait rattrapé plus loin, n'est pas interrompu."""
    radii = sorted(traced)
    hits = [r for r in radii if traced[r]]
    if not hits:
        return 0.0
    worst, run, before = 0.0, 0, None
    for r in radii:
        if not traced[r]:
            run += 1
            continue
        if run and before is not None and before - hits[0] >= SPOKE_CONTINUES_MM \
                and hits[-1] - r >= SPOKE_CONTINUES_MM:
            worst = max(worst, run * TRACK_STEP_MM)
        run, before = 0, r
    return worst


def _hub(spokes: list[Spoke], e: Ellipse) -> np.ndarray:
    """Point le plus proche des droites des rayons ; les droites qui passent
    loin de ce point (rayon mal suivi, rayon d'enfant décalé) sont écartées
    pour le recalculer."""
    lines = [s.line for s in spokes if s.line is not None]
    hub = e.center
    for _ in range(2):
        a, b = np.zeros((2, 2)), np.zeros(2)
        for center, direction in lines:
            project = np.eye(2) - np.outer(direction, direction)
            a += project
            b += project @ center
        if len(lines) < 2 or abs(np.linalg.det(a)) < 1e-6:
            return hub
        found = np.linalg.solve(a, b)
        if e.radial(found[None])[0] >= 0.5:
            return hub
        hub = found
        near = [(c, d) for c, d in lines
                if abs((hub - c)[0] * d[1] - (hub - c)[1] * d[0]) <= HUB_LINE_MM]
        if len(near) < 2 or len(near) == len(lines):
            break
        lines = near
    return hub


def _difference(a: float, b: float) -> float:
    """Écart signé (degrés) de ``a`` à ``b``, entre -180 et 180."""
    return float((a - b + 180) % 360 - 180)


def _pairs(spokes: list[Spoke]) -> list[tuple[int, int]]:
    """Cordes : rayons opposés, les mieux alignés d'abord."""
    options = sorted((abs(_difference(spokes[i].angle + 180, spokes[j].angle)), i, j)
                     for i in range(len(spokes)) for j in range(i + 1, len(spokes)))
    used: set[int] = set()
    pairs = []
    for deviation, i, j in options:
        if deviation <= OPPOSITE_DEG and i not in used and j not in used:
            pairs.append((i, j))
            used |= {i, j}
    return pairs


def _segmented(wheel: Wheel) -> int:
    """Cordes tracées en plusieurs morceaux : une moitié interrompue (deux
    moitiés opposées, à 15° près, sont déjà la condition d'une corde)."""
    return sum(max(wheel.spokes[i].gap, wheel.spokes[j].gap) > GAP_MM for i, j in wheel.chords)


def _axes(wheel: Wheel) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Corde horizontale et corde verticale (à 10° près), s'il y en a."""
    found = []
    for target in (0.0, 90.0):
        near = [(abs(_difference(wheel.chord_angle(p), target) % 180), p) for p in wheel.chords]
        near = [(min(d, 180 - d), p) for d, p in near]
        best = min(near, default=None)
        found.append(best[1] if best is not None and best[0] <= AXIS_LOOSE_DEG else None)
    return found[0], found[1]


def _quadrants(wheel: Wheel) -> list[int] | None:
    """Nombre de rayons dans chacun des quatre quadrants délimités par les
    cordes horizontale et verticale."""
    horizontal, vertical = _axes(wheel)
    if horizontal is None or vertical is None:
        return None
    axes = set(horizontal) | set(vertical)
    bounds = sorted(wheel.spokes[k].angle for k in axes)
    counts = [0] * len(bounds)
    for k, spoke in enumerate(wheel.spokes):
        if k in axes:
            continue
        for q in range(len(bounds)):
            low, high = bounds[q], bounds[(q + 1) % len(bounds)]
            if (spoke.angle - low) % 360 < (high - low) % 360:
                counts[q] += 1
                break
    return counts


def _axle_cover(drawing: Drawing, a: np.ndarray, b: np.ndarray) -> float:
    """Part de la distance entre les moyeux longée par un trait (l'essieu)."""
    ab = b - a
    length = float(np.linalg.norm(ab))
    if length < 1e-6:
        return 0.0
    points = drawing.points
    t = ((points - a) @ ab) / length ** 2
    near = (t >= 0) & (t <= 1) & (np.linalg.norm(points - (a + np.outer(t, ab)), axis=1)
                                  <= AXLE_NEAR_MM)
    bins = max(1, int(length / SPOKE_STEP_MM))
    covered = np.unique(np.minimum((t[near] * bins).astype(int), bins - 1))
    return len(covered) / bins


def _rim_gap(drawing: Drawing, e: Ellipse, other: Ellipse) -> float:
    """Plus grand intervalle (mm) de la jante : directions, depuis le centre,
    où aucune encre ne passe près de l'ellipse (les rayons, dans l'axe de leur
    direction, n'en masquent qu'une très petite part). La partie dans l'autre
    roue peut être cachée."""
    angles = np.radians(np.arange(0.0, 360.0, 0.5))
    rim = e.at(angles)
    scales = np.arange(RIM_BAND[0], RIM_BAND[1] + 1e-9, 0.2 / max(e.minor / 2, 1e-6))
    samples = e.center + (rim - e.center)[:, None, :] * scales[None, :, None]
    hit = drawing.on_ink(samples.reshape(-1, 2)).reshape(len(angles), len(scales)).any(axis=1)
    ok = hit | (other.radial(rim) < 1)
    if ok.all():
        return 0.0
    if not ok.any():
        return e.perimeter
    run = longest = 0
    for flag in np.concatenate([ok[np.argmax(ok):], ok[:np.argmax(ok)]]):
        run = 0 if flag else run + 1
        longest = max(longest, run)
    return float(longest * e.perimeter / len(angles))

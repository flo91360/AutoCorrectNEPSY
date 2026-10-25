"""Item 15 : croix (figure à douze côtés).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Le contour extérieur de l'encre est simplifié en polygone : huit coins
saillants (bouts des branches) et quatre coins rentrants (coins du carré
central). Chaque branche va d'un coin rentrant au suivant.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio
from .shapes import EXTRA_ELEMENT_MM, closed_outline

POLYGON_EPSILONS_MM = (1.0, 1.4, 1.8, 2.4, 3.0)  # simplification du contour
WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
MOTOR_MAX_CHANGES = 3  # Motricité A, par ligne
ROUNDED_MM = 1.5  # Motricité B : coin arrondi (contour loin du coin des deux côtés)
SIDE_TRIM_MM = 1.5  # bouts d'un côté écartés pour ajuster sa droite
MAX_CORNER_SHIFT_MM = 6.0  # coin recalculé trop loin du contour : on garde le sommet
GENERAL_MAX_RATIO = 1.5  # largeurs et longueurs des branches
PARALLEL_MAX_DEG = 15.0  # branches opposées dans le prolongement l'une de l'autre…
OFFSET_MAX_FRACTION = 0.5  # … sans décalage de plus de la moitié de leur largeur
GLOBAL_MIN_HEIGHT_MM = 20.0  # Global C
GLOBAL_MAX_RATIO = 1.2  # Global D : distances du centre aux bouts opposés
LOCAL_MAX_OFFSET_MM = 3.0  # Local E : branche entièrement décalée de l'axe
LOCAL_MAX_BRANCH_RATIO = 1.2  # Local E : côtés d'une même branche
SQUARE_MAX_RATIO = 1.5  # Local F : « manifestement un rectangle » au-delà
ON_OUTLINE_MM = 1.5  # encre plus éloignée du contour : autre élément


@dataclass
class Branch:
    name: str
    inner: tuple[np.ndarray, np.ndarray]  # coins rentrants (base de la branche)
    outer: tuple[np.ndarray, np.ndarray]  # coins saillants (bout de la branche)

    @property
    def end_middle(self) -> np.ndarray:
        return (self.outer[0] + self.outer[1]) / 2

    @property
    def base_middle(self) -> np.ndarray:
        return (self.inner[0] + self.inner[1]) / 2

    @property
    def direction(self) -> np.ndarray:
        return geo.unit(self.end_middle - self.base_middle)

    @property
    def sides(self) -> list[float]:
        a, b = self.inner
        o1, o2 = self.outer
        return [float(np.linalg.norm(o1 - a)), float(np.linalg.norm(o2 - o1)),
                float(np.linalg.norm(b - o2)), float(np.linalg.norm(a - b))]

    @property
    def width(self) -> float:
        return max(self.sides[1], self.sides[3])

    @property
    def length(self) -> float:
        return max(self.sides[0], self.sides[2])


def score(drawing: Drawing, item: int = 15) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {}
    marks: list = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, marks=marks)

    outline = closed_outline(drawing)
    polygon = None if outline is None else _cross_polygon(outline)
    if polygon is None:
        reason = "croix à deux dimensions non reconnue (contour à 12 côtés attendu)"
        for code in codes:
            checks[code].fail(reason)
        return result()
    corners, concave = polygon
    sides = [outline[a:b + 1] if a < b else np.vstack([outline[a:], outline[:b + 1]])
             for a, b in zip(corners, np.roll(corners, -1))]
    side_lines = _side_lines(sides, outline[corners])
    vertices = _refined_corners(side_lines, outline[corners])
    branches = _branches(vertices, concave)
    by_name = {b.name: b for b in branches}
    if len(by_name) < 4:
        reason = "branches de la croix non reconnues (haut, droite, bas, gauche)"
        for code in codes:
            checks[code].fail(reason)
        return result()
    top, right, bottom, left = (by_name[n] for n in ("haut", "droite", "bas", "gauche"))
    center = geo.line_intersection(top.end_middle, bottom.end_middle - top.end_middle,
                                   right.end_middle, left.end_middle - right.end_middle)
    if center is None:
        center = vertices[concave].mean(axis=0)
    height = float(np.linalg.norm(bottom.end_middle - top.end_middle))
    span = float(np.linalg.norm(right.end_middle - left.end_middle))
    reach = {b.name: max(float(np.linalg.norm(p - center)) for p in b.outer) for b in branches}
    vertical_ratio = _ratio(reach["haut"], reach["bas"])
    horizontal_ratio = _ratio(reach["droite"], reach["gauche"])
    widths = [b.width for b in branches]
    lengths = [b.length for b in branches]
    width_ratio = max(widths) / max(min(widths), 1e-6)
    length_ratio = max(lengths) / max(min(lengths), 1e-6)
    inner = vertices[concave]
    square_sides = [float(np.linalg.norm(inner[i] - inner[(i + 1) % 4])) for i in range(4)]
    square_ratio = max(square_sides) / max(min(square_sides), 1e-6)
    measures.update({"hauteur_mm": height, "largeur_mm": span, "rapport_largeurs": width_ratio,
                     "rapport_longueurs": length_ratio, "rapport_vertical": vertical_ratio,
                     "rapport_horizontal": horizontal_ratio, "rapport_carre_central": square_ratio})

    marks.append(mk.trace(np.vstack([vertices, vertices[:1]]), "contour lu", 0))
    marks.append(mk.segment(top.end_middle, bottom.end_middle, f"hauteur {fmt(height)}"))
    marks.append(mk.segment(left.end_middle, right.end_middle, f"largeur {fmt(span)}"))
    marks.append(mk.point(center, "centre"))

    rounded = _rounded_corners(sides, vertices)
    for i, gap in rounded:
        marks.append(mk.point(vertices[i], f"coin arrondi {fmt(gap)}"))

    for k, pts in enumerate(sides):
        changes = geo.count_direction_changes(pts, WOBBLE_MM) if len(pts) >= 3 else 0
        length = float(np.linalg.norm(vertices[(k + 1) % 12] - vertices[k]))
        checks["A"].add(changes <= MOTOR_MAX_CHANGES, f"côté de {fmt(length)} : {changes} "
                        "changement(s) de direction (3 au plus)")
    checks["B"].add(not rounded, "aucun coin arrondi ou pincé" if not rounded
                    else f"{len(rounded)} coin(s) arrondi(s)")

    general = checks["G"]
    general.add(True, "croix à deux dimensions")
    for first, second in ((top, bottom), (left, right)):
        angle = geo.angle_between(first.direction, -second.direction)
        offset = _offset(first, second)
        allowed = OFFSET_MAX_FRACTION * (first.width + second.width) / 2
        general.add(angle <= PARALLEL_MAX_DEG and offset <= allowed,
                    f"branches {first.name} et {second.name} dans le prolongement l'une de "
                    f"l'autre (écart d'angle {angle:.0f}°, décalage {fmt(offset)})")
    general.limit(width_ratio, f"largeurs des branches {_list(widths)} : rapport "
                  f"{fmt_ratio(width_ratio)} ≤ 1,5:1", high=GENERAL_MAX_RATIO, unit="ratio")
    general.limit(length_ratio, f"longueurs des branches {_list(lengths)} : rapport "
                  f"{fmt_ratio(length_ratio)} ≤ 1,5:1", high=GENERAL_MAX_RATIO, unit="ratio")

    checks["C"].add(True, "croix à deux dimensions")
    checks["C"].limit(height, f"hauteur de la croix {fmt(height)} ≥ 20 mm", low=GLOBAL_MIN_HEIGHT_MM)

    checks["D"].limit(vertical_ratio, f"centre → bouts haut et bas : {fmt(reach['haut'])} et "
                      f"{fmt(reach['bas'])}, rapport {fmt_ratio(vertical_ratio)} ≤ 1,2:1",
                      high=GLOBAL_MAX_RATIO, unit="ratio")
    checks["D"].limit(horizontal_ratio, f"centre → bouts droite et gauche : "
                      f"{fmt(reach['droite'])} et {fmt(reach['gauche'])}, rapport "
                      f"{fmt_ratio(horizontal_ratio)} ≤ 1,2:1", high=GLOBAL_MAX_RATIO, unit="ratio")

    vertical_axis = geo.unit(bottom.end_middle - top.end_middle)
    horizontal_axis = np.array([vertical_axis[1], -vertical_axis[0]])
    for branch in branches:
        # Une branche verticale est comparée à l'axe central vertical : son
        # décalage se mesure à l'horizontale, et inversement.
        across = horizontal_axis if branch.name in ("haut", "bas") else vertical_axis
        shift = _shift(branch, center, across)
        checks["E"].limit(shift, f"branche {branch.name} : décalée de {fmt(shift)} de l'axe "
                          "central (≤ 3 mm)", high=LOCAL_MAX_OFFSET_MM)
        ratio = max(branch.sides) / max(min(branch.sides), 1e-6)
        checks["E"].limit(ratio, f"branche {branch.name} : côtés {_list(branch.sides)}, rapport "
                          f"{fmt_ratio(ratio)} ≤ 1,2:1", high=LOCAL_MAX_BRANCH_RATIO, unit="ratio")

    extras = _extras(drawing, outline)
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    for branch in branches:
        drawn = branch.sides[:3]
        ratio = max(drawn) / max(min(drawn), 1e-6)
        checks["F"].limit(ratio, f"branche {branch.name} : trois côtés d'un carré (rapport "
                          f"{fmt_ratio(ratio)}, manifestement rectangle au-delà de 1,5:1)",
                          high=SQUARE_MAX_RATIO, unit="ratio")
    checks["F"].limit(square_ratio, f"centre carré (rapport des côtés {fmt_ratio(square_ratio)}, "
                      "manifestement rectangle au-delà de 1,5:1)", high=SQUARE_MAX_RATIO,
                      unit="ratio")
    return result()


def _cross_polygon(outline: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Sommets d'un polygone à 12 côtés qui suit le contour (indices dans le
    contour, parcouru dans le sens des aiguilles d'une montre à l'écran) et
    rangs de ses 4 coins rentrants parmi eux, ou None."""
    contour = outline.astype(np.float32).reshape(-1, 1, 2)
    for epsilon in POLYGON_EPSILONS_MM:
        poly = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2).astype(float)
        if len(poly) != 12:
            continue
        corners = np.array([int(np.argmin(np.linalg.norm(outline - v, axis=1))) for v in poly])
        order = np.argsort(corners)
        corners, poly = corners[order], poly[order]
        concave = np.array([_turn(poly, i) < 0 for i in range(12)])
        if concave.sum() != 4:
            continue
        index = np.flatnonzero(concave)
        if not np.all(np.diff(np.append(index, index[0] + 12)) == 3):
            continue
        return corners, index
    return None


def _signed_area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


def _turn(poly: np.ndarray, i: int) -> float:
    a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
    u, v = b - a, c - b
    return float(u[0] * v[1] - u[1] * v[0])


def _branches(vertices: np.ndarray, concave: np.ndarray) -> list[Branch]:
    """Une branche entre deux coins rentrants qui se suivent, nommée d'après
    sa direction (haut, droite, bas, gauche)."""
    names = {0: "droite", 1: "bas", 2: "gauche", 3: "haut"}
    branches = []
    for k, i in enumerate(concave):
        j = concave[(k + 1) % 4]
        branch = Branch("", (vertices[i], vertices[j]),
                        (vertices[(i + 1) % 12], vertices[(i + 2) % 12]))
        d = branch.direction
        quarter = int(np.round(np.degrees(np.arctan2(d[1], d[0])) / 90)) % 4
        branch.name = names[quarter]
        branches.append(branch)
    return branches


def _side_lines(sides: list[np.ndarray], vertices: np.ndarray) -> list[tuple]:
    """Droite (point, direction) ajustée sur chaque côté, sans ses bouts."""
    lines = []
    for k, pts in enumerate(sides):
        a, b = vertices[k], vertices[(k + 1) % len(vertices)]
        keep = np.minimum(np.linalg.norm(pts - a, axis=1), np.linalg.norm(pts - b, axis=1))
        core = pts[keep > SIDE_TRIM_MM]
        lines.append(geo.principal_axis(core if len(core) >= 3 else np.array([a, b])))
    return lines


def _refined_corners(lines: list[tuple], vertices: np.ndarray) -> np.ndarray:
    """Coins à la rencontre des droites de deux côtés consécutifs (un coin
    arrondi ne raccourcit pas les côtés)."""
    refined = vertices.copy()
    for k in range(len(vertices)):
        (c1, d1), (c2, d2) = lines[k - 1], lines[k]
        corner = geo.line_intersection(c1, d1, c2, d2)
        if corner is not None and np.linalg.norm(corner - vertices[k]) <= MAX_CORNER_SHIFT_MM:
            refined[k] = corner
    return refined


def _rounded_corners(sides: list[np.ndarray], vertices: np.ndarray) -> list[tuple[int, float]]:
    """Coins où le contour passe loin du point de rencontre des deux côtés."""
    found = []
    for k in range(len(vertices)):
        nearest = float(np.sqrt(((np.vstack([sides[k - 1], sides[k]]) - vertices[k]) ** 2)
                                .sum(-1)).min())
        if nearest > ROUNDED_MM:
            found.append((k, nearest))
    return found


def _offset(first: Branch, second: Branch) -> float:
    """Distance entre le bout de la branche opposée et l'axe prolongé de la
    première : décalage ou écartement des branches."""
    normal = np.array([-first.direction[1], first.direction[0]])
    return abs(float((second.end_middle - first.base_middle) @ normal))


def _shift(branch: Branch, center: np.ndarray, normal: np.ndarray) -> float:
    """Distance dont toute la branche est décalée d'un même côté de l'axe
    central passant par ``center`` (0 si l'axe traverse la branche)."""
    values = [float((p - center) @ normal) for p in (*branch.inner, *branch.outer)]
    if min(values) > 0:
        return min(values)
    if max(values) < 0:
        return -max(values)
    return 0.0


def _ratio(a: float, b: float) -> float:
    return max(a, b) / max(min(a, b), 1e-6)


def _list(values: list[float]) -> str:
    return ", ".join(fmt(v, "") for v in values) + " mm"


def _extras(drawing: Drawing, outline: np.ndarray) -> list[float]:
    """Traits éloignés du contour de la croix (à l'intérieur ou à côté)."""
    extras = []
    for stroke in drawing.strokes:
        dist = np.sqrt(((stroke.points[:, None, :] - outline[None, :, :]) ** 2).sum(-1)).min(1)
        away = float((dist > ON_OUTLINE_MM + drawing.stroke_width).sum()) * STEP_MM
        if away >= EXTRA_ELEMENT_MM:
            extras.append(away)
    extras += [size for size in drawing.component_sizes[1:] if size >= EXTRA_ELEMENT_MM]
    return extras

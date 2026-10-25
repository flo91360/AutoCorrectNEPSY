"""Item 11 : rectangle avec un petit carré dans le coin supérieur gauche (drapeau).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

import numpy as np

from ..strokes import Drawing, StraightLine
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio, not_recognized
from .shapes import (check_lines, dangling_tail, end_at, extra_elements, intersection,
                     review_notes, split_line)

STRAIGHT_BAND_MM = 3.0  # Motricité A : barre grisée de 3 mm
JOIN_MM = 2.0  # Général et Motricité B : intervalle ou dépassement aux intersections
GENERAL_RATIO = (1.2, 1.7)  # plus long côté horizontal / plus court côté vertical
HORIZONTAL_SIDES_DEG = 20.0  # Global C : haut et bas du rectangle
# Global D : un côté du petit carré posé sur la ligne médiane du rectangle
# compte comme contenu dans la moitié (épaisseur du trait et de la règle).
HALF_TOLERANCE_MM = 1.0
LOCAL_MAX_HORIZONTAL_MM = 70.0  # Local E
LOCAL_MAX_VERTICAL_MM = 50.0  # Local F
LOCAL_MAX_SQUARE_RATIO = 1.2  # Local F : plus long / plus court côté du petit carré


def score(drawing: Drawing, item: int = 11) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    horizontals = [l for l in lines if l.angle_to_horizontal() <= 45]
    verticals = [l for l in lines if l.angle_to_horizontal() > 45]
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)
    marks: list = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    def fail(reason: str) -> ItemResult:
        check_lines(checks["A"], lines, STRAIGHT_BAND_MM)
        marks.extend(mk.bande(line, at="bout") for line in lines)
        not_recognized(checks, ("G", "B", "C", "D", "E", "F"), reason, notes)
        return result()

    rectangle = _rectangle(horizontals, verticals)
    if rectangle is None:
        return fail(f"grand rectangle non reconnu ({len(horizontals)} ligne(s) horizontale(s), "
                    f"{len(verticals)} verticale(s))")
    top, bottom, left, right = rectangle
    corners = [intersection(a, b) for a, b in ((top, left), (top, right), (bottom, right),
                                                (bottom, left))]
    if any(p is None for p in corners):
        return fail("côtés parallèles : coins introuvables")
    tl, tr, br, bl = corners
    square = _square(horizontals, verticals, rectangle, tl, tr, bl)
    if square is None:
        return fail("petit carré non reconnu dans le coin supérieur gauche")
    inner_h, inner_v = square
    s_left, s_corner, s_top = (intersection(inner_h, left), intersection(inner_h, inner_v),
                               intersection(inner_v, top))
    if any(p is None for p in (s_left, s_corner, s_top)):
        return fail("côtés parallèles : coins du petit carré introuvables")
    figure = [top, bottom, left, right, inner_h, inner_v]
    # Le haut et le côté gauche du rectangle sont aussi des côtés du petit
    # carré : chaque côté est mesuré à part avec la barre grisée.
    sides = (split_line(top, [s_top]) + split_line(left, [s_left])
             + [l for l in lines if l is not top and l is not left])
    check_lines(checks["A"], sides, STRAIGHT_BAND_MM)
    marks.extend(mk.bande(line, at="bout") for line in sides)

    widths = {"haut": float(np.linalg.norm(tr - tl)), "bas": float(np.linalg.norm(br - bl))}
    heights = {"gauche": float(np.linalg.norm(bl - tl)), "droit": float(np.linalg.norm(br - tr))}
    ratio = max(widths.values()) / max(min(heights.values()), 1e-6)
    square_sides = [float(np.linalg.norm(s_top - tl)), float(np.linalg.norm(s_left - tl)),
                    float(np.linalg.norm(s_corner - s_left)), float(np.linalg.norm(s_top - s_corner))]
    square_ratio = max(square_sides) / max(min(square_sides), 1e-6)
    # Position du petit carré : part du côté gauche (depuis le haut) et du côté
    # supérieur (depuis la gauche).
    down = float((s_left - tl) @ (bl - tl)) / max(float((bl - tl) @ (bl - tl)), 1e-6)
    across = float((s_top - tl) @ (tr - tl)) / max(float((tr - tl) @ (tr - tl)), 1e-6)
    below_middle = max(_beyond_middle(p, top, bottom, axis=1) for p in inner_h.ends)
    right_of_middle = max(_beyond_middle(p, left, right, axis=0) for p in inner_v.ends)
    measures.update({f"cote_{k}_mm": v for k, v in (widths | heights).items()})
    measures.update({"rapport_horizontal_vertical": ratio, "rapport_petit_carre": square_ratio,
                     "position_bas_carre": down, "position_droite_carre": across})

    marks += [mk.cote(tl, tr, f"haut {fmt(widths['haut'])}", side=(0.0, -1.0)),
              mk.cote(bl, br, f"bas {fmt(widths['bas'])}", side=(0.0, 1.0)),
              mk.cote(tl, bl, f"gauche {fmt(heights['gauche'])}", side=(-1.0, 0.0)),
              mk.cote(tr, br, f"droit {fmt(heights['droit'])}", side=(1.0, 0.0)),
              mk.segment(s_left, s_corner, fmt(square_sides[2])),
              mk.segment(s_corner, s_top, fmt(square_sides[3]))]

    junctions = [(name, point, max(value, dangling_tail(drawing, figure, point)))
                 for name, point, value in _junctions(rectangle, square, corners, s_left,
                                                      s_corner, s_top)]
    worst_name, worst_point, worst_value = max(junctions, key=lambda j: j[2])
    measures["jonction_max_mm"] = worst_value
    if worst_value > 0.5:
        marks.append(mk.point(worst_point, f"{worst_name} {fmt(worst_value)}"))
    join_text = (f"plus grand intervalle ou dépassement aux intersections {fmt(worst_value)} "
                 f"({worst_name}) ≤ 2 mm")
    shared = (end_at(inner_h, s_left).gap <= JOIN_MM and end_at(inner_v, s_top).gap <= JOIN_MM)

    general = checks["G"]
    general.add(max(widths.values()) > max(heights.values()),
                "grand rectangle plus large que haut")
    general.limit(worst_value, join_text, high=JOIN_MM)
    general.limit(down, f"bas du petit carré au {down * 100:.0f} % du côté gauche "
                  "(tiers central : 33 à 67 %)", low=1 / 3, high=2 / 3, unit="part")
    general.limit(across, f"droite du petit carré au {across * 100:.0f} % du côté supérieur "
                  "(moitié gauche : ≤ 50 %)", high=0.5, unit="part")
    general.add(shared, "petit carré qui partage le coin supérieur gauche" if shared
                else "petit carré détaché du coin supérieur gauche")
    lo, hi = GENERAL_RATIO
    general.limit(ratio, f"plus long côté horizontal / plus court côté vertical "
                  f"{fmt_ratio(ratio)} (entre 1,2:1 et 1,7:1)", low=lo, high=hi, unit="ratio")

    checks["B"].limit(worst_value, join_text, high=JOIN_MM)

    checks["C"].add(True, "drapeau : petit carré dans le coin supérieur gauche du rectangle")
    for name, line in (("haut", top), ("bas", bottom)):
        angle = line.angle_to_horizontal()
        checks["C"].limit(angle, f"côté {name} à {angle:.0f}° de l'horizontale (≤ 20°)",
                          high=HORIZONTAL_SIDES_DEG, unit="deg")

    checks["D"].limit(below_middle, "bas du petit carré dans la moitié supérieure "
                      f"({_side_text(below_middle, 'sous', 'au-dessus de')} la ligne médiane)",
                      high=HALF_TOLERANCE_MM)
    checks["D"].limit(right_of_middle, "droite du petit carré dans la moitié gauche "
                      f"({_side_text(right_of_middle, 'à droite de', 'à gauche de')} "
                      "la ligne médiane)", high=HALF_TOLERANCE_MM)

    for name, value in widths.items():
        checks["E"].limit(value, f"côté {name} {fmt(value)} ≤ 70 mm", high=LOCAL_MAX_HORIZONTAL_MM)

    extras = extra_elements(drawing, figure)
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    for name, value in heights.items():
        checks["F"].limit(value, f"côté {name} {fmt(value)} ≤ 50 mm", high=LOCAL_MAX_VERTICAL_MM)
    checks["F"].limit(square_ratio, f"petit carré : plus long / plus court côté "
                      f"{fmt_ratio(square_ratio)} ≤ 1,2:1", high=LOCAL_MAX_SQUARE_RATIO,
                      unit="ratio")
    return result()


def _rectangle(horizontals: list[StraightLine], verticals: list[StraightLine]):
    """Haut, bas, gauche et droite du grand rectangle : les deux plus longues
    horizontales, puis les verticales qui les relient le mieux à gauche et à droite."""
    if len(horizontals) < 2 or len(verticals) < 2:
        return None
    top, bottom = sorted(sorted(horizontals, key=lambda l: -l.length)[:2],
                         key=lambda l: l.center[1])
    if bottom.center[1] - top.center[1] < 5.0:
        return None

    def side(pick_left: bool) -> StraightLine | None:
        a = min(top.ends, key=lambda p: p[0] if pick_left else -p[0])
        b = min(bottom.ends, key=lambda p: p[0] if pick_left else -p[0])
        def cost(line: StraightLine) -> float:
            upper, lower = sorted(line.ends, key=lambda p: p[1])
            return float(np.linalg.norm(upper - a) + np.linalg.norm(lower - b))

        return min(verticals, key=cost)

    left, right = side(True), side(False)
    if left is right or left.center[0] >= right.center[0]:
        return None
    return top, bottom, left, right


def _square(horizontals, verticals, rectangle, tl, tr, bl):
    """Côté inférieur et côté droit du petit carré : lignes à l'intérieur du
    rectangle, les plus proches du coin supérieur gauche."""
    top, bottom, left, right = rectangle
    inner_h = [l for l in horizontals if l is not top and l is not bottom
               and _inside(l.center, tl, tr, bl)]
    inner_v = [l for l in verticals if l is not left and l is not right
               and _inside(l.center, tl, tr, bl)]
    if not inner_h or not inner_v:
        return None
    return (max(inner_h, key=lambda l: l.length), max(inner_v, key=lambda l: l.length))


def _inside(point, tl, tr, bl) -> bool:
    u = float((point - tl) @ (tr - tl)) / max(float((tr - tl) @ (tr - tl)), 1e-6)
    v = float((point - tl) @ (bl - tl)) / max(float((bl - tl) @ (bl - tl)), 1e-6)
    return 0 < u < 1 and 0 < v < 1


def _distance_to_line(point: np.ndarray, line: StraightLine) -> float:
    normal = np.array([-line.direction[1], line.direction[0]])
    return abs(float((point - line.center) @ normal))


def _beyond_middle(point: np.ndarray, first: StraightLine, second: StraightLine,
                   axis: int) -> float:
    """Distance (mm) dont ``point`` dépasse la ligne médiane entre deux côtés
    opposés (vers le bas pour ``axis=1``, vers la droite pour ``axis=0``)."""
    a = _at(first, point, axis)
    b = _at(second, point, axis)
    return float(point[axis] - (a + b) / 2)


def _at(line: StraightLine, point: np.ndarray, axis: int) -> float:
    """Coordonnée ``axis`` de la ligne à la hauteur (ou l'abscisse) du point."""
    other = 1 - axis
    d = line.direction
    if abs(d[other]) < 1e-9:
        return float(line.center[axis])
    t = (point[other] - line.center[other]) / d[other]
    return float(line.center[axis] + t * d[axis])


def _side_text(value: float, positive: str, negative: str) -> str:
    return f"{fmt(abs(value))} {positive if value > 0 else negative}"


def _junctions(rectangle, square, corners, s_left, s_corner, s_top):
    top, bottom, left, right = rectangle
    inner_h, inner_v = square
    tl, tr, br, bl = corners

    def worst(*pairs) -> float:
        values = [end_at(line, point) for line, point in pairs]
        return max(max(v.gap, v.overshoot) for v in values)

    return [("coin haut-gauche", tl, worst((top, tl), (left, tl))),
            ("coin haut-droit", tr, worst((top, tr), (right, tr))),
            ("coin bas-droit", br, worst((bottom, br), (right, br))),
            ("coin bas-gauche", bl, worst((bottom, bl), (left, bl))),
            ("carré à gauche", s_left, worst((inner_h, s_left))),
            ("coin du carré", s_corner, worst((inner_h, s_corner), (inner_v, s_corner))),
            ("carré en haut", s_top, worst((inner_v, s_top)))]

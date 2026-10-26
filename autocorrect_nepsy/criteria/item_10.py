"""Item 10 : triangle posé sur un trapèze isocèle (bateau).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Le haut du trapèze peut être tracé en plusieurs morceaux (de part et d'autre du
triangle) : ses coins sont pris là où ses côtés obliques le rejoignent, et les
coins du triangle au bas de ses côtés. Quand un côté du triangle se prolonge
un peu au-delà de l'endroit où un autre trait le touche (il continue le long
du haut du trapèze), le coin est à cette jonction : selon les petits détails
du tracé, ce prolongement est rattaché au côté ou à l'autre trait.
"""

from __future__ import annotations

from itertools import permutations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing, StraightLine
from . import marks as mk
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .shapes import (check_lines, dangling_tail, end_at, extra_elements, intersection,
                     review_notes)

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
STRAIGHT_BAND_MM = threshold(3.0, "A", "largeur de la barre grisée où tient chaque ligne")
JOIN_MM = threshold(2.0, "B", "intervalle ou dépassement à chaque intersection, au plus")
GENERAL_MAX_GAP_MM = threshold(3.0, "G", "écart entre la base du triangle et le haut du trapèze, "
                               "au plus")
GENERAL_MAX_PARTS_RATIO = threshold(1.5, "G", "rapport des parties du haut du trapèze de part et "
                                    "d'autre du triangle, au plus", "ratio")
GLOBAL_MAX_GAP_MM = threshold(5.0, "C", "écart entre la base du triangle et le haut de la "
                              "figure, au plus")
LOCAL_MAX_HEIGHT_RATIO = threshold(1.3, "F", "rapport de la hauteur à la base du triangle, au plus",
                                   "ratio")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
HORIZONTAL_DEG = 30.0  # côtés horizontaux : base du triangle, haut et bas du trapèze
APEX_MAX_GAP_MM = 8.0  # les deux côtés du triangle se rejoignent au sommet
CROSSING_MM = 5.0  # côté du triangle qui traverse le haut du trapèze : coin à la traversée
OWN_BASE_MM = 3.0  # base propre du triangle : ses bouts sont aux coins du triangle
TOUCH_MM = 1.0  # le bout d'un autre trait touche le côté du triangle
TAIL_MAX_FRACTION = 0.25  # prolongement coupé : au plus ce quart du côté
# Global D : un côté si courbé que la forme n'est plus reconnaissable (flèche
# de la courbe, encre non comprise, plus grande que cette part de sa longueur
# et que la marge de mesure).
CURVED_FRACTION = 0.25
CURVED_MIN_MM = 2.0
ISOSCELES_MIN_BASES_RATIO = 1.15  # plus long / plus court des côtés parallèles
ISOSCELES_MAX_PARALLEL_DEG = 12.0  # côtés supérieur et inférieur parallèles
ISOSCELES_MIN_LEG_DEG = 8.0  # côtés obliques inclinés (pas un rectangle)
ISOSCELES_MAX_LEG_DIFF_DEG = 20.0  # côtés obliques symétriques
ISOSCELES_MAX_LEGS_RATIO = 1.5  # côtés obliques de longueurs voisines


def score(drawing: Drawing, item: int = 10) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    lines = drawing.significant_lines()
    scoring.measures["nombre_lignes"] = len(lines)
    scoring.notes += review_notes(lines)
    check_lines(scoring["A"], lines, STRAIGHT_BAND_MM)
    scoring.marks += [mk.bande(line, at="bout") for line in lines]

    def fail(reason: str) -> ItemResult:
        scoring.not_recognized(("G", "B", "C", "D", "E", "F"), reason)
        return scoring.result()

    sides = _triangle_sides(lines)
    if sides is None:
        return fail("triangle non reconnu (deux côtés qui se rejoignent en un sommet)")
    drawn = list(sides)  # côtés tels que tracés, avant coupe
    left, right = (_cut_at_junction(side, drawing) for side in sides)
    apex = intersection(left, right)
    if apex is None:
        apex = (_top(left) + _top(right)) / 2
    rest = [l for l in lines if all(l is not side for side in drawn)]
    horizontals = [l for l in rest if l.angle_to_horizontal() <= HORIZONTAL_DEG
                   and l.center[1] > apex[1]]
    lowest_side = max(_bottom(left)[1], _bottom(right)[1])
    bottoms = [l for l in horizontals if l.center[1] > lowest_side + 3.0]
    if not bottoms:
        return fail("figure à quatre côtés non reconnue sous le triangle")
    bottom = max(bottoms, key=lambda l: l.center[1])
    uppers = [l for l in horizontals if l is not bottom]
    slanted = [l for l in rest if l.angle_to_horizontal() > HORIZONTAL_DEG]
    bottom_left, bottom_right = sorted(bottom.ends, key=lambda p: p[0])
    leg_left = _leg(slanted, bottom_left, True, bottom)
    leg_right = _leg(slanted, bottom_right, False, bottom)
    if leg_left is None or leg_right is None or not uppers:
        return fail("figure à quatre côtés non reconnue sous le triangle")
    top_left = _nearest(uppers, _top(leg_left))
    top_right = _nearest(uppers, _top(leg_right))
    pl, pr = _corner(left, uppers), _corner(right, uppers)
    corners = [intersection(top_left, leg_left), intersection(top_right, leg_right),
               intersection(bottom, leg_right), intersection(bottom, leg_left)]
    if any(p is None for p in corners):
        return fail("côtés parallèles : coins introuvables")
    tl, tr, br, bl = corners
    own_base = next((l for l in uppers if _joins(l, pl, pr)), None)
    figure = list({id(l): l for l in (left, right, bottom, leg_left, leg_right, top_left,
                                      top_right, own_base) if l is not None}.values())
    owned = figure + drawn  # lignes du dessin qui appartiennent à la figure

    base_length = float(np.linalg.norm(pr - pl))
    top_length = float(np.linalg.norm(tr - tl))
    along = geo.unit(tr - tl)
    left_part, right_part = float((pl - tl) @ along), float((tr - pr) @ along)
    parts_ratio = (max(left_part, right_part) / min(left_part, right_part)
                   if min(left_part, right_part) > 0 else float("inf"))
    # Écart entre chaque coin du triangle et le tracé du trapèze (hors base propre).
    excluded = {id(l) for l in (*drawn, own_base, leg_left, leg_right, bottom)}
    others = [l for l in drawing.lines if id(l) not in excluded]
    corner_gaps = [_distance_to_lines(p, others) for p in (pl, pr)]
    gap = max(corner_gaps)
    under = _line_under(apex, uppers)
    foot = (_project(apex, under) if under is not None
            else pl + geo.unit(pr - pl) * float((apex - pl) @ geo.unit(pr - pl)))
    height = float(np.linalg.norm(apex - foot))
    height_ratio = height / max(base_length, 1e-6)
    scoring.measures.update({"base_triangle_mm": base_length, "cote_haut_trapeze_mm": top_length,
                             "hauteur_triangle_mm": height, "ecart_base_mm": gap,
                             "partie_gauche_mm": left_part, "partie_droite_mm": right_part,
                             "rapport_parties_haut": parts_ratio,
                             "rapport_hauteur_base": height_ratio})

    scoring.marks += [mk.cote(pl, pr, f"base {fmt(base_length)}", side=(0.0, -1.0)),
                      mk.cote(tl, tr, f"haut {fmt(top_length)}", side=(0.0, 1.0)),
                      mk.segment(apex, foot, f"hauteur {fmt(height)}")]
    if min(left_part, right_part) > 0:
        scoring.marks += [mk.segment(tl, tl + along * left_part, fmt(left_part)),
                          mk.segment(tr - along * right_part, tr, fmt(right_part))]
    if gap > 0.5:
        worst = (pl, pr)[int(np.argmax(corner_gaps))]
        scoring.marks.append(mk.point(worst, f"écart {fmt(gap)}"))

    def junction(name: str, point: np.ndarray, *meeting: StraightLine,
                 extra: float = 0.0) -> tuple[str, np.ndarray, float]:
        values = [extra, dangling_tail(drawing, owned, point)]
        for line in meeting:
            at = end_at(line, point)
            values += [at.gap, at.overshoot]
        return name, point, max(values)

    junctions = [junction("sommet", apex, left, right),
                 junction("coin haut-gauche", tl, top_left, leg_left),
                 junction("coin haut-droit", tr, top_right, leg_right),
                 junction("coin bas-droit", br, bottom, leg_right),
                 junction("coin bas-gauche", bl, bottom, leg_left),
                 junction("coin gauche du triangle", pl, left, extra=corner_gaps[0]),
                 junction("coin droit du triangle", pr, right, extra=corner_gaps[1])]
    worst_name, worst_point, worst_value = max(junctions, key=lambda j: j[2])
    scoring.measures["jonction_max_mm"] = worst_value
    if worst_value > 0.5:
        scoring.marks.append(mk.point(worst_point, f"{worst_name} {fmt(worst_value)}"))
    scoring["B"].limit(worst_value, f"plus grand intervalle ou dépassement aux intersections "
                       f"{fmt(worst_value)} ({worst_name}) ≤ {JOIN_MM.text}", high=JOIN_MM)

    curved = [l for l in figure
              if l.width - l.stroke_width > max(CURVED_FRACTION * l.length, CURVED_MIN_MM)]
    trapezoid, trapezoid_text = _isosceles(tl, tr, br, bl)

    general = scoring["G"]
    general.add(trapezoid and not curved, "triangle au-dessus d'un trapèze isocèle, sans "
                "distorsion majeure" if trapezoid and not curved
                else f"triangle au-dessus d'un trapèze isocèle : non ({trapezoid_text})")
    general.add(base_length < top_length, f"base du triangle {fmt(base_length)} plus courte "
                f"que le haut du trapèze {fmt(top_length)}")
    general.limit(gap, f"écart base du triangle / haut du trapèze {fmt(gap)} ≤ "
                  f"{GENERAL_MAX_GAP_MM.text}",
                  high=GENERAL_MAX_GAP_MM)
    general.limit(parts_ratio, f"parties du haut du trapèze de part et d'autre du triangle "
                  f"({fmt(left_part)} et {fmt(right_part)}) : rapport {fmt_ratio(parts_ratio)} "
                  f"≤ {GENERAL_MAX_PARTS_RATIO.text}", high=GENERAL_MAX_PARTS_RATIO, unit="ratio")

    scoring["C"].add(True, "triangle au-dessus d'une figure à quatre côtés")
    scoring["C"].limit(gap, f"écart base du triangle / haut de la figure {fmt(gap)} ≤ "
                       f"{GLOBAL_MAX_GAP_MM.text}",
                       high=GLOBAL_MAX_GAP_MM)
    scoring["C"].add(base_length < top_length, f"base du triangle {fmt(base_length)} plus courte "
                     f"que le haut de la figure {fmt(top_length)}")

    scoring["D"].add(not curved, "aucun côté courbe" if not curved
                     else f"{len(curved)} côté(s) trop courbé(s)")

    scoring["E"].add(trapezoid, f"triangle et trapèze isocèle ({trapezoid_text})")

    extras = extra_elements(drawing, owned)
    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    scoring["F"].limit(height_ratio, f"hauteur / base du triangle {fmt_ratio(height_ratio)} "
                       f"≤ {LOCAL_MAX_HEIGHT_RATIO.text}", high=LOCAL_MAX_HEIGHT_RATIO, unit="ratio")
    return scoring.result()


def _top(line: StraightLine) -> np.ndarray:
    return min(line.ends, key=lambda p: p[1])


def _bottom(line: StraightLine) -> np.ndarray:
    return max(line.ends, key=lambda p: p[1])


def _project(point: np.ndarray, line: StraightLine) -> np.ndarray:
    return line.center + line.direction * float((point - line.center) @ line.direction)


def _distance_to_lines(point: np.ndarray, lines: list[StraightLine]) -> float:
    if not lines:
        return float("inf")
    points = np.vstack([line.points for line in lines])
    return float(np.sqrt(((points - point) ** 2).sum(axis=1)).min())


def _nearest(lines: list[StraightLine], point: np.ndarray) -> StraightLine:
    return min(lines, key=lambda l: _distance_to_lines(point, [l]))


def _triangle_sides(lines: list[StraightLine]) -> tuple[StraightLine, StraightLine] | None:
    """Côtés gauche (« / ») et droit (« \\ ») du triangle : les deux lignes
    obliques les plus longues dont les hauts se rejoignent."""
    slanted = [l for l in lines if l.angle_to_horizontal() > HORIZONTAL_DEG]
    best = None
    for a, b in permutations(slanted, 2):
        if not (_bottom(a)[0] < _top(a)[0] and _bottom(b)[0] > _top(b)[0]):
            continue
        apex_gap = float(np.linalg.norm(_top(a) - _top(b)))
        if apex_gap > max(APEX_MAX_GAP_MM, 0.25 * min(a.length, b.length)):
            continue
        if best is None or a.length + b.length > best[0]:
            best = (a.length + b.length, a, b)
    return None if best is None else (best[1], best[2])


def _cut_at_junction(side: StraightLine, drawing: Drawing) -> StraightLine:
    """Côté du triangle coupé là où le bout d'un autre trait le touche près de
    son bas : au-delà, le trait continue le long du haut du trapèze."""
    top = _top(side)
    down = 1.0 if side.position(_bottom(side)) > side.position(top) else -1.0
    bottom_at = down * side.position(_bottom(side))
    cut = None
    for stroke in drawing.strokes:
        if stroke.closed or len(stroke.points) < 2:
            continue
        for end in (stroke.points[0], stroke.points[-1]):
            gaps = np.linalg.norm(side.points - end, axis=1)
            if gaps.min() > TOUCH_MM:
                continue
            at = down * side.position(side.points[int(np.argmin(gaps))])
            tail = bottom_at - at
            if TOUCH_MM < tail <= TAIL_MAX_FRACTION * side.length and (cut is None or at < cut):
                cut = at
    if cut is None:
        return side
    kept = side.points[down * ((side.points - side.center) @ side.direction) <= cut]
    return StraightLine([kept], side.stroke_width) if len(kept) >= 3 else side


def _leg(slanted: list[StraightLine], corner: np.ndarray, left_side: bool,
         bottom: StraightLine) -> StraightLine | None:
    """Côté oblique du trapèze qui part du coin ``corner`` du côté inférieur."""
    candidates = [l for l in slanted
                  if (l.center[0] < bottom.center[0]) == left_side
                  and np.linalg.norm(_bottom(l) - corner) <= max(6.0, 0.5 * l.length)]
    return min(candidates, key=lambda l: np.linalg.norm(_bottom(l) - corner), default=None)


def _corner(side: StraightLine, uppers: list[StraightLine]) -> np.ndarray:
    """Coin du triangle au bas d'un côté : le bout du côté, ou l'endroit où il
    traverse le haut du trapèze s'il le dépasse."""
    end = _bottom(side)
    for line in uppers:
        crossing = intersection(side, line)
        if crossing is None or np.linalg.norm(crossing - end) > CROSSING_MM:
            continue
        on_side = side.t0 <= side.position(crossing) <= side.t1
        on_line = line.t0 - 1.0 <= line.position(crossing) <= line.t1 + 1.0
        if on_side and on_line:
            return crossing
    return end


def _joins(line: StraightLine, pl: np.ndarray, pr: np.ndarray) -> bool:
    """La ligne va d'un coin du triangle à l'autre : c'est sa base propre."""
    a, b = sorted(line.ends, key=lambda p: p[0])
    return np.linalg.norm(a - pl) <= OWN_BASE_MM and np.linalg.norm(b - pr) <= OWN_BASE_MM


def _line_under(apex: np.ndarray, uppers: list[StraightLine]) -> StraightLine | None:
    """Ligne horizontale qui passe sous le sommet (base du triangle)."""
    under = [l for l in uppers if l.t0 - 1.0 <= l.position(apex) <= l.t1 + 1.0
             and _project(apex, l)[1] > apex[1]]
    return min(under, key=lambda l: _project(apex, l)[1], default=None)


def _isosceles(tl, tr, br, bl) -> tuple[bool, str]:
    """La figure à quatre côtés est-elle un trapèze isocèle ?"""
    parallel = geo.angle_between(tr - tl, br - bl)
    parallel = min(parallel, 180 - parallel)
    lengths = sorted((np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    bases_ratio = lengths[1] / max(lengths[0], 1e-6)
    legs = sorted((np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    legs_ratio = legs[1] / max(legs[0], 1e-6)
    # Inclinaison des côtés obliques par rapport à la verticale, positive quand
    # ils se rapprochent vers le bas.
    lean_left = float(np.degrees(np.arctan2(bl[0] - tl[0], bl[1] - tl[1])))
    lean_right = float(np.degrees(np.arctan2(tr[0] - br[0], br[1] - tr[1])))
    mirrored = (min(abs(lean_left), abs(lean_right)) >= ISOSCELES_MIN_LEG_DEG
                and np.sign(lean_left) == np.sign(lean_right)
                and abs(lean_left - lean_right) <= ISOSCELES_MAX_LEG_DIFF_DEG)
    ok = (parallel <= ISOSCELES_MAX_PARALLEL_DEG and bases_ratio >= ISOSCELES_MIN_BASES_RATIO
          and legs_ratio <= ISOSCELES_MAX_LEGS_RATIO and mirrored)
    text = (f"haut et bas à {parallel:.0f}° l'un de l'autre, rapport {fmt_ratio(bases_ratio)} ; "
            f"côtés obliques inclinés de {abs(lean_left):.0f}° et {abs(lean_right):.0f}°, "
            f"rapport de longueur {fmt_ratio(legs_ratio)}")
    return ok, text

"""Item 13 : éventail de sept lignes radiales sur une ligne de base.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Les lignes radiales sont les lignes qui partent de la ligne de base ; la plus
verticale est la ligne centrale, les autres sont de part et d'autre.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing, StraightLine
from . import marks as mk
from .base import Checks, ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .shapes import check_lines, extra_elements, intersection, review_notes

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
STRAIGHT_BAND_MM = threshold(2.0, "A", "largeur de la barre grisée où tient chaque ligne")
JOIN_MM = threshold(2.0, "B", "intervalle ou dépassement entre une ligne radiale et la base, "
                    "au plus")
PER_SIDE = threshold(3, "GC", "lignes radiales de chaque côté de la ligne centrale, exactement",
                     "nombre")
GENERAL_BASE_DEG = threshold(20.0, "G", "écart de la base à l'horizontale, au plus", "deg")
CONVERGENCE_THIRD = (threshold(1 / 3, "GD", "position du point de convergence sur la base, au "
                               "moins (tiers central)", "part"),
                     threshold(2 / 3, "GD", "position du point de convergence sur la base, au "
                               "plus (tiers central)", "part"))
GENERAL_SPREAD_MM = threshold(5.0, "G", "écart sur la base entre les lignes radiales d'un même "
                              "côté, au plus")
GLOBAL_BASE_DEG = threshold(10.0, "D", "écart de la base à l'horizontale, au plus", "deg")
GLOBAL_CLUSTER_MM = threshold(3.0, "D", "écart sur la base entre lignes qui convergent au même "
                              "point, au plus")
GLOBAL_MIN_CONVERGING = threshold(5, "D", "lignes radiales qui convergent au même point, au moins",
                                  "nombre")
LOCAL_MAX_RADIAL_RATIO = threshold(1.2, "E", "rapport de la plus longue à la plus courte ligne "
                                   "radiale, au plus", "ratio")
LOCAL_MIN_BASE_MM = threshold(40.0, "F", "longueur de la base, au moins")
LOCAL_MIN_RADIAL_MM = threshold(15.0, "F", "longueur de la plus courte ligne radiale, au moins")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
BASE_MAX_DEG = 30.0  # au-delà, ce n'est plus la ligne de base
RADIAL_MIN_DEG = 10.0  # une ligne radiale s'élève au-dessus de la base
RADIAL_NEAR_MM = 8.0  # bas d'une ligne radiale près de la ligne de base
CENTRAL_MAX_DEG = 25.0  # ligne centrale « relativement verticale »
CONVERGENCE_ZONE_MM = 3.0  # tache d'encre au point de convergence, ignorée
DOUBLED_MAX_MM = 3.0  # base repassée : ce n'est plus un seul trait


def score(drawing: Drawing, item: int = 13) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()
    lines = drawing.significant_lines()
    scoring.measures["nombre_lignes"] = len(lines)
    scoring.notes += review_notes(lines)

    def fail(reason: str) -> ItemResult:
        _check_straight(scoring["A"], scoring.marks, lines, None)
        scoring.not_recognized(("G", "B", "C", "D", "E", "F"), reason)
        return scoring.result()

    flat = [l for l in lines if l.angle_to_horizontal() <= BASE_MAX_DEG]
    if not flat:
        return fail("ligne de base non reconnue")
    base = max(flat, key=lambda l: l.length)
    radials = [l for l in lines if l is not base and _is_radial(l, base)]
    if not radials:
        return fail("aucune ligne radiale reconnue sur la ligne de base")
    central = min(radials, key=lambda l: l.angle_to_vertical())
    if central.angle_to_vertical() > CENTRAL_MAX_DEG:
        central = None
    left = [l for l in radials if l is not central and _top(l)[0] < _bottom(l)[0]]
    right = [l for l in radials if l is not central and _top(l)[0] >= _bottom(l)[0]]
    feet = {id(l): _foot(l, base) for l in radials}
    meeting = np.median(np.array(list(feet.values())), axis=0)
    _check_straight(scoring["A"], scoring.marks, lines, meeting)
    position = {id(l): base.position(feet[id(l)]) - base.t0 for l in radials}
    base_angle = base.angle_to_horizontal()
    lengths = [l.length for l in radials]
    scoring.measures.update({"base_mm": base.length, "base_angle_deg": base_angle,
                             "radiales_gauche": len(left), "radiales_droite": len(right),
                             "ligne_centrale": float(central is not None)})

    scoring.marks.append(mk.cote(*base.ends, f"base {fmt(base.length)} · {base_angle:.0f}°",
                                 side=(0.0, 1.0)))
    for line in radials:
        scoring.marks.append(mk.segment(*sorted(line.ends, key=lambda p: p[1]), fmt(line.length)))

    junctions = [(_join_gap(line, base), _bottom(line)) for line in radials]
    worst, worst_point = max(junctions, key=lambda j: j[0])
    scoring.measures["jonction_max_mm"] = worst
    if worst > 0.5:
        scoring.marks.append(mk.point(worst_point, f"écart {fmt(worst)}"))
    scoring["B"].limit(worst, f"plus grand intervalle ou dépassement entre une ligne radiale et "
                       f"la base {fmt(worst)} ≤ {JOIN_MM.text}", high=JOIN_MM)

    layout_ok = central is not None and len(left) == PER_SIDE and len(right) == PER_SIDE
    layout_text = (f"{len(left)} à gauche, {len(right)} à droite, ligne centrale "
                   f"{'verticale' if central is not None else 'absente'}")
    convergence = float(np.median(list(position.values()))) / max(base.length, 1e-6)
    scoring.measures["convergence_sur_base"] = convergence
    continuous = base.interruptions == 0 and base.doubled_length < DOUBLED_MAX_MM

    general = scoring["G"]
    general.add(continuous, "ligne de base d'un seul trait" if continuous
                else f"ligne de base en plusieurs traits ({base.interruptions} interruption(s))")
    general.limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale "
                  f"(≤ {GENERAL_BASE_DEG.text})",
                  high=GENERAL_BASE_DEG, unit="deg")
    general.add(layout_ok, "trois lignes radiales de chaque côté d'une ligne centrale "
                f"({layout_text})")
    first, last = CONVERGENCE_THIRD
    general.limit(convergence, f"convergence au {convergence * 100:.0f} % de la base "
                  "(tiers central : 33 à 67 %)", low=first, high=last, unit="part")
    for name, side in (("gauche", left), ("droite", right)):
        if len(side) >= 2:
            spread = _spread([feet[id(l)] for l in side])
            scoring.measures[f"ecart_{name}_mm"] = spread
            general.limit(spread, f"lignes radiales à {name} : à {fmt(spread)} au plus l'une "
                          f"de l'autre sur la base (≤ {GENERAL_SPREAD_MM.text})",
                          high=GENERAL_SPREAD_MM)

    scoring["C"].add(layout_ok, f"seulement trois lignes radiales de chaque côté d'une ligne "
                     f"centrale ({layout_text})")

    cluster, center = _largest_cluster(sorted(position.values()), GLOBAL_CLUSTER_MM)
    scoring.measures["lignes_convergentes"] = cluster
    scoring["D"].limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale "
                       f"(≤ {GLOBAL_BASE_DEG.text})",
                       high=GLOBAL_BASE_DEG, unit="deg")
    scoring["D"].add(cluster >= GLOBAL_MIN_CONVERGING,
                     f"{cluster} ligne(s) radiale(s) convergeant à moins de "
                     f"{GLOBAL_CLUSTER_MM.text} (au moins {GLOBAL_MIN_CONVERGING.text})")
    at = center / max(base.length, 1e-6)
    scoring["D"].limit(at, f"point de convergence au {at * 100:.0f} % de la base "
                       "(tiers central : 33 à 67 %)", low=first, high=last, unit="part")

    ratio = max(lengths) / max(min(lengths), 1e-6)
    scoring.measures["rapport_radiales"] = ratio
    scoring["E"].limit(ratio, f"plus longue / plus courte ligne radiale {fmt_ratio(ratio)} "
                       f"≤ {LOCAL_MAX_RADIAL_RATIO.text}", high=LOCAL_MAX_RADIAL_RATIO, unit="ratio")

    extras = extra_elements(drawing, [base] + radials)
    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    scoring["F"].limit(base.length, f"base {fmt(base.length)} ≥ {LOCAL_MIN_BASE_MM.text}",
                       low=LOCAL_MIN_BASE_MM)
    shortest = min(lengths)
    scoring["F"].limit(shortest, f"plus courte ligne radiale {fmt(shortest)} ≥ "
                       f"{LOCAL_MIN_RADIAL_MM.text}", low=LOCAL_MIN_RADIAL_MM)
    return scoring.result()


def _check_straight(checks: Checks, marks: list, lines: list[StraightLine],
                    meeting: np.ndarray | None) -> None:
    """Motricité A, barre grisée de 2 mm. Une ligne interrompue est faite de
    morceaux tracés séparément, mesurés chacun ; la tache d'encre au point de
    convergence (``meeting``) n'est pas prise en compte."""
    drawn = []
    for line in lines:
        pieces = line.pieces
        if meeting is not None:
            pieces = [p[np.linalg.norm(p - meeting, axis=1) > CONVERGENCE_ZONE_MM] for p in pieces]
            pieces = [p for p in pieces if len(p) >= 2]
        if not pieces:
            continue
        if line.interruptions:
            drawn += [StraightLine([piece], line.stroke_width) for piece in pieces]
        else:
            drawn.append(StraightLine(pieces, line.stroke_width))
    check_lines(checks, drawn, STRAIGHT_BAND_MM)
    marks.extend(mk.bande(line, at="bout") for line in drawn)


def _join_gap(radial: StraightLine, base: StraightLine) -> float:
    """Intervalle (bas de la ligne radiale au-dessus de la base) ou dépassement
    (longueur de la ligne radiale sous la base), en mm."""
    normal = np.array([-base.direction[1], base.direction[0]])
    if normal[1] > 0:
        normal = -normal  # vers le haut
    height = float((_bottom(radial) - base.center) @ normal)
    if height >= 0:
        return height
    sine = max(np.sin(np.radians(geo.angle_between(radial.direction, base.direction))), 0.2)
    return -height / sine


def _top(line: StraightLine) -> np.ndarray:
    return min(line.ends, key=lambda p: p[1])


def _bottom(line: StraightLine) -> np.ndarray:
    return max(line.ends, key=lambda p: p[1])


def _is_radial(line: StraightLine, base: StraightLine) -> bool:
    """La ligne s'élève au-dessus de la base et son bas la rejoint."""
    if line.angle_to_horizontal() < RADIAL_MIN_DEG:
        return False
    foot = _foot(line, base)
    return (np.linalg.norm(_bottom(line) - foot) <= RADIAL_NEAR_MM
            and base.t0 - RADIAL_NEAR_MM <= base.position(foot) <= base.t1 + RADIAL_NEAR_MM
            and _top(line)[1] < foot[1])


def _foot(line: StraightLine, base: StraightLine) -> np.ndarray:
    """Point où la ligne radiale (prolongée) rencontre la ligne de base."""
    point = intersection(line, base)
    return _bottom(line) if point is None else point


def _spread(points: list[np.ndarray]) -> float:
    """Plus grande distance entre deux des points."""
    pts = np.array(points)
    return float(np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)).max())


def _largest_cluster(positions: list[float], width: float) -> tuple[int, float]:
    """Plus grand nombre de positions dans une fenêtre de ``width`` mm, et le
    milieu de cette fenêtre."""
    best, center = 0, positions[0] if positions else 0.0
    for i, start in enumerate(positions):
        inside = [p for p in positions[i:] if p - start <= width]
        if len(inside) > best:
            best, center = len(inside), (inside[0] + inside[-1]) / 2
    return best, center

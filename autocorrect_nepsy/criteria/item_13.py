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
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio, not_recognized
from .shapes import check_lines, extra_elements, intersection, review_notes

STRAIGHT_BAND_MM = 2.0  # Motricité A : barre grisée de 2 mm
JOIN_MM = 2.0  # Motricité B : intervalle ou dépassement à la ligne de base
BASE_MAX_DEG = 30.0  # au-delà, ce n'est plus la ligne de base
RADIAL_MIN_DEG = 10.0  # une ligne radiale s'élève au-dessus de la base
RADIAL_NEAR_MM = 8.0  # bas d'une ligne radiale près de la ligne de base
CENTRAL_MAX_DEG = 25.0  # ligne centrale « relativement verticale »
PER_SIDE = 3
CONVERGENCE_ZONE_MM = 3.0  # tache d'encre au point de convergence, ignorée
GENERAL_BASE_DEG = 20.0
GENERAL_SPREAD_MM = 5.0  # de chaque côté, lignes radiales proches à la base
DOUBLED_MAX_MM = 3.0  # base repassée : ce n'est plus un seul trait
GLOBAL_BASE_DEG = 10.0  # Global D
GLOBAL_CLUSTER_MM = 3.0  # Global D : lignes qui convergent au même point…
GLOBAL_MIN_CONVERGING = 5  # … au moins cinq
LOCAL_MAX_RADIAL_RATIO = 1.2  # Local E
LOCAL_MIN_BASE_MM = 40.0  # Local F
LOCAL_MIN_RADIAL_MM = 15.0  # Local F


def score(drawing: Drawing, item: int = 13) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    lines = drawing.significant_lines()
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {"nombre_lignes": len(lines)}
    notes = review_notes(lines)
    marks: list = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    def fail(reason: str) -> ItemResult:
        _check_straight(checks["A"], marks, lines, None)
        not_recognized(checks, ("G", "B", "C", "D", "E", "F"), reason, notes)
        return result()

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
    _check_straight(checks["A"], marks, lines, meeting)
    position = {id(l): base.position(feet[id(l)]) - base.t0 for l in radials}
    base_angle = base.angle_to_horizontal()
    lengths = [l.length for l in radials]
    measures.update({"base_mm": base.length, "base_angle_deg": base_angle,
                     "radiales_gauche": len(left), "radiales_droite": len(right),
                     "ligne_centrale": float(central is not None)})

    marks.append(mk.cote(*base.ends, f"base {fmt(base.length)} · {base_angle:.0f}°",
                         side=(0.0, 1.0)))
    for line in radials:
        marks.append(mk.segment(*sorted(line.ends, key=lambda p: p[1]), fmt(line.length)))

    junctions = [(_join_gap(line, base), _bottom(line)) for line in radials]
    worst, worst_point = max(junctions, key=lambda j: j[0])
    measures["jonction_max_mm"] = worst
    if worst > 0.5:
        marks.append(mk.point(worst_point, f"écart {fmt(worst)}"))
    checks["B"].limit(worst, f"plus grand intervalle ou dépassement entre une ligne radiale et "
                      f"la base {fmt(worst)} ≤ 2 mm", high=JOIN_MM)

    layout_ok = central is not None and len(left) == PER_SIDE and len(right) == PER_SIDE
    layout_text = (f"{len(left)} à gauche, {len(right)} à droite, ligne centrale "
                   f"{'verticale' if central is not None else 'absente'}")
    convergence = float(np.median(list(position.values()))) / max(base.length, 1e-6)
    measures["convergence_sur_base"] = convergence
    continuous = base.interruptions == 0 and base.doubled_length < DOUBLED_MAX_MM

    general = checks["G"]
    general.add(continuous, "ligne de base d'un seul trait" if continuous
                else f"ligne de base en plusieurs traits ({base.interruptions} interruption(s))")
    general.limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale (≤ 20°)",
                  high=GENERAL_BASE_DEG, unit="deg")
    general.add(layout_ok, f"trois lignes radiales de chaque côté d'une ligne centrale ({layout_text})")
    general.limit(convergence, f"convergence au {convergence * 100:.0f} % de la base "
                  "(tiers central : 33 à 67 %)", low=1 / 3, high=2 / 3, unit="part")
    for name, side in (("gauche", left), ("droite", right)):
        if len(side) >= 2:
            spread = _spread([feet[id(l)] for l in side])
            measures[f"ecart_{name}_mm"] = spread
            general.limit(spread, f"lignes radiales à {name} : à {fmt(spread)} au plus l'une "
                          "de l'autre sur la base (≤ 5 mm)", high=GENERAL_SPREAD_MM)

    checks["C"].add(layout_ok, f"seulement trois lignes radiales de chaque côté d'une ligne "
                    f"centrale ({layout_text})")

    cluster, center = _largest_cluster(sorted(position.values()), GLOBAL_CLUSTER_MM)
    measures["lignes_convergentes"] = cluster
    checks["D"].limit(base_angle, f"base à {base_angle:.0f}° de l'horizontale (≤ 10°)",
                      high=GLOBAL_BASE_DEG, unit="deg")
    checks["D"].add(cluster >= GLOBAL_MIN_CONVERGING,
                    f"{cluster} ligne(s) radiale(s) convergeant à moins de 3 mm (au moins 5)")
    at = center / max(base.length, 1e-6)
    checks["D"].limit(at, f"point de convergence au {at * 100:.0f} % de la base "
                      "(tiers central : 33 à 67 %)", low=1 / 3, high=2 / 3, unit="part")

    ratio = max(lengths) / max(min(lengths), 1e-6)
    measures["rapport_radiales"] = ratio
    checks["E"].limit(ratio, f"plus longue / plus courte ligne radiale {fmt_ratio(ratio)} "
                      "≤ 1,2:1", high=LOCAL_MAX_RADIAL_RATIO, unit="ratio")

    extras = extra_elements(drawing, [base] + radials)
    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    checks["F"].limit(base.length, f"base {fmt(base.length)} ≥ 40 mm", low=LOCAL_MIN_BASE_MM)
    shortest = min(lengths)
    checks["F"].limit(shortest, f"plus courte ligne radiale {fmt(shortest)} ≥ 15 mm",
                      low=LOCAL_MIN_RADIAL_MM)
    return result()


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

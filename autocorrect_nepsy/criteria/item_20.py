"""Item 20 : fleur à six pétales pointus, aux bords en « S », qui partent
tous du centre.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Les pointes des pétales sont les sommets du contour extérieur du dessin vu
depuis le centre (la plus grande distance au centre, angle par angle). Chaque
pétale est la région fermée qui touche sa pointe ; son extrémité intérieure
est le point de la région le plus proche du centre de la fleur. Les angles se
mesurent à la pointe de la région, là où les deux bords se rejoignent (la fine
pointe d'encre qui la prolonge se recourbe). Deux pétales
mal fermés au centre forment une seule région, partagée entre leurs pointes.

Global D : les pointes des quatre pétales latéraux forment un « X », un segment
du pétale en haut à gauche à celui en bas à droite, l'autre du pétale en haut à
droite à celui en bas à gauche. L'angle contrôlé est celui que forment ces deux
segments à leur intersection, ouvert vers la gauche (égal à celui ouvert vers la
droite), comme au rapporteur : ni l'horizontale ni la verticale n'interviennent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import geometry as geo
from ..strokes import Drawing
from . import marks as mk
from . import polygons
from .base import ItemResult, Scoring, fmt, fmt_limit, manual_thresholds, unrecognized_note
from .curves import extrema
from .shapes import separate_extras

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
PETALS = threshold(6, "GCF", "nombre de pétales, exactement", "nombre")
CONVERGE_LOOSE_MM = threshold(5.0, "G", "écart entre les extrémités intérieures des pétales, "
                              "au plus")
CONVERGE_MM = threshold(2.0, "D", "écart entre les extrémités intérieures des pétales, au plus")
TIP_JOIN_MM = threshold(1.0, "B", "intervalle ou dépassement à la pointe d'un pétale, au plus")
VERTICAL_MAX_DEG = threshold(5.0, "D", "écart de l'axe des deux pétales verticaux à la verticale, "
                             "au plus", "deg")
CROSS_MIN_DEG = threshold(20.0, "D", "angle entre les deux segments qui joignent les pointes des "
                          "pétales latéraux opposés, au moins", "deg")
CROSS_MAX_DEG = threshold(45.0, "D", "angle entre les deux segments qui joignent les pointes des "
                          "pétales latéraux opposés, au plus", "deg")
MAX_WIDTH_MM = threshold(11.0, "E", "largeur de chaque pétale, au plus")
MIN_LENGTH_MM = threshold(27.0, "E", "longueur de chaque pétale, au moins")
MAX_LENGTH_MM = threshold(33.0, "F", "longueur de chaque pétale, au plus")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
BIN_DEG = 2.0  # pas angulaire du contour extérieur
TIP_PROMINENCE_MM = 6.0  # une pointe dépasse d'autant les creux qui l'entourent
TIP_REGION_MM = 5.0  # la région d'un pétale s'arrête avant la fine pointe d'encre
MIN_PETAL_MM2 = 40.0  # région assez grande pour être un pétale
# Une région s'arrête un peu avant la rencontre de ses deux bords (épaisseur du
# trait redessiné, coin aigu) : écart retiré à l'étalement des extrémités.
INNER_SHORTFALL_MM = 0.5
TIP_GAP_REACH_MM = 3.0  # interruption recousue près de la pointe
OVERSHOOT_REACH_MM = 4.0
BEYOND_MM = 0.5  # encre au-delà de la pointe de la région
TIP_ARC_MM = 3.0  # angle de la pointe, entre les bords à 3 mm de part et d'autre
POINTED_MAX_DEG = 90.0
VERTICAL_LOOSE_DEG = 20.0  # Général : axe « relativement » vertical
WAVE_MM = 1.0  # crête ou creux d'un bord (écart à sa corde)
CORNER_DEG = 75.0  # Motricité A : angle marqué le long d'un bord
CORNER_ARC_MM = 1.5
# Marge « à vérifier » de l'angle entre les deux segments (Global D), plus large
# que celle d'un angle lu sur un seul trait (2°) : au rapporteur (2°) s'ajoute
# l'emplacement des quatre pointes, choisies à l'œil par l'ergothérapeute. Un
# millimètre d'écart au bout d'un segment d'environ 50 mm le tourne d'environ
# 1°, soit 2° de plus pour deux segments. Sur le cas qui a motivé cette mesure,
# l'ergothérapeute lit 45° et la capture de l'outil donne environ 48°.
CROSS_BORDERLINE_DEG = 4.0
# Bouts d'un bord écartés pour chercher les angles : le centre, où les bords se
# rejoignent, et la pointe, qui se recourbe en crochet sur le modèle aussi.
INNER_ZONE_MM = 4.0
TIP_ZONE_MM = 7.0


@dataclass
class Petal:
    tip: np.ndarray  # pointe d'encre
    outline: np.ndarray | None  # contour de la région du pétale (sa part), dans l'ordre
    closed: bool  # ``outline`` fait le tour de la région
    apex: int = 0  # indice de la pointe de la région dans ``outline``
    inner: int = 0  # indice de l'extrémité intérieure

    @property
    def point(self) -> np.ndarray:
        """Pointe de la région (rencontre des deux bords), sinon pointe d'encre."""
        return self.tip if self.outline is None else self.outline[self.apex]

    @property
    def inner_end(self) -> np.ndarray | None:
        return None if self.outline is None else self.outline[self.inner]

    def sides(self) -> list[np.ndarray]:
        """Les deux bords, de l'extrémité intérieure à la pointe."""
        o, i, a = self.outline, self.inner, self.apex
        if self.closed:
            forward = np.roll(o, -i, axis=0)[:(a - i) % len(o) + 1]
            backward = np.roll(o[::-1], -(len(o) - 1 - i), axis=0)[:(i - a) % len(o) + 1]
            return [forward, backward]
        first, second = o[:a + 1], o[a:][::-1]
        return [part for part in (first, second) if len(part) >= 2]

    def axis(self, center: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        start = center if self.outline is None else self.inner_end
        return start, self.tip


def score(drawing: Drawing, item: int = 20) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()

    outlines = polygons.regions(drawing, opened=False)
    center = _center(drawing, outlines)
    tips = _tips(drawing, center)
    if len(tips) < 2:
        scoring.not_recognized(scoring.codes,
                               "fleur non reconnue (pétales qui partent d'un centre)")
        return scoring.result()
    petals = _petals(tips, outlines, center)
    count = len(petals)
    scoring.measures["pétales"] = float(count)
    if count != PETALS:
        # Pétales fondus ou manqués, ou gribouillis pris pour une fleur : le
        # nombre lu n'est pas sûr.
        scoring.notes.append(unrecognized_note(f"{count} pétale(s) lu(s) au lieu de {PETALS.text}"))

    lengths, widths, angles, tip_angles = [], [], [], []
    for k, petal in enumerate(petals):
        start, tip = petal.axis(center)
        lengths.append(float(np.linalg.norm(tip - start)))
        widths.append(_width(petal, start, tip))
        rel = petal.point - center
        angles.append(float(np.degrees(np.arctan2(-rel[1], rel[0]))))
        tip_angles.append(_tip_angle(petal))
        if petal.outline is not None:
            trace = np.roll(petal.outline, -petal.apex, axis=0) if petal.closed else petal.outline
            scoring.marks.append(mk.trace(trace, f"{fmt(lengths[-1], '')} × {fmt(widths[-1])}", k))
    inner_ends = [p.inner_end for p in petals if p.outline is not None]
    spread = _spread(inner_ends)
    if inner_ends:
        scoring.marks.append(mk.cercle(np.mean(inner_ends, axis=0), max(spread / 2, 0.5),
                                       f"extrémités intérieures {fmt(spread)}"))
    open_petals = sum(p.outline is None for p in petals)
    scoring.measures.update({"longueur_min_mm": min(lengths), "longueur_max_mm": max(lengths),
                             "largeur_max_mm": max(widths), "convergence_mm": spread})

    # Formes des bords : un « S » (une crête, un creux), pas d'angle marqué.
    waves, corners = [], []
    for petal in petals:
        if petal.outline is None:
            continue
        for side in petal.sides():
            waves.append(_waves(side))
            corners.append(_corner(side, petal.inner_end, petal.point))
    not_s = sum(not 1 <= w <= 2 for w in waves)
    sharp = max(corners, default=0.0)
    blunt = [k + 1 for k, a in enumerate(tip_angles) if a > POINTED_MAX_DEG]
    scoring.measures.update({"angle_bord_max_deg": sharp,
                             "angle_pointe_max_deg": max(tip_angles)})
    above = sum(p.point[1] < center[1] for p in petals)
    top, bottom = _vertical_pair(angles)
    vertical = _axis_tilt(petals[top].point, petals[bottom].point) if top != bottom else 90.0
    others = [k for k in range(count) if k not in (top, bottom)]
    scoring.measures["axe_vertical_deg"] = vertical
    for k in {top, bottom}:
        rel = petals[k].point - center
        scoring.marks.append(mk.segment(center, petals[k].point,
                                        f"{_from_horizontal(angles[k]):.0f}°",
                                        side=np.array([-rel[1], rel[0]])))
    cross = _cross([petals[k].point for k in others])
    if cross is not None:
        cross_angle, (top_left, bottom_right, top_right, bottom_left) = cross
        scoring.measures["angle_pétales_latéraux_deg"] = cross_angle
        meet = geo.line_intersection(top_left, bottom_right - top_left,
                                     top_right, bottom_left - top_right)
        meet = center if meet is None else meet
        scoring.marks += [mk.segment(top_left, bottom_right, "pointes opposées"),
                          mk.segment(top_right, bottom_left, "pointes opposées"),
                          mk.angle(meet, top_left, bottom_left, f"{cross_angle:.0f}°")]

    corner_text = (f"angle le plus marqué le long des bords {sharp:.0f}° ≤ "
                   f"{fmt_limit(CORNER_DEG, 'deg')}")
    general = scoring["G"]
    general.add(count == PETALS, f"{count} pétale(s) (six attendus)")
    general.add(not open_petals, "pétales fermés" if not open_petals
                else f"{open_petals} pétale(s) non fermé(s)")
    general.add(not not_s, "bords en « S » (une crête, un creux)" if not not_s
                else f"{not_s} bord(s) de pétale droit(s) ou ondulé(s)")
    general.limit(sharp, f"{corner_text} (pas de distorsion)", high=CORNER_DEG, unit="deg")
    general.add(not blunt, "extrémités pointues" if not blunt
                else f"pointe(s) arrondie(s) : pétale(s) {', '.join(map(str, blunt))}")
    general.limit(vertical, f"deux pétales sur un axe à {vertical:.0f}° de la verticale "
                  "(relativement vertical)", high=VERTICAL_LOOSE_DEG, unit="deg")
    general.add(above == count - above == PETALS // 2,
                f"{above} pointe(s) au-dessus de l'axe horizontal, {count - above} en dessous")
    general.limit(spread, f"extrémités intérieures à {fmt(spread)} les unes des autres "
                  f"(≤ {CONVERGE_LOOSE_MM.text})", high=CONVERGE_LOOSE_MM)

    if corners:
        scoring["A"].limit(sharp, f"{corner_text} (pas de distorsion majeure)", high=CORNER_DEG,
                           unit="deg")
    else:
        scoring["A"].fail("bords des pétales non mesurables (aucun pétale fermé)")

    raster = polygons.raster(drawing)
    tip_gaps = [_tip_gap(drawing, raster, p) for p in petals]
    worst = max(tip_gaps)
    scoring.measures["pointe_intervalle_max_mm"] = worst
    if open_petals:
        scoring["B"].fail(f"{open_petals} pétale(s) ouvert(s) de plus de 3 mm")
    else:
        scoring["B"].limit(worst, f"plus grand intervalle ou dépassement aux pointes {fmt(worst)} "
                           f"≤ {TIP_JOIN_MM.text}", high=TIP_JOIN_MM)

    scoring["C"].add(count == PETALS, f"fleur à {count} pétale(s) (six attendus)")
    scoring["C"].add(above == count - above, f"{above} pointe(s) au-dessus de l'axe horizontal, "
                     f"{count - above} en dessous")

    scoring["D"].add(not blunt, "extrémités pointues" if not blunt
                     else f"pointe(s) arrondie(s) : pétale(s) {', '.join(map(str, blunt))}")
    scoring["D"].limit(spread, f"extrémités intérieures à {fmt(spread)} les unes des autres "
                       f"(≤ {CONVERGE_MM.text})", high=CONVERGE_MM)
    scoring["D"].limit(vertical, f"axe des deux pétales verticaux à {vertical:.0f}° de la "
                       f"verticale (≤ {VERTICAL_MAX_DEG.text})", high=VERTICAL_MAX_DEG, unit="deg")
    if cross is None:
        scoring["D"].fail(f"{len(others)} pétale(s) latéral(aux) au lieu de quatre : angle entre "
                          "les segments qui joignent leurs pointes non mesurable")
    else:
        scoring["D"].limit(cross_angle, f"angle de {cross_angle:.0f}° entre les segments qui "
                           "joignent les pointes des pétales latéraux opposés "
                           f"({CROSS_MIN_DEG.text} à {CROSS_MAX_DEG.text})",
                           low=CROSS_MIN_DEG, high=CROSS_MAX_DEG,
                           unit="deg", margin=CROSS_BORDERLINE_DEG)

    for k, (length, width) in enumerate(zip(lengths, widths)):
        scoring["E"].limit(width, f"pétale {k + 1} : largeur {fmt(width)} ≤ {MAX_WIDTH_MM.text}",
                           high=MAX_WIDTH_MM)
        scoring["E"].limit(length, f"pétale {k + 1} : longueur {fmt(length)} ≥ "
                           f"{MIN_LENGTH_MM.text}",
                           low=MIN_LENGTH_MM)

    figure = np.vstack([p.outline for p in petals if p.outline is not None]
                       + [np.array([p.tip for p in petals])])
    extras = len(separate_extras(drawing, figure, distance=TIP_REGION_MM))
    added = max(count - PETALS, 0)
    scoring["F"].add(added == 0 and extras == 0, "aucun autre élément" if not (added or extras)
                     else f"{added} pétale(s) ajouté(s), {extras} autre(s) élément(s)")
    for k, length in enumerate(lengths):
        scoring["F"].limit(length, f"pétale {k + 1} : longueur {fmt(length)} ≤ "
                           f"{MAX_LENGTH_MM.text}",
                           high=MAX_LENGTH_MM)
    return scoring.result()


def _center(drawing: Drawing, outlines: list[np.ndarray]) -> np.ndarray:
    """Centre de la fleur : là où se rejoignent les extrémités intérieures des
    pétales (médiane des points de chaque région les plus proches du centre)."""
    center = drawing.points.mean(axis=0)
    petals = [o for o in outlines if abs(polygons.signed_area(o)) >= MIN_PETAL_MM2]
    for _ in range(3):
        if not petals:
            break
        inner = [o[np.argmin(np.linalg.norm(o - center, axis=1))] for o in petals]
        center = np.median(inner, axis=0)
    return center


def _tips(drawing: Drawing, center: np.ndarray) -> list[np.ndarray]:
    """Pointes : sommets de la distance au centre du contour extérieur, angle
    par angle, qui dépassent nettement les creux voisins (dans l'ordre)."""
    rel = drawing.points - center
    radius = np.linalg.norm(rel, axis=1)
    bins = int(round(360 / BIN_DEG))
    which = (np.degrees(np.arctan2(rel[:, 1], rel[:, 0])) % 360 // BIN_DEG).astype(int) % bins
    envelope = np.zeros(bins)
    farthest = np.full(bins, -1)
    for i in np.argsort(radius):  # le plus éloigné l'emporte
        envelope[which[i]], farthest[which[i]] = radius[i], i
    start = int(np.argmin(envelope))
    order = np.roll(np.arange(bins), -start)
    values = np.append(envelope[order], envelope[start])
    # En partant du creux le plus profond, les extremums alternent : sommet, creux…
    peaks = extrema(values, TIP_PROMINENCE_MM)[0::2]
    return [drawing.points[farthest[order[i % bins]]] for i, _ in peaks]


def _petals(tips: list[np.ndarray], outlines: list[np.ndarray],
            center: np.ndarray) -> list[Petal]:
    owner = []
    for tip in tips:
        dist = [float(np.linalg.norm(o - tip, axis=1).min()) for o in outlines]
        k = int(np.argmin(dist)) if dist else -1
        owner.append(k if k >= 0 and dist[k] <= TIP_REGION_MM else -1)
    petals = []
    for t, tip in enumerate(tips):
        if owner[t] < 0:
            petals.append(Petal(tip, None, False))
            continue
        outline = outlines[owner[t]]
        sharing = [s for s in range(len(tips)) if owner[s] == owner[t]]
        if len(sharing) == 1:
            part, closed = outline, True
        else:
            # Région partagée : chaque pointe garde la partie du contour la plus proche d'elle.
            near = np.argmin(np.stack([np.linalg.norm(outline - tips[s], axis=1)
                                       for s in sharing]), axis=0)
            part, closed = _run(outline, near == sharing.index(t), tip), False
        apex = int(np.argmin(np.linalg.norm(part - tip, axis=1)))
        inner = int(np.argmin(np.linalg.norm(part - center, axis=1)))
        petals.append(Petal(tip, part, closed, apex, inner))
    return petals


def _run(outline: np.ndarray, mine: np.ndarray, tip: np.ndarray) -> np.ndarray:
    """Tronçon d'un seul tenant du contour fermé, parmi les points ``mine``,
    qui passe au plus près de ``tip``."""
    start = int(np.argmin(mine))  # premier point qui n'est pas à cette pointe
    order = np.roll(np.arange(len(outline)), -start)
    flags = mine[order]
    best, run = None, []
    for i, flag in zip(order, flags):
        if flag:
            run.append(i)
        if (not flag or i == order[-1]) and run:
            gap = float(np.linalg.norm(outline[run] - tip, axis=1).min())
            if best is None or gap < best[0]:
                best = (gap, list(run))
            run = []
    return outline[best[1]]


def _width(petal: Petal, start: np.ndarray, tip: np.ndarray) -> float:
    """Largeur du pétale, perpendiculairement à son axe (extrémité intérieure
    → pointe), d'un bord à l'autre (milieu du trait)."""
    if petal.outline is None:
        return float("nan")
    axis = geo.unit(tip - start)
    offsets = (petal.outline - start) @ np.array([-axis[1], axis[0]])
    return float(offsets.max() - offsets.min() + 2 * polygons.EDGE_OFFSET_MM)


def _arc(points: np.ndarray, closed: bool) -> np.ndarray:
    pts = np.vstack([points, points[:1]]) if closed else points
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])


def _tip_angle(petal: Petal) -> float:
    """Angle (degrés) de la pointe de la région, entre ses deux bords pris à
    3 mm de part et d'autre : petit pour une pointe, plat pour un bout arrondi."""
    if petal.outline is None:
        return 0.0
    o, a = petal.outline, petal.apex
    arc = _arc(o, petal.closed)
    total = arc[-1]

    def at(shift: float) -> np.ndarray:
        s = arc[a] + shift
        s = s % total if petal.closed else min(max(s, 0.0), arc[len(o) - 1])
        return o[int(np.argmin(np.abs(arc[:len(o)] - s)))]

    return geo.angle_between(at(TIP_ARC_MM) - o[a], at(-TIP_ARC_MM) - o[a])


def _tip_gap(drawing: Drawing, raster: polygons.Raster | None, petal: Petal) -> float:
    """Intervalle recousu près de la pointe, ou dépassement : au-delà de la
    pointe de la région, deux traits distincts (deux bords qui se croisent et
    continuent). Une pointe effilée, où les deux bords se rejoignent en un seul
    trait, n'est pas un dépassement."""
    if petal.outline is None:
        return float("inf")
    apex = petal.outline[petal.apex]
    gaps = [g for g, p in zip(raster.gaps, raster.gap_points)
            if np.linalg.norm(p - apex) <= TIP_GAP_REACH_MM] if raster is not None else []
    behind = []
    for side in petal.sides():
        arc = _arc(side, False)
        behind.append(side[int(np.searchsorted(arc, arc[-1] - TIP_ARC_MM))])
    behind = np.mean(behind, axis=0)
    direction = geo.unit(apex - behind)
    beyond = []
    for stroke in drawing.strokes:
        pts = stroke.points
        far = pts[(np.linalg.norm(pts - apex, axis=1) <= OVERSHOOT_REACH_MM)
                  & ((pts - apex) @ direction > BEYOND_MM)]
        if len(far):
            beyond.append(float(np.linalg.norm(far - apex, axis=1).max()))
    overshoot = sorted(beyond)[-2] if len(beyond) >= 2 else 0.0
    return max(gaps + [overshoot])


def _waves(side: np.ndarray) -> int:
    """Crêtes et creux d'un bord (écart à sa corde)."""
    if len(side) < 3:
        return 0
    chord = side[-1] - side[0]
    norm = max(float(np.linalg.norm(chord)), 1e-9)
    offsets = (chord[0] * (side[:, 1] - side[0, 1]) - chord[1] * (side[:, 0] - side[0, 0])) / norm
    return len(extrema(offsets, WAVE_MM))


def _corner(side: np.ndarray, inner: np.ndarray, apex: np.ndarray) -> float:
    """Changement de direction le plus marqué (degrés) le long d'un bord, loin
    du centre et de la pointe (sur 1,5 mm de part et d'autre de chaque point)."""
    arc = _arc(side, False)
    keep = ((np.linalg.norm(side - inner, axis=1) > INNER_ZONE_MM)
            & (np.linalg.norm(side - apex, axis=1) > TIP_ZONE_MM)
            & (arc >= INNER_ZONE_MM) & (arc[-1] - arc >= CORNER_ARC_MM))
    worst = 0.0
    for i in np.flatnonzero(keep):
        before = side[int(np.searchsorted(arc, arc[i] - CORNER_ARC_MM))]
        after = side[min(int(np.searchsorted(arc, arc[i] + CORNER_ARC_MM)), len(side) - 1)]
        worst = max(worst, 180.0 - geo.angle_between(before - side[i], after - side[i]))
    return worst


def _spread(points: list[np.ndarray]) -> float:
    """Plus grande distance entre deux extrémités intérieures."""
    if len(points) < 2:
        return 0.0
    pts = np.array(points)
    farthest = float(np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)).max())
    return max(farthest - 2 * INNER_SHORTFALL_MM, 0.0)


def _cross(tips: list[np.ndarray]) -> tuple[float, tuple] | None:
    """Angle (degrés) entre les deux segments qui joignent les pointes des quatre
    pétales latéraux opposés (haut gauche → bas droite, haut droite → bas gauche),
    ouvert vers la gauche, et ces quatre pointes dans cet ordre. None s'il n'y a
    pas quatre pétales latéraux."""
    if len(tips) != 4:
        return None
    by_x = sorted(tips, key=lambda p: p[0])
    # Repère de l'image : l'ordonnée croît vers le bas.
    top_left, bottom_left = sorted(by_x[:2], key=lambda p: p[1])
    top_right, bottom_right = sorted(by_x[2:], key=lambda p: p[1])
    angle = geo.angle_between(top_left - bottom_right, bottom_left - top_right)
    return angle, (top_left, bottom_right, top_right, bottom_left)


def _from_horizontal(angle: float) -> float:
    """Écart (degrés, 0 à 90) entre une direction et l'horizontale."""
    a = abs(angle) % 180
    return min(a, 180 - a)


def _vertical_pair(angles: list[float]) -> tuple[int, int]:
    """Pétales les plus proches de la verticale, vers le haut et vers le bas."""
    top = int(np.argmin([abs(a - 90) for a in angles]))
    bottom = int(np.argmin([abs(a + 90) for a in angles]))
    return top, bottom


def _axis_tilt(a: np.ndarray, b: np.ndarray) -> float:
    """Écart (degrés) entre la droite qui joint deux pointes et la verticale."""
    return 90.0 - _from_horizontal(float(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0]))))

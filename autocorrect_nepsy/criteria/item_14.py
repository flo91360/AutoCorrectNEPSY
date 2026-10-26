"""Item 14 : cylindre couché, incliné vers le bas de gauche à droite.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Le dessin est lu le long de son axe : les deux côtés sont les traits droits
du milieu du cylindre, l'arrière est ce qui précède leurs bouts arrière et
l'ellipse avant ce qui suit leurs bouts avant.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing, StraightLine
from . import marks as mk
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds
from .shapes import EXTRA_ELEMENT_MM

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
MOTOR_MAX_CHANGES = threshold(3, "A", "changements de direction par côté, au plus", "nombre")
STRAIGHT_BAND_MM = threshold(2.0, "B", "largeur de la barre grisée où tient chaque côté")
# Un côté rejoint l'arrière ou l'ellipse : sert aussi à repérer la jonction.
MEET_MM = threshold(1.0, "G", "intervalle entre un côté et l'arrière ou l'ellipse, au plus")
SIDES_RANGE_DEG = (threshold(30.0, "GC", "angle de chaque côté avec l'horizontale, au moins",
                             "deg"),
                   threshold(60.0, "GC", "angle de chaque côté avec l'horizontale, au plus",
                             "deg"))
LENGTH_WIDTH_RANGE = (threshold(1.5, "D", "rapport de la longueur à la largeur, au moins", "ratio"),
                      threshold(2.0, "D", "rapport de la longueur à la largeur, au plus", "ratio"))
LOCAL_MIN_ELLIPSE_RATIO = threshold(1.2, "F", "rapport du grand au petit diamètre de l'ellipse "
                                    "avant, au moins (une ellipse, pas un cercle)", "ratio")
LOCAL_MAX_SIDES_RATIO = threshold(1.2, "F", "rapport du plus long au plus court côté, au plus",
                                  "ratio")
# Réglages de l'outil (reconnaissance des figures, tolérances de mesure).
WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
SIDE_FIT_MM = 1.5  # point d'un côté : à moins de cette distance de sa droite
PROFILE_STEP_MM = 0.6  # pas du profil moyen d'un côté (trait repassé compris)
# Le tracé d'un côté suit sa droite ; aux bouts, l'arrière et l'ellipse qui le
# prolongent en tournant peu à peu sont écartés par leur direction.
SIDE_PARALLEL_DEG = 30.0
SIDE_GAP_MM = 2.0  # interruption tolérée le long d'un côté
SIDE_MIN_FRACTION = 0.3  # un côté couvre au moins cette part de la longueur
BACK_BULGE_MM = 1.0  # arrière incurvé vers l'extérieur d'au moins cette flèche
DISTORTION_MAX_SPREAD = 0.15  # irrégularité du rayon de l'ellipse (bosses, angles)


@dataclass
class Side:
    line: StraightLine
    meets_back: np.ndarray  # où le côté rejoint l'arrière (ou son bout)
    meets_front: np.ndarray  # où il rejoint l'ellipse (ou son bout)
    back_gap: float
    front_gap: float

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.meets_front - self.meets_back))


def score(drawing: Drawing, item: int = 14) -> ItemResult:
    scoring = Scoring(item, "GABCDEF")
    if drawing.is_empty:
        return scoring.empty()

    def fail(reason: str, *failing: str) -> ItemResult:
        scoring.not_recognized(failing, reason)
        return scoring.result()

    points = drawing.points
    tangents = _tangents(drawing)
    center, axis = geo.principal_axis(points)
    if axis[0] < 0:
        axis = -axis
    across = np.array([-axis[1], axis[0]])
    t = (points - center) @ axis
    s = (points - center) @ across
    span = float(t.max() - t.min())
    found = [_side(points, tangents, t, s, sign, span, drawing.stroke_width)
             for sign in (-1, 1)]
    sides_found = [f for f in found if f is not None]
    scoring["E"].add(len(sides_found) == 2, f"{len(sides_found)} côté(s) du cylindre "
                     "représenté(s) (il en faut 2)")
    if len(sides_found) < 2:
        return fail("forme cylindrique non reconnue (deux côtés droits attendus)",
                    "G", "A", "B", "C", "D", "F")
    upper, lower = sides_found  # en haut à droite de l'axe, en bas à gauche
    side_mask = upper[1] | lower[1]
    sides_t = [((line.points - center) @ axis) for line, _ in (upper, lower)]
    back_limit = max(float(st.min()) for st in sides_t) + 1.0
    front_limit = min(float(st.max()) for st in sides_t)
    width = _width(upper[0], lower[0])
    back_pts = points[(~side_mask) & (t <= back_limit)]
    front_pts = points[(~side_mask) & (t >= front_limit - 0.8 * width)]
    other_pts = points[(~side_mask) & (t > back_limit) & (t < front_limit - 0.8 * width)]

    sides = [_meeting(line, back_pts, front_pts, axis) for line, _ in (upper, lower)]
    ellipse = _ellipse(front_pts)
    if ellipse is None:
        return fail("ellipse avant non reconnue", "G", "C", "D", "F")
    e_center, (e_major, e_minor), e_spread, e_major_axis = ellipse
    near_front = e_center - axis * _radius_along(axis, e_major_axis, e_major, e_minor)

    if len(back_pts):
        bt = (back_pts - center) @ axis
        apex = back_pts[int(np.argmin(bt))]
        # Bouts de l'arrière : ses points les plus proches du début de chaque côté.
        ends = [back_pts[int(np.argmin(np.linalg.norm(back_pts - side.meets_back, axis=1)))]
                for side in sides]
        chord_t = float(np.mean([(end - center) @ axis for end in ends]))
        bulge = chord_t - float(bt.min())
    else:
        apex, bulge = None, 0.0
    length = float((near_front - center) @ axis - ((apex - center) @ axis if apex is not None
                                                   else min(float(st.min()) for st in sides_t)))
    length_ratio = length / max(width, 1e-6)
    side_angles = [s_.line.angle_to_horizontal() for s_ in sides]
    descending = axis[1] > 0
    sides_ratio = max(s_.length for s_ in sides) / max(min(s_.length for s_ in sides), 1e-6)
    gaps = [g for s_ in sides for g in (s_.back_gap, s_.front_gap)]
    scoring.measures.update({"largeur_mm": width, "longueur_mm": length,
                             "rapport_longueur_largeur": length_ratio, "ellipse_grand_mm": e_major,
                             "ellipse_petit_mm": e_minor, "fleche_arriere_mm": bulge,
                             "rapport_cotes": sides_ratio, "intervalle_max_mm": max(gaps)})

    for side, angle in zip(sides, side_angles):
        scoring.marks.append(mk.bande(side.line, f"côté {fmt(side.length)} · {angle:.0f}°"))
    scoring.marks.append(mk.segment(e_center - e_major_axis * e_major / 2,
                                    e_center + e_major_axis * e_major / 2,
                                    f"ellipse {fmt(e_major, '')} × {fmt(e_minor)}"))
    if apex is not None:
        scoring.marks.append(mk.point(apex, f"arrière {'+' if bulge >= 0 else '−'}"
                                            f"{fmt(abs(bulge))}"))
        scoring.marks.append(mk.cote(apex, apex + axis * length, f"longueur {fmt(length)}",
                                     side=-across))
    for side in sides:
        for gap, at in ((side.back_gap, side.meets_back), (side.front_gap, side.meets_front)):
            if gap > 0.5:
                scoring.marks.append(mk.point(at, f"intervalle {fmt(gap)}"))

    lo, hi = SIDES_RANGE_DEG
    general = scoring["G"]
    general.add(True, "forme cylindrique (deux côtés, un arrière, une ellipse avant)")
    general.add(descending, "inclinée vers le bas de gauche à droite" if descending
                else "inclinée vers le haut de gauche à droite")
    distorted = e_spread > DISTORTION_MAX_SPREAD
    general.add(not distorted, f"ellipse avant sans distorsion majeure (irrégularité "
                f"{e_spread * 100:.0f} %, au plus {DISTORTION_MAX_SPREAD * 100:.0f} %)")
    general.add(bulge >= BACK_BULGE_MM, f"arrière incurvé vers l'extérieur (flèche {fmt(bulge)})")
    general.limit(max(gaps), f"plus grand intervalle entre un côté et l'arrière ou l'ellipse "
                  f"{fmt(max(gaps))} ≤ {MEET_MM.text}", high=MEET_MM)
    for angle in side_angles:
        general.limit(angle, f"côté à {angle:.0f}° de l'horizontale (entre {lo.text} et "
                      f"{hi.text})",
                      low=lo, high=hi, unit="deg")

    for side in sides:
        changes = geo.count_direction_changes(_profile(side.line), WOBBLE_MM)
        scoring["A"].add(changes <= MOTOR_MAX_CHANGES, f"côté de {fmt(side.length)} : {changes} "
                         f"changement(s) de direction ({MOTOR_MAX_CHANGES.text} au plus)")
        scoring["B"].limit(side.line.width, f"côté de {fmt(side.length)} droit : bande de "
                           f"{fmt(side.line.width)} ≤ {STRAIGHT_BAND_MM.text}",
                           high=STRAIGHT_BAND_MM)

    scoring["C"].add(True, "forme cylindrique")
    scoring["C"].add(descending, "inclinée vers le bas de gauche à droite" if descending
                     else "inclinée vers le haut de gauche à droite")
    for angle in side_angles:
        scoring["C"].limit(angle, f"côté à {angle:.0f}° de l'horizontale (entre {lo.text} et "
                           f"{hi.text})",
                           low=lo, high=hi, unit="deg")

    scoring["D"].add(bulge >= BACK_BULGE_MM,
                     f"arrière incurvé vers l'extérieur (flèche {fmt(bulge)})")
    lo, hi = LENGTH_WIDTH_RANGE
    scoring["D"].limit(length_ratio, f"longueur {fmt(length)} / largeur {fmt(width)} : "
                       f"{fmt_ratio(length_ratio)} (entre {lo.text} et {hi.text})", low=lo, high=hi,
                       unit="ratio")

    extra = len(other_pts) * STEP_MM
    extras = ([extra] if extra >= EXTRA_ELEMENT_MM else []) + [
        size for size in drawing.component_sizes[1:] if size >= EXTRA_ELEMENT_MM]
    scoring["F"].add(not extras, "aucun autre élément" if not extras
                     else f"{len(extras)} élément(s) en trop")
    e_ratio = e_major / max(e_minor, 1e-6)
    scoring["F"].limit(e_ratio, f"ellipse avant : grand / petit diamètre {fmt_ratio(e_ratio)} "
                       f"≥ {LOCAL_MIN_ELLIPSE_RATIO.text}", low=LOCAL_MIN_ELLIPSE_RATIO,
                       unit="ratio")
    scoring["F"].limit(sides_ratio, f"plus long / plus court côté {fmt_ratio(sides_ratio)} "
                       f"≤ {LOCAL_MAX_SIDES_RATIO.text}", high=LOCAL_MAX_SIDES_RATIO, unit="ratio")
    return scoring.result()


def _tangents(drawing: Drawing) -> np.ndarray:
    """Direction locale du tracé en chaque point (sur ~2 mm)."""
    found = []
    for stroke in drawing.strokes:
        pts = stroke.points
        k = min(3, len(pts) - 1)
        ahead = np.vstack([pts[k:], np.repeat(pts[-1:], k, axis=0)])
        behind = np.vstack([np.repeat(pts[:1], k, axis=0), pts[:-k]])
        d = ahead - behind
        found.append(d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    return np.vstack(found)


def _side(points: np.ndarray, tangents: np.ndarray, t: np.ndarray, s: np.ndarray, sign: int,
          span: float, stroke_width: float) -> tuple[StraightLine, np.ndarray] | None:
    """Côté du cylindre d'un bord de l'axe (``sign``) : droite ajustée sur le
    milieu du dessin, puis étendue aux points alignés qui se suivent."""
    mid = (t.min() + t.max()) / 2
    middle = np.flatnonzero((np.abs(t - mid) <= 0.2 * span) & (np.sign(s) == sign))
    # Au milieu du cylindre, le côté est le tracé le plus éloigné de l'axe de
    # ce bord-ci : un point par tranche de 1 mm le long de l'axe.
    edge = []
    for b in np.unique(np.floor(t[middle]).astype(int)):
        in_bin = middle[np.floor(t[middle]).astype(int) == b]
        edge.append(in_bin[np.argmax(np.abs(s[in_bin]))])
    if len(edge) < 5:
        return None
    c, d = geo.principal_axis(points[edge])
    if d[0] < 0:
        d = -d
    normal = np.array([-d[1], d[0]])
    parallel = np.abs(tangents @ d) >= np.cos(np.radians(SIDE_PARALLEL_DEG))
    near = (np.abs((points - c) @ normal) <= SIDE_FIT_MM) & parallel
    along = (points - c) @ d
    order = np.argsort(along)
    keep = np.zeros(len(points), bool)
    # Plus longue suite de points alignés (trous ≤ 2 mm) qui passe par le milieu.
    run, runs = [], []
    for i in order:
        if not near[i]:
            continue
        if run and along[i] - along[run[-1]] > SIDE_GAP_MM:
            runs.append(run)
            run = []
        run.append(i)
    if run:
        runs.append(run)
    if not runs:
        return None
    best = np.array(max(runs, key=lambda r: along[r[-1]] - along[r[0]]))
    if along[best[-1]] - along[best[0]] < SIDE_MIN_FRACTION * span:
        return None
    keep[best] = True
    return StraightLine([points[best]], stroke_width), keep


def _profile(line: StraightLine) -> np.ndarray:
    """Tracé moyen d'un côté le long de sa droite (un trait repassé ne
    double pas les ondulations)."""
    along = (line.points - line.center) @ line.direction
    bins = np.floor((along - along.min()) / PROFILE_STEP_MM).astype(int)
    return np.array([line.points[bins == b].mean(axis=0) for b in np.unique(bins)])


def _width(a: StraightLine, b: StraightLine) -> float:
    """Plus grand écart entre les deux côtés (aux bouts de l'un, depuis l'autre)."""
    normal = np.array([-a.direction[1], a.direction[0]])
    return float(max(abs((p - a.center) @ normal) for p in b.ends))


def _meeting(line: StraightLine, back: np.ndarray, front: np.ndarray, axis: np.ndarray) -> Side:
    """Où le côté rejoint l'arrière et l'ellipse ; un dépassement n'allonge pas le côté."""
    pts = line.points[np.argsort(line.points @ axis)]

    def first_touch(curve: np.ndarray, ordered: np.ndarray) -> tuple[np.ndarray, float]:
        if len(curve) == 0:
            return ordered[0], float("inf")
        dist = np.sqrt(((ordered[:, None, :] - curve[None, :, :]) ** 2).sum(-1)).min(1)
        touching = np.flatnonzero(dist <= MEET_MM)
        if len(touching):
            return ordered[touching[0]], 0.0
        return ordered[0], float(dist[0])

    meets_back, back_gap = first_touch(back, pts[::-1])
    meets_front, front_gap = first_touch(front, pts)
    # Le côté va d'une rencontre à l'autre : les dépassements ne comptent pas.
    lo, hi = sorted((line.position(meets_back), line.position(meets_front)))
    along = (line.points - line.center) @ line.direction
    kept = line.points[(along >= lo) & (along <= hi)]
    if len(kept) >= 2:
        line = StraightLine([kept], line.stroke_width)
    return Side(line, meets_back, meets_front, back_gap, front_gap)


def _ellipse(points: np.ndarray):
    """Ellipse ajustée : centre, (grand, petit diamètre), irrégularité, direction du grand axe."""
    if len(points) < 10:
        return None
    (cx, cy), (w, h), angle = cv2.fitEllipse(points.astype(np.float32))
    major, minor = max(w, h), min(w, h)
    if minor < 1.0:
        return None
    theta = np.radians(angle + (90 if h > w else 0))
    major_axis = np.array([np.cos(theta), np.sin(theta)])
    minor_axis = np.array([-major_axis[1], major_axis[0]])
    center = np.array([cx, cy])
    rel = points - center
    r = np.sqrt(((rel @ major_axis) / (major / 2)) ** 2 + ((rel @ minor_axis) / (minor / 2)) ** 2)
    return center, (float(major), float(minor)), float(r.std()), major_axis


def _radius_along(direction: np.ndarray, major_axis: np.ndarray, major: float,
                  minor: float) -> float:
    """Distance du centre de l'ellipse à son bord dans une direction donnée."""
    cos = float(direction @ major_axis)
    sin = float(np.sqrt(max(0.0, 1 - cos ** 2)))
    a, b = major / 2, minor / 2
    return float(1 / np.sqrt((cos / a) ** 2 + (sin / b) ** 2))

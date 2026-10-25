"""Item 12 : deux lignes en « S » qui se croisent (moulinet).

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.

Chaque ligne est suivie le long de l'encre entre deux bouts libres opposés ;
sa corde relie ses deux extrémités.
"""

from __future__ import annotations

import numpy as np

from .. import geometry as geo
from ..strokes import STEP_MM, Drawing
from . import marks as mk
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio, not_recognized
from .curves import Curve, InkGraph, crossing, extrema
from .shapes import EXTRA_ELEMENT_MM

WOBBLE_MM = 0.8  # amplitude d'une ondulation de la main (Motricité A)
SHAPE_MM = 2.0  # amplitude minimale d'une crête ou d'un creux du « S »
SHAPE_FRACTION = 0.08  # … ou cette part de la corde, si elle est plus grande
STIMULUS_CHANGES = 2  # une crête et un creux : changements de direction du modèle
MOTOR_MAX_EXTRA_CHANGES = 3  # Motricité A, par ligne
MOTOR_MAX_INTERRUPTIONS = 2  # Motricité B, par ligne
AXIS_TOUCH_MM = 1.0  # une extrémité à moins de cette distance touche l'axe
CROSS_MAX_GAP_MM = 1.0  # les deux lignes se coupent
CHORD_MAX_DEG = 15.0  # Global C (horizontale) et D (verticale)
GLOBAL_MAX_SEGMENT_RATIO = 1.2  # Global D : bouts de part et d'autre du croisement
LOCAL_MAX_CHORD_MM = 50.0  # Local F
LOCAL_MAX_LENGTH_RATIO = 1.3  # Local F : verticale / horizontale
ON_CURVE_MM = 1.5  # encre plus éloignée des deux lignes : autre élément


def score(drawing: Drawing, item: int = 12) -> ItemResult:
    codes = ("G", "A", "B", "C", "D", "E", "F")
    if drawing.is_empty:
        return empty_result(item, codes, "aucun tracé dans la zone")
    checks = {code: Checks() for code in codes}
    measures: dict[str, float] = {}
    marks: list = []
    notes: list[str] = []

    def result() -> ItemResult:
        return ItemResult(item, {c: checks[c].criterion(c) for c in codes}, measures, notes,
                          marks)

    graph = InkGraph(drawing.strokes)
    tips = _tips(graph)
    measures["extremites_libres"] = len(graph.free_ends())
    curves = _curves(graph, tips) if len(tips) == 4 else None
    if curves is None:
        reason = (f"deux lignes qui se croisent non reconnues ({len(tips)} extrémité(s) "
                  "libre(s), il en faut 4)")
        not_recognized(checks, codes, reason, notes)
        return result()
    horizontal, vertical = curves
    x = crossing(horizontal, vertical)
    cross_gap = _gap(horizontal, vertical)
    lines = {"horizontale": horizontal, "verticale": vertical}
    info = {name: _describe(curve, x, name == "verticale") for name, curve in lines.items()}
    for color, (name, d) in enumerate(info.items()):
        measures.update({f"{name}_corde_mm": d["chord"], f"{name}_angle_deg": d["angle"],
                         f"{name}_rapport_bouts": d["ratio"], f"{name}_croisement": d["at"]})
        marks.append(mk.trace(lines[name].points, f"ligne {name}", color))
        marks.append(mk.segment(lines[name].start, lines[name].end,
                                f"{fmt(d['chord'])} · {d['angle']:.0f}°"))
    marks.append(mk.point(x, "croisement"))

    for name, curve in lines.items():
        d = info[name]
        checks["A"].add(d["extra_changes"] <= MOTOR_MAX_EXTRA_CHANGES,
                        f"ligne {name} : {d['extra_changes']} changement(s) de direction en plus "
                        "du « S » (3 au plus)")
        checks["B"].add(curve.interruptions <= MOTOR_MAX_INTERRUPTIONS,
                        f"ligne {name} : {curve.interruptions} interruption(s) (2 au plus)")

    general = checks["G"]
    for name, d in info.items():
        general.add(d["s_shape"] and len(d["extrema"]) <= 2 and d["oriented"],
                    f"ligne {name} en « S », dans le sens du modèle, sans distorsion "
                    f"({_shape_text(d)})")
        general.limit(d["at"], f"ligne {name} : croisement au {d['at'] * 100:.0f} % de sa corde "
                      "(tiers central : 33 à 67 %)", low=1 / 3, high=2 / 3, unit="part")
        general.add(d["tips_ok"], f"ligne {name} : extrémités qui touchent ou recoupent l'axe "
                    f"passant par le croisement ({d['tips_text']})")

    curved = all(np.abs(c.offsets()).max() >= SHAPE_MM for c in lines.values())
    checks["C"].add(curved and cross_gap <= CROSS_MAX_GAP_MM, "deux lignes courbes qui se coupent")
    checks["C"].limit(info["horizontale"]["angle"], "corde de la ligne horizontale à "
                      f"{info['horizontale']['angle']:.0f}° de l'horizontale (≤ 15°)",
                      high=CHORD_MAX_DEG, unit="deg")

    checks["D"].limit(info["verticale"]["angle"], "corde de la ligne verticale à "
                      f"{info['verticale']['angle']:.0f}° de la verticale (≤ 15°)",
                      high=CHORD_MAX_DEG, unit="deg")
    for name, d in info.items():
        checks["D"].limit(d["ratio"], f"ligne {name} : bouts de {fmt(d['ends'][0])} et "
                          f"{fmt(d['ends'][1])} depuis le croisement, rapport {fmt_ratio(d['ratio'])} "
                          "≤ 1,2:1", high=GLOBAL_MAX_SEGMENT_RATIO, unit="ratio")

    extras = _extras(drawing, list(lines.values()))
    checks["E"].add(not extras, "seulement deux lignes" if not extras
                    else f"{len(extras)} trait(s) en plus des deux lignes")
    for name, d in info.items():
        checks["E"].add(d["s_shape"], f"ligne {name} sinusoïdale : une crête et un creux "
                        f"({_shape_text(d)})")

    checks["F"].add(not extras, "aucun autre élément" if not extras
                    else f"{len(extras)} élément(s) en trop")
    for name, d in info.items():
        checks["F"].limit(d["chord"], f"ligne {name} : {fmt(d['chord'])} d'une extrémité à "
                          "l'autre (≤ 50 mm)", high=LOCAL_MAX_CHORD_MM)
    ratio = info["verticale"]["chord"] / max(info["horizontale"]["chord"], 1e-6)
    measures["rapport_verticale_horizontale"] = ratio
    checks["F"].limit(ratio, f"longueur verticale / horizontale {fmt_ratio(ratio)} ≤ 1,3:1",
                      high=LOCAL_MAX_LENGTH_RATIO, unit="ratio")
    return result()


def _tips(graph: InkGraph) -> list[int]:
    """Les quatre extrémités libres les plus éloignées du centre du dessin."""
    ends = graph.free_ends()
    center = graph.points.mean(axis=0)
    ends.sort(key=lambda i: -np.linalg.norm(graph.points[i] - center))
    return ends[:4]


def _curves(graph: InkGraph, tips: list[int]) -> tuple[Curve, Curve] | None:
    """Ligne horizontale (de gauche à droite) et verticale (de haut en bas),
    chacune entre deux extrémités opposées autour du centre."""
    center = graph.points[tips].mean(axis=0)
    ids = sorted(tips, key=lambda i: np.arctan2(*(graph.points[i] - center)[::-1]))
    found = [graph.path(ids[0], ids[2]), graph.path(ids[1], ids[3])]
    if any(c is None for c in found):
        return None
    found.sort(key=lambda c: geo.angle_to_horizontal(c.chord))
    horizontal, vertical = found
    if horizontal.chord[0] < 0:
        horizontal = horizontal.reversed()
    if vertical.chord[1] < 0:
        vertical = vertical.reversed()
    return horizontal, vertical


def _gap(a: Curve, b: Curve) -> float:
    """Plus petit écart entre deux lignes (0 si elles se coupent)."""
    return float(np.sqrt(((a.points[:, None, :] - b.points[None, :, :]) ** 2).sum(-1)).min())


def _describe(curve: Curve, x: np.ndarray, vertical: bool) -> dict:
    chord = curve.chord_length
    angle = (geo.angle_to_vertical(curve.chord) if vertical
             else geo.angle_to_horizontal(curve.chord))
    at = float((x - curve.start) @ curve.chord) / max(chord ** 2, 1e-9)
    ends = (float(np.linalg.norm(curve.start - x)), float(np.linalg.norm(curve.end - x)))
    ratio = max(ends) / max(min(ends), 1e-6)
    offsets = curve.offsets()
    found = extrema(offsets, max(SHAPE_MM, SHAPE_FRACTION * chord))
    s_shape = len(found) == 2 and found[0][1] * found[1][1] < 0
    # Sens du modèle : creux puis crête pour l'horizontale (de gauche à droite),
    # bosse à gauche puis à droite pour la verticale (de haut en bas).
    oriented = bool(found) and found[0][1] > 0
    changes = geo.count_direction_changes(curve.points, WOBBLE_MM)
    tips_ok, tips_text = _tips_reach_axis(curve, x, vertical)
    return {"chord": chord, "angle": angle, "at": at, "ends": ends, "ratio": ratio,
            "extrema": found, "s_shape": s_shape, "oriented": oriented,
            "extra_changes": max(0, changes - STIMULUS_CHANGES),
            "tips_ok": tips_ok, "tips_text": tips_text}


def _tips_reach_axis(curve: Curve, x: np.ndarray, vertical: bool) -> tuple[bool, str]:
    """Chaque moitié de la ligne s'écarte d'abord de l'axe passant par le
    croisement (bosse) ; son extrémité doit revenir toucher ou recouper cet axe."""
    axis = 0 if vertical else 1
    values = curve.points[:, axis] - x[axis]
    split = int(np.argmin(np.linalg.norm(curve.points - x, axis=1)))
    texts, ok = [], True
    # Chaque moitié est parcourue du croisement vers son extrémité.
    for arm in (values[:split + 1][::-1], values[split:]):
        away = np.nonzero(np.abs(arm) >= SHAPE_MM)[0]
        bulge = arm[away[0]] if len(away) else 0.0
        tip = arm[-1]
        reached = abs(tip) <= AXIS_TOUCH_MM or tip * bulge < 0
        ok &= reached
        texts.append("oui" if reached else f"non, à {fmt(abs(tip))}")
    return ok, " ; ".join(texts)


def _shape_text(d: dict) -> str:
    signs = "".join("+" if v > 0 else "−" for _, v in d["extrema"])
    return f"{len(d['extrema'])} crête(s) ou creux" + (f" ({signs})" if signs else "")


def _extras(drawing: Drawing, curves: list[Curve]) -> list[float]:
    """Longueurs des traits (ou morceaux) éloignés des deux lignes."""
    on_curves = np.vstack([c.points for c in curves])
    extras = []
    for stroke in drawing.strokes:
        dist = np.sqrt(((stroke.points[:, None, :] - on_curves[None, :, :]) ** 2).sum(-1)).min(1)
        away = float((dist > ON_CURVE_MM).sum()) * STEP_MM
        if away >= EXTRA_ELEMENT_MM:
            extras.append(away)
    extras += [size for size in drawing.component_sizes[1:] if size >= EXTRA_ELEMENT_MM]
    return extras

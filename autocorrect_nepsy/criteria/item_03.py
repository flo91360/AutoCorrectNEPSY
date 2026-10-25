"""Item 3 : cercle.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

from ..strokes import Drawing
from .base import Checks, ItemResult, empty_result, fmt, fmt_ratio, unrecognized_note
from . import marks as mk
from .shapes import STRAIGHT_MARGIN_MM, circle_metrics, circular_strokes

MAX_DIAMETER_RATIO = 2.0  # rapport grand / petit diamètre
MIN_SHORT_DIAMETER_MM = 30.0  # Global D : petit diamètre d'au moins 3 cm


def score(drawing: Drawing, item: int = 3) -> ItemResult:
    if drawing.is_empty:
        return empty_result(item, ("G", "A", "B", "C", "D"), "aucun tracé dans la zone")
    circles = circular_strokes(drawing)
    main = max(circles or drawing.strokes, key=lambda s: s.length)
    m = circle_metrics(main, drawing.stroke_width)
    half = m.perimeter / 2

    general = Checks()
    general.add(bool(circles), "forme circulaire reconnue")
    general.add(len(circles) <= 1, f"une seule forme circulaire ({len(circles)} trouvée(s))")
    general.limit(m.gap, f"intervalle {fmt(m.gap)} ≤ moitié du contour ({fmt(half)})", high=half)
    general.limit(m.overshoot, f"dépassement {fmt(m.overshoot)} ≤ moitié du contour ({fmt(half)})",
                  high=half)
    general.limit(m.ratio, f"rapport des diamètres {fmt_ratio(m.ratio)} ≤ 2:1",
                  high=MAX_DIAMETER_RATIO, unit="ratio")

    motor_a = Checks().add(m.rounded, "au moins un changement de direction arrondi")
    motor_b = Checks().limit(
        m.longest_straight,
        f"plus longue section droite {fmt(m.longest_straight)} < grand diamètre "
        f"{fmt(m.long_diameter)} (marge de mesure 1 mm)",
        high=m.long_diameter - STRAIGHT_MARGIN_MM)

    global_c = Checks().add(bool(circles), "figure circulaire quelconque")
    global_d = Checks()
    global_d.limit(m.short_diameter, f"petit diamètre {fmt(m.short_diameter)} ≥ 30 mm",
                   low=MIN_SHORT_DIAMETER_MM)
    global_d.limit(m.ratio, f"rapport des diamètres {fmt_ratio(m.ratio)} ≤ 2:1",
                   high=MAX_DIAMETER_RATIO, unit="ratio")

    marks = [mk.segment(*m.long_ends, f"grand Ø {fmt(m.long_diameter)}"),
             mk.segment(*m.short_ends, f"petit Ø {fmt(m.short_diameter)}"),
             mk.segment(*m.straight_ends, f"section droite {fmt(m.longest_straight)}")]

    return ItemResult(
        item,
        {"G": general.criterion("G"), "A": motor_a.criterion("A"),
         "B": motor_b.criterion("B"), "C": global_c.criterion("C"),
         "D": global_d.criterion("D")},
        measures={"grand_diametre_mm": m.long_diameter, "petit_diametre_mm": m.short_diameter,
                  "intervalle_mm": m.gap, "depassement_mm": m.overshoot,
                  "section_droite_max_mm": m.longest_straight},
        notes=[] if circles else [unrecognized_note("forme circulaire non reconnue")],
        marks=marks,
    )

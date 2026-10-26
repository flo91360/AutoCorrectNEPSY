"""Item 3 : cercle.

Seuils repris du manuel NEPSY-II (Copie de figures), reformulés.
"""

from __future__ import annotations

from ..strokes import Drawing
from .base import ItemResult, Scoring, fmt, fmt_ratio, manual_thresholds, unrecognized_note
from . import marks as mk
from .shapes import STRAIGHT_MARGIN_MM, circle_metrics, circular_strokes

# Seuils du manuel, reformulés (liste : autocorrect-nepsy seuils).
threshold = manual_thresholds(__name__)
MAX_DIAMETER_RATIO = threshold(2.0, "GD", "rapport du grand au petit diamètre, au plus", "ratio")
MIN_SHORT_DIAMETER_MM = threshold(30.0, "D", "petit diamètre, au moins")


def score(drawing: Drawing, item: int = 3) -> ItemResult:
    scoring = Scoring(item, "GABCD")
    if drawing.is_empty:
        return scoring.empty()
    circles = circular_strokes(drawing)
    main = max(circles or drawing.strokes, key=lambda s: s.length)
    m = circle_metrics(main, drawing.stroke_width)
    half = m.perimeter / 2
    ratio_text = f"rapport des diamètres {fmt_ratio(m.ratio)} ≤ {MAX_DIAMETER_RATIO.text}"

    general = scoring["G"]
    general.add(bool(circles), "forme circulaire reconnue")
    general.add(len(circles) <= 1, f"une seule forme circulaire ({len(circles)} trouvée(s))")
    general.limit(m.gap, f"intervalle {fmt(m.gap)} ≤ moitié du contour ({fmt(half)})", high=half)
    general.limit(m.overshoot, f"dépassement {fmt(m.overshoot)} ≤ moitié du contour ({fmt(half)})",
                  high=half)
    general.limit(m.ratio, ratio_text, high=MAX_DIAMETER_RATIO, unit="ratio")

    scoring["A"].add(m.rounded, "au moins un changement de direction arrondi")
    scoring["B"].limit(
        m.longest_straight,
        f"plus longue section droite {fmt(m.longest_straight)} < grand diamètre "
        f"{fmt(m.long_diameter)} (marge de mesure 1 mm)",
        high=m.long_diameter - STRAIGHT_MARGIN_MM)

    scoring["C"].add(bool(circles), "figure circulaire quelconque")
    scoring["D"].limit(m.short_diameter,
                       f"petit diamètre {fmt(m.short_diameter)} ≥ {MIN_SHORT_DIAMETER_MM.text}",
                       low=MIN_SHORT_DIAMETER_MM)
    scoring["D"].limit(m.ratio, ratio_text, high=MAX_DIAMETER_RATIO, unit="ratio")

    scoring.marks += [mk.segment(*m.long_ends, f"grand Ø {fmt(m.long_diameter)}"),
                      mk.segment(*m.short_ends, f"petit Ø {fmt(m.short_diameter)}"),
                      mk.segment(*m.straight_ends, f"section droite {fmt(m.longest_straight)}")]
    scoring.measures.update(grand_diametre_mm=m.long_diameter, petit_diametre_mm=m.short_diameter,
                            intervalle_mm=m.gap, depassement_mm=m.overshoot,
                            section_droite_max_mm=m.longest_straight)
    if not circles:
        scoring.notes.append(unrecognized_note("forme circulaire non reconnue"))
    return scoring.result()

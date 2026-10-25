"""Silhouette, régions fermées et polygones des figures à côtés droits."""

import numpy as np
import pytest

from autocorrect_nepsy.criteria import polygons
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PX_PER_MM, canvas, polyline


def drawing_of(image):
    return extract_drawing(ink_mask(image), PX_PER_MM)


def test_square_cut_by_a_diagonal_gives_two_triangles():
    image = polyline(canvas(), [(12, 24), (52, 24), (52, 64), (12, 64)], closed=True)
    polyline(image, [(12, 24), (52, 64)])
    found = polygons.regions(drawing_of(image))
    assert len(found) == 2
    triangles = [polygons.fit_polygon(o, 3) for o in found]
    assert all(t is not None for t in triangles)
    for t in triangles:
        assert sorted(t.lengths) == pytest.approx([40, 40, 40 * np.sqrt(2)], abs=1.0)


def test_small_gap_is_closed_and_measured():
    image = polyline(canvas(), [(14, 24), (52, 24), (52, 64), (12, 64), (12, 26)])
    drawing = drawing_of(image)
    outline = polygons.silhouette(drawing)
    square = polygons.fit_polygon(outline, 4, offset=-polygons.EDGE_OFFSET_MM)
    assert square is not None
    assert sorted(square.lengths) == pytest.approx([40, 40, 40, 40], abs=1.0)
    assert max(polygons.raster(drawing).gaps) == pytest.approx(2.0, abs=0.8)


def test_short_side_of_a_badly_closed_corner_is_merged():
    # Triangle dont un coin est fermé par un petit côté de 3 mm.
    image = polyline(canvas(), [(12, 64), (32, 24), (50, 61), (52, 64)], closed=True)
    [region] = polygons.regions(drawing_of(image))
    triangle = polygons.fit_polygon(region, 3)
    assert triangle is not None
    assert min(np.linalg.norm(triangle.vertices - (52, 64), axis=1)) < 1.5

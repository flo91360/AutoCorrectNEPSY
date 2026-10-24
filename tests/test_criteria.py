"""Cotation de dessins synthétiques : copies fidèles et erreurs typiques."""

import numpy as np
import pytest

from autocorrect_nepsy.criteria import score_item
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PX_PER_MM, canvas, circle_points, draw_model, polyline


def score(item, image):
    return score_item(item, extract_drawing(ink_mask(image), PX_PER_MM))


def scores(result):
    return {code: c.score for code, c in result.criteria.items()}


@pytest.mark.parametrize("item", range(1, 9))
@pytest.mark.parametrize("wobble", [0.0, 0.5])
def test_faithful_copy_gets_full_marks(item, wobble):
    result = score(item, draw_model(item, canvas(), wobble=wobble))
    assert set(scores(result).values()) == {1}, {c: k.details for c, k in result.criteria.items()}


@pytest.mark.parametrize("item, codes", [(1, "GABCD"), (4, "GABCDEF"), (8, "GABCDEF")])
def test_empty_zone_scores_zero_and_asks_review(item, codes):
    result = score(item, canvas())
    assert scores(result) == {c: 0 for c in codes}
    assert result.to_review


def test_item1_short_line():
    result = scores(score(1, polyline(canvas(), [(32, 40), (32, 48)])))
    assert result == {"G": 1, "A": 0, "B": 1, "C": 1, "D": 0}


def test_item1_tilted_line_fails_global_c():
    result = scores(score(1, polyline(canvas(), [(15, 20), (55, 50)])))
    assert result["C"] == 0 and result["G"] == 0 and result["A"] == 1


def test_item2_too_long_line_fails_global_d():
    image = canvas(width_mm=100)
    result = scores(score(2, polyline(image, [(5, 44), (90, 44)])))
    assert result["D"] == 0 and result["A"] == 1


def test_item3_small_circle_and_d_shape():
    small = scores(score(3, polyline(canvas(), circle_points((32, 44), 10), closed=True)))
    assert small["D"] == 0 and small["G"] == 1
    arc = circle_points((22, 44), 20, start_deg=-90, sweep_deg=180)
    d_shape = scores(score(3, polyline(canvas(), np.vstack([arc, [(22, 24)]]), closed=True)))
    assert d_shape["B"] == 0


def test_item4_rectangle_fails_local_f_only():
    image = polyline(canvas(), [(7, 30), (57, 30), (57, 60), (7, 60)], closed=True)
    result = scores(score(4, image))
    assert result == {"G": 1, "A": 1, "B": 1, "C": 1, "D": 1, "E": 1, "F": 0}


def test_item4_skewed_corners_fail_global_d():
    image = polyline(canvas(), [(5, 30), (35, 30), (60, 64), (30, 64)], closed=True)
    result = scores(score(4, image))
    assert result["D"] == 0 and result["E"] == 1


def test_item4_triangle_is_not_a_square():
    image = polyline(canvas(), [(10, 60), (54, 60), (32, 20)], closed=True)
    result = scores(score(4, image))
    assert result["G"] == 0 and result["E"] == 0


def test_item5_junction_at_top_fails_global_d():
    image = canvas()
    polyline(image, [(20, 14), (20, 74)])
    polyline(image, [(20, 18), (50, 18)])
    result = scores(score(5, image))
    assert result["D"] == 0 and result["C"] == 1


def test_item5_gap_at_junction_fails_motricite_b():
    image = canvas()
    polyline(image, [(20, 14), (20, 74)])
    polyline(image, [(24, 44), (52, 44)])
    result = scores(score(5, image))
    assert result["B"] == 0 and result["G"] == 0


def test_item6_wide_v_fails_global_d():
    image = polyline(canvas(), [(4, 50), (32, 70), (60, 50)])
    result = scores(score(6, image))
    assert result["D"] == 0 and result["E"] == 1


def test_item6_unequal_branches_fail_local_f():
    image = polyline(canvas(), [(16, 50), (32, 70), (54.5, 31)])
    result = scores(score(6, image))
    assert result["F"] == 0 and result["E"] == 1


def test_item7_low_horizontal_fails_global_d():
    image = canvas()
    polyline(image, [(22, 14), (22, 74)])
    polyline(image, [(42, 14), (42, 74)])
    polyline(image, [(8, 64), (56, 64)])
    result = scores(score(7, image))
    assert result["D"] == 0 and result["C"] == 1


def test_item8_two_circles_only():
    image = canvas()
    for y in (34, 54):
        polyline(image, circle_points((32, y), 13), closed=True)
    result = scores(score(8, image))
    assert result["C"] == 0 and result["G"] == 0


def test_item8_small_overlap_fails_global_d():
    image = canvas()
    for y in (20, 43, 66):
        polyline(image, circle_points((32, y), 13), closed=True)
    result = scores(score(8, image))
    assert result["D"] == 0 and result["C"] == 1


def test_borderline_measure_is_flagged():
    # Angle au sommet de 79° : rempli mais proche de la limite de 80°.
    half = np.radians(79.0 / 2)
    left = (32 - 40 * np.sin(half), 70 - 40 * np.cos(half))
    right = (32 + 40 * np.sin(half), 70 - 40 * np.cos(half))
    result = score(6, polyline(canvas(), [left, (32, 70), right]))
    assert result.criteria["D"].met
    assert result.criteria["D"].borderline
    assert result.to_review

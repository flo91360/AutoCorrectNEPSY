"""Cotation de dessins synthétiques : copies fidèles et erreurs typiques."""

import numpy as np
import pytest

from autocorrect_nepsy.criteria import score_item
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import (PX_PER_MM, bucket, canvas, circle_points, cross_points, cylinder, dot, dot_row,
                   draw_model, flower, nested_triangles, polyline, s_curve, stairs_points, v_shape,
                   wheels)


def score(item, image):
    return score_item(item, extract_drawing(ink_mask(image), PX_PER_MM))


def scores(result):
    return {code: c.score for code, c in result.criteria.items()}


@pytest.mark.parametrize("item", range(1, 22))
@pytest.mark.parametrize("wobble", [0.0, 0.5])
def test_faithful_copy_gets_full_marks(item, wobble):
    result = score(item, draw_model(item, canvas(), wobble=wobble))
    assert set(scores(result).values()) == {1}, {c: k.details for c, k in result.criteria.items()}


@pytest.mark.parametrize("item, codes", [(1, "GABCD"), (4, "GABCDEF"), (8, "GABCDEF"),
                                         (9, "GABCDEF"), (10, "GABCDEF"), (11, "GABCDEF"),
                                         (12, "GABCDEF"), (13, "GABCDEF"), (14, "GABCDEF"),
                                         (15, "GABCDEF"), (16, "GABCDEF"), (17, "GABCDEF"),
                                         (18, "GABCDEF"), (19, "GABCDEF"), (20, "GABCDEF"),
                                         (21, "GABCDEF")])
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


def dots(centers, diameter=1.9):
    image = canvas()
    for center in centers:
        dot(image, center, diameter)
    return image


def test_item9_dashes_instead_of_circles():
    image = canvas()
    for x, y in dot_row((18, 58), (3, -3)):
        polyline(image, [(x - 0.8, y + 0.8), (x + 0.8, y - 0.8)])
    result = scores(score(9, image))
    assert result == {"G": 0, "A": 1, "B": 0, "C": 1, "D": 1, "E": 0, "F": 0}


def test_item9_empty_circles_and_points_are_not_filled():
    image = canvas()
    for center in dot_row((14, 62), (4, -4)):
        polyline(image, circle_points(center, 1.5), closed=True)
    empty = scores(score(9, image))
    assert empty["G"] == 0 and empty["E"] == 0 and empty["B"] == 1 and empty["C"] == 1
    points = scores(score(9, dots(dot_row((18, 58), (3, -3)), diameter=0.8)))
    assert points["G"] == 0 and points["E"] == 0 and points["A"] == 1 and points["D"] == 1


def test_item9_flat_row_fails_global_d():
    result = scores(score(9, dots(dot_row((10, 50), (4.2, -1.1)))))
    assert result["D"] == 0 and result["G"] == 0 and result["C"] == 1 and result["E"] == 1


def test_item9_extra_circles_and_wide_gaps_fail_local_f():
    twelve = scores(score(9, dots(dot_row((12, 64), (3, -3), count=12))))
    assert twelve["F"] == 0 and twelve["E"] == 0 and twelve["G"] == 0
    spread = scores(score(9, dots(dot_row((6, 80), (5.5, -5.5)))))
    assert spread["F"] == 0 and spread["E"] == 1 and spread["D"] == 1


def test_item9_large_marks_fail_motricite_a():
    result = scores(score(9, dots(dot_row((10, 66), (4.5, -4.5)), diameter=3.6)))
    assert result["A"] == 0 and result["G"] == 1


def test_item10_rectangle_is_not_an_isosceles_trapezoid():
    image = polyline(canvas(), [(20, 42), (32, 20), (44, 42)])
    polyline(image, [(14, 42), (50, 42), (50, 51), (14, 51)], closed=True)
    result = scores(score(10, image))
    assert result["E"] == 0 and result["G"] == 0 and result["C"] == 1 and result["D"] == 1


def test_item10_tall_triangle_fails_local_f():
    image = polyline(canvas(), [(24, 50), (32, 14), (40, 50)])
    polyline(image, [(14, 50), (50, 50), (44, 59), (20, 59)], closed=True)
    result = scores(score(10, image))
    assert result["F"] == 0 and result["E"] == 1


def test_item10_floating_triangle_and_off_center():
    # Triangle fermé posé 4 mm au-dessus du trapèze : relié pour Global C
    # (≤ 5 mm) mais pas pour le critère général (≤ 3 mm).
    image = polyline(canvas(), [(20, 38), (32, 16), (44, 38)], closed=True)
    polyline(image, [(14, 42), (50, 42), (44, 51), (20, 51)], closed=True)
    floating = scores(score(10, image))
    assert floating["G"] == 0 and floating["C"] == 1 and floating["B"] == 0
    # Triangle décalé vers la droite : parties du haut de 2 et 10 mm.
    image = polyline(canvas(), [(16, 42), (28, 20), (40, 42)])
    polyline(image, [(14, 42), (50, 42), (44, 51), (20, 51)], closed=True)
    shifted = score(10, image)
    assert scores(shifted)["G"] == 0 and scores(shifted)["C"] == 1
    assert shifted.measures["rapport_parties_haut"] > 1.5


def test_item11_square_below_the_middle_fails_global_d():
    image = polyline(canvas(), [(4, 24), (60, 24), (60, 64), (4, 64)], closed=True)
    polyline(image, [(4, 48), (26, 48), (26, 24)])
    result = scores(score(11, image))
    assert result == {"G": 1, "A": 1, "B": 1, "C": 1, "D": 0, "E": 1, "F": 1}


def test_item11_overshoot_fails_motricite_b():
    image = polyline(canvas(), [(4, 24), (60, 24), (60, 64), (4, 64)], closed=True)
    polyline(image, [(4, 43), (24, 43), (24, 19)])
    result = scores(score(11, image))
    assert result["B"] == 0 and result["G"] == 0 and result["D"] == 1


def test_item11_tall_rectangle_fails_general():
    image = polyline(canvas(), [(10, 20), (54, 20), (54, 66), (10, 66)], closed=True)
    polyline(image, [(10, 42), (31, 42), (31, 20)])
    result = scores(score(11, image))
    assert result["G"] == 0 and result["E"] == 1 and result["F"] == 1


def test_item12_tilted_and_long_lines():
    image = canvas()
    tilted = s_curve((32, 44))
    angle = np.radians(25)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    polyline(image, (tilted - (32, 44)) @ rotation.T + (32, 44))
    polyline(image, s_curve((32, 44), vertical=True))
    result = scores(score(12, image))
    assert result["C"] == 0 and result["E"] == 1 and result["A"] == 1
    image = canvas()
    polyline(image, s_curve((32, 44), half=27, bulge=9))
    polyline(image, s_curve((32, 44), vertical=True))
    long = scores(score(12, image))
    assert long["F"] == 0 and long["E"] == 1


def test_item12_reversed_s_fails_general():
    image = canvas()
    mirrored = s_curve((32, 44)) * (1, -1) + (0, 88)
    polyline(image, mirrored)
    polyline(image, s_curve((32, 44), vertical=True))
    result = scores(score(12, image))
    assert result["G"] == 0 and result["E"] == 1 and result["C"] == 1


def fan(radials, length=25.0, base=(7, 57), y=58, center=32):
    image = canvas()
    polyline(image, [(base[0], y), (base[1], y)])
    for i, (angle, size) in enumerate(radials):
        a = np.radians(angle)
        polyline(image, [(center, y), (center + size * np.cos(a), y - size * np.sin(a))], seed=i)
    return image


def test_item13_missing_radials_and_short_lines():
    five = [(a, 25.0) for a in (30, 60, 90, 120, 150)]
    result = scores(score(13, fan(five)))
    assert result["C"] == 0 and result["G"] == 0 and result["D"] == 1 and result["E"] == 1
    uneven = [(a, 25.0 if i % 2 else 12.0) for i, a in enumerate(np.arange(22.5, 180, 22.5))]
    result = scores(score(13, fan(uneven)))
    assert result["E"] == 0 and result["F"] == 0 and result["C"] == 1


def test_item13_off_center_convergence_fails_general():
    seven = [(a, 25.0) for a in np.arange(22.5, 180, 22.5)]
    result = scores(score(13, fan(seven, center=14, base=(5, 59))))
    assert result["G"] == 0 and result["D"] == 0 and result["C"] == 1


def test_item14_straight_back_and_rising_cylinder():
    image = canvas()
    for points, closed, seed in cylinder((32, 44), back_depth=0.0):
        polyline(image, points, closed=closed, seed=seed)
    flat = scores(score(14, image))
    assert flat["D"] == 0 and flat["G"] == 0 and flat["C"] == 1
    image = canvas()
    for points, closed, seed in cylinder((32, 44)):
        polyline(image, np.asarray(points) * (1, -1) + (0, 88), closed=closed, seed=seed)
    rising = scores(score(14, image))
    assert rising["C"] == 0 and rising["G"] == 0


def test_item14_round_front_and_one_side():
    image = canvas()
    for points, closed, seed in cylinder((32, 44), depth=9.3):
        polyline(image, points, closed=closed, seed=seed)
    round_front = scores(score(14, image))
    assert round_front["F"] == 0 and round_front["C"] == 1
    image = canvas()
    for points, closed, seed in cylinder((32, 44))[:3]:
        polyline(image, points, closed=closed, seed=seed)
    one_side = scores(score(14, image))
    assert one_side["E"] == 0


def test_item15_plain_crossing_lines_are_not_a_cross():
    image = polyline(canvas(), [(15, 44), (49, 44)])
    polyline(image, [(32, 27), (32, 61)])
    assert scores(score(15, image))["C"] == 0


def test_item15_uneven_branches():
    image = polyline(canvas(), cross_points((32, 44), arms=(11, 18, 11, 11)), closed=True)
    result = scores(score(15, image))
    assert result["D"] == 0 and result["E"] == 0 and result["G"] == 0 and result["C"] == 1
    wide = polyline(canvas(), cross_points((32, 44), half_width=9, arm=8), closed=True)
    result = scores(score(15, wide))
    assert result["E"] == 0 and result["C"] == 1 and result["D"] == 1


def test_item16_missing_small_triangle_and_links():
    parts = nested_triangles((32, 26))
    image = canvas()
    for i, points in enumerate(parts[:2]):
        polyline(image, points, closed=True, seed=i)
    result = scores(score(16, image))
    assert result["C"] == 0 and result["G"] == 0 and result["E"] == 0
    image = canvas()
    for i, points in enumerate(parts[:3]):
        polyline(image, points, closed=True, seed=i)
    no_links = scores(score(16, image))
    assert no_links["D"] == 0 and no_links["G"] == 0 and no_links["F"] == 0


def test_item16_tilted_small_triangle_fails_global_d():
    image = canvas()
    for i, points in enumerate(nested_triangles((32, 26), small_shift=(4.5, 0))):
        polyline(image, points, closed=len(points) == 3, seed=i)
    result = score(16, image)
    assert scores(result)["D"] == 0
    assert result.measures["alignement_sommets_mm"] > 4


def test_item17_single_lines_and_wide_angle():
    image = polyline(canvas(), [(10, 26), (32, 57), (54, 26)])
    assert scores(score(17, image))["C"] == 0
    image = canvas()
    for i, points in enumerate(v_shape((32, 57), height=14, width=60)):
        polyline(image, points, closed=True, seed=i)
    flat = scores(score(17, image))
    assert flat["G"] == 0 and flat["D"] == 0


def test_item17_tilted_tops_fail_general():
    image = canvas()
    for i, points in enumerate(v_shape((32, 57), tilt=9)):
        polyline(image, points, closed=True, seed=i)
    result = scores(score(17, image))
    assert result["G"] == 0 and result["C"] == 1


def test_item18_step_count_and_heights():
    three = scores(score(18, polyline(canvas(), stairs_points((10, 20), step=14, steps=3),
                                      closed=True)))
    assert three["E"] == 0 and three["G"] == 0 and three["C"] == 1
    five = scores(score(18, polyline(canvas(), stairs_points((7, 15), step=10, steps=5),
                                     closed=True)))
    assert five["F"] == 0 and five["E"] == 0
    uneven = scores(score(18, polyline(canvas(), stairs_points((7.5, 15),
                                                               heights=[16, 12.3, 12.3, 12.3]),
                                       closed=True)))
    assert uneven["D"] == 0 and uneven["E"] == 1


def bucket_image(top=(32, 30), **kwargs):
    image = canvas()
    for i, (points, closed) in enumerate(bucket(top, **kwargs)):
        polyline(image, points, closed=closed, seed=i)
    return image


def test_item19_narrow_opening_fails_local_f():
    result = scores(score(19, bucket_image(inner=0.65)))
    assert result["F"] == 0 and result["G"] == 1 and result["D"] == 1


def test_item19_circles_and_detached_base():
    circles = scores(score(19, bucket_image(top=(32, 24), a=18, b=17, drop=30)))
    assert circles["E"] == 0 and circles["F"] == 0
    detached = scores(score(19, bucket_image(drop=40)))
    assert detached["G"] == 0 and detached["C"] == 0


def flower_image(**kwargs):
    image = canvas()
    for i, petal in enumerate(flower((32, 44), **kwargs)):
        polyline(image, petal, closed=True, seed=i)
    return image


def test_item20_seven_petals_and_rounded_tips():
    seven = scores(score(20, flower_image(petals=7)))
    assert seven["C"] == 0 and seven["F"] == 0 and seven["G"] == 0
    blunt = scores(score(20, flower_image(blunt=True)))
    assert blunt["D"] == 0 and blunt["G"] == 0 and blunt["C"] == 1


def test_item20_petal_away_from_center_and_petal_sizes():
    away = scores(score(20, flower_image(starts=[4, 0, 0, 0, 0, 0])))
    assert away["D"] == 0 and away["G"] == 1
    long = scores(score(20, flower_image(length=36)))
    assert long["F"] == 0 and long["E"] == 1
    wide = scores(score(20, flower_image(width=12)))
    assert wide["E"] == 0 and wide["F"] == 1


def wheels_image(strokes=None, size=(64, 88), **kwargs):
    image = canvas(*size)
    for i, (points, closed) in enumerate(strokes or wheels(**kwargs)):
        polyline(image, points, closed=closed, seed=i)
    return image


def test_item21_five_chords_and_no_axle():
    five = scores(score(21, wheels_image(chords=(5, 5))))
    assert five["G"] == 0 and five["F"] == 0 and five["D"] == 1
    loose = scores(score(21, wheels_image(axle=False)))
    assert loose["C"] == 0 and loose["G"] == 0 and loose["D"] == 1


def test_item21_wheel_sizes():
    equal = scores(score(21, wheels_image(size=(80, 90), left_center=(30, 55), left=23.0,
                                          right=23.0, offset=(16, -18))))
    assert equal["D"] == 0 and equal["G"] == 0 and equal["E"] == 1
    large = scores(score(21, wheels_image(size=(90, 100), left_center=(34, 62), left=31.0,
                                          right=25.0, offset=(18, -22))))
    assert large["E"] == 0 and large["D"] == 1


def test_item21_broken_spoke_fails_motricite_b():
    strokes = wheels()
    center, u = np.array([27.0, 52.0]), np.array([25.0, 0.0])
    strokes[2] = ([center - u, center - 0.5 * u], False)  # corde horizontale de la grande roue
    strokes.append(([center - 0.42 * u, center + u], False))
    broken = scores(score(21, wheels_image(strokes)))
    assert broken["B"] == 0 and broken["A"] == 1


def test_borderline_measure_is_flagged():
    # Angle au sommet de 79° : rempli mais proche de la limite de 80°.
    half = np.radians(79.0 / 2)
    left = (32 - 40 * np.sin(half), 70 - 40 * np.cos(half))
    right = (32 + 40 * np.sin(half), 70 - 40 * np.cos(half))
    result = score(6, polyline(canvas(), [left, (32, 70), right]))
    assert result.criteria["D"].met
    assert result.criteria["D"].borderline
    assert result.to_review

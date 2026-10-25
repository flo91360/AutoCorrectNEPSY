import numpy as np
import pytest

from autocorrect_nepsy.ink import ink_mask, printed_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import (DARK_BLUE_PEN, PENCIL, PRINT_BLACK, PX_PER_MM, canvas, circle_points, dot,
                   polyline)


def drawing_of(image):
    return extract_drawing(ink_mask(image), PX_PER_MM)


def test_blue_pen_is_separated_from_pencil_and_print():
    image = canvas()
    polyline(image, [(10, 20), (50, 20)])
    polyline(image, [(10, 40), (50, 40)], color=PENCIL)
    polyline(image, [(10, 60), (50, 60)], color=PRINT_BLACK)
    ink = ink_mask(image)
    ys = np.nonzero(ink)[0] / PX_PER_MM
    assert ys.min() > 18 and ys.max() < 22
    assert printed_mask(image)[int(60 * PX_PER_MM), int(30 * PX_PER_MM)] == 1


def test_darker_ink_does_not_cut_a_continuous_stroke():
    # Sur 3 mm, le stylo a laissé une encre plus épaisse : bleu presque noir.
    image = canvas()
    polyline(image, [(10, 40), (54, 40)])
    polyline(image, [(30, 40), (33, 40)], color=DARK_BLUE_PEN)
    drawing = drawing_of(image)
    assert len(drawing.strokes) == 1
    [line] = drawing.significant_lines()
    assert line.interruptions == 0
    assert line.length == pytest.approx(44, abs=1.0)


def test_pencil_touching_the_stroke_is_not_ink():
    image = canvas()
    polyline(image, [(10, 40), (54, 40)])
    polyline(image, [(30, 20), (30, 60)], color=PENCIL)
    ink = ink_mask(image)
    pencil_only = ink[int(25 * PX_PER_MM):int(35 * PX_PER_MM), int(29 * PX_PER_MM):int(31 * PX_PER_MM)]
    assert pencil_only.sum() == 0
    assert len(drawing_of(image).significant_lines()) == 1


def test_empty_zone():
    assert drawing_of(canvas()).is_empty


def test_crossing_lines_give_two_continuous_strokes():
    image = canvas()
    polyline(image, [(10, 40), (54, 40)])
    polyline(image, [(32, 15), (32, 70)])
    drawing = drawing_of(image)
    assert len(drawing.strokes) == 2
    lengths = sorted(s.length for s in drawing.strokes)
    assert lengths == pytest.approx([44, 55], abs=1.5)
    assert len(drawing.significant_lines()) == 2


def test_square_has_four_sides():
    image = polyline(canvas(), [(12, 24), (52, 24), (52, 64), (12, 64)], closed=True)
    lines = drawing_of(image).significant_lines()
    assert len(lines) == 4
    assert sorted(round(l.length) for l in lines) == pytest.approx([40, 40, 40, 40], abs=1.5)


def test_interrupted_line_is_one_line_with_one_interruption():
    image = canvas()
    polyline(image, [(10, 40), (28, 40)])
    polyline(image, [(31, 40), (54, 40)])
    lines = drawing_of(image).significant_lines()
    assert len(lines) == 1
    assert lines[0].interruptions == 1
    assert lines[0].length == pytest.approx(44, abs=1.0)


def test_circle_is_one_closed_stroke():
    image = polyline(canvas(), circle_points((32, 44), 18), closed=True)
    drawing = drawing_of(image)
    assert len(drawing.strokes) == 1
    assert drawing.strokes[0].closed
    assert drawing.strokes[0].length == pytest.approx(2 * np.pi * 18, rel=0.03)


def test_line_retraced_beside_itself_is_detected():
    image = canvas()
    polyline(image, [(30, 15), (30, 75)])
    polyline(image, [(31.8, 15), (31.8, 45)])
    lines = drawing_of(image).significant_lines()
    assert len(lines) == 1
    assert lines[0].doubled_length > 20


def test_stroke_width_is_measured():
    image = polyline(canvas(), [(10, 40), (54, 40)], width_mm=0.8)
    assert drawing_of(image).stroke_width == pytest.approx(0.8, abs=0.25)


def test_isolated_marks_are_measured():
    image = canvas()
    dot(image, (15, 20), 2.0)
    polyline(image, circle_points((35, 20), 1.6), closed=True)
    polyline(image, [(50, 20), (53, 20)])
    dot(image, (15, 50), 0.7)  # simple point : trop petit pour un trait, gardé comme marque
    drawing = drawing_of(image)
    disk, ring, dash, speck = sorted(drawing.blobs, key=lambda b: (round(b.center[1] / 10), b.center[0]))
    assert disk.diameter == pytest.approx(2.2, abs=0.35)  # liseré de l'encre compris
    assert disk.solidity > 0.9 and disk.hole_fraction < 0.05
    assert ring.hole_fraction > 0.2
    assert dash.length == pytest.approx(3.5, abs=0.5) and dash.area / dash.length < 1.0
    assert speck.length < 1.2
    # Écart bord à bord : 20 mm entre centres, moins les deux rayons.
    assert disk.distance_to(ring) == pytest.approx(20 - 1.0 - 1.85, abs=0.5)

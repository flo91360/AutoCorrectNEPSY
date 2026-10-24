import numpy as np
import pytest

from autocorrect_nepsy.ink import ink_mask, printed_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PENCIL, PRINT_BLACK, PX_PER_MM, canvas, circle_points, polyline


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

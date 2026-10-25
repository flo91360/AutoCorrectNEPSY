"""Mesures dessinées sur les traits lus par l'outil, dans le rapport."""

from collections import Counter

import numpy as np
import pytest

from autocorrect_nepsy import render
from autocorrect_nepsy.criteria import score_item
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PX_PER_MM, canvas, draw_model

EXPECTED_MARKS = {
    1: {"cote": 1, "bande": 1, "angle": 1},
    2: {"cote": 1, "bande": 1, "angle": 1},
    3: {"segment": 3},
    4: {"cote": 4, "angle": 4, "bande": 4},
    5: {"cote": 2, "bande": 2, "point": 1},
    6: {"cote": 2, "bande": 2, "angle": 3},
    7: {"cote": 7, "bande": 3, "angle": 2},
    8: {"segment": 3, "cercle": 2},
    9: {"tache": 10, "angle": 1, "cote": 1, "segment": 2},
    10: {"bande": 6, "cote": 2, "segment": 3},
    11: {"bande": 6, "cote": 4, "segment": 2},
    12: {"trace": 2, "segment": 2, "point": 1},
    13: {"bande": 8, "cote": 1, "segment": 7},
    14: {"bande": 2, "segment": 1, "point": 1, "cote": 1},
    15: {"trace": 1, "segment": 2, "point": 1},
    16: {"trace": 3, "segment": 3},
    17: {"trace": 3, "angle": 1, "cote": 1, "segment": 2},
    18: {"trace": 1, "cote": 2, "segment": 4},
    19: {"trace": 3, "segment": 3, "bande": 2},
    20: {"trace": 6, "segment": 6, "cercle": 1},
    21: {"trace": 2, "segment": 13},
}


def scored(item, image=None):
    image = draw_model(item, canvas()) if image is None else image
    drawing = extract_drawing(ink_mask(image), PX_PER_MM)
    return drawing, score_item(item, drawing)


@pytest.mark.parametrize("item", range(1, 22))
def test_each_item_marks_its_measures(item):
    _, result = scored(item)
    kinds = Counter(mark.kind for mark in result.marks)
    for kind, count in EXPECTED_MARKS[item].items():
        assert kinds[kind] >= count, (kind, kinds)
    assert all(mark.label for mark in result.marks)


def test_square_sides_are_measured_between_corners():
    _, result = scored(4)
    cotes = [mark for mark in result.marks if mark.kind == "cote"]
    corners = {(12, 24), (52, 24), (52, 64), (12, 64)}
    for mark in cotes:
        assert mark.label == "40,0 mm"
        for end in mark.points:
            assert min(np.hypot(end[0] - x, end[1] - y) for x, y in corners) < 1.0


def test_overlap_circle_sits_in_the_lens():
    _, result = scored(8)
    lenses = [mark for mark in result.marks if mark.kind == "cercle"]
    # Cercles de centres (32, 24), (32, 44), (32, 64) : lentilles vers y = 34 et y = 54.
    assert sorted(round(float(mark.points[0][1])) for mark in lenses) == pytest.approx([34, 54], abs=1)
    assert all(mark.radius * 2 == pytest.approx(6.0, abs=0.6) for mark in lenses)


@pytest.mark.parametrize("item", [3, 4, 7, 9, 12, 15, 16, 18, 19, 20, 21])
def test_measured_image_is_drawn(item):
    drawing, result = scored(item)
    zone = canvas()
    bare = render.measured_image(zone.shape, PX_PER_MM, drawing.strokes, [], [], drawing.stroke_width)
    marked = render.measured_image(zone.shape, PX_PER_MM, drawing.strokes,
                                   drawing.significant_lines(), result.marks, drawing.stroke_width)
    assert marked.shape[1] == render.DISPLAY_WIDTH * render.RENDER_SCALE
    assert marked.shape == bare.shape
    # Les repères et leurs étiquettes ajoutent du dessin (plus de 1 % de l'image).
    changed = np.abs(marked.astype(int) - bare.astype(int)).sum(axis=2) > 60
    assert changed.mean() > 0.01


def test_labels_without_system_font_lose_their_accents(monkeypatch):
    monkeypatch.setattr(render, "FONT_FILES", ())
    render._font.cache_clear()
    try:
        _, plain = render._font(20)
        assert plain
        assert render._plain("écart 3° · Ø 39,1 mm") == "ecart 3° · diam. 39,1 mm"
    finally:
        render._font.cache_clear()

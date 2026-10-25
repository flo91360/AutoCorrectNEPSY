"""Même lecture des dessins quelle que soit la résolution du scan."""

import numpy as np
import pytest

from autocorrect_nepsy.criteria.ellipses import find_ellipses
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.layout import WORK_DPI, prepare_page
from autocorrect_nepsy.pipeline import PageInput, correct_pages
from autocorrect_nepsy.scan import ScannedPage
from autocorrect_nepsy.strokes import extract_drawing

from synth import canvas, draw_model, page


@pytest.mark.parametrize("item", [19, 21])
def test_ellipses_are_found_alike_at_200_and_300_dpi(item):
    found = []
    for dpi in (200, 300):
        ppm = dpi / 25.4
        image = draw_model(item, canvas(ppm=ppm), ppm=ppm, wobble=0.5)
        ellipses = find_ellipses(extract_drawing(ink_mask(image), ppm), 2)
        found.append(sorted(ellipses, key=lambda e: (e.center[0], e.center[1])))
    assert len(found[0]) == len(found[1]) == 2
    for a, b in zip(*found):
        assert np.linalg.norm(a.center - b.center) < 0.5
        assert a.major == pytest.approx(b.major, abs=0.5)
        assert a.minor == pytest.approx(b.minor, abs=0.5)


def test_fine_scan_is_reduced_to_the_working_resolution():
    dpi = 2 * WORK_DPI
    prepared = prepare_page(ScannedPage(page({0: 4, 1: 5, 2: 6, 3: 7}, ppm=dpi / 25.4), dpi,
                                        "fin"))
    assert prepared.scale == pytest.approx(0.5, abs=0.01)
    assert prepared.px_per_mm == pytest.approx(WORK_DPI / 25.4, rel=0.01)


def test_same_scores_at_200_and_400_dpi():
    scores = []
    for dpi in (200, 400):
        image = page({0: 19, 1: 20, 2: 21}, layout=3, ppm=dpi / 25.4)
        correction = correct_pages([PageInput(ScannedPage(image, dpi, "synthétique"), 6)])
        scores.append({report.item: {code: c.score for code, c in report.result.criteria.items()}
                       for report in correction.items})
    assert scores[0] == scores[1]
    assert sorted(scores[0]) == [19, 20, 21]

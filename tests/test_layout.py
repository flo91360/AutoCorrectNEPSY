import cv2
import numpy as np
import pytest

from autocorrect_nepsy.layout import (LayoutError, analyse_page, deskew, guess_page_numbers,
                                      prepare_page)
from autocorrect_nepsy.scan import ScannedPage

from synth import page, polyline

DPI = 100


@pytest.fixture(scope="module")
def page_image():
    return page({0: 4, 1: 5, 2: 6, 3: 7})


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_any_scan_orientation_is_restored(page_image, turns):
    raw = np.ascontiguousarray(np.rot90(page_image, turns))
    layout = analyse_page(ScannedPage(raw, DPI, "synthétique"), 2)
    assert [zone.item for zone in layout.zones] == [4, 5, 6, 7]
    assert layout.image.shape == page_image.shape
    assert abs(layout.separator.pos / layout.image.shape[0] - 0.5) < 0.03
    for zone in layout.zones:
        x0, y0, x1, y1 = zone.drawing_box
        assert layout.ink[y0:y1, x0:x1].sum() > 100
        # Rien de bleu dans la rangée des modèles.
        mx0, my0, mx1, my1 = zone.model_box
        assert layout.ink[my0:my1, mx0:mx1].sum() == 0


def test_slight_skew_is_corrected(page_image):
    h, w = page_image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 1.5, 1.0)
    tilted = cv2.warpAffine(page_image, matrix, (w, h), borderValue=(245, 245, 245))
    straightened, skew = deskew(tilted)
    assert skew == pytest.approx(-1.5, abs=0.2)
    layout = analyse_page(ScannedPage(tilted, DPI, "synthétique"), 2)
    assert [zone.item for zone in layout.zones] == [4, 5, 6, 7]


def test_wrong_page_number_is_reported(page_image):
    with pytest.raises(LayoutError, match="4 zones"):
        analyse_page(ScannedPage(page_image, DPI, "synthétique"), 1)


def test_blank_scan_is_reported():
    with pytest.raises(LayoutError):
        analyse_page(ScannedPage(np.full((800, 1100, 3), 240, np.uint8), DPI, "vide"), 2)


def test_page_structure_and_numbering():
    page1 = prepare_page(ScannedPage(page({0: 1, 1: 2, 2: 3}, layout="page1"), DPI, "p1"))
    four = prepare_page(ScannedPage(page({0: 4, 1: 5, 2: 6, 3: 7}), DPI, "p2"))
    three = prepare_page(ScannedPage(page({0: 1, 1: 2, 2: 3}, layout=3), DPI, "p5"))
    assert page1.has_header and page1.compatible_pages() == [1]
    assert four.compatible_pages() == [2, 3, 4]
    assert three.compatible_pages() == [5, 6]
    # Scans dans l'ordre du cahier, page 4 absente.
    assert guess_page_numbers([page1, four, four, three]) == [1, 2, 3, 5]
    assert guess_page_numbers([page1, four, four, four, three, three]) == [1, 2, 3, 4, 5, 6]
    # Un choix manuel est respecté et oriente la suite.
    assert guess_page_numbers([four, four, three], fixed={0: 3}) == [3, 4, 5]
    zones = page1.layout(1).zones
    assert [zone.item for zone in zones] == [1, 2, 3]


def test_drawing_past_the_end_of_the_separator_is_kept():
    # L'enfant a dessiné au-delà du bout du trait de séparation (277 mm).
    ppm = DPI / 25.4
    image = page({0: 4, 1: 5, 2: 6, 3: 7})
    polyline(image, [(270, 150), (285, 150)], ppm=ppm)
    polyline(image, [(12, 160), (25, 160)], ppm=ppm)
    layout = analyse_page(ScannedPage(image, DPI, "synthétique"), 2)
    first, last = layout.zone(4).drawing_box, layout.zone(7).drawing_box
    assert first[0] < 12 * ppm and last[2] > 285 * ppm
    # En page 1, l'en-tête est à droite : la dernière zone n'y est pas élargie.
    page1 = analyse_page(ScannedPage(page({0: 1, 1: 2, 2: 3}, layout="page1"), DPI, "p1"), 1)
    assert page1.zone(3).drawing_box[2] < 213 * ppm

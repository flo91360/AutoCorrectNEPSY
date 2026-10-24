import cv2
import numpy as np
import pytest

from autocorrect_nepsy.layout import LayoutError, analyse_page, deskew
from autocorrect_nepsy.scan import ScannedPage

from synth import page

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

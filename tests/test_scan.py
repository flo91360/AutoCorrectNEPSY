"""Lecture des scans : images, TIFF multipage, résolution, fichiers illisibles."""

import numpy as np
import pytest
from PIL import Image

from autocorrect_nepsy.scan import load_pages


def picture(value: int) -> Image.Image:
    return Image.fromarray(np.full((40, 60, 3), value, np.uint8))


@pytest.mark.parametrize("name", ["scan.png", "scan.jpg", "scan.tif"])
def test_image_resolution_is_read(tmp_path, name):
    path = tmp_path / name
    picture(200).save(path, dpi=(300, 300))
    [scan] = load_pages(path)
    assert scan.dpi == pytest.approx(300, abs=0.1)  # le PNG compte en pixels par mètre
    assert scan.image.shape == (40, 60, 3) and scan.source == name


def test_every_page_of_a_multipage_tiff_is_read(tmp_path):
    path = tmp_path / "cahier.tif"
    picture(200).save(path, save_all=True, append_images=[picture(100), picture(50)],
                      dpi=(200, 200))
    scans = load_pages(path)
    assert [scan.source for scan in scans] == ["cahier.tif p1", "cahier.tif p2", "cahier.tif p3"]
    assert [int(scan.image[0, 0, 0]) for scan in scans] == [200, 100, 50]
    assert all(scan.dpi == pytest.approx(200) for scan in scans)


def test_unknown_resolution_must_be_given(tmp_path):
    path = tmp_path / "sans resolution.png"
    picture(200).save(path)
    with pytest.raises(ValueError, match="résolution inconnue"):
        load_pages(path)
    assert load_pages(path, dpi=250)[0].dpi == 250


def test_missing_and_unreadable_files_give_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="introuvable"):
        load_pages(tmp_path / "absent.pdf")
    broken = tmp_path / "casse.pdf"
    broken.write_bytes(b"%PDF-1.4 pas un vrai PDF")
    with pytest.raises(ValueError, match="PDF illisible"):
        load_pages(broken)
    text = tmp_path / "notes.png"
    text.write_text("pas une image", encoding="utf-8")
    with pytest.raises(ValueError, match="ni un PDF ni une image"):
        load_pages(text)

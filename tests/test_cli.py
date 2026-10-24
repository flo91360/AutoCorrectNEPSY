"""De bout en bout : PDF scanné synthétique -> cotation.csv et rapport.html."""

import csv

import cv2
import pytest
from PIL import Image

from autocorrect_nepsy.cli import main
from autocorrect_nepsy.compare import Pair, cohen_kappa, pair_scores, read_scores
from autocorrect_nepsy.scan import load_pages

from synth import page

DPI = 100


@pytest.fixture(scope="module")
def scanned_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("scan") / "page2.pdf"
    rgb = cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}), cv2.COLOR_BGR2RGB)
    # Scan « à l'envers », comme souvent sur le scanner.
    Image.fromarray(rgb).rotate(180).save(path, "PDF", resolution=DPI)
    return path


def test_pdf_resolution_is_read(scanned_pdf):
    [scan] = load_pages(scanned_pdf)
    assert scan.dpi == pytest.approx(DPI, rel=0.01)


def test_correct_command_writes_scores_and_report(scanned_pdf, tmp_path, capsys):
    out = tmp_path / "sortie"
    assert main(["corriger", str(scanned_pdf), "--pages", "2", "-o", str(out)]) == 0
    rows = list(csv.DictReader(open(out / "cotation.csv", encoding="utf-8")))
    assert [row["item"] for row in rows] == ["4", "5", "6", "7"]
    for row in rows:
        assert row["motricite_total"] == row["global_total"] == row["local_total"] == "2"
    html = (out / "rapport.html").read_text(encoding="utf-8")
    assert "Item 7" in html and "data:image/png;base64," in html
    assert "item" in capsys.readouterr().out

    assert main(["comparer", str(out / "cotation.csv"), str(out / "cotation.csv")]) == 0
    assert "Accord global : 28/28" in capsys.readouterr().out


def test_page_number_is_guessed_when_omitted(scanned_pdf, tmp_path, capsys):
    assert main(["corriger", str(scanned_pdf), "-o", str(tmp_path)]) == 0
    assert "Page 2 (items 4 à 7)" in capsys.readouterr().out


def test_bad_page_number_is_a_clean_error(scanned_pdf, tmp_path, capsys):
    assert main(["corriger", str(scanned_pdf), "--pages", "1", "-o", str(tmp_path)]) == 1
    assert "Erreur" in capsys.readouterr().err


def test_cohen_kappa():
    pairs = [Pair(1, "G", a, b) for a, b in [(1, 1), (1, 1), (0, 0), (1, 0)]]
    # accord observé 3/4, attendu 0,75*0,5 + 0,25*0,5 = 0,5
    assert cohen_kappa(pairs) == pytest.approx(0.5)
    assert cohen_kappa([]) is None


def test_read_scores_skips_empty_cells(tmp_path):
    path = tmp_path / "ergo.csv"
    path.write_text("item,general,motricite_A,local_E\n1,1,0,\n", encoding="utf-8")
    assert read_scores(path) == {1: {"G": 1, "A": 0}}
    assert len(pair_scores(read_scores(path), read_scores(path))) == 2

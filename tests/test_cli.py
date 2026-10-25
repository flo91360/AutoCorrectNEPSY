"""De bout en bout : PDF scanné synthétique -> cotation.csv et rapport.html."""

import csv

import cv2
import pytest
from PIL import Image

from autocorrect_nepsy.cli import main
from autocorrect_nepsy.compare import Pair, cohen_kappa, pair_scores, read_flags, read_scores
from autocorrect_nepsy.pipeline import page_label
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
    assert html.count('class="mesures"') == 4  # une image de mesures par item
    assert "item" in capsys.readouterr().out

    assert main(["comparer", str(out / "cotation.csv"), str(out / "cotation.csv")]) == 0
    assert "Accord global : 28/28" in capsys.readouterr().out


def test_lone_scan_needs_its_page_number(scanned_pdf, tmp_path, capsys):
    # Les pages 2 à 4 du cahier ont la même structure : un scan seul pourrait être
    # l'une ou l'autre, le numéro n'est pas deviné.
    assert main(["corriger", str(scanned_pdf), "-o", str(tmp_path)]) == 1
    assert "--pages" in capsys.readouterr().err


def test_page_numbers_are_guessed_when_certain(tmp_path, capsys):
    path = tmp_path / "pages 2 à 4.pdf"
    scan = Image.fromarray(cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}), cv2.COLOR_BGR2RGB))
    scan.save(path, "PDF", resolution=DPI, save_all=True, append_images=[scan, scan])
    assert main(["corriger", str(path), "-o", str(tmp_path / "sortie")]) == 0
    out = capsys.readouterr().out
    assert all(page_label(number) in out for number in (2, 3, 4))


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


def test_read_scores_accepts_csv_saved_by_excel(tmp_path):
    expected = {4: {"G": 1, "A": 0, "E": 1}, 5: {"G": 0}}
    plain = "item,general,motricite_A,local_E\n4,1,0,1\n5,0,,\nTotal,1,0,1\n"
    # Excel en français : point-virgule, encodage Windows (« é » de la ligne de
    # total), en-têtes retouchés à la main.
    excel = plain.replace(",", ";").replace("Total", "Total général").replace("item", "Item ")
    variants = {
        "bom.csv": plain.encode("utf-8-sig"),
        "point-virgule.csv": plain.replace(",", ";").encode("utf-8"),
        "windows.csv": excel.encode("cp1252"),
    }
    for name, content in variants.items():
        path = tmp_path / name
        path.write_bytes(content)
        assert read_scores(path) == expected, name


def test_unusable_reference_is_a_clean_error(tmp_path, capsys):
    auto = tmp_path / "auto.csv"
    auto.write_text("item,general\n4,1\n", encoding="utf-8")
    bad_header = tmp_path / "sans item.csv"
    bad_header.write_text("numero,general\n4,1\n", encoding="utf-8")
    bad_value = tmp_path / "note.csv"
    bad_value.write_text("item,general\n4,2\n", encoding="utf-8")
    for reference, message in ((bad_header, "colonne « item » absente"),
                               (bad_value, "note « 2 » illisible"),
                               (tmp_path / "absent.csv", "introuvable")):
        assert main(["comparer", str(auto), str(reference)]) == 1
        assert message in capsys.readouterr().err


def test_missing_or_broken_scan_is_a_clean_error(tmp_path, capsys):
    broken = tmp_path / "casse.pdf"
    broken.write_bytes(b"%PDF-1.4 pas un vrai PDF")
    for scan, message in ((tmp_path / "absent.pdf", "introuvable"), (broken, "PDF illisible")):
        assert main(["corriger", str(scan), "--pages", "2", "-o", str(tmp_path / "sortie")]) == 1
        assert message in capsys.readouterr().err


def test_compare_shows_flagged_disagreements(tmp_path, capsys):
    auto = tmp_path / "cotation.csv"
    auto.write_text("item,general,motricite_A,a_verifier\n4,1,1,oui\n5,1,1,\n", encoding="utf-8")
    ergo = tmp_path / "ergo.csv"
    ergo.write_text("item,general,motricite_A\n4,0,1\n5,1,0\n", encoding="utf-8")
    assert read_flags(auto) == {4} and read_flags(ergo) is None
    assert main(["comparer", str(auto), str(ergo)]) == 0
    out = capsys.readouterr().out
    assert "Désaccords dans un item signalé « à vérifier » : 1/2" in out
    assert "item  4  Général      1 / 0  (à vérifier)" in out
    assert "item  5  Motricité A  1 / 0\n" in out + "\n"

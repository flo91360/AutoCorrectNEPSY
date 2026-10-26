"""Sorties : notes retenues après vérification, proposition de l'outil, identification."""

import csv

from autocorrect_nepsy.pipeline import PageInput, correct_pages
from autocorrect_nepsy.report import (AUTOMATIC_NAME, save_results, summary_text, totals)
from autocorrect_nepsy.scan import ScannedPage

from synth import page


def reviewed_correction():
    scan = ScannedPage(page({0: 4, 1: 5, 2: 6, 3: 7}), 100, "synthétique")
    correction = correct_pages([PageInput(scan, 2)])
    correction.child, correction.session_date = "L.<M>", "20/10/2026"
    item5 = next(report for report in correction.items if report.item == 5)
    item5.review({"G": 1, "A": 0, "B": 1, "C": 1, "D": 1, "E": 1, "F": 1})
    return correction


def rows(path):
    rows = csv.DictReader(open(path, encoding="utf-8-sig"), delimiter=";")
    return {row["item"]: row for row in rows}


def test_scores_file_holds_the_ergo_corrections_and_the_automatic_one_does_not(tmp_path):
    csv_path, _ = save_results(reviewed_correction(), tmp_path)
    final, automatic = rows(csv_path), rows(tmp_path / AUTOMATIC_NAME)
    assert final["5"]["motricite_A"] == "0" and final["5"]["motricite_total"] == "1"
    assert final["5"]["verifie"] == "oui" and final["5"]["corrige"] == "A"
    assert final["4"]["verifie"] == final["4"]["corrige"] == ""
    assert automatic["5"]["motricite_A"] == "1" and automatic["5"]["motricite_total"] == "2"
    assert "verifie" not in automatic["5"]


def test_scores_file_opens_in_french_excel_and_is_read_back(tmp_path):
    from autocorrect_nepsy.compare import read_flags, read_scores

    csv_path, _ = save_results(reviewed_correction(), tmp_path)
    raw = csv_path.read_bytes()
    # Marque d'ordre des octets (accents lus en UTF-8) et point-virgule (une
    # colonne par critère dans Excel en français).
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw[3:].decode("utf-8").startswith("item;general;motricite_A;")
    assert read_scores(csv_path)[5]["A"] == 0 and read_flags(csv_path) == set()
    assert read_scores(tmp_path / AUTOMATIC_NAME)[5]["A"] == 1


def test_report_shows_child_and_corrected_scores(tmp_path):
    correction = reviewed_correction()
    _, html_path = save_results(correction, tmp_path)
    html = html_path.read_text(encoding="utf-8")
    assert "Enfant : L.&lt;M&gt; – passation du 20/10/2026" in html  # texte saisi échappé
    assert "<title>Copie de figures – L.&lt;M&gt; – correction" in html
    assert html.count("class='corr'") == 3  # A et total Motricité, puis détail du critère A
    assert "note changée par l’ergothérapeute (outil : 1)" in html
    assert "✓ vérifié, corrigé (A)" in html


def test_totals_and_summary_use_the_retained_scores():
    correction = reviewed_correction()
    assert totals(correction)["motricite"] == 7  # 4 items à 2 points, moins la correction
    text = summary_text(correction)
    assert text.startswith("Enfant : L.<M> – passation du 20/10/2026\n")

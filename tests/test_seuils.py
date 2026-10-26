"""Seuils du manuel séparés des réglages de l'outil, et échafaudage commun des items."""

import pytest

from autocorrect_nepsy.cli import format_thresholds, main
from autocorrect_nepsy.criteria import SUPPORTED_ITEMS, all_manual_thresholds, score_item
from autocorrect_nepsy.criteria.base import Scoring, fmt_limit, manual_thresholds
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PX_PER_MM, canvas, draw_model


def test_threshold_is_a_plain_number_with_its_text():
    threshold = manual_thresholds("essai")
    band = threshold(4.0, "A", "largeur de la barre grisée")
    count = threshold(3, "A", "interruptions, au plus", "nombre")
    assert band == 4.0 and band + 1 == 5.0 and f"{band:.1f}" == "4.0"
    assert list(range(count)) == [0, 1, 2]
    assert (band.text, count.text, band.codes, band.module) == ("4 mm", "3", "A", "essai")
    for value, unit, text in ((1.5, "mm", "1,5 mm"), (30.0, "deg", "30°"), (1.3, "ratio", "1,3:1"),
                              (2.0, "ratio", "2:1"), (1 / 3, "part", "33,3 %"), (0.8, "part", "80 %")):
        assert fmt_limit(value, unit) == text
    with pytest.raises(ValueError):
        threshold(1.0, "Z", "critère inconnu")
    with pytest.raises(ValueError):
        threshold(1.0, "G", "unité inconnue", "cm")


def test_every_item_lists_its_manual_thresholds_for_its_own_criteria():
    entries = all_manual_thresholds()
    assert {item for e in entries for item in e.items} == set(SUPPORTED_ITEMS)
    for item in SUPPORTED_ITEMS:
        drawing = extract_drawing(ink_mask(draw_model(item, canvas())), PX_PER_MM)
        criteria = set(score_item(item, drawing).criteria)
        mine = [e.threshold for e in entries if item in e.items]
        assert len(mine) >= 2, item
        # Chaque seuil sert un critère que l'item cote vraiment.
        assert all(set(t.codes) <= criteria for t in mine), item
        assert all(t.description and t.description == t.description.strip() for t in mine)


def test_seuils_command_lists_the_thresholds_of_an_item(capsys):
    assert main(["seuils", "--item", "4"]) == 0
    out = capsys.readouterr().out
    assert "Item 4" in out and "Item 5" not in out
    assert "  F        1,3:1  rapport du plus long au plus court côté, au plus" in out
    assert len(format_thresholds().splitlines()) > len(all_manual_thresholds())


def test_scoring_handles_empty_drawings_and_unrecognized_figures():
    empty = Scoring(4, "GABCDEF").empty()
    assert list(empty.criteria) == list("GABCDEF") and empty.to_review
    assert all(c.score == 0 for c in empty.criteria.values())

    scoring = Scoring(4, "GAB")
    scoring["A"].add(True, "ligne droite")
    scoring.not_recognized("GB", "carré non reconnu")
    result = scoring.result()
    assert {code: c.score for code, c in result.criteria.items()} == {"G": 0, "A": 1, "B": 0}
    assert result.to_review and "carré non reconnu" in result.notes[0]

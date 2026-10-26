"""Doutes qui touchent toute une page : numéro de page deviné, échelle du scan."""

import pytest

from autocorrect_nepsy.pipeline import PageInput, correct_pages
from autocorrect_nepsy.scan import ScannedPage

from synth import page

DPI = 100


def correct(dpi: float = DPI, guessed: bool = False):
    scan = ScannedPage(page({0: 4, 1: 5, 2: 6, 3: 7}), dpi, "synthétique")
    return correct_pages([PageInput(scan, 2, guessed=guessed)])


def test_sure_page_at_the_right_scale_raises_no_doubt():
    correction = correct()
    assert not correction.warnings
    assert not any(report.result.to_review for report in correction.items)


def test_guessed_page_flags_every_item():
    correction = correct(guessed=True)
    assert len(correction.warnings) == 1 and "à confirmer" in correction.warnings[0]
    assert all(any("page du cahier devinée" in note for note in report.result.notes)
               for report in correction.items)


def test_doubtful_scale_flags_every_item():
    # Image déclarée à 72 dpi au lieu de 100 : toutes les mesures en mm sont fausses.
    correction = correct(dpi=72)
    assert any("échelle douteuse" in warning for warning in correction.warnings)
    assert all(any("échelle douteuse" in note for note in report.result.notes)
               for report in correction.items)


def test_review_keeps_only_the_scores_the_ergo_changed():
    report = next(r for r in correct(guessed=True).items if r.item == 5)
    assert report.to_review and report.score("A") == 1
    report.review({"G": 1, "A": 0, "B": 1})
    assert report.corrections == {"A": 0} and report.checked
    assert report.score("A") == 0 and report.result.score("A") == 1  # proposition gardée
    assert report.total("A", "B") == 1 and report.total("A", "Z") is None  # Z : absent
    assert not report.to_review  # vérifié : plus à vérifier
    report.review({"A": 1})  # retour à la note de l'outil : plus de correction
    assert report.corrections == {} and report.score("A") == 1


def test_review_rejects_unknown_criteria_and_scores():
    report = correct().items[0]
    for scores in ({"Z": 1}, {"A": 2}):
        with pytest.raises(ValueError):
            report.review(scores)
    assert not report.checked

"""Doutes qui touchent toute une page : numéro de page deviné, échelle du scan."""

import pytest

from autocorrect_nepsy.pipeline import PageInput, correct_pages
from autocorrect_nepsy.scan import ScannedPage

from synth import page

DPI = 100


def correct(dpi: float = DPI, guessed: bool = False, drawn_dpi: float = DPI):
    """Page 2 dessinée à ``drawn_dpi``, déclarée à ``dpi``."""
    scan = ScannedPage(page({0: 4, 1: 5, 2: 6, 3: 7}, ppm=drawn_dpi / 25.4), dpi, "synthétique")
    return correct_pages([PageInput(scan, 2, guessed=guessed)])


def test_sure_page_at_the_right_scale_raises_no_doubt():
    correction = correct(dpi=200, drawn_dpi=200)
    assert not correction.warnings
    assert not any(report.result.to_review for report in correction.items)


def test_low_resolution_is_a_warning_not_a_doubt_on_each_item():
    correction = correct()  # 100 dpi, sous les 200 dpi demandés
    assert correction.warnings == ["synthétique : résolution de 100 dpi, sous les 200 dpi "
                                   "demandés : mesures moins précises, scanner à 200 dpi au moins "
                                   "(300 conseillés)"]
    assert not any(report.result.to_review for report in correction.items)


def test_guessed_page_flags_every_item():
    correction = correct(guessed=True)
    assert len([w for w in correction.warnings if "à confirmer" in w]) == 1
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

"""Doutes qui touchent toute une page : numéro de page deviné, échelle du scan."""

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

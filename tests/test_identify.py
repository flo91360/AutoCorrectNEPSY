"""Numéro de page lu sur les modèles imprimés (pages synthétiques)."""

import pytest

from autocorrect_nepsy.identify import better_page, model_score, resolve
from autocorrect_nepsy.layout import prepare_page
from autocorrect_nepsy.scan import ScannedPage

from synth import page

DPI = 100
CONTENT = {1: ({0: 1, 1: 2, 2: 3}, "page1"), 2: ({0: 4, 1: 5, 2: 6, 3: 7}, 4),
           3: ({0: 8, 1: 9, 2: 10, 3: 11}, 4), 4: ({0: 12, 1: 13, 2: 14, 3: 15}, 4),
           5: ({0: 16, 1: 17, 2: 18}, 3), 6: ({0: 19, 1: 20, 2: 21}, 3)}


def scan(number, models=True):
    items, layout = CONTENT[number]
    return prepare_page(ScannedPage(page(items, layout=layout, models=models), DPI, f"p{number}"))


@pytest.fixture(scope="module")
def scans():
    return {number: scan(number) for number in (1, 2, 3, 4, 5)}


def test_printed_models_match_their_own_page(scans):
    assert model_score(scans[3], 3) > 0.9
    assert model_score(scans[3], 2) < 0.4 and model_score(scans[3], 4) < 0.4


def test_lone_scans_and_missing_pages_are_read_on_their_models(scans):
    assert resolve([scans[3]]) == ([3], set())
    # Page 2 absente : les scans des pages 3 et 4 ne sont plus pris pour 2 et 3.
    assert resolve([scans[1], scans[3], scans[4], scans[5]]) == ([1, 3, 4, 5], set())


def test_scans_out_of_order_are_read_on_their_models(scans):
    assert resolve([scans[4], scans[2]]) == ([4, 2], set())


def test_unreadable_models_leave_the_page_uncertain():
    blank = scan(3, models=False)
    numbers, unsure = resolve([blank])
    assert unsure == {0}
    assert better_page(blank, 2) is None


def test_manual_choice_is_kept_but_contradicted_by_the_models(scans):
    assert resolve([scans[3]], fixed={0: 2}) == ([2], set())
    assert better_page(scans[3], 2) == 3 and better_page(scans[3], 3) is None

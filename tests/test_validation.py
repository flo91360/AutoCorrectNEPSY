"""Validation sur un corpus local, ici synthétique (aucune donnée réelle d'enfant)."""

import cv2
import pytest
from PIL import Image

from autocorrect_nepsy import validation
from autocorrect_nepsy.cli import main

from synth import page

DPI = 100
HEADER = "item,general,motricite_A,motricite_B,global_C,global_D,local_E,local_F\n"
FULL = ["4,1,1,1,1,1,1,1\n", "5,1,1,1,1,1,1,1\n", "6,1,1,1,1,1,1,1\n", "7,1,1,1,1,1,1,1\n"]


def protocol(corpus, name, rows, pages="2"):
    folder = corpus / name
    folder.mkdir()
    rgb = cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}), cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).save(folder / "scan.pdf", "PDF", resolution=DPI)
    (folder / validation.REFERENCE_NAME).write_text(HEADER + "".join(rows), encoding="utf-8")
    if pages:
        (folder / validation.PAGES_NAME).write_text(pages, encoding="utf-8")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    protocol(root, "P001", FULL)
    # L'ergothérapeute retire deux points à l'item 5 : deux désaccords, non signalés.
    protocol(root, "P002", [FULL[0], "5,1,0,1,1,0,1,1\n", FULL[2], FULL[3]])
    # Scan seul sans pages.txt : numéro de page incertain, protocole écarté.
    protocol(root, "P003", FULL, pages=None)
    (root / "notes").mkdir()  # dossier sans cotation de l'ergothérapeute : ignoré
    return root


@pytest.fixture(scope="module")
def corrected(corpus):
    return validation.run(corpus)


def test_corpus_is_corrected_protocol_by_protocol(corrected):
    protocols, errors = corrected
    assert [p.name for p in protocols] == ["P001", "P002"]
    assert len(errors) == 1 and errors[0].startswith("P003") and "pages.txt" in errors[0]


def test_summary_figures(corrected):
    summary = validation.summarize(corrected[0])
    assert summary["protocoles"] == 2 and summary["items"] == 8
    assert summary["ensemble"]["criteres"] == 56
    assert summary["ensemble"]["accord"] == pytest.approx(54 / 56)
    assert summary["par_critere"]["A"]["accord"] == pytest.approx(7 / 8)
    assert summary["par_item"][5]["accord"] == pytest.approx(12 / 14)
    motricite = summary["totaux"]["Motricité"]
    assert motricite["ecart_moyen"] == pytest.approx(0.5)
    assert motricite["dans_la_tolerance"] == 1.0
    assert summary["a_verifier"] == {"items_signales": 0.0, "desaccords": 2,
                                     "desaccords_signales": 0}
    reached = [goal["atteint"] for goal in summary["objectifs"]]
    # Kappa nul (l'outil donne toujours 1), items et totaux dans les objectifs,
    # désaccords non signalés.
    assert reached == [False, True, False, True]
    text = validation.format_summary(summary)
    assert "Motricité" in text and "NON ATTEINT" in text and "P002" not in text


def test_versions_are_compared_on_the_same_corpus(corrected, tmp_path):
    protocols = corrected[0]
    summary = validation.summarize(protocols)
    validation.save(summary, tmp_path / "v1.json")
    previous = validation.load(tmp_path / "v1.json")
    # Version précédente fictive : elle donnait 0 en Motricité A à l'item 5 de P002,
    # comme l'ergothérapeute.
    previous["version"] = "0.1.0"
    previous["cotations"]["P002"]["5"]["A"] = 0
    text = validation.compare_versions(summary, previous, protocols)
    assert text == ("Depuis la version 0.1.0 : 1 critère(s) changent, dont 0 se rapprochent de "
                    "l'ergothérapeute et 1 s'en éloignent.")


def test_validate_command(corpus, tmp_path, capsys):
    out = tmp_path / "resultats.json"
    assert main(["valider", str(corpus), "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Objectifs" in text and "P003 : " in text and out.exists()
    assert main(["valider", str(corpus), "--precedent", str(out)]) == 0
    assert "0 critère(s) changent" in capsys.readouterr().out
    assert main(["valider", str(tmp_path / "absent")]) == 1

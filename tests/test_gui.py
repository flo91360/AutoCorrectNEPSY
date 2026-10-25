"""Interface graphique pilotée par le code (nécessite un écran, réel ou virtuel)."""

import os
import time

import cv2
import pytest
from PIL import Image

from synth import page

# En intégration continue, l'interface doit être testée : sans tkinter ou sans
# écran, les tests échouent au lieu d'être ignorés en silence.
REQUIRED = os.environ.get("AUTOCORRECT_TESTS_INTERFACE") == "obligatoires"

try:
    import tkinter as tk
except ImportError:
    if REQUIRED:
        raise
    pytest.skip("tkinter absent", allow_module_level=True)


def new_root(attempts: int = 3) -> "tk.Tk":
    """Fenêtre Tk. Sous Windows, la création échoue parfois au hasard après
    d'autres fenêtres (« Can't find a usable init.tcl… No error ») : on réessaie
    avant de conclure qu'il n'y a pas d'écran."""
    for attempt in range(attempts):
        try:
            return tk.Tk()
        except tk.TclError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)


@pytest.fixture
def app():
    from autocorrect_nepsy.gui import App

    try:
        root = new_root()
    except tk.TclError:
        if REQUIRED:
            raise
        pytest.skip("pas d'écran disponible")
    root.withdraw()
    yield App(root)
    root.destroy()


def wait(app, condition, timeout=60):
    end = time.time() + timeout
    while not condition():
        app.root.update()
        time.sleep(0.02)
        assert time.time() < end, "délai dépassé"


@pytest.fixture
def scan(tmp_path):
    path = tmp_path / "scan page 2.pdf"
    rgb = cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}), cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).rotate(90, expand=True).save(path, "PDF", resolution=100)
    return path


def test_scan_to_scores(app, scan):
    app.add_paths([scan])
    wait(app, lambda: app.rows and not app.busy)
    [row] = app.rows
    assert row.number() == 2
    assert row.dpi() == pytest.approx(100)
    assert app._row_problem(row) is None
    assert str(app.run_button.cget("state")) == "normal"

    app.run_correction()
    wait(app, lambda: app.correction is not None and not app.busy)
    items = [app.tree.item(iid)["values"] for iid in app.tree.get_children()]
    assert [values[0] for values in items] == [4, 5, 6, 7, "Total"]
    assert items[-1][4] == 8  # total Motricité : 4 items à 2 points
    assert (app.output / "cotation.csv").exists()
    assert (app.output / "rapport.html").exists()
    assert app.output.parent == scan.parent


def test_report_and_item_open_in_the_browser(app, scan, tmp_path, monkeypatch):
    from autocorrect_nepsy import gui

    opened = []
    monkeypatch.setattr(gui, "open_path", opened.append)
    monkeypatch.setattr(gui.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))
    app.add_paths([scan])
    wait(app, lambda: app.rows and not app.busy)
    app.run_correction()
    wait(app, lambda: app.correction is not None and not app.busy)
    report = app.output / "rapport.html"

    app.open_report()
    assert opened[-1] == report

    # Double-clic sur l'item 5 : page relais qui saute à l'item dans le rapport.
    app.tree.selection_set("5")
    app.open_item_report()
    relay = opened[-1]
    assert relay.name == "item-5.html"
    assert report.resolve().as_uri() + "#item5" in relay.read_text(encoding="utf-8")

    app.tree.selection_set("total")
    app.open_item_report()
    assert opened[-1] == relay  # la ligne des totaux n'ouvre rien

    app.open_folder()
    assert opened[-1] == app.output


def test_opening_failure_is_reported(app, tmp_path, monkeypatch):
    from autocorrect_nepsy import gui

    def fail(path):
        raise OSError("aucune application associée")

    errors = []
    monkeypatch.setattr(gui, "open_path", fail)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, text: errors.append(text))
    app.output = tmp_path
    app.open_report()
    assert errors and str(tmp_path / "rapport.html") in errors[0]


def test_windows_gets_a_plain_path_not_an_url(tmp_path, monkeypatch):
    import os
    import sys

    from autocorrect_nepsy.gui import open_path

    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", calls.append, raising=False)
    report = tmp_path / "Correction NEPSY 2026-10-25 08h15" / "rapport.html"
    open_path(report)
    assert calls == [report]


def test_wrong_page_and_resolution_are_flagged(app, scan):
    from autocorrect_nepsy.pipeline import page_label

    app.add_paths([scan])
    wait(app, lambda: app.rows and not app.busy)
    [row] = app.rows
    row.page_var.set(page_label(5))
    assert "page 2, 3, 4" in app._row_problem(row)
    row.page_var.set(page_label(3))
    assert app._row_problem(row) is None
    row.dpi_var.set("abc")
    assert "résolution" in app._row_problem(row)
    assert str(app.run_button.cget("state")) == "disabled"


def test_lone_scan_page_is_read_on_its_printed_models(app, scan):
    app.add_paths([scan])
    wait(app, lambda: app.rows and not app.busy)
    [row] = app.rows
    assert row.number() == 2 and not row.guessed_page


def test_guessed_page_of_a_lone_scan_is_to_confirm(app, tmp_path):
    from autocorrect_nepsy.pipeline import page_label

    # Un scan seul à quatre items, sans modèles lisibles : page 2, 3 ou 4 du cahier.
    scan = tmp_path / "sans modeles.pdf"
    rgb = cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}, models=False), cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).rotate(90, expand=True).save(scan, "PDF", resolution=100)
    app.add_paths([scan])
    wait(app, lambda: app.rows and not app.busy)
    [row] = app.rows
    assert row.guessed_page and "à confirmer" in str(row.status.cget("text"))
    assert app._row_problem(row) is None  # signalée, mais pas bloquante

    app.run_correction()
    wait(app, lambda: app.correction is not None and not app.busy)
    assert all(report.result.to_review for report in app.correction.items)

    row.page_var.set(page_label(2))
    app._page_chosen(row)
    assert not row.guessed_page and "Prête" in str(row.status.cget("text"))


def test_results_never_overwrite_a_previous_correction(tmp_path):
    from autocorrect_nepsy.gui import results_folder

    # Deux enfants corrigés dans la même minute, scans dans le même dossier.
    first = results_folder(tmp_path / "enfant A.pdf")
    first.mkdir()
    second = results_folder(tmp_path / "enfant B.pdf")
    assert second != first and second.parent == tmp_path and not second.exists()


def test_icon_is_drawn():
    from autocorrect_nepsy.gui import app_icon

    assert app_icon(32).size == (32, 32)

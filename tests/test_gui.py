"""Interface graphique pilotée par le code (nécessite un écran, réel ou virtuel)."""

import time

import cv2
import pytest
from PIL import Image

from synth import page

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app():
    from autocorrect_nepsy.gui import App

    try:
        root = tk.Tk()
    except tk.TclError:
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


def test_icon_is_drawn():
    from autocorrect_nepsy.gui import app_icon

    assert app_icon(32).size == (32, 32)

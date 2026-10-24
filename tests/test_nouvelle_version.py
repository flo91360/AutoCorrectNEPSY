"""Préparation de la version d'une PR (packaging/nouvelle_version.py)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "packaging" / "nouvelle_version.py"
spec = importlib.util.spec_from_file_location("nouvelle_version", SCRIPT)
nv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nv)


@pytest.mark.parametrize(
    "niveau, attendu",
    [("correctif", "0.2.1"), ("mineure", "0.3.0"), ("majeure", "1.0.0")],
)
def test_incrementer(niveau, attendu):
    assert nv.incrementer("0.2.0", niveau) == attendu


def test_publier(tmp_path):
    (tmp_path / "autocorrect_nepsy").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.2.0"\n', encoding="utf-8"
    )
    (tmp_path / "autocorrect_nepsy" / "__init__.py").write_text(
        '"""x"""\n\n__version__ = "0.2.0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Journal\n\n{nv.REPERE}\n\n## [0.2.0] - 2026-10-24\n\n- Ancien\n", encoding="utf-8"
    )

    version = nv.publier(tmp_path, "mineure", ["Item 9", "Item 10"], "2026-11-01")

    assert version == "0.3.0"
    assert 'version = "0.3.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.3.0"' in (
        tmp_path / "autocorrect_nepsy" / "__init__.py"
    ).read_text(encoding="utf-8")
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.index("## [0.3.0] - 2026-11-01") < changelog.index("## [0.2.0]")
    assert "- Item 9\n- Item 10\n" in changelog


def test_projet_compatible():
    """Le vrai dépôt contient ce que le script attend."""
    racine = SCRIPT.parent.parent
    assert nv.REPERE in (racine / "CHANGELOG.md").read_text(encoding="utf-8")
    assert nv.VERSION_PYPROJECT.search((racine / "pyproject.toml").read_text(encoding="utf-8"))
    assert nv.VERSION_PAQUET.search(
        (racine / "autocorrect_nepsy" / "__init__.py").read_text(encoding="utf-8")
    )

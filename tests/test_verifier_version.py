"""Contrôle de version du job « Version » (packaging/verifier_version.py)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "packaging" / "verifier_version.py"
spec = importlib.util.spec_from_file_location("verifier_version", SCRIPT)
vv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vv)

PYPROJECT = '[project]\nname = "x"\nversion = "{}"\n\n[tool.autre]\nversion = "9.9.9"\n'


def projet(tmp_path, version="0.3.0", paquet=None, changelog=None):
    (tmp_path / "autocorrect_nepsy").mkdir(exist_ok=True)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(version), encoding="utf-8")
    (tmp_path / "autocorrect_nepsy" / "__init__.py").write_text(
        f'__version__ = "{paquet or version}"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        changelog
        if changelog is not None
        else f"# Journal\n\n## [{version}] - 2026-11-01\n\n- Item 9\n\n## [0.2.0] - 2026-10-24\n\n- Ancien\n",
        encoding="utf-8",
    )
    return tmp_path


def test_version_coherente(tmp_path):
    assert vv.erreurs(projet(tmp_path), PYPROJECT.format("0.2.9")) == []
    assert vv.version_pyproject(PYPROJECT.format("1.2.3")) == "1.2.3"


def test_version_non_augmentee(tmp_path):
    (probleme,) = vv.erreurs(projet(tmp_path), PYPROJECT.format("0.3.0"))
    assert "chaque PR augmente la version" in probleme
    assert vv.erreurs(projet(tmp_path), PYPROJECT.format("0.10.0"))


def test_paquet_et_changelog_suivent_la_version(tmp_path):
    problemes = vv.erreurs(projet(tmp_path, paquet="0.2.0", changelog="# Journal\n\n## [0.2.0] - 2026-10-24\n\n- x\n"))
    assert len(problemes) == 2
    assert any("__version__" in p for p in problemes)
    assert any("CHANGELOG.md" in p for p in problemes)


def test_notes_de_la_version(tmp_path):
    texte = (projet(tmp_path) / "CHANGELOG.md").read_text(encoding="utf-8")
    assert vv.section(texte, "0.3.0") == "- Item 9"
    assert vv.section(texte, "0.2.0") == "- Ancien"


def test_depot_coherent():
    """Le dépôt lui-même passe le contrôle de la CI."""
    assert vv.erreurs(SCRIPT.parent.parent) == []


def test_notes_en_utf8(capfd, monkeypatch):
    """Les notes de la Release gardent leurs accents, quel que soit l'encodage de la console."""
    monkeypatch.setattr(vv.sys, "stdout", open(1, "w", encoding="cp1252", closefd=False))
    vv.main(["--notes"])
    vv.sys.stdout.flush()
    sortie = capfd.readouterr().out
    attendu = vv.section((vv.RACINE / "CHANGELOG.md").read_text(encoding="utf-8"), vv.version_pyproject((vv.RACINE / "pyproject.toml").read_text(encoding="utf-8")))
    assert sortie.strip() == attendu

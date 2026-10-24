"""Vérifie la version livrée, comme le job « Version » de la CI.

- même version dans pyproject.toml et autocorrect_nepsy/__init__.py ;
- section « ## [<version>] - <date> » renseignée dans CHANGELOG.md ;
- avec --base : version supérieure à celle du pyproject.toml de main.

    python packaging/verifier_version.py [--base pyproject-de-main.toml]
    python packaging/verifier_version.py --afficher   # affiche la version
    python packaging/verifier_version.py --notes      # section du CHANGELOG
"""

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
VERSION_PYPROJECT = re.compile(r'^version = "(\d+\.\d+\.\d+)"$', re.M)
VERSION_PAQUET = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"$', re.M)


def version_pyproject(texte: str) -> str | None:
    """Version de la table [project] (et non d'une autre table)."""
    debut = re.search(r"^\[project\]\s*$", texte, re.M)
    if not debut:
        return None
    suite = texte[debut.end():]
    fin = re.search(r"^\[", suite, re.M)
    trouve = VERSION_PYPROJECT.search(suite[: fin.start()] if fin else suite)
    return trouve.group(1) if trouve else None


def section(changelog: str, version: str) -> str | None:
    """Lignes de la section de cette version, sans son titre."""
    trouve = re.search(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}[ \t]*\n(.*?)(?=^## |\Z)",
        changelog,
        re.M | re.S,
    )
    return trouve.group(1).strip() if trouve else None


def nombres(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))


def erreurs(racine: Path, base: str | None = None) -> list[str]:
    problemes = []
    version = version_pyproject((racine / "pyproject.toml").read_text(encoding="utf-8"))
    if not version:
        return ["pyproject.toml : version de [project] introuvable (format x.y.z)"]
    paquet = VERSION_PAQUET.search(
        (racine / "autocorrect_nepsy" / "__init__.py").read_text(encoding="utf-8")
    )
    if not paquet or paquet.group(1) != version:
        problemes.append(f"autocorrect_nepsy/__init__.py : __version__ différent de {version}")
    notes = section((racine / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if not notes or not re.search(r"^- \S", notes, re.M):
        problemes.append(f"CHANGELOG.md : pas de section « ## [{version}] - <date> » renseignée")
    if base is not None:
        avant = version_pyproject(base)
        if avant and nombres(version) <= nombres(avant):
            problemes.append(
                f"version {version} ≤ {avant} (main) : chaque PR augmente la version"
            )
    return problemes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", type=Path, help="pyproject.toml de la branche cible")
    p.add_argument("--afficher", action="store_true", help="affiche la version")
    p.add_argument("--notes", action="store_true", help="affiche la section du CHANGELOG")
    a = p.parse_args(argv)
    # Sous Windows, la console de la CI est en cp1252 : les notes de la Release
    # perdraient leurs accents.
    sys.stdout.reconfigure(encoding="utf-8")
    version = version_pyproject((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    if a.afficher:
        print(version)
        return 0
    if a.notes:
        print(section((RACINE / "CHANGELOG.md").read_text(encoding="utf-8"), version) or "")
        return 0
    base = a.base.read_text(encoding="utf-8") if a.base else None
    problemes = erreurs(RACINE, base)
    for probleme in problemes:
        print(f"::error::{probleme}")
    if not problemes:
        print(f"Version {version} : pyproject.toml, __version__ et CHANGELOG.md cohérents.")
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(main())

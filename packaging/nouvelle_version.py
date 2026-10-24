"""Prépare la version d'une PR : incrémente la version et ajoute sa section au CHANGELOG.

Chaque PR livre une nouvelle version, vérifiée par le job « Version » de la CI.
Les cartes PlaniFiKateur le font d'elles-mêmes (worker) ; pour une PR ouverte
directement, lancer avant de committer :

    python packaging/nouvelle_version.py --niveau correctif \
        --resume "Corriger l'item 3" [--resume "Autre modification"]

Affiche la nouvelle version. Niveau : correctif (0.2.0 -> 0.2.1, par défaut),
mineure (nouvelle fonctionnalité, 0.3.0) ou majeure (changement incompatible).
"""

import argparse
import datetime
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NIVEAUX = ("correctif", "mineure", "majeure")
# Les nouvelles versions sont insérées juste sous cette ligne du CHANGELOG.
REPERE = "<!-- nouvelles versions -->"

VERSION_PYPROJECT = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.M)
VERSION_PAQUET = re.compile(r'^__version__ = "\d+\.\d+\.\d+"$', re.M)


def incrementer(version: str, niveau: str) -> str:
    majeure, mineure, correctif = (int(n) for n in version.split("."))
    if niveau == "majeure":
        return f"{majeure + 1}.0.0"
    if niveau == "mineure":
        return f"{majeure}.{mineure + 1}.0"
    return f"{majeure}.{mineure}.{correctif + 1}"


def entree_changelog(version: str, date: str, resumes: list[str]) -> str:
    lignes = "\n".join(f"- {resume.strip()}" for resume in resumes)
    return f"## [{version}] - {date}\n\n{lignes}"


def publier(racine: Path, niveau: str, resumes: list[str], date: str) -> str:
    pyproject = racine / "pyproject.toml"
    texte = pyproject.read_text(encoding="utf-8")
    actuelle = ".".join(VERSION_PYPROJECT.search(texte).groups())
    nouvelle = incrementer(actuelle, niveau)
    pyproject.write_text(
        VERSION_PYPROJECT.sub(f'version = "{nouvelle}"', texte, count=1), encoding="utf-8"
    )

    paquet = racine / "autocorrect_nepsy" / "__init__.py"
    paquet.write_text(
        VERSION_PAQUET.sub(f'__version__ = "{nouvelle}"', paquet.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    changelog = racine / "CHANGELOG.md"
    texte = changelog.read_text(encoding="utf-8")
    if REPERE not in texte:
        raise SystemExit(f"Repère {REPERE!r} absent de CHANGELOG.md")
    entree = entree_changelog(nouvelle, date, resumes)
    changelog.write_text(texte.replace(REPERE, f"{REPERE}\n\n{entree}", 1), encoding="utf-8")
    return nouvelle


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--niveau", choices=NIVEAUX, default="correctif")
    p.add_argument("--resume", action="append", required=True, help="ligne du CHANGELOG")
    p.add_argument("--date", default=datetime.date.today().isoformat())
    a = p.parse_args(argv)
    print(publier(RACINE, a.niveau, a.resume, a.date))


if __name__ == "__main__":
    main()

"""Incrémente la version et ajoute la PR fusionnée au CHANGELOG.

Appelé par le workflow « Version et changelog » à chaque PR fusionnée dans
main ; affiche la nouvelle version (sans le « v »).

    python packaging/nouvelle_version.py --niveau correctif \
        --titre "Corriger l'item 3" --numero 12 --url https://github.com/.../pull/12
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


def niveau_depuis_etiquettes(etiquettes: list[str]) -> str:
    """« version: majeure » ou « version: mineure » sur la PR, sinon correctif."""
    noms = {e.strip().lower() for e in etiquettes}
    for niveau in ("majeure", "mineure"):
        if f"version: {niveau}" in noms:
            return niveau
    return "correctif"


def entree_changelog(version: str, date: str, titre: str, numero: int, url: str) -> str:
    return f"## [{version}] - {date}\n\n- {titre} ([#{numero}]({url}))"


def publier(racine: Path, niveau: str, titre: str, numero: int, url: str, date: str) -> str:
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
    entree = entree_changelog(nouvelle, date, titre, numero, url)
    changelog.write_text(texte.replace(REPERE, f"{REPERE}\n\n{entree}", 1), encoding="utf-8")
    return nouvelle


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--niveau", choices=NIVEAUX)
    p.add_argument("--etiquettes", default="", help="étiquettes de la PR, séparées par des virgules")
    p.add_argument("--titre", required=True)
    p.add_argument("--numero", type=int, required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    a = p.parse_args(argv)
    niveau = a.niveau or niveau_depuis_etiquettes(a.etiquettes.split(","))
    print(publier(RACINE, niveau, a.titre, a.numero, a.url, a.date))


if __name__ == "__main__":
    main()

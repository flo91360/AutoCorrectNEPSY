# AutoCorrectNEPSY

Correction automatique du subtest Copie de figures de la NEPSY-II (paquet
Python `autocorrect_nepsy/`, interface Tkinter, exécutable Windows). Textes
visibles, commentaires, messages de commit et réponses en français.

## Données

Ce dépôt est **public** : jamais de scan, de cotation d'enfant, de page du
manuel ou du cahier de réponses. Ne pas affaiblir le `.gitignore` (PDF, images,
CSV). Les tests n'utilisent que des dessins synthétiques (`tests/synth.py`).

## CI et livraison

`.github/workflows/tests.yml` (« Tests et exécutable Windows ») tourne à chaque
PR vers `main` et à chaque push sur `main` :

- job `Version` : même version dans `pyproject.toml` et
  `autocorrect_nepsy/__init__.py`, section `## [<version>] - <date>` dans
  `CHANGELOG.md` et, sur une PR, version supérieure à celle de `main`
  (`packaging/verifier_version.py`) ;
- jobs `Tests Python 3.10 (Linux)`, `Tests Python 3.12 (Linux)` (sous
  `xvfb-run`) et `Tests Python 3.12 (Windows)` : `pytest` ;
- job `Exécutable Windows` (après les autres) : construit et teste
  `AutoCorrectNEPSY.exe`. Une nouvelle version arrivée sur `main` publie la
  Release `v<version>` avec l'exécutable ; une version déjà publiée n'est pas
  remplacée. PlaniFiKateur exige tous ces jobs avant de fusionner et archive
  les Releases dans Google Drive.

**Chaque PR livre une nouvelle version** : lancer
`python packaging/nouvelle_version.py --niveau correctif --resume "…"`
(`mineure` pour une fonctionnalité, `majeure` pour un changement incompatible)
avant de committer. Si `main` a avancé entre-temps, reprendre la version
suivante. Lors d'une exécution par le worker PlaniFiKateur, le worker augmente
lui-même la version et complète le CHANGELOG : ne pas les modifier.

Ne pas committer `build/`, `dist/`, `*.egg-info/` ni `.venv/`.

## Fusion des PR

Quand la CI est verte sur une PR (tous les jobs, dont `Exécutable Windows`, sur
le dernier commit) et qu'elle n'a pas de conflit, Claude la fusionne (squash)
dans `main` automatiquement, sans demander l'accord de l'utilisateur.

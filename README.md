# AutoCorrectNEPSY

Correction automatique du subtest **Copie de figures** de la NEPSY-II, à partir
des pages scannées du cahier de réponses. **Prototype** : le logiciel propose une
cotation que l'ergothérapeute valide.

## État

- Items **1 à 21** (tout le subtest) pris en charge, avec tous leurs critères :
  Général, Motricité A/B, Global C/D, Local E/F (pas de Local pour les items 1
  à 3).
- Chaque critère est accompagné des mesures qui le justifient (longueurs en mm,
  angles, rapports).
- Les items douteux sont signalés **« à vérifier »** : mesure proche d'un seuil,
  trait repassé à côté du premier tracé, zone vide, figure du modèle non
  retrouvée dans le dessin (l'outil a pu mal le lire), page du cahier devinée
  sans certitude, échelle du scan douteuse.
- Premier essai sur un protocole réel : 124 critères sur 141 identiques à la
  cotation de l'ergothérapeute (kappa de Cohen 0,75).

## Pour l'ergothérapeute : le logiciel Windows

1. Téléchargez **[AutoCorrectNEPSY.exe](https://github.com/flo91360/AutoCorrectNEPSY/releases/latest/download/AutoCorrectNEPSY.exe)**
   (dernière version, aussi disponible sur la page
   [Releases](https://github.com/flo91360/AutoCorrectNEPSY/releases)).
2. Double-cliquez dessus : aucune installation n'est nécessaire.
   Au premier lancement, si Windows affiche « Windows a protégé votre
   ordinateur », cliquez sur **Informations complémentaires**, puis
   **Exécuter quand même**.
3. Dans la fenêtre :
   - **Ajouter des scans…** : choisissez les pages scannées du cahier ;
   - vérifiez pour chaque scan la **page du cahier** proposée (déduite de la
     structure de la page et de ses modèles imprimés ; « à confirmer » quand
     elle reste incertaine : choisissez-la alors dans la liste) et sa
     **résolution** en dpi (lue dans le fichier, modifiable) ;
   - si vous le souhaitez, saisissez le **pseudonyme ou les initiales** de
     l'enfant et la **date de passation** : ils sont repris dans le rapport,
     et le pseudonyme dans le nom du dossier des résultats ;
   - cliquez sur **Lancer la correction automatique**.
4. Les notes s'affichent, les items à vérifier sont surlignés en orange. Le
   rapport détaillé et le tableau des notes sont enregistrés dans un dossier
   « Correction NEPSY » à côté des scans. Double-cliquez sur un item pour voir
   son dessin annoté.
5. Sélectionnez un item et cliquez sur **Vérifier / corriger l'item
   sélectionné…** : la fenêtre montre le dessin de l'enfant et la note de
   l'outil pour chaque critère. Confirmez ou changez chaque note, puis
   **Valider ces notes**. L'item passe en vert (« vérifié »), une note changée
   est marquée « ✎ », les totaux suivent et les résultats sont réenregistrés.

Tout est calculé sur l'ordinateur : aucun scan n'est envoyé sur Internet.

## Installation pour développer

```bash
python -m pip install -e ".[test]"
```

Lancer la fenêtre : `python -m autocorrect_nepsy` (ou `autocorrect-nepsy-gui`).

## Ligne de commande

### Scanner les pages

- Une page du cahier par page de PDF ou de TIFF (ou par image), **en couleur**,
  à 200 ou 300 dpi, **en taille réelle**, sans redimensionner. Un scan plus fin est
  ramené à 200 dpi, la résolution de réglage de l'outil : il n'apporte rien de
  plus, et la cotation ne dépend pas de la résolution du scan.
- Le sens du scan n'a pas d'importance, une légère inclinaison est corrigée.
- L'enfant dessine au **stylo** (bleu par défaut, voir `--encre`). Les
  annotations de l'ergothérapeute au crayon à papier sont ignorées, y compris
  un trait de crayon qui coupe le tracé de l'enfant (pas un trait de crayon
  posé le long de ce tracé, qui le masque).

### Corriger

```bash
autocorrect-nepsy corriger page1.pdf page2.pdf page3.pdf -o correction/
```

Options :

- `--pages 1,2,3` : numéro de page du cahier de chaque page scannée, dans
  l'ordre. Sans cette option, il est déduit de la structure des scans (la
  page 1 a un en-tête, les pages 2 à 4 ont quatre items, les pages 5 et 6
  trois), dans l'ordre du cahier. Quand cela ne suffit pas (page manquante,
  scan seul, scans dans le désordre), les modèles imprimés en haut de la page
  départagent : ils sont notés avec les critères des items de chaque page
  possible. Si les modèles ne sont pas lisibles, la commande s'arrête et
  demande `--pages`. Une page dont les modèles ressemblent nettement à ceux
  d'une autre page est signalée « à vérifier ».
- `--dpi 300` : impose la résolution si celle du fichier est fausse.
- `--encre rouge` : couleur du stylo de l'enfant (bleu par défaut).

Pages du cahier :

| Page du cahier | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Items | 1-3 | 4-7 | 8-11 | 12-15 | 16-18 | 19-21 |

- `--enfant "L. M."` et `--passation 20/10/2026` : pseudonyme (ou initiales)
  de l'enfant et date de passation, repris dans le rapport.

Sorties dans le dossier choisi :

- `cotation.csv` : notes retenues de chaque critère, par item, avec les
  colonnes `a_verifier`, `verifie` et `corrige` (critères dont l'ergothérapeute
  a changé la note dans la fenêtre) ;
- `cotation_automatique.csv` : proposition de l'outil telle quelle, avant les
  corrections de l'ergothérapeute (identique à `cotation.csv` en ligne de
  commande) ;
- `rapport.html` : dessin annoté de chaque item et détail de chaque critère ;
  les notes changées par l'ergothérapeute y sont surlignées.

### Comparer à la cotation de l'ergothérapeute

```bash
autocorrect-nepsy comparer correction/cotation_automatique.csv cotation_ergo.csv
```

Pour évaluer l'outil, comparez sa proposition (`cotation_automatique.csv`),
pas les notes déjà corrigées dans la fenêtre. Le bouton **Comparer à la
cotation de l'ergo…** de la fenêtre le fait de lui-même.

Affiche l'accord global, le kappa de Cohen (global et par critère) et la liste
des désaccords, en indiquant ceux qui tombent dans un item signalé « à
vérifier ». Les deux fichiers ont les colonnes
`item,general,motricite_A,motricite_B,motricite_total,global_C,global_D,global_total,local_E,local_F,local_total`
(case vide pour un critère qui n'existe pas). Un tableau enregistré en CSV par
Excel convient (séparateur point-virgule, encodage Windows) ; les lignes sans
numéro d'item, comme une ligne de total, sont ignorées.

### Valider sur un corpus de protocoles

```bash
autocorrect-nepsy valider donnees/validation --json donnees/validation-0.10.0.json
autocorrect-nepsy valider donnees/validation --precedent donnees/validation-0.10.0.json
```

Corrige chaque protocole d'un corpus et le compare à la cotation de
l'ergothérapeute. Le corpus reste sur l'ordinateur (dossier `donnees/`, ignoré
par git) : un sous-dossier par protocole, nommé par un pseudonyme (`P001`…),
avec ses scans, `cotation_ergo.csv` (cotation faite sans voir celle de
l'outil) et, si le numéro de page ne peut pas être deviné, `pages.txt`
(ex. `1,2,3,4,5,6`).

Seuls des chiffres d'ensemble sont affichés :

- accord et kappa par processus et par critère ;
- accord par item ;
- écart des totaux ;
- part des items « à vérifier » et part des désaccords qu'ils couvrent.

Ces chiffres sont confrontés à des objectifs (kappa d'au moins 0,80 par
processus, aucun item sous 85 % d'accord, 95 % des désaccords dans des items
signalés, totaux à 1 point près dans 90 % des protocoles), à fixer avec
l'ergothérapeute.

`--json` enregistre les résultats, avec la cotation automatique de chaque
protocole. Il faut garder ce fichier hors du dépôt. `--precedent` indique ce
qui a changé depuis un passage précédent sur le même corpus.

Pour ne pas régler l'outil sur ses propres données de validation :

- garder un dossier de réglage et un dossier de validation séparés ;
- ne lancer la validation qu'une fois la version figée.

## Fonctionnement

1. **Scan** (`scan.py`) : lecture du PDF ou de l'image et de sa résolution,
   pour mesurer en mm réels.
2. **Mise en page** (`layout.py`) : redressement, choix du sens (modèles en
   haut, copies de l'enfant en bas), découpage des zones d'items à partir des
   traits imprimés du cahier. Le numéro de page est déduit de la structure de
   la page et, si besoin, de ses modèles imprimés (`identify.py`).
3. **Encres** (`ink.py`) : le stylo de l'enfant est séparé de l'impression et
   du crayon de l'ergothérapeute par la couleur.
4. **Traits** (`strokes.py`) : squelette du tracé, graphe des croisements,
   recollement des traits qui se croisent, puis découpage en lignes droites
   (avec leurs interruptions et les passages repassés).
5. **Critères** (`criteria/`) : un module par item, qui applique les seuils du
   manuel (reformulés) aux mesures. Des modules communs retrouvent les lignes
   courbes (`curves.py`), les régions fermées et les polygones (`polygons.py`)
   et les ellipses (`ellipses.py`).
6. **Rapport** (`report.py`, `compare.py`) : CSV, HTML et comparaison avec la
   cotation de référence.
7. **Interface** (`gui.py`) : fenêtre Tkinter ; `packaging/` contient de quoi
   construire l'exécutable Windows.

## Données et confidentialité

Ce dépôt est **public**. Il ne contient et ne doit contenir :

- aucun scan ni aucune cotation d'enfant (données de santé de mineurs) ;
- aucune page du manuel ni du cahier de réponses (droits d'auteur de l'éditeur).

Le `.gitignore` exclut les PDF, images et CSV. Les tests utilisent uniquement
des dessins synthétiques (`tests/synth.py`). Les seuils sont reformulés à
partir du manuel et ne le remplacent pas.

## Limites connues

- Les items 9 à 21 n'ont été réglés que sur un protocole réel. Les rayons
  d'une roue dessinés à main levée (item 21) et les pétales mal fermés
  (item 20) sont repérés de façon approchée : le rapport les montre, à vérifier.
- Certains cas restent ambigus entre la règle et le jugement de
  l'ergothérapeute : trait repassé à côté du premier tracé, ligne légèrement
  courbée jugée « non droite ». Ils doivent être revus à la main.
- « Relativement vertical / horizontal » (item 5, Global C) est interprété
  comme moins de 45° d'écart à l'axe.
- Un stylo noir se confond avec le crayon de l'ergothérapeute : il faut alors
  que l'ergothérapeute annote dans une autre couleur.
- Un dessin qui déborde de sa zone n'est pas pris en compte en dehors de la
  zone.
- Les coins arrondis sont reconnus jusqu'à 6 mm de rayon environ pour un
  carré de 4 cm ; au-delà, ou avec un fort tremblement, la figure peut ne pas
  être reconnue : l'item est alors noté 0 et signalé « à vérifier ».
- Aux items 1 et 2, le trait noté est le trait continu qui porte la plus
  longue ligne droite, mesuré en entier (zigzag, ondulation ou crochet
  compris) ; un trait brisé ou un trait en plus est signalé « à vérifier ».
- Un petit gribouillis peut être pris pour une petite figure (cercle de
  l'item 3, V de l'item 17, cylindre de l'item 14) et recevoir quelques points
  sans être signalé.

## Développement

```bash
python -m pip install -e ".[test]"
pytest
```

Les tests de l'interface ont besoin de `tkinter` et d'un écran (sous Linux sans
écran : `xvfb-run -a pytest`) ; sans eux, ils sont ignorés. En intégration
continue, `AUTOCORRECT_TESTS_INTERFACE=obligatoires` les rend obligatoires.

### Construire l'exécutable

```bash
python -m pip install -e ".[exe]" -c packaging/contraintes.txt
python packaging/build.py      # produit dist/AutoCorrectNEPSY(.exe)
```

`packaging/contraintes.txt` fixe les versions exactes des dépendances (numpy,
OpenCV, Pillow, pypdf, PyInstaller) de l'exécutable et des tests sous
Python 3.12 : deux Releases notent un même scan de la même façon. Pour les
mettre à jour, changer les versions dans ce fichier, vérifier que la CI reste
verte, puis livrer une nouvelle version.

L'intégration continue (workflow « Tests et exécutable Windows ») construit et
teste `AutoCorrectNEPSY.exe` sous Windows après les tests ; l'exécutable de
chaque exécution est dans l'onglet *Actions* (artefact
« AutoCorrectNEPSY-windows »).

### Versions et publication

Même parcours que les autres projets livrés par PlaniFiKateur : **chaque pull
request livre une nouvelle version**.

- La PR augmente la version (`pyproject.toml` et
  `autocorrect_nepsy/__init__.py`) et ajoute sa section
  `## [x.y.z] - date` en tête du [CHANGELOG](CHANGELOG.md). Une carte
  PlaniFiKateur le fait d'elle-même ; pour une PR ouverte directement :
  `python packaging/nouvelle_version.py --niveau correctif --resume "…"`
  (`mineure` pour une nouvelle fonctionnalité, `majeure` pour un changement
  incompatible).
- Le job « Version » de la CI refuse une PR dont la version n'est pas
  supérieure à celle de `main`, ou dont `__version__` ou le CHANGELOG ne
  suivent pas (`python packaging/verifier_version.py` pour le vérifier en
  local).
- Une fois la PR fusionnée, la CI de `main` publie la version `vx.y.z` dans
  les *Releases*, avec `AutoCorrectNEPSY.exe` et la section du CHANGELOG. Une
  version déjà publiée n'est jamais remplacée ; PlaniFiKateur archive chaque
  version dans Google Drive.

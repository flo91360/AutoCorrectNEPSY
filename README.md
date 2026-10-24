# AutoCorrectNEPSY

Correction automatique du subtest **Copie de figures** de la NEPSY-II, à partir
des pages scannées du cahier de réponses. **Prototype** : le logiciel propose une
cotation que l'ergothérapeute valide.

## État

- Items **1 à 8** pris en charge, avec tous leurs critères : Général, Motricité
  A/B, Global C/D, Local E/F (pas de Local pour les items 1 à 3).
- Chaque critère est accompagné des mesures qui le justifient (longueurs en mm,
  angles, rapports).
- Les items douteux sont signalés **« à vérifier »** : mesure proche d'un seuil,
  trait repassé à côté du premier tracé, zone vide.
- Premier essai sur un protocole réel : 46 critères sur 50 identiques à la
  cotation de l'ergothérapeute (kappa de Cohen 0,71).

## Installation

```bash
python -m pip install -e .
```

## Utilisation

### Scanner les pages

- Une page du cahier par page de PDF (ou par image), à 200 dpi minimum
  (300 dpi conseillés), **en taille réelle**, sans redimensionner.
- Le sens du scan n'a pas d'importance, une légère inclinaison est corrigée.
- L'enfant dessine au **stylo** (bleu par défaut, voir `--encre`). Les
  annotations de l'ergothérapeute au crayon à papier sont ignorées.

### Corriger

```bash
autocorrect-nepsy corriger page1.pdf page2.pdf page3.pdf --pages 1,2,3 -o correction/
```

`--pages` indique le numéro de page du cahier de chaque page scannée, dans
l'ordre :

| Page du cahier | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Items | 1-3 | 4-7 | 8-11 | 12-15 | 16-18 | 19-21 |

Sorties dans le dossier choisi :

- `cotation.csv` : note de chaque critère, par item ;
- `rapport.html` : dessin annoté de chaque item et détail de chaque critère.

### Comparer à la cotation de l'ergothérapeute

```bash
autocorrect-nepsy comparer correction/cotation.csv cotation_ergo.csv
```

Affiche l'accord global, le kappa de Cohen, l'accord par critère et la liste
des désaccords. Les deux fichiers ont les colonnes
`item,general,motricite_A,motricite_B,motricite_total,global_C,global_D,global_total,local_E,local_F,local_total`
(case vide pour un critère qui n'existe pas).

## Fonctionnement

1. **Scan** (`scan.py`) : lecture du PDF ou de l'image et de sa résolution,
   pour mesurer en mm réels.
2. **Mise en page** (`layout.py`) : redressement, choix du sens (modèles en
   haut, copies de l'enfant en bas), découpage des zones d'items à partir des
   traits imprimés du cahier.
3. **Encres** (`ink.py`) : le stylo de l'enfant est séparé de l'impression et
   du crayon de l'ergothérapeute par la couleur.
4. **Traits** (`strokes.py`) : squelette du tracé, graphe des croisements,
   recollement des traits qui se croisent, puis découpage en lignes droites
   (avec leurs interruptions et les passages repassés).
5. **Critères** (`criteria/`) : un module par item, qui applique les seuils du
   manuel (reformulés) aux mesures.
6. **Rapport** (`report.py`, `compare.py`) : CSV, HTML et comparaison avec la
   cotation de référence.

## Données et confidentialité

Ce dépôt est **public**. Il ne contient et ne doit contenir :

- aucun scan ni aucune cotation d'enfant (données de santé de mineurs) ;
- aucune page du manuel ni du cahier de réponses (droits d'auteur de l'éditeur).

Le `.gitignore` exclut les PDF, images et CSV. Les tests utilisent uniquement
des dessins synthétiques (`tests/synth.py`). Les seuils sont reformulés à
partir du manuel et ne le remplacent pas.

## Limites connues

- Items 9 à 21 pas encore traités.
- Certains cas restent ambigus entre la règle et le jugement de
  l'ergothérapeute : trait repassé à côté du premier tracé, ligne légèrement
  courbée jugée « non droite ». Ils doivent être revus à la main.
- « Relativement vertical / horizontal » (item 5, Global C) est interprété
  comme moins de 45° d'écart à l'axe.
- Un stylo noir se confond avec le crayon de l'ergothérapeute : il faut alors
  que l'ergothérapeute annote dans une autre couleur.
- Un dessin qui déborde de sa zone n'est pas pris en compte en dehors de la
  zone.

## Développement

```bash
python -m pip install -e ".[test]"
pytest
```

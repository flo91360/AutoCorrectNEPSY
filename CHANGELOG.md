# Journal des modifications

Toutes les évolutions notables d'AutoCorrectNEPSY. Chaque pull request ajoute
la section de sa nouvelle version (voir « Versions et publication » dans le
README).

<!-- nouvelles versions -->

## [0.8.0] - 2026-10-25

- Items signalés « à vérifier » quand la figure du modèle n'est pas retrouvée (coins arrondis, dessin mal lu), quand la page du cahier est devinée sans certitude (page manquante, scan seul) ou quand l'échelle du scan est douteuse ; en ligne de commande, --pages est demandé si le numéro de page est incertain
- Toutes les pages d'un TIFF multipage sont lues ; la comparaison accepte les CSV enregistrés par Excel ; fichiers absents ou illisibles signalés par un message clair ; un dossier de résultats n'est jamais écrasé

## [0.7.2] - 2026-10-25

- Item 10 : le coin du triangle est pris là où un autre trait touche son côté, même si le côté se prolonge un peu au-delà (même cotation à 200 et 300 dpi)

## [0.7.1] - 2026-10-25

- Cotation indépendante de la résolution du scan : recherche d'ellipses systématique (seau, roues) et scans plus fins que 200 dpi ramenés à 200 dpi

## [0.7.0] - 2026-10-25

- Correction des items 19 à 21 (seau, fleur, roues) : tout le subtest Copie de figures est pris en charge

## [0.6.0] - 2026-10-25

- Correction des items 16 à 18 (triangles imbriqués, figure en V, escalier) à partir des régions fermées du dessin

## [0.5.0] - 2026-10-25

- Correction des items 12 à 15 (deux lignes en S, éventail, cylindre, croix) ; le rapport montre les lignes reconstituées par l'outil

## [0.4.0] - 2026-10-25

- Correction des items 9 à 11 (rangée de cercles pleins, triangle sur trapèze, drapeau) ; les dessins qui dépassent le bout du trait de séparation ne sont plus coupés

## [0.3.1] - 2026-10-25

- Corriger le double-clic sur un item et le bouton « Ouvrir le rapport détaillé », qui n'ouvraient rien sous Windows

## [0.3.0] - 2026-10-25

- Rapport : les mesures de l'outil (longueurs, angles, barre grisée, diamètres, chevauchements) sont dessinées sur les traits de chaque item, pour pouvoir les vérifier sans les annotations de l'ergothérapeute

## [0.2.6] - 2026-10-25

- Ne plus couper un trait continu là où l'encre du stylo est plus foncée (l'outil y voyait à tort une interruption du tracé)

## [0.2.5] - 2026-10-24

- Rapport détaillé : le dessin de l'enfant et les traits lus par l'outil sont affichés côte à côte au lieu d'être superposés.

## [0.2.4] - 2026-10-24

- Garder les accents des notes de version publiées avec l'exécutable

## [0.2.3] - 2026-10-24

- Livrer comme les autres projets PlaniFiKateur : version augmentée dans chaque PR et vérifiée par la CI, exécutable publié automatiquement à chaque nouvelle version

## [0.2.2] - 2026-10-24

- Ajouter les consignes pour Claude (fusion automatique quand la CI est verte) ([#5](https://github.com/flo91360/AutoCorrectNEPSY/pull/5))

## [0.2.1] - 2026-10-24

- Mettre à jour le CHANGELOG et la version à chaque PR fusionnée ([#4](https://github.com/flo91360/AutoCorrectNEPSY/pull/4))

## [0.2.0] - 2026-10-24

- Interface graphique et exécutable Windows (AutoCorrectNEPSY.exe) ([#2](https://github.com/flo91360/AutoCorrectNEPSY/pull/2))
- Publier l'exécutable depuis l'interface de GitHub ([#3](https://github.com/flo91360/AutoCorrectNEPSY/pull/3))

## [0.1.0] - 2026-10-24

- Prototype de correction automatique de la Copie de figures (items 1 à 8) ([#1](https://github.com/flo91360/AutoCorrectNEPSY/pull/1))

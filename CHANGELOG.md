# Journal des modifications

Toutes les évolutions notables d'AutoCorrectNEPSY. Chaque pull request ajoute
la section de sa nouvelle version (voir « Versions et publication » dans le
README).

<!-- nouvelles versions -->

## [0.14.2] - 2026-11-05
<!-- planifikateur:0bb4e358-c0ec-4dd4-810e-165891bb5b0b -->

- **figure 19 critère générale** : L'hypothèse de l'ergothérapeute est confirmée et j'ai corrigé la cause : le critère Général de l'item 19 n'échoue plus à tort quand la verticale de droite est repassée. Un vrai intervalle continue de le faire échouer. Les tests de l'item 19 passent, tout comme le contrôle pyflakes. La suite complète, lancée en cours de travail, n'avait qu'un échec : l'instantané de cotation, régénéré depuis. Je ne l'ai pas relancée en entier après les dernières retouches. **Cause.** J'ai reproduit le cas sur un dessin synthétique avec une deuxième verticale à droite, tracée à 1,5–2,5 mm de la première. L'outil réunit les deux traits en une seule ligne et mesure l'intervalle depuis les bouts de cette ligne. Or ces bouts sont placés sur un axe moyen qui passe entre les deux traits, donc à l'écart de l'un et de l'autre. Le programme trouvait ainsi un « intervalle » de 1,0 à 1,8 mm, au-delà du seuil de 1 mm, et Général échouait (le critère A aussi, qui utilise la même mesure). **Correction** (`autocorrect_nepsy/criteria/item_19.py`, fonction `_reach`). À chaque jonction, l'intervalle est maintenant la distance entre l'ellipse et le point le plus proche de la moitié haute ou basse de la verticale. Il suffit donc qu'un des deux traits touche l'ellipse, et un dépassement n'est pas compté. Les seuils du manuel n'ont pas changé. **Tests ajoutés** (`tests/test_criteria.py`, dessins synthétiques uniquement) : - **Reprise de tracé :** verticales qui dépassent de 3 mm et verticale de droite repassée à 2,5 mm. Jonction mesurée à 1 mm au plus, Général et A réussis. Ce test échoue avec l'ancien code. - **Vrai intervalle :** une verticale seule à 1,5 mm des ellipses sur le côté, ou arrêtée 8 mm sous l'ellipse du haut. Général et A restent échoués. **Instantané de cotation régénéré** (`tests/instantane_cotation.json`) : un seul cas change, le seau très déformé de l'item 19. Son critère Général reste échoué mais est maintenant marqué « limite ». **Limite.** Les verticales rejoignent les ellipses à leu

## [0.14.1] - 2026-11-05
<!-- planifikateur:1b4d646e-faa7-44c4-9956-7e6443857940 -->

- **concernant la figure 12 critère Local E** : Local E de l'item 12 ne compte plus comme crête une reprise de tracé proche du premier tracé. Sur un dessin synthétique qui reproduit le défaut, il passe de 0 à 1 et Local F reste à 1. Je n'ai pas pu le vérifier sur le dessin de l'enfant : la pièce jointe est une capture du résultat (les deux lignes suivies), pas le scan, et je ne peux donc pas y relancer la cotation. **Cause reproduite** : quand l'enfant revient sur le bout d'une ligne d'un seul trait (aller-retour à environ 2 mm du premier tracé), l'outil suit ce retour comme le début de la ligne. Le demi-tour crée une crête en trop (3 au lieu de 2) et Local E tombe à 0. **Correction** : - Dans `criteria/curves.py`, une nouvelle fonction (`Curve.without_retraces`) repère, à chaque bout de ligne, un aller-retour qui reste à moins de 2,5 mm du premier tracé et revient d'au moins 2 mm. Elle retire ce retour et ramène le bout de la ligne au demi-tour, sur le tracé initial. - Ne sont pas concernés : les boucles ou retours qui s'écartent à plus de 2,5 mm, les reprises en traits séparés et les retours de moins de 2 mm. - Dans `criteria/item_12.py`, seul le critère Local E utilise la ligne corrigée. Son détail précise la longueur de la reprise rattachée. Les autres critères ne changent pas, comme demandé. **Point à décider** : Général G vérifie aussi la forme en S sur la même ligne, sans cette correction. Sur mon dessin synthétique, G reste donc à 0, et Global D aussi quand le retour fait environ 8 mm. Si la reprise doit aussi être ignorée pour G, c'est une modification courte à faire dans une autre carte. **Tests** (dans `tests/test_criteria.py`) : - Une forme en S avec une reprise repliée près du premier tracé, sur chaque ligne et à chaque bout : Local E vaut 1, sans crête supplémentaire, et Local F vaut 1. - Une ligne qui a vraiment des crêtes en plus reste à 0 en Local E. Toute la suite passe (301 tests, 1 ignoré), y compris l'instantané des cotations, qui est inchangé ; pyflakes ne signale rien. Aucun scan ni dessin

## [0.14.0] - 2026-11-01

- Bouton « Valider un corpus… » dans la fenêtre : validation sans ligne de commande, enregistrée dans le corpus avec les désaccords en CSV pour Excel et comparée au passage précédent ; version de l'outil dans cotation.csv, cotation_automatique.csv, le rapport et les fichiers de validation ; option --desaccords de la commande valider

## [0.13.2] - 2026-10-27

- Les critères et les mesures limites ressortent en rouge et en gras dans le rapport, et en rouge dans la fenêtre Vérifier / corriger.

## [0.13.1] - 2026-10-26

- Marge « limite » calibrée sur l'incertitude de la comparaison avec l'ergothérapeute : 0,5 mm (2 % du seuil pour une longueur), 2° pour un angle, 3 % pour un rapport, sans part proportionnelle pour les angles ; moins d'items signalés à tort (copies fidèles avec un tremblement de 0,5 mm : 5 sur 21 au lieu de 7), aucune note changée et aucun point perdu sans signalement de plus
- Colonne « À vérifier » de la fenêtre : critères dont une mesure est proche du seuil (« ⚠ B F »)
- Avertissement pour un scan à moins de 200 dpi (ligne de commande, rapport, fenêtre)
- cotation.csv et cotation_automatique.csv s'ouvrent directement dans Excel en français (point-virgule, UTF-8 avec BOM)
- CI : actions GitHub épinglées par empreinte, cache pip, analyse pyflakes

## [0.13.0] - 2026-10-26

- Seuils du manuel séparés des réglages internes de l'outil dans les 21 items : chacun est déclaré avec son ou ses critères, son unité et une description reformulée, et les textes du rapport citent ces constantes au lieu de recopier les valeurs
- Commande « seuils » : liste des 178 seuils du manuel utilisés, item par item (--item N pour un seul item), à vérifier sur le manuel
- Échafaudage commun Scoring pour les 20 modules d'items : dessin vide et figure non reconnue traités au même endroit
- Instantané de la cotation sur les copies synthétiques de tous les modèles (tests/test_instantane.py) : la restructuration ne change aucune note

## [0.12.0] - 2026-10-26

- Vérification par l'ergothérapeute dans la fenêtre (« Vérifier / corriger l'item sélectionné… ») : chaque note d'un item est confirmée ou changée, l'item passe « vérifié », les totaux, cotation.csv (colonnes verifie et corrige) et le rapport suivent
- cotation_automatique.csv garde la proposition de l'outil, avant corrections : c'est elle que compare le bouton « Comparer à la cotation de l'ergo… »
- Pseudonyme de l'enfant et date de passation (fenêtre, --enfant, --passation) repris dans le rapport, et le pseudonyme dans le nom du dossier des résultats

## [0.11.0] - 2026-10-25

- Numéro de page lu sur les modèles imprimés quand la structure ne suffit pas (page manquante, scan seul, scans dans le désordre) : --pages n'est plus demandé que si les modèles sont illisibles
- Une page dont les modèles imprimés ressemblent nettement à ceux d'une autre page est signalée « à vérifier » (scans dans le désordre, mauvais choix de page)

## [0.10.0] - 2026-10-25

- Commande « valider » : correction d'un corpus local de protocoles comparée à la cotation de l'ergothérapeute, avec des chiffres d'ensemble seulement (accord et kappa par processus, critère et item, écarts des totaux, désaccords signalés, objectifs d'acceptation) et le suivi des changements d'une version à l'autre
- « comparer » donne le kappa de chaque critère et la part des désaccords dans des items « à vérifier »

## [0.9.0] - 2026-10-25

- Coins arrondis reconnus comme des coins (carré de 4 cm aux coins jusqu'à 6 mm de rayon environ, rectangle de l'item 11) sans découper les lignes ondulées ni les cercles
- Items 1 et 2 : le trait est mesuré en entier (zigzag, ondulation, crochet compris) et un trait brisé ou en plus est signalé « à vérifier »
- Un trait de crayon de l'ergothérapeute qui coupe le tracé de l'enfant ne le coupe plus en deux éléments
- Versions exactes des dépendances de l'exécutable et des tests sous Python 3.12 (packaging/contraintes.txt) ; tests de chaque seuil sensible de part et d'autre

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

# Journal des modifications

Toutes les évolutions notables d'AutoCorrectNEPSY. Chaque pull request ajoute
la section de sa nouvelle version (voir « Versions et publication » dans le
README).

<!-- nouvelles versions -->

## [0.14.6] - 2026-11-06
<!-- planifikateur:d30cc188-11bc-4859-80d5-d8a169281951 -->

- **figure 16 critère générale** : Le critère Général de l'item 16 est corrigé : un dessin dont les coins sont reliés et qui ne dépasse pas obtient maintenant 1. Toute la suite de tests passe (316 tests, 1 ignoré, celui de l'interface sans écran) et pyflakes ne signale rien. **Cause du 0.** Ce n'était ni le petit triangle « non collé » ni le test de dépassement. Sur le scan, les côtés du grand triangle sont un peu bombés vers l'extérieur. Le logiciel place alors les coins du grand triangle là où se croisent ses côtés redressés, soit 2 à 3 mm au-delà de la pointe réellement tracée. Le bout de ligne entre ce coin calculé et la pointe dessinée n'a pas d'encre : la liaison paraissait tracée à 88–93 % (« liaison 93 % » sur le rapport du scan), sous les 95 % exigés, avec un trou apparent de 2,6 mm au-delà de la limite de 2 mm. **Correction (`autocorrect_nepsy/criteria/item_16.py`).** - Pour le critère Général seulement, chaque coin estimé hors de l'encre est ramené sur le point d'encre le plus proche, dans la limite de 4 mm. La liaison est ensuite mesurée entre les coins réellement dessinés. - La règle elle-même ne change pas : le critère est réussi si chaque coin du grand triangle est relié au coin du petit (ligne tracée à 95 % au moins, trou de 2 mm au plus) et si aucun coin ne dépasse de plus de 2 mm du triangle qui le contient. - Les pourcentages du critère Général et les repères « liaison … % » du rapport utilisent cette nouvelle mesure, donc ils restent cohérents avec la note. - Les autres critères (Motricité B, Global D, Local F) gardent leur mesure d'avant, pour ne pas changer leur cotation. - Les seuils du manuel déclarés pour l'item 16 n'étaient pas en cause et n'ont pas été modifiés. **Tests ajoutés (`tests/test_criteria.py`).** Les dessins synthétiques ont des côtés de grand triangle légèrement bombés, grâce à deux ajouts à `tests/synth.py` : une fonction `bowed` et des options de `nested_triangles` pour réduire ou agrandir le petit triangle et raccourcir les lignes de liaison. - **Coins reliés

## [0.14.5] - 2026-11-06
<!-- planifikateur:cc61a266-b78c-49a1-9b3a-fd4ead451c80 -->

- **figure 17 critère motricité B** : Item 17 corrigé : sur la capture jointe, Motricité B affiche maintenant un dépassement d'environ 1,75 à 1,8 mm (2,3 à 2,4 mm avant) et le critère est réussi. Le seuil de 2 mm du manuel n'a pas changé. La suite de tests passe (317 réussis, 1 ignoré). Limite : la pièce jointe est une capture d'écran basse résolution (environ 3,8 pixels par mm), pas le scan original. Je n'ai donc pas obtenu exactement 1,6 mm ; la valeur reste à moins de 0,2 mm de celle de l'ergothérapeute. Il faudrait refaire la vérification sur le vrai scan. **Cause trouvée** - La ligne extérieure gauche du V est un peu incurvée et le coin en bas à gauche est arrondi. - L'outil place le coin à la rencontre des côtés ajustés en lignes droites. Ce coin calculé tombait environ 1,2 mm à droite de l'endroit où la ligne intérieure croise réellement la base. - L'outil mesurait la distance entre la pointe du dépassement et ce coin calculé. Ce décalage s'ajoutait donc à la longueur du dépassement. - Mesurée depuis la droite de la base, la pointe est à 1,63 mm : c'est la mesure de l'ergothérapeute à la règle. **Correction (`criteria/polygons.py`, fonction `overshoot`, utilisée seulement par l'item 17)** - Le dépassement se mesure le long du trait, depuis l'endroit où il franchit la droite d'un côté jusqu'à sa pointe. Ce passage n'est retenu que s'il est net (au moins 30° par rapport au côté) et si le côté y est réellement dessiné. Si aucun passage n'est trouvé, l'ancienne mesure s'applique et ne peut pas être dépassée. - Les petits côtés parasites de moins de 2,5 mm, qui coupent parfois un coin arrondi en deux, sont fusionnés en un seul coin. - La recherche autour du coin est élargie de la distance entre le coin calculé et le tracé, pour ne pas perdre la pointe d'un long dépassement. L'item 18 a sa propre mesure et n'est pas touché. **Tests** - Dans `tests/synth.py`, un nouveau dessin `v_overshoot` reproduit la situation : un V dont la ligne extérieure gauche est droite ou incurvée, avec un dépassement au coin

## [0.14.4] - 2026-11-05
<!-- planifikateur:3cb75d0d-e2b6-484d-8869-2f191cb34aca -->

- **figure 18 critère motricité B** : À l'item 18, un angle pincé n'est plus compté comme un dépassement : sur votre dessin, Motricité B est maintenant réussi, avec 0,1 mm mesuré au lieu de 2,6 mm. Le seuil du manuel (1 mm) n'a pas changé. Les tests passent (309, 1 ignoré, sans erreur pyflakes). **Pourquoi l'outil voyait 2,8 mm.** Il calcule chaque coin comme le croisement de deux droites ajustées sur les côtés. Puis il compte comme dépassement toute encre qui sort de l'angle formé par ces droites. Sur votre dessin, le côté gauche s'incurve vers la gauche près du haut : l'encre du coin réel se trouve donc à l'extérieur de ce coin calculé. S'y ajoute le petit crochet en diagonale laissé par le stylo au départ du trait. Les deux comptaient comme dépassement. **Ce qui change.** Le coin est maintenant pris là où il est réellement dessiné. Seule l'encre qui prolonge un côté au-delà de ce coin (à 30° près) compte comme dépassement. L'encre qui suit le tracé de la figure (côté incurvé) ou qui part en crochet vers l'extérieur (stylo posé ou levé) est classée comme coin mal tracé. Pour rester vigilant, ce cas est affiché sur le rapport (« coin mal tracé … (pas un dépassement) ») et dans la mesure `coin_mal_trace_max_mm`, sans faire échouer Motricité B. **Autres items inchangés.** L'item 17 utilise la même mesure des dépassements, qui est conservée telle quelle ; la nouvelle ne sert qu'à l'item 18. **Vérification.** - **Pièce jointe :** je l'ai reconstruite en local à partir de la capture d'écran, qui est en basse résolution, sans rien verser dans le dépôt. L'ancienne mesure y donne 2,6 mm, proche des 2,8 mm de l'outil, et la nouvelle 0,1 mm. C'est une approximation : il faudra confirmer sur le scan d'origine. - **Nouveaux tests synthétiques :** un escalier à angle pincé avec crochet (ancienne mesure : 2,9 mm) est noté réussi. De vrais dépassements de 1,5, 2 et 3 mm restent notés échoués, sur un coin net comme sur un coin pincé. - **Instantané de cotation :** j'ai régénéré `tests/instantane_cotation.json`. Une se

## [0.14.3] - 2026-11-05
<!-- planifikateur:0bb4e358-c0ec-4dd4-810e-165891bb5b0b -->

- **figure 19 critère générale** : L'hypothèse de l'ergothérapeute est confirmée et j'ai corrigé la cause : le critère Général de l'item 19 n'échoue plus à tort quand la verticale de droite est repassée. Un vrai intervalle continue de le faire échouer. Les tests de l'item 19 passent, tout comme le contrôle pyflakes. La suite complète, lancée en cours de travail, n'avait qu'un échec : l'instantané de cotation, régénéré depuis. Je ne l'ai pas relancée en entier après les dernières retouches. **Cause.** J'ai reproduit le cas sur un dessin synthétique avec une deuxième verticale à droite, tracée à 1,5–2,5 mm de la première. L'outil réunit les deux traits en une seule ligne et mesure l'intervalle depuis les bouts de cette ligne. Or ces bouts sont placés sur un axe moyen qui passe entre les deux traits, donc à l'écart de l'un et de l'autre. Le programme trouvait ainsi un « intervalle » de 1,0 à 1,8 mm, au-delà du seuil de 1 mm, et Général échouait (le critère A aussi, qui utilise la même mesure). **Correction** (`autocorrect_nepsy/criteria/item_19.py`, fonction `_reach`). À chaque jonction, l'intervalle est maintenant la distance entre l'ellipse et le point le plus proche de la moitié haute ou basse de la verticale. Il suffit donc qu'un des deux traits touche l'ellipse, et un dépassement n'est pas compté. Les seuils du manuel n'ont pas changé. **Tests ajoutés** (`tests/test_criteria.py`, dessins synthétiques uniquement) : - **Reprise de tracé :** verticales qui dépassent de 3 mm et verticale de droite repassée à 2,5 mm. Jonction mesurée à 1 mm au plus, Général et A réussis. Ce test échoue avec l'ancien code. - **Vrai intervalle :** une verticale seule à 1,5 mm des ellipses sur le côté, ou arrêtée 8 mm sous l'ellipse du haut. Général et A restent échoués. **Instantané de cotation régénéré** (`tests/instantane_cotation.json`) : un seul cas change, le seau très déformé de l'item 19. Son critère Général reste échoué mais est maintenant marqué « limite ». **Limite.** Les verticales rejoignent les ellipses à leu

## [0.14.2] - 2026-11-05
<!-- planifikateur:bb146978-8be7-4b51-acbe-b490c8025728 -->

- **figure 13 critère globale C** : L'item 13 accepte maintenant, au critère Global C, une ligne centrale jusqu'à 20° de la verticale. Avec ce changement, le cas de la copie réelle obtient 1, comme l'a coté l'ergothérapeute. Tous les tests passent (300 réussis, ceux de l'interface ignorés faute d'écran) et pyflakes ne signale rien. **Ce qui faisait coter 0.** L'outil prenait comme ligne centrale la ligne la plus verticale. Sur la copie, c'est la 3ᵉ ligne qui est la plus verticale, et non la 4ᵉ. L'outil comptait donc 2 lignes d'un côté et 4 de l'autre, d'où le 0. La 4ᵉ ligne, marquée en rouge, est inclinée d'environ 15°. **Ce qui change (`autocorrect_nepsy/criteria/item_13.py`).** - Quand la figure a bien 7 lignes radiales, l'outil les range dans l'ordre de l'éventail et prend la 4ᵉ comme ligne centrale. Il y a ainsi forcément 3 lignes de chaque côté. - Cette 4ᵉ ligne doit être à 20° au plus de la verticale. - Si son angle est à 2° ou moins de 20°, l'item est signalé « à vérifier ». - L'angle mesuré apparaît dans le rapport (par exemple « ligne centrale (4ᵉ ligne radiale) à 19° de la verticale (≤ 20°) ») et dans les mesures (`centrale_angle_deg`). - Le seuil est déclaré comme seuil du manuel pour le critère C. `autocorrect-nepsy seuils --item 13` affiche : « C 20° écart à la verticale de la ligne centrale (4ᵉ des 7 lignes radiales), au plus ». - S'il n'y a pas 7 lignes radiales, Global C est calculé comme avant. Le critère Général, les autres critères et les autres items ne changent pas. **Effet de bord.** Avant, une ligne centrale entre 20° et 25° pouvait encore être acceptée en Global C. Elle ne l'est plus. **Cohérence avec le manuel : à vérifier.** Le manuel n'est pas dans le dépôt, je n'ai donc pas pu faire ce contrôle. D'après le texte du code, il demande seulement une ligne centrale « relativement verticale », sans valeur chiffrée. Les 20° sont donc l'interprétation de l'ergothérapeute, à confirmer sur le manuel. **Point à décider.** Le critère Général compte encore les lignes à l'ancienne façon.

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

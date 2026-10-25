"""Numéro de page du cahier lu sur les modèles imprimés.

Les pages 2 à 4, comme les pages 5 et 6, ont la même structure (nombre de
colonnes) : quand une page manque, ou pour un scan seul, la structure ne suffit
pas à trouver le numéro de page. Les modèles imprimés en haut de chaque colonne
départagent : ils sont notés avec les critères des items de chaque page
candidate. Un modèle imprimé est une copie parfaite de sa figure et obtient
presque tous les points ; le modèle d'un autre item n'est en général pas
reconnu. Faute d'écart net, le numéro reste incertain.
"""

from __future__ import annotations

from .criteria import score_item
from .ink import printed_mask
from .layout import PreparedPage, guess_page_numbers, uncertain_guesses
from .strokes import extract_drawing

MODEL_MIN_SCORE = 0.7  # part des critères remplis par les modèles de la bonne page
MODEL_MARGIN = 0.3  # avance minimale sur les autres pages candidates


def model_score(page: PreparedPage, number: int) -> float:
    """Part des critères remplis par les modèles imprimés de la page, notés
    comme les items de la page ``number`` du cahier (gardée en cache)."""
    if number not in page.model_scores:
        layout = page.layout(number)
        met = total = 0
        for zone in layout.zones:
            x0, y0, x1, y1 = zone.model_box
            drawing = extract_drawing(printed_mask(layout.image[y0:y1, x0:x1]), layout.px_per_mm)
            result = score_item(zone.item, drawing)
            met += sum(criterion.score for criterion in result.criteria.values())
            total += len(result.criteria)
        page.model_scores[number] = met / total if total else 0.0
    return page.model_scores[number]


def best_match(page: PreparedPage, candidates) -> int | None:
    """La page candidate dont les modèles imprimés correspondent nettement, ou
    ``None`` si aucune ne se détache."""
    scores = {number: model_score(page, number) for number in candidates}
    if not scores:
        return None
    best = max(scores, key=scores.get)
    if scores[best] >= MODEL_MIN_SCORE and all(scores[best] - score >= MODEL_MARGIN
                                               for number, score in scores.items()
                                               if number != best):
        return best
    return None


def resolve(pages: list[PreparedPage],
            fixed: dict[int, int] | None = None) -> tuple[list[int], set[int]]:
    """Numéros de page des scans et scans dont le numéro reste incertain.

    Les scans que leur structure ne suffit pas à numéroter sont départagés par
    leurs modèles imprimés, parmi toutes les pages de même structure : des
    modèles nettement reconnus l'emportent sur l'ordre supposé des scans. Un
    numéro ainsi trouvé compte comme un choix sûr pour la suite. ``fixed`` :
    numéros choisis à la main (index -> numéro).
    """
    fixed = dict(fixed or {})
    while True:
        for index in sorted(uncertain_guesses(pages, fixed)):
            match = best_match(pages[index], pages[index].compatible_pages())
            if match is not None:
                fixed[index] = match
                break
        else:
            break
    return guess_page_numbers(pages, fixed), uncertain_guesses(pages, fixed)


def better_page(page: PreparedPage, number: int) -> int | None:
    """Une autre page du cahier dont les modèles imprimés correspondent
    nettement mieux que ceux de la page ``number`` (scans dans le désordre,
    mauvais choix de page), ou ``None``."""
    if model_score(page, number) >= MODEL_MIN_SCORE:
        return None
    others = [n for n in page.compatible_pages() if n != number]
    match = best_match(page, [number, *others]) if others else None
    return match if match != number else None

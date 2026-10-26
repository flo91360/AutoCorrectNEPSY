"""Critères de cotation, item par item."""

from __future__ import annotations

import sys
from typing import Callable, NamedTuple

from ..strokes import Drawing
from . import (item_01_02, item_03, item_04, item_05, item_06, item_07, item_08, item_09,
               item_10, item_11, item_12, item_13, item_14, item_15, item_16,
               item_17, item_18, item_19, item_20, item_21)
from .base import CODES, PROCESS_NAMES, Criterion, ItemResult, Threshold

SCORERS: dict[int, Callable[[Drawing, int], ItemResult]] = {
    1: item_01_02.score,
    2: item_01_02.score,
    3: item_03.score,
    4: item_04.score,
    5: item_05.score,
    6: item_06.score,
    7: item_07.score,
    8: item_08.score,
    9: item_09.score,
    10: item_10.score,
    11: item_11.score,
    12: item_12.score,
    13: item_13.score,
    14: item_14.score,
    15: item_15.score,
    16: item_16.score,
    17: item_17.score,
    18: item_18.score,
    19: item_19.score,
    20: item_20.score,
    21: item_21.score,
}

SUPPORTED_ITEMS = tuple(sorted(SCORERS))


def score_item(item: int, drawing: Drawing) -> ItemResult:
    if item not in SCORERS:
        raise KeyError(f"item {item} pas encore pris en charge (items {SUPPORTED_ITEMS})")
    return SCORERS[item](drawing, item)


class ManualThreshold(NamedTuple):
    items: tuple[int, ...]  # items notés par le module qui déclare le seuil
    name: str  # nom de la constante dans le module
    threshold: Threshold


def all_manual_thresholds() -> list[ManualThreshold]:
    """Seuils du manuel déclarés par les modules d'items, dans l'ordre des items
    puis de leur déclaration (une plage compte pour deux seuils)."""
    found = []
    for module in dict.fromkeys(sys.modules[f.__module__] for f in SCORERS.values()):
        items = tuple(i for i, f in SCORERS.items() if f.__module__ == module.__name__)
        for name, value in vars(module).items():
            values = value if isinstance(value, tuple) else (value,)
            found += [ManualThreshold(items, name, v) for v in values
                      if isinstance(v, Threshold) and v.module == module.__name__]
    return found


__all__ = ["CODES", "PROCESS_NAMES", "Criterion", "ItemResult", "ManualThreshold",
           "SUPPORTED_ITEMS", "all_manual_thresholds", "score_item"]

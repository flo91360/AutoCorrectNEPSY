"""Critères de cotation, item par item."""

from __future__ import annotations

from typing import Callable

from ..strokes import Drawing
from . import (item_01_02, item_03, item_04, item_05, item_06, item_07, item_08, item_09,
               item_10, item_11)
from .base import CODES, PROCESS_NAMES, Criterion, ItemResult

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
}

SUPPORTED_ITEMS = tuple(sorted(SCORERS))


def score_item(item: int, drawing: Drawing) -> ItemResult:
    if item not in SCORERS:
        raise KeyError(f"item {item} pas encore pris en charge (items {SUPPORTED_ITEMS})")
    return SCORERS[item](drawing, item)


__all__ = ["CODES", "PROCESS_NAMES", "Criterion", "ItemResult", "SUPPORTED_ITEMS", "score_item"]

"""Structures communes : critère, résultat d'un item, liste de vérifications."""

from __future__ import annotations

from dataclasses import dataclass, field

CODES = ("G", "A", "B", "C", "D", "E", "F")
PROCESS_NAMES = {"G": "Général", "A": "Motricité A", "B": "Motricité B",
                 "C": "Global C", "D": "Global D", "E": "Local E", "F": "Local F"}


# Une mesure est « limite » si elle est à moins de 5 % du seuil, avec une
# marge minimale qui tient compte de la précision du scan et du tracé.
BORDERLINE_FRACTION = 0.05
BORDERLINE_MIN = {"mm": 0.5, "deg": 2.0, "ratio": 0.03, "part": 0.02}


@dataclass
class Criterion:
    code: str
    met: bool
    details: list[str]
    borderline: bool = False  # une mesure proche du seuil peut faire basculer la note

    @property
    def score(self) -> int:
        return int(self.met)


class Checks:
    """Accumule les conditions d'un critère : il est rempli si toutes le sont."""

    def __init__(self) -> None:
        self._items: list[tuple[bool, str, bool]] = []

    def add(self, ok: bool, text: str, near: bool = False) -> "Checks":
        self._items.append((bool(ok), text, near))
        return self

    def fail(self, text: str) -> "Checks":
        return self.add(False, text)

    def limit(self, value: float, text: str, low: float | None = None,
              high: float | None = None, unit: str = "mm") -> "Checks":
        """Condition chiffrée ``low <= value <= high`` (bornes facultatives)."""
        ok = (low is None or value >= low) and (high is None or value <= high)
        near = any(abs(value - t) <= max(BORDERLINE_FRACTION * abs(t), BORDERLINE_MIN[unit])
                   for t in (low, high) if t is not None)
        return self.add(ok, text, near)

    def criterion(self, code: str) -> Criterion:
        met = bool(self._items) and all(ok for ok, _, _ in self._items)
        failing = [near for ok, _, near in self._items if not ok]
        if met:
            borderline = any(near for _, _, near in self._items)
        else:
            borderline = len(failing) == 1 and failing[0]
        details = [("✓ " if ok else "✗ ") + text + (" (limite)" if near else "")
                   for ok, text, near in self._items]
        return Criterion(code, met, details, borderline)


@dataclass
class ItemResult:
    item: int
    criteria: dict[str, Criterion]
    measures: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def score(self, code: str) -> int | None:
        criterion = self.criteria.get(code)
        return None if criterion is None else criterion.score

    def total(self, *codes: str) -> int | None:
        scores = [self.score(code) for code in codes]
        return None if any(s is None for s in scores) else sum(scores)

    @property
    def motricite(self) -> int | None:
        return self.total("A", "B")

    @property
    def global_(self) -> int | None:
        return self.total("C", "D")

    @property
    def local(self) -> int | None:
        return self.total("E", "F")

    @property
    def to_review(self) -> bool:
        """L'ergothérapeute devrait vérifier cet item."""
        return bool(self.notes) or any(c.borderline for c in self.criteria.values())


def empty_result(item: int, codes: tuple[str, ...], reason: str) -> ItemResult:
    """Résultat d'un item sans dessin exploitable : tous les critères à 0."""
    return ItemResult(item, {code: Checks().fail(reason).criterion(code) for code in codes},
                      notes=[reason])


def fmt(value: float, unit: str = "mm") -> str:
    """Nombre au format français (virgule décimale)."""
    text = f"{value:.1f}".replace(".", ",")
    return f"{text} {unit}" if unit else text


def fmt_ratio(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + ":1"

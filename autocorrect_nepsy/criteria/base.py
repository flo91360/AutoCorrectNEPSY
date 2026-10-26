"""Structures communes : seuils du manuel, critère, résultat d'un item, liste de
vérifications et échafaudage de la cotation d'un item."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

CODES = ("G", "A", "B", "C", "D", "E", "F")
PROCESS_NAMES = {"G": "Général", "A": "Motricité A", "B": "Motricité B",
                 "C": "Global C", "D": "Global D", "E": "Local E", "F": "Local F"}


# Une mesure est « limite » si elle est à moins de 5 % du seuil, avec une
# marge minimale qui tient compte de la précision du scan et du tracé.
BORDERLINE_FRACTION = 0.05
BORDERLINE_MIN = {"mm": 0.5, "deg": 2.0, "ratio": 0.03, "part": 0.02}
THRESHOLD_UNITS = (*BORDERLINE_MIN, "nombre")


class Threshold:
    """Seuil chiffré du manuel, reformulé (jamais recopié). Le nombre s'emploie
    tel quel dans les calculs et garde le ou les critères qu'il sert, son unité
    et une description, pour la liste des seuils (``autocorrect-nepsy seuils``).

    Les autres constantes des modules d'items sont des réglages internes de
    l'outil (reconnaissance des figures, tolérances de mesure), absents du manuel.
    """

    codes: str
    unit: str
    description: str
    module: str

    @property
    def text(self) -> str:
        """Valeur telle qu'écrite dans les textes de cotation (voir ``fmt_limit``)."""
        return fmt_limit(self, self.unit)


class FloatThreshold(Threshold, float):
    pass


class IntThreshold(Threshold, int):
    pass


def manual_thresholds(module: str):
    """Fabrique des seuils du manuel d'un module d'item, à créer une fois en tête
    du module : ``threshold = manual_thresholds(__name__)``, puis par exemple
    ``MAX_RATIO = threshold(2.0, "G", "rapport des côtés, au plus", "ratio")``."""
    def threshold(value: float, codes: str, description: str,
                  unit: str = "mm") -> FloatThreshold | IntThreshold:
        if not codes or any(code not in CODES for code in codes):
            raise ValueError(f"critère(s) inconnu(s) : {codes!r}")
        if unit not in THRESHOLD_UNITS:
            raise ValueError(f"unité inconnue : {unit!r}")
        made = IntThreshold(value) if isinstance(value, int) else FloatThreshold(value)
        made.codes, made.description, made.unit, made.module = codes, description, unit, module
        return made
    return threshold


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
    marks: list = field(default_factory=list)  # repères de mesure (voir marks.py)

    def score(self, code: str) -> int | None:
        criterion = self.criteria.get(code)
        return None if criterion is None else criterion.score

    @property
    def to_review(self) -> bool:
        """L'ergothérapeute devrait vérifier cet item."""
        return bool(self.notes) or any(c.borderline for c in self.criteria.values())


def empty_result(item: int, codes: tuple[str, ...], reason: str) -> ItemResult:
    """Résultat d'un item sans dessin exploitable : tous les critères à 0."""
    return ItemResult(item, {code: Checks().fail(reason).criterion(code) for code in codes},
                      notes=[reason])


def not_recognized(checks: dict[str, Checks], codes: Iterable[str], reason: str,
                   notes: list[str]) -> None:
    """La figure du modèle n'est pas retrouvée dans le dessin : les critères ``codes``
    échouent et l'item est à vérifier. L'enfant a peut-être dessiné autre chose, mais
    l'outil a aussi pu mal lire un dessin correct (coins arrondis, traits mal fermés)."""
    for code in codes:
        checks[code].fail(reason)
    notes.append(unrecognized_note(reason))


class Scoring:
    """Échafaudage commun de la cotation d'un item : les conditions de chaque
    critère (``scoring["A"]``), les mesures, les notes « à vérifier » et les
    repères de mesure, réunis en ``ItemResult`` par ``result()``. Le dessin vide
    et la figure non reconnue sont traités ici, de la même façon pour tous les
    items."""

    def __init__(self, item: int, codes: Iterable[str]):
        self.item = item
        self.codes = tuple(codes)
        self.checks = {code: Checks() for code in self.codes}
        self.measures: dict[str, float] = {}
        self.notes: list[str] = []
        self.marks: list = []

    def __getitem__(self, code: str) -> Checks:
        return self.checks[code]

    def empty(self, reason: str = "aucun tracé dans la zone") -> ItemResult:
        """Pas de dessin exploitable : tous les critères à 0, item à vérifier."""
        return empty_result(self.item, self.codes, reason)

    def not_recognized(self, codes: Iterable[str], reason: str) -> None:
        """Voir ``not_recognized`` : les critères ``codes`` échouent, item à vérifier."""
        not_recognized(self.checks, codes, reason, self.notes)

    def result(self) -> ItemResult:
        return ItemResult(self.item, {code: self.checks[code].criterion(code)
                                      for code in self.codes},
                          self.measures, self.notes, self.marks)


def unrecognized_note(reason: str) -> str:
    return f"{reason} : vérifier la cotation, l'outil a pu mal lire le dessin"


def fmt(value: float, unit: str = "mm") -> str:
    """Nombre au format français (virgule décimale)."""
    text = f"{value:.1f}".replace(".", ",")
    return f"{text} {unit}" if unit else text


def fmt_limit(value: float, unit: str = "mm") -> str:
    """Seuil tel qu'écrit dans les textes de cotation, sans zéro inutile :
    « 70 mm », « 1,5 mm », « 30° », « 1,3:1 », « 50 % », « 3 »."""
    value = round(float(value) * 100, 1) if unit == "part" else float(value)
    number = f"{value:g}".replace(".", ",")
    return {"mm": f"{number} mm", "deg": f"{number}°", "ratio": f"{number}:1",
            "part": f"{number} %"}.get(unit, number)


def fmt_ratio(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + ":1"

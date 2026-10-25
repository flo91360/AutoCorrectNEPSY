"""Lignes courbes suivies le long de l'encre, d'un bout libre à un autre.

Quand deux courbes se croisent, les traits reconstruits peuvent mal se
raccorder au croisement (petite tache, retouche). On relie donc tous les points
des traits en un graphe (voisins le long d'un trait, traits qui se touchent,
bouts repris un peu plus loin) et chaque courbe est le plus court chemin
d'encre entre deux bouts libres.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np

from ..strokes import Stroke

LINK_MM = 1.2  # deux traits qui se touchent (croisement, jonction)
GAP_MM = 3.0  # trait repris un peu plus loin : l'interruption est franchie
INTERRUPTION_STEP_MM = 0.8  # saut plus grand le long d'un chemin : interruption


@dataclass
class Curve:
    """Courbe suivie d'un bout à l'autre (points ordonnés, en mm)."""

    points: np.ndarray
    interruptions: int

    @property
    def start(self) -> np.ndarray:
        return self.points[0]

    @property
    def end(self) -> np.ndarray:
        return self.points[-1]

    @property
    def chord(self) -> np.ndarray:
        return self.end - self.start

    @property
    def chord_length(self) -> float:
        return float(np.linalg.norm(self.chord))

    def reversed(self) -> "Curve":
        return Curve(self.points[::-1].copy(), self.interruptions)

    def offsets(self) -> np.ndarray:
        """Écart signé de chaque point à la corde (positif à droite en
        parcourant la corde, l'axe des y de l'image allant vers le bas)."""
        chord = self.chord
        norm = max(np.linalg.norm(chord), 1e-9)
        rel = self.points - self.start
        return (chord[0] * rel[:, 1] - chord[1] * rel[:, 0]) / norm


def extrema(values: np.ndarray, amplitude: float) -> list[tuple[int, float]]:
    """Extremums (indice, valeur) d'une suite, en ignorant les oscillations
    plus petites que ``amplitude`` (crêtes et creux d'une courbe)."""
    found: list[tuple[int, float]] = []
    direction, pivot, at = 0, values[0], 0
    for i, value in enumerate(values[1:], start=1):
        if direction == 0:
            if abs(value - values[0]) >= amplitude:
                direction = 1 if value > values[0] else -1
                pivot, at = value, i
        elif direction * (value - pivot) > 0:
            pivot, at = value, i
        elif abs(value - pivot) >= amplitude:
            found.append((at, float(pivot)))
            direction, pivot, at = -direction, value, i
    return found


class InkGraph:
    """Points des traits reliés le long des traits et entre traits proches."""

    def __init__(self, strokes: list[Stroke]):
        self.strokes = [s for s in strokes if len(s.points) >= 2]
        sizes = [len(s.points) for s in self.strokes]
        self.offsets = np.cumsum([0] + sizes)
        self.points = (np.vstack([s.points for s in self.strokes]) if self.strokes
                       else np.zeros((0, 2)))
        self.neighbors: list[list[tuple[int, float]]] = [[] for _ in range(len(self.points))]
        for k, stroke in enumerate(self.strokes):
            first, last = self.offsets[k], self.offsets[k + 1] - 1
            for i in range(first, last):
                self._link(i, i + 1)
            if stroke.closed:
                self._link(last, first)
        for k in range(len(self.strokes)):
            for j in range(k + 1, len(self.strokes)):
                self._link_strokes(k, j)

    def _link(self, i: int, j: int) -> None:
        d = float(np.linalg.norm(self.points[i] - self.points[j]))
        self.neighbors[i].append((j, d))
        self.neighbors[j].append((i, d))

    def _ends(self, k: int) -> list[int]:
        if self.strokes[k].closed:
            return []
        return [int(self.offsets[k]), int(self.offsets[k + 1] - 1)]

    def _link_strokes(self, k: int, j: int) -> None:
        a = self.points[self.offsets[k]:self.offsets[k + 1]]
        b = self.points[self.offsets[j]:self.offsets[j + 1]]
        dist = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
        if dist.min() > GAP_MM:
            return
        # Traits qui se touchent : chaque point proche est relié au plus proche de l'autre trait.
        for i in np.nonzero(dist.min(axis=1) <= LINK_MM)[0]:
            self._link(int(self.offsets[k] + i), int(self.offsets[j] + np.argmin(dist[i])))
        # Bout de trait repris plus loin : relié par-dessus l'interruption.
        for end in self._ends(k):
            i = end - self.offsets[k]
            if LINK_MM < dist[i].min() <= GAP_MM:
                self._link(end, int(self.offsets[j] + np.argmin(dist[i])))
        for end in self._ends(j):
            i = end - self.offsets[j]
            if LINK_MM < dist[:, i].min() <= GAP_MM:
                self._link(end, int(self.offsets[k] + np.argmin(dist[:, i])))

    def free_ends(self) -> list[int]:
        """Bouts de traits qui ne touchent aucun autre trait : extrémités des lignes."""
        found = []
        for k in range(len(self.strokes)):
            others = np.vstack([self.points[:self.offsets[k]], self.points[self.offsets[k + 1]:]])
            for end in self._ends(k):
                if len(others) == 0 or np.sqrt(((others - self.points[end]) ** 2)
                                                .sum(-1)).min() > GAP_MM:
                    found.append(end)
        return found

    def path(self, source: int, target: int) -> Curve | None:
        """Plus court chemin d'encre entre deux points du graphe."""
        best = np.full(len(self.points), np.inf)
        previous = np.full(len(self.points), -1)
        best[source] = 0.0
        queue = [(0.0, source)]
        while queue:
            d, i = heapq.heappop(queue)
            if i == target:
                break
            if d > best[i]:
                continue
            for j, w in self.neighbors[i]:
                if d + w < best[j]:
                    best[j], previous[j] = d + w, i
                    heapq.heappush(queue, (d + w, j))
        if not np.isfinite(best[target]):
            return None
        order = [target]
        while order[-1] != source:
            order.append(int(previous[order[-1]]))
        points = self.points[order[::-1]]
        steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        return Curve(points, int((steps > INTERRUPTION_STEP_MM).sum()))


def crossing(a: Curve, b: Curve) -> np.ndarray:
    """Point où deux courbes se croisent (ou se rapprochent le plus)."""
    dist = np.sqrt(((a.points[:, None, :] - b.points[None, :, :]) ** 2).sum(-1))
    shared = dist.min(axis=1) <= 0.5
    if shared.any():
        return a.points[shared].mean(axis=0)
    i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
    return (a.points[i] + b.points[j]) / 2

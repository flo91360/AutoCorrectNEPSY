"""Repères de mesure à dessiner sur les traits lus par l'outil, dans le
rapport, pour que l'ergothérapeute puisse vérifier chaque mesure.

Coordonnées en mm, dans le repère de la zone de dessin de l'item.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import geometry as geo
from ..strokes import StraightLine


@dataclass
class Mark:
    # « cote » : longueur entre deux points, reportée à côté du dessin ;
    # « segment » : mesure tracée sur le dessin (diamètre, section droite) ;
    # « angle » : arc au sommet ``points[0]`` entre ``points[1]`` et ``points[2]`` ;
    # « bande » : rectangle de la barre grisée (quatre coins) ;
    # « point » : point remarquable (jonction, intersection) ;
    # « cercle » : cercle de centre ``points[0]`` et de rayon ``radius``.
    kind: str
    points: list[np.ndarray]
    label: str
    radius: float = 0.0
    extra: dict = field(default_factory=dict)


def cote(a, b, label: str, side=None) -> Mark:
    """Longueur entre ``a`` et ``b``. ``side`` : direction (vecteur) où reporter
    la cote ; par défaut, à l'opposé du centre du dessin."""
    extra = {} if side is None else {"side": np.asarray(side, float)}
    return Mark("cote", [np.asarray(a, float), np.asarray(b, float)], label, extra=extra)


def segment(a, b, label: str) -> Mark:
    return Mark("segment", [np.asarray(a, float), np.asarray(b, float)], label)


def angle(vertex, p1, p2, label: str) -> Mark:
    return Mark("angle", [np.asarray(vertex, float), np.asarray(p1, float),
                          np.asarray(p2, float)], label)


def point(p, label: str) -> Mark:
    return Mark("point", [np.asarray(p, float)], label)


def cercle(center, radius: float, label: str) -> Mark:
    return Mark("cercle", [np.asarray(center, float)], label, radius=radius)


def bande(line: StraightLine, label: str | None = None, at: str = "milieu") -> Mark:
    """Barre grisée de la ligne, encre comprise (même largeur que ``line.width``).

    ``at`` : étiquette au « milieu » de la bande (côté intérieur du dessin) ou
    au « bout » le plus éloigné du centre, quand les milieux se croisent."""
    _, corners = geo.min_strip(line.points)
    across = corners[3] - corners[0]
    norm = np.linalg.norm(across)
    unit = across / norm if norm > 0 else np.array([-line.direction[1], line.direction[0]])
    half_ink = unit * line.stroke_width / 2
    corners = np.array([corners[0] - half_ink, corners[1] - half_ink,
                        corners[2] + half_ink, corners[3] + half_ink])
    text = label or f"bande {line.width:.1f} mm".replace(".", ",")
    return Mark("bande", list(corners), text, extra={"at": at})


def line_length(line: StraightLine) -> Mark:
    a, b = line.ends
    return cote(a, b, f"{line.length:.1f} mm".replace(".", ","))

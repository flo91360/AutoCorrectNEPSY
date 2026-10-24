"""Fabrique un scan PDF synthétique (page 2 du cahier) pour tester l'exécutable."""

import sys
from pathlib import Path

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from synth import page  # noqa: E402

rgb = cv2.cvtColor(page({0: 4, 1: 5, 2: 6, 3: 7}), cv2.COLOR_BGR2RGB)
Image.fromarray(rgb).rotate(180).save(sys.argv[1], "PDF", resolution=100)

"""Construit l'exécutable autonome (AutoCorrectNEPSY.exe sous Windows).

    python -m pip install -e ".[exe]"
    python packaging/build.py
"""

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autocorrect_nepsy.gui import app_icon  # noqa: E402

icon = ROOT / "build" / "icone.ico"
icon.parent.mkdir(exist_ok=True)
app_icon(256).save(icon, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

PyInstaller.__main__.run([
    str(ROOT / "packaging" / "AutoCorrectNEPSY.py"),
    "--name", "AutoCorrectNEPSY",
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    "--icon", str(icon),
    # Pillow charge ce module dynamiquement pour afficher les images dans Tk.
    "--hidden-import", "PIL._tkinter_finder",
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
])

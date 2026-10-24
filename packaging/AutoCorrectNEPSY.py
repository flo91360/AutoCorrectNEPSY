"""Point d'entrée de l'exécutable : la fenêtre, ou la ligne de commande si des
arguments sont donnés (utilisé pour tester l'exécutable automatiquement).

``--test-interface [scan.pdf]`` ouvre la fenêtre, corrige le scan donné puis
referme la fenêtre : sert à vérifier en intégration continue que l'exécutable
embarque tout ce qu'il faut.
"""

import os
import sys
import traceback

if __name__ == "__main__":
    # Un exécutable sans console n'a pas de sortie standard.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.argv[1:2] == ["--test-interface"]:
        try:
            import time
            import tkinter as tk
            from pathlib import Path

            from autocorrect_nepsy.gui import App

            def wait(condition, timeout=120):
                end = time.time() + timeout
                while not condition():
                    root.update()
                    time.sleep(0.05)
                    if time.time() > end:
                        raise TimeoutError("délai dépassé")

            root = tk.Tk()
            app = App(root)
            root.update()
            scans = [Path(arg) for arg in sys.argv[2:]]
            if scans:
                app.add_paths(scans)
                wait(lambda: app.rows and not app.busy)
                app.run_correction()
                wait(lambda: app.correction is not None and not app.busy)
                if not (app.output / "rapport.html").exists():
                    raise RuntimeError("rapport.html absent")
            root.destroy()
        except Exception:
            with open("test-interface-erreur.txt", "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            sys.exit(1)
        sys.exit(0)
    if len(sys.argv) > 1:
        from autocorrect_nepsy.cli import main as cli_main

        sys.exit(cli_main())
    from autocorrect_nepsy.gui import main as gui_main

    gui_main()

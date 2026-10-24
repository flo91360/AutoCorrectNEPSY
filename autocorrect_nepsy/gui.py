"""Interface graphique : ajouter les scans, lancer la correction, lire les notes.

Pensée pour un usage sans ligne de commande : tout se fait à la souris, les
calculs tournent en arrière-plan et les résultats sont enregistrés tout seuls à
côté des scans.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .compare import format_comparison, pair_scores, read_scores
from .criteria import SUPPORTED_ITEMS
from .ink import INK_HUES
from .layout import ITEMS_BY_PAGE, LayoutError, PreparedPage, guess_page_numbers, prepare_page
from .pipeline import Correction, PageInput, correct_pages, page_label
from .report import save_results, score_row, totals
from .scan import ScannedPage, load_pages

APP_NAME = "AutoCorrect NEPSY"
SCAN_TYPES = [("Scans (PDF, images)", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
              ("Tous les fichiers", "*.*")]
PAGE_LABELS = {page_label(number): number for number in ITEMS_BY_PAGE}
THUMB_WIDTH = 180
REVIEW_COLOR = "#fde7c4"
TOTAL_COLOR = "#e8eef8"
HELP_TEXT = f"""Comment corriger un protocole

1. Scannez chaque page du cahier de réponses remplie par l'enfant, à 200 dpi au moins (300 dpi conseillés), en taille réelle. Le sens du scan n'a pas d'importance.

2. Cliquez sur « Ajouter des scans » et choisissez les fichiers (PDF ou images).

3. Vérifiez pour chaque scan la page du cahier proposée (les numéros d'items sont imprimés sur la vignette) et sa résolution.

4. Cliquez sur « Lancer la correction automatique ».

Les notes s'affichent à droite. Les lignes surlignées sont « à vérifier » : une mesure est proche d'un seuil ou le dessin est ambigu. Le rapport détaillé montre chaque dessin et les mesures qui justifient chaque note. Les résultats sont enregistrés dans un dossier « Correction NEPSY » à côté des scans.

L'enfant doit dessiner au stylo de couleur (bleu par défaut). Les annotations au crayon à papier sont ignorées.

Prototype : items {SUPPORTED_ITEMS[0]} à {SUPPORTED_ITEMS[-1]}. La cotation proposée doit être validée par l'ergothérapeute."""


@dataclass
class ScanRow:
    """Une page scannée dans la liste, avec ses réglages."""

    path: Path
    scan: ScannedPage
    prepared: PreparedPage | None = None
    error: str | None = None
    manual_page: bool = False
    page_var: tk.StringVar | None = None
    dpi_var: tk.StringVar | None = None
    status: ttk.Label | None = None
    frame: ttk.Frame | None = None
    thumbnail: ImageTk.PhotoImage | None = None

    def number(self) -> int | None:
        return PAGE_LABELS.get(self.page_var.get()) if self.page_var else None

    def dpi(self) -> float | None:
        try:
            value = float(self.dpi_var.get().replace(",", "."))
        except (AttributeError, ValueError):
            return None
        return value if 50 <= value <= 2400 else None


def app_icon(size: int = 256) -> Image.Image:
    """Icône : un cercle et un carré (des figures à copier) sur fond bleu."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 256
    draw.rounded_rectangle((8 * s, 8 * s, 248 * s, 248 * s), radius=48 * s, fill=(37, 99, 235))
    width = max(2, int(16 * s))
    draw.ellipse((40 * s, 40 * s, 150 * s, 150 * s), outline="white", width=width)
    draw.rectangle((106 * s, 106 * s, 216 * s, 216 * s), outline="white", width=width)
    return image


def natural_key(path: Path) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def results_folder(first_scan: Path) -> Path:
    """Dossier de résultats daté, à côté des scans (ou dans Documents)."""
    name = f"Correction NEPSY {datetime.now():%Y-%m-%d %Hh%M}"
    for base in (first_scan.parent, Path.home() / "Documents" / "AutoCorrectNEPSY", Path.home()):
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".autocorrect_test"
            probe.write_text("")
            probe.unlink()
            return base / name
        except OSError:
            continue
    return Path.cwd() / name


def open_path(path: Path, anchor: str = "") -> None:
    """Ouvre un fichier ou un dossier avec l'application par défaut."""
    if path.suffix == ".html":
        webbrowser.open(path.resolve().as_uri() + anchor)
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def thumbnail(row: ScanRow) -> Image.Image:
    """Vignette de la page dans le sens de passation, zones repérées en vert."""
    image = row.prepared.image if row.prepared else row.scan.image
    scale = THUMB_WIDTH / image.shape[1]
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    pil = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    if row.prepared:
        draw = ImageDraw.Draw(pil)
        sep = row.prepared.separator
        y = sep.pos * scale
        draw.line((sep.start * scale, y, sep.end * scale, y), fill=(22, 163, 74), width=2)
        for x0, x1 in row.prepared.columns:
            draw.rectangle((x0 * scale, row.prepared.top * scale, x1 * scale,
                            row.prepared.bottom * scale), outline=(22, 163, 74), width=1)
    return pil


class Worker:
    """Exécute les calculs dans un fil séparé et rend la main à Tk."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        root.after(100, self._poll)

    def run(self, task, on_done, on_error) -> None:
        def target():
            try:
                self.events.put((on_done, task()))
            except Exception as error:  # noqa: BLE001 - toute erreur est montrée à l'utilisateur
                self.events.put((on_error, (error, traceback.format_exc())))
        threading.Thread(target=target, daemon=True).start()

    def post(self, callback, value) -> None:
        self.events.put((callback, value))

    def _poll(self) -> None:
        while True:
            try:
                callback, value = self.events.get_nowait()
            except queue.Empty:
                break
            callback(value)
        self.root.after(100, self._poll)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.rows: list[ScanRow] = []
        self.worker = Worker(root)
        self.busy = False
        self.correction: Correction | None = None
        self.output: Path | None = None
        self.ink_var = tk.StringVar(value="bleu")
        root.title(f"{APP_NAME} – Copie de figures (version {__version__})")
        root.geometry("1260x780")
        root.minsize(1100, 640)
        self._icon = ImageTk.PhotoImage(app_icon(64))
        root.iconphoto(True, self._icon)
        self._styles()
        self._build()

    # -- construction de la fenêtre -------------------------------------------
    def _styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" not in style.theme_names() and "clam" in style.theme_names():
            style.theme_use("clam")
        base = ("Segoe UI", 10) if sys.platform.startswith("win") else ("TkDefaultFont", 10)
        style.configure("Title.TLabel", font=(base[0], 16, "bold"))
        style.configure("Step.TLabel", font=(base[0], 12, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Name.TLabel", font=(base[0], 10, "bold"))
        style.configure("Ok.TLabel", foreground="#15803d")
        style.configure("Warn.TLabel", foreground="#b45309")
        style.configure("Big.TButton", font=(base[0], 12, "bold"), padding=(16, 10))
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=(base[0], 9, "bold"))

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(16, 12, 16, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Correction automatique – Copie de figures (NEPSY-II)",
                  style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Aide", command=self.show_help).pack(side="right")
        ttk.Label(self.root, text=f"Prototype : items {SUPPORTED_ITEMS[0]} à {SUPPORTED_ITEMS[-1]}. "
                  "La cotation proposée est à valider par l'ergothérapeute.",
                  style="Hint.TLabel", padding=(16, 0, 16, 8)).pack(fill="x")

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        left = ttk.Frame(panes, padding=6)
        right = ttk.Frame(panes, padding=6)
        panes.add(left, weight=1)
        panes.add(right, weight=1)
        self._build_scans(left)
        self._build_results(right)
        # Le panneau des scans a besoin de place pour ses réglages.
        self.root.after(50, lambda: panes.sashpos(0, 560))

        bar = ttk.Frame(self.root, padding=(16, 4, 16, 10))
        bar.pack(fill="x")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=260)
        self.progress.pack(side="left")
        self.status = ttk.Label(bar, text="Ajoutez les pages scannées du cahier de l'enfant.")
        self.status.pack(side="left", padx=12)

    def _build_scans(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="1. Scans du cahier de l'enfant", style="Step.TLabel").pack(anchor="w")
        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=6)
        self.add_button = ttk.Button(buttons, text="＋  Ajouter des scans…", command=self.add_scans)
        self.add_button.pack(side="left")
        self.clear_button = ttk.Button(buttons, text="Tout retirer", command=self.clear_scans)
        self.clear_button.pack(side="left", padx=6)

        holder = ttk.Frame(parent, relief="groove", borderwidth=1)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, highlightthickness=0, background="#ffffff")
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, background="#ffffff")
        self.list_frame.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))
        self.empty_hint = tk.Label(
            self.list_frame, background="#ffffff", foreground="#666666", justify="left",
            wraplength=440, padx=12, pady=16,
            text="Aucun scan pour l'instant.\n\nCliquez sur « Ajouter des scans… » et choisissez "
                 "les pages scannées (PDF ou images). Le sens du scan n'a pas d'importance : "
                 "chaque page est remise à l'endroit automatiquement.")
        self.empty_hint.pack(fill="x")

        options = ttk.Frame(parent)
        options.pack(fill="x", pady=(10, 4))
        ttk.Label(options, text="2. Couleur du stylo de l'enfant :", style="Step.TLabel").pack(side="left")
        for color in INK_HUES:
            ttk.Radiobutton(options, text=color, value=color, variable=self.ink_var,
                            command=self.ink_changed).pack(side="left", padx=6)

        self.run_button = ttk.Button(parent, text="▶  Lancer la correction automatique",
                                     style="Big.TButton", command=self.run_correction,
                                     state="disabled")
        self.run_button.pack(fill="x", pady=(8, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="3. Résultats", style="Step.TLabel").pack(anchor="w")
        self.summary = ttk.Label(parent, text="Les notes apparaîtront ici après la correction.",
                                 style="Hint.TLabel", wraplength=640, justify="left")
        self.summary.pack(fill="x", pady=6)
        columns = [("item", "Item", 44), ("G", "Général", 58), ("A", "Mot. A", 52),
                   ("B", "Mot. B", 52), ("mot", "Motricité", 68), ("C", "Glob. C", 54),
                   ("D", "Glob. D", 54), ("glob", "Global", 52), ("E", "Loc. E", 50),
                   ("F", "Loc. F", 50), ("loc", "Local", 48), ("verif", "À vérifier", 70)]
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in columns], show="headings",
                                 selectmode="browse")
        for key, title, width in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=40, anchor="center", stretch=True)
        self.tree.tag_configure("review", background=REVIEW_COLOR)
        self.tree.tag_configure("total", background=TOTAL_COLOR)
        self.tree.bind("<Double-1>", self.open_item_report)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        ttk.Label(parent, text="Double-cliquez sur un item pour voir son dessin et le détail "
                  "des mesures.", style="Hint.TLabel").pack(anchor="w", pady=(4, 0))
        self.warnings = ttk.Label(parent, text="", style="Warn.TLabel", wraplength=640,
                                  justify="left")
        self.warnings.pack(fill="x", pady=(4, 0))

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(8, 0))
        self.report_button = ttk.Button(buttons, text="Ouvrir le rapport détaillé",
                                        command=self.open_report, state="disabled")
        self.report_button.pack(side="left")
        self.folder_button = ttk.Button(buttons, text="Ouvrir le dossier des résultats",
                                        command=self.open_folder, state="disabled")
        self.folder_button.pack(side="left", padx=6)
        self.compare_button = ttk.Button(buttons, text="Comparer à la cotation de l'ergo…",
                                         command=self.compare, state="disabled")
        self.compare_button.pack(side="left")

    def _on_wheel(self, event) -> None:
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None and widget is not self.canvas:
            widget = widget.master
        if widget is self.canvas:
            self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1),
                                     "units")

    # -- scans ----------------------------------------------------------------
    def add_scans(self) -> None:
        names = filedialog.askopenfilenames(title="Choisir les pages scannées",
                                            filetypes=SCAN_TYPES)
        if names:
            self.add_paths([Path(n) for n in names])

    def add_paths(self, paths: list[Path]) -> None:
        paths = sorted(paths, key=natural_key)
        ink = self.ink_var.get()

        def task():
            loaded = []
            for index, path in enumerate(paths):
                self.worker.post(self._progress, (index, len(paths), f"Lecture de {path.name}…"))
                try:
                    scans = load_pages(path)
                except Exception as error:  # noqa: BLE001
                    loaded.append((path, None, None, f"fichier illisible : {error}"))
                    continue
                for scan in scans:
                    try:
                        loaded.append((path, scan, prepare_page(scan, ink), None))
                    except LayoutError as error:
                        loaded.append((path, scan, None, str(error)))
            return loaded

        self._set_busy(True, "Analyse des scans…")
        self.worker.run(task, self._scans_loaded, self._failed)

    def _scans_loaded(self, loaded) -> None:
        self._set_busy(False)
        unreadable = [f"{path.name} : {error}" for path, scan, _, error in loaded if scan is None]
        for path, scan, prepared, error in loaded:
            if scan is not None:
                self.rows.append(ScanRow(path, scan, prepared, error))
        self._refresh_guesses()
        self._render_rows()
        self._update_status()
        if unreadable:
            messagebox.showwarning(APP_NAME, "Certains fichiers n'ont pas pu être lus :\n\n"
                                   + "\n".join(unreadable))

    def clear_scans(self) -> None:
        self.rows.clear()
        self._render_rows()
        self._update_status()

    def remove_row(self, row: ScanRow) -> None:
        self.rows.remove(row)
        self._refresh_guesses()
        self._render_rows()
        self._update_status()

    def ink_changed(self) -> None:
        if not self.rows:
            return
        ink = self.ink_var.get()
        rows = list(self.rows)

        def task():
            results = []
            for index, row in enumerate(rows):
                self.worker.post(self._progress, (index, len(rows), f"Nouvelle analyse de {row.path.name}…"))
                try:
                    results.append((prepare_page(row.scan, ink), None))
                except LayoutError as error:
                    results.append((None, str(error)))
            return results

        def done(results) -> None:
            self._set_busy(False)
            for row, (prepared, error) in zip(rows, results):
                row.prepared, row.error = prepared, error
            self._refresh_guesses()
            self._render_rows()
            self._update_status()

        self._set_busy(True, "Nouvelle analyse avec la couleur choisie…")
        self.worker.run(task, done, self._failed)

    def _refresh_guesses(self) -> None:
        ready = [row for row in self.rows if row.prepared]
        fixed = {i: row.number() for i, row in enumerate(ready) if row.manual_page and row.number()}
        for row, number in zip(ready, guess_page_numbers([r.prepared for r in ready], fixed)):
            if not row.manual_page:
                if row.page_var is None:
                    row.page_var = tk.StringVar()
                row.page_var.set(page_label(number))

    def _render_rows(self) -> None:
        for child in self.list_frame.winfo_children():
            if child is not self.empty_hint:
                child.destroy()
        if not self.rows:
            self.empty_hint.pack(fill="x")
            return
        self.empty_hint.pack_forget()
        for index, row in enumerate(self.rows):
            self._render_row(index, row)

    def _render_row(self, index: int, row: ScanRow) -> None:
        frame = tk.Frame(self.list_frame, background="#ffffff", padx=8, pady=8)
        frame.pack(fill="x")
        if index:
            ttk.Separator(self.list_frame).pack(fill="x", before=frame)
        row.frame = frame
        row.thumbnail = ImageTk.PhotoImage(thumbnail(row))
        tk.Label(frame, image=row.thumbnail, background="#ffffff", borderwidth=1,
                 relief="solid").grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, 10))
        ttk.Label(frame, text=row.scan.source, style="Name.TLabel", background="#ffffff").grid(
            row=0, column=1, columnspan=3, sticky="w")
        ttk.Button(frame, text="Retirer", width=8, command=lambda r=row: self.remove_row(r)).grid(
            row=0, column=4, sticky="e")

        ttk.Label(frame, text="Page du cahier :", background="#ffffff").grid(
            row=1, column=1, sticky="w", pady=2)
        if row.page_var is None:
            row.page_var = tk.StringVar(value=page_label(1))
        combo = ttk.Combobox(frame, textvariable=row.page_var, values=list(PAGE_LABELS),
                             state="readonly", width=21)
        combo.grid(row=1, column=2, columnspan=3, sticky="w", pady=2)
        combo.bind("<<ComboboxSelected>>", lambda _e, r=row: self._page_chosen(r))

        ttk.Label(frame, text="Résolution :", background="#ffffff").grid(row=2, column=1, sticky="w")
        if row.dpi_var is None:
            row.dpi_var = tk.StringVar(value=f"{row.scan.dpi:.0f}")
            row.dpi_var.trace_add("write", lambda *_a, r=row: self._update_row_status(r))
        dpi = tk.Frame(frame, background="#ffffff")
        dpi.grid(row=2, column=2, columnspan=3, sticky="w")
        ttk.Spinbox(dpi, from_=50, to=1200, increment=25, width=7,
                    textvariable=row.dpi_var).pack(side="left")
        ttk.Label(dpi, text="dpi", background="#ffffff").pack(side="left", padx=4)

        row.status = ttk.Label(frame, text="", background="#ffffff", wraplength=300, justify="left")
        row.status.grid(row=3, column=1, columnspan=4, sticky="w", pady=(4, 0))
        frame.columnconfigure(3, weight=1)
        self._update_row_status(row)

    def _page_chosen(self, row: ScanRow) -> None:
        row.manual_page = True
        self._refresh_guesses()
        for other in self.rows:
            self._update_row_status(other)

    def _row_problem(self, row: ScanRow) -> str | None:
        if row.error:
            return row.error
        if row.dpi() is None:
            return "résolution invalide (nombre de dpi entre 50 et 2400)"
        compatible = row.prepared.compatible_pages()
        if row.number() not in compatible:
            pages = ", ".join(str(n) for n in compatible)
            return f"cette page ressemble plutôt à la page {pages} du cahier"
        return None

    def _update_row_status(self, row: ScanRow) -> None:
        if row.status is None:
            return
        problem = self._row_problem(row)
        if problem:
            row.status.configure(text=f"⚠ {problem}", style="Warn.TLabel")
        else:
            row.status.configure(text="✓ Prête pour la correction", style="Ok.TLabel")
        self._update_status()

    def _update_status(self) -> None:
        if self.busy:
            return
        ready = [row for row in self.rows if not self._row_problem(row)]
        self.run_button.configure(state="normal" if ready else "disabled")
        if not self.rows:
            self.status.configure(text="Ajoutez les pages scannées du cahier de l'enfant.")
        else:
            self.status.configure(text=f"{len(ready)} page(s) prête(s) sur {len(self.rows)}.")

    # -- correction -----------------------------------------------------------
    def run_correction(self) -> None:
        ready = [row for row in self.rows if not self._row_problem(row)]
        skipped = [row for row in self.rows if row not in ready]
        if not ready:
            return
        numbers = [row.number() for row in ready]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            messagebox.showwarning(APP_NAME, "La même page du cahier est choisie pour plusieurs "
                                   f"scans (page {', '.join(map(str, duplicates))}). Corrigez le "
                                   "choix de page avant de lancer la correction.")
            return
        if skipped and not messagebox.askyesno(
                APP_NAME, f"{len(skipped)} scan(s) ont un problème (voir le message en orange) "
                "et seront ignorés. Continuer quand même ?"):
            return
        inputs = [PageInput(replace(row.scan, dpi=row.dpi()), row.number(), row.prepared)
                  for row in ready]
        ink = self.ink_var.get()
        first = ready[0].path

        def task():
            correction = correct_pages(
                inputs, ink, lambda i, n, src: self.worker.post(
                    self._progress, (i, n, f"Correction de {src}…" if src else "Rapport…")))
            folder = results_folder(first)
            save_results(correction, folder)
            return correction, folder

        self._set_busy(True, "Correction en cours…")
        self.worker.run(task, self._corrected, self._failed)

    def _corrected(self, result) -> None:
        self._set_busy(False)
        self.correction, self.output = result
        self.tree.delete(*self.tree.get_children())
        for report in self.correction.items:
            row = score_row(report)
            review = report.result.to_review
            values = [row["item"], row["general"], row["motricite_A"], row["motricite_B"],
                      row["motricite_total"], row["global_C"], row["global_D"],
                      row["global_total"], row["local_E"] or "–", row["local_F"] or "–",
                      row["local_total"] or "–", "⚠ oui" if review else ""]
            self.tree.insert("", "end", iid=str(report.item), values=values,
                             tags=("review",) if review else ())
        if self.correction.items:
            sums = totals(self.correction)
            self.tree.insert("", "end", iid="total", tags=("total",), values=[
                "Total", sums["general"], "", "", sums["motricite"], "", "", sums["global"],
                "", "", sums["local"], ""])
        items = [report.item for report in self.correction.items]
        to_review = sum(report.result.to_review for report in self.correction.items)
        self.summary.configure(
            text=f"{len(items)} item(s) corrigé(s) ({', '.join(map(str, items))}), dont "
                 f"{to_review} à vérifier (surlignés en orange).\nRésultats enregistrés dans le "
                 f"dossier « {self.output.name} », à côté des scans.")
        self.warnings.configure(text="\n".join(f"⚠ {w}" for w in self.correction.warnings))
        for button in (self.report_button, self.folder_button, self.compare_button):
            button.configure(state="normal")
        self.status.configure(text="Correction terminée.")

    def _progress(self, value) -> None:
        index, total, text = value
        self.progress.configure(maximum=max(total, 1), value=index)
        if text:
            self.status.configure(text=text)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.add_button, self.clear_button):
            button.configure(state=state)
        if busy:
            self.run_button.configure(state="disabled")
            self.progress.configure(value=0)
            self.status.configure(text=text)
            self.root.configure(cursor="watch")
        else:
            self.progress.configure(value=0)
            self.root.configure(cursor="")
            self._update_status()

    def _failed(self, value) -> None:
        error, details = value
        self._set_busy(False)
        log = Path.home() / "AutoCorrectNEPSY-erreur.txt"
        try:
            log.write_text(details, encoding="utf-8")
            where = f"\n\nLe détail technique est enregistré dans :\n{log}"
        except OSError:
            where = ""
        messagebox.showerror(APP_NAME, f"Une erreur est survenue :\n\n{error}{where}")

    # -- résultats ------------------------------------------------------------
    def open_report(self) -> None:
        if self.output:
            open_path(self.output / "rapport.html")

    def open_item_report(self, _event=None) -> None:
        selection = self.tree.selection()
        if self.output and selection and selection[0] != "total":
            open_path(self.output / "rapport.html", f"#item{selection[0]}")

    def open_folder(self) -> None:
        if self.output:
            open_path(self.output)

    def compare(self) -> None:
        if not self.output:
            return
        name = filedialog.askopenfilename(
            title="Cotation de l'ergothérapeute (fichier CSV)",
            filetypes=[("Tableau CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if not name:
            return
        try:
            text = format_comparison(pair_scores(read_scores(self.output / "cotation.csv"),
                                                 read_scores(name)))
        except (OSError, KeyError, ValueError) as error:
            messagebox.showerror(APP_NAME, "Ce fichier ne peut pas être comparé. Il doit avoir "
                                 "les colonnes item, general, motricite_A, motricite_B, global_C, "
                                 f"global_D, local_E, local_F.\n\n({error})")
            return
        window = tk.Toplevel(self.root)
        window.title("Comparaison avec la cotation de l'ergothérapeute")
        box = tk.Text(window, width=72, height=28, wrap="word", padx=10, pady=10)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)

    def show_help(self) -> None:
        messagebox.showinfo(f"{APP_NAME} – aide", HELP_TEXT)


def _enable_high_dpi() -> None:
    """Évite une fenêtre floue sur les écrans Windows à haute résolution."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main() -> None:
    _enable_high_dpi()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

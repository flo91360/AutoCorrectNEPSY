"""Sorties de la correction : tableau CSV, rapport HTML, images annotées."""

from __future__ import annotations

import base64
import csv
import html
from pathlib import Path

import cv2
import numpy as np

from .criteria import CODES, PROCESS_NAMES
from .pipeline import Correction, ItemReport
from .render import DISPLAY_WIDTH, measured_image

# Mêmes colonnes que la retranscription de la feuille de cotation de l'ergo.
CSV_FIELDS = ["item", "general", "motricite_A", "motricite_B", "motricite_total",
              "global_C", "global_D", "global_total", "local_E", "local_F", "local_total"]
FIELD_BY_CODE = {"G": "general", "A": "motricite_A", "B": "motricite_B", "C": "global_C",
                 "D": "global_D", "E": "local_E", "F": "local_F"}
# cotation.csv : notes retenues, corrections de l'ergothérapeute comprises.
# cotation_automatique.csv : proposition de l'outil telle quelle, pour mesurer
# son accord avec l'ergothérapeute (``comparer``).
SCORES_NAME = "cotation.csv"
AUTOMATIC_NAME = "cotation_automatique.csv"
REPORT_NAME = "rapport.html"


def _blank(value: int | None) -> str:
    return "" if value is None else str(value)


def score_row(report: ItemReport, automatic: bool = False) -> dict[str, str]:
    """Notes d'un item : retenues, ou proposées par l'outil si ``automatic``."""
    score = report.result.score if automatic else report.score
    row = {"item": str(report.item)}
    for code, name in FIELD_BY_CODE.items():
        row[name] = _blank(score(code))
    for name, codes in (("motricite_total", "AB"), ("global_total", "CD"), ("local_total", "EF")):
        scores = [score(code) for code in codes]
        row[name] = _blank(None if None in scores else sum(scores))
    return row


def corrected_codes(report: ItemReport) -> list[str]:
    return [code for code in CODES if code in report.corrections]


def write_csv(correction: Correction, path: Path, automatic: bool = False) -> None:
    extra = ["a_verifier"] if automatic else ["a_verifier", "verifie", "corrige"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS + extra)
        writer.writeheader()
        for report in correction.items:
            if automatic:
                flags = {"a_verifier": "oui" if report.result.to_review else ""}
            else:
                flags = {"a_verifier": "oui" if report.to_review else "",
                         "verifie": "oui" if report.checked else "",
                         "corrige": " ".join(corrected_codes(report))}
            writer.writerow(score_row(report, automatic) | flags)


def _scale_bar(image: np.ndarray, ppm: float) -> None:
    h = image.shape[0]
    x0, y0 = int(5 * ppm), h - int(5 * ppm)
    cv2.line(image, (x0, y0), (x0 + int(10 * ppm), y0), (0, 0, 0), 2)
    cv2.putText(image, "1 cm", (x0, y0 - int(1.5 * ppm)), cv2.FONT_HERSHEY_SIMPLEX,
                0.05 * ppm, (0, 0, 0), 1, cv2.LINE_AA)


def drawing_image(report: ItemReport) -> np.ndarray:
    """Dessin de l'enfant tel qu'il a été scanné, avec une échelle."""
    image = report.zone_image.copy()
    _scale_bar(image, report.px_per_mm)
    return image


def annotate(report: ItemReport) -> np.ndarray:
    """Traits reconstruits par l'outil, seuls sur fond blanc, avec les mesures
    qui ont servi à la cotation (voir ``render.py``).

    Ils ne sont pas superposés au dessin de l'enfant, qui est montré à part
    (``drawing_image``) : superposés, ils ressemblaient à un second tracé lissé.
    """
    drawing = report.drawing
    marks = report.result.marks
    # Les taches (item 9) sont dessinées telles quelles, à la place de leurs traits.
    strokes = [] if any(m.kind == "tache" for m in marks) else drawing.strokes
    return measured_image(report.zone_image.shape, report.px_per_mm, strokes, [],
                          marks, drawing.stroke_width)


def _png_data_uri(image: np.ndarray, max_width: int | None = 320) -> str:
    if max_width and image.shape[1] > max_width:
        scale = max_width / image.shape[1]
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".png", image)
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode()


def identity(correction: Correction) -> str:
    """« Enfant : … – passation du … », vide si rien n'a été saisi."""
    parts = [f"Enfant : {correction.child}" if correction.child else "",
             f"passation du {correction.session_date}" if correction.session_date else ""]
    return " – ".join(part for part in parts if part)


def _review_state(report: ItemReport) -> str:
    if report.checked:
        corrected = corrected_codes(report)
        return "✓ vérifié" + (f", corrigé ({', '.join(corrected)})" if corrected else "")
    return "⚠ à vérifier" if report.to_review else ""


def write_html(correction: Correction, path: Path) -> None:
    esc = html.escape
    rows = []
    for report in correction.items:
        row, auto = score_row(report), score_row(report, automatic=True)
        cells = "".join(f"<td>{row[f]}</td>" if row[f] == auto[f] else
                        f"<td class='corr' title='note de l’outil : {auto[f]}'>{row[f]}</td>"
                        for f in CSV_FIELDS[1:])
        state = "ok" if report.checked else "warn"
        rows.append(f'<tr><td><a href="#item{report.item}">{report.item}</a></td>{cells}'
                    f'<td class="{state}">{_review_state(report)}</td></tr>')
    sections = []
    for report in correction.items:
        result = report.result
        criteria = []
        for code in CODES:
            criterion = result.criteria.get(code)
            if criterion is None:
                continue
            details = "".join(f"<li>{esc(d)}</li>" for d in criterion.details)
            score = report.score(code)
            if code in report.corrections:
                details = (f"<li class='corr'>✎ note changée par l’ergothérapeute "
                           f"(outil : {criterion.score})</li>{details}")
            criteria.append(f"<tr><th>{PROCESS_NAMES[code]}</th>"
                            f"<td class='score s{score}'>{score}</td>"
                            f"<td><ul>{details}</ul></td></tr>")
        notes = "".join(f"<p class='warn'>⚠ {esc(n)}</p>" for n in result.notes)
        if report.checked:
            notes = f"<p class='ok'>{_review_state(report)} par l’ergothérapeute</p>{notes}"
        sections.append(
            f"<section id='item{report.item}'><h2>Item {report.item}</h2>"
            f"<p class='source'>{esc(report.source)}, page {report.page} du cahier</p>{notes}"
            f'<div class="item"><figure><img src="{_png_data_uri(drawing_image(report))}" '
            f'alt="Dessin de l’item {report.item}"><figcaption>Dessin de l’enfant</figcaption></figure>'
            f'<figure class="mesures"><img src="{_png_data_uri(annotate(report), None)}" '
            f'width="{DISPLAY_WIDTH}" alt="Traits et mesures de l’item {report.item}">'
            f'<figcaption>Traits lus par l’outil et mesures utilisées pour la cotation '
            f'(barre grisée en gris clair)</figcaption></figure>'
            f'<table>{"".join(criteria)}</table></div></section>')
    warnings = "".join(f"<p class='warn'>⚠ {esc(w)}</p>" for w in correction.warnings)
    who = identity(correction)
    who = f"<p class='enfant'>{esc(who)}</p>" if who else ""
    title = "Copie de figures – " + (f"{esc(correction.child)} – " if correction.child else "")
    headers = "".join(f"<th>{h}</th>" for h in
                      ["Item", "G", "A", "B", "Mot.", "C", "D", "Glob.", "E", "F", "Loc.", ""])
    path.write_text(f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}correction automatique</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 980px; padding: 0 1rem;
       color: #1d1d1f; background: #fff; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #ccc; padding: .3rem .5rem; vertical-align: top; text-align: left; }}
.summary td {{ text-align: center; }}
.item {{ display: flex; gap: 1.5rem; flex-wrap: wrap; align-items: flex-start; }}
.item img {{ border: 1px solid #ddd; max-width: 100%; }}
figure {{ margin: 0; max-width: 320px; }}
figure.mesures {{ max-width: {DISPLAY_WIDTH}px; }}
figure.mesures img {{ width: 100%; height: auto; }}
figcaption {{ color: #666; font-size: .85rem; }}
.score {{ font-weight: bold; text-align: center; }}
.s1 {{ background: #e3f4e3; }} .s0 {{ background: #fbe4e4; }}
.warn {{ color: #a15c00; }} .ok {{ color: #15803d; }}
.corr {{ background: #fff3c4; font-weight: bold; }}
.enfant {{ font-size: 1.1rem; }}
ul {{ margin: 0; padding-left: 0; list-style: none; }}
.source {{ color: #666; font-size: .9rem; }}
</style></head><body>
<h1>Copie de figures – correction automatique (prototype)</h1>
{who}
<p>Proposition de cotation à valider par l'ergothérapeute. Les mesures sont en mm,
d'après la résolution du scan. Les notes changées par l'ergothérapeute sont
surlignées (la note de l'outil s'affiche au survol).</p>
{warnings}
<table class="summary"><tr>{headers}</tr>{''.join(rows)}</table>
{''.join(sections)}
</body></html>
""", encoding="utf-8")


def save_results(correction: Correction, folder: Path) -> tuple[Path, Path]:
    """Écrit cotation.csv, cotation_automatique.csv et rapport.html dans
    ``folder`` (créé au besoin)."""
    folder.mkdir(parents=True, exist_ok=True)
    csv_path, html_path = folder / SCORES_NAME, folder / REPORT_NAME
    write_csv(correction, csv_path)
    write_csv(correction, folder / AUTOMATIC_NAME, automatic=True)
    write_html(correction, html_path)
    return csv_path, html_path


def totals(correction: Correction) -> dict[str, int]:
    """Sommes des notes retenues des items corrigés, par processus."""
    sums = {"general": 0, "motricite": 0, "global": 0, "local": 0}
    for report in correction.items:
        sums["general"] += report.score("G") or 0
        sums["motricite"] += report.total("A", "B") or 0
        sums["global"] += report.total("C", "D") or 0
        sums["local"] += report.total("E", "F") or 0
    return sums


def summary_text(correction: Correction) -> str:
    who = identity(correction)
    lines = [who, ""] if who else []
    lines.append("item  G  A  B  Mot  C  D  Glob  E  F  Loc")
    for report in correction.items:
        row = score_row(report)
        values = [row[f] or "-" for f in CSV_FIELDS[1:]]
        flag = "  à vérifier" if report.to_review else ""
        lines.append(f"{report.item:>4}  {values[0]}  {values[1]}  {values[2]}  {values[3]:>3}  "
                     f"{values[4]}  {values[5]}  {values[6]:>4}  {values[7]}  {values[8]}  "
                     f"{values[9]:>3}{flag}")
    lines += [f"⚠ {w}" for w in correction.warnings]
    return "\n".join(lines)

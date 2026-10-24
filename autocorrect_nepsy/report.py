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

# Mêmes colonnes que la retranscription de la feuille de cotation de l'ergo.
CSV_FIELDS = ["item", "general", "motricite_A", "motricite_B", "motricite_total",
              "global_C", "global_D", "global_total", "local_E", "local_F", "local_total"]
FIELD_BY_CODE = {"G": "general", "A": "motricite_A", "B": "motricite_B", "C": "global_C",
                 "D": "global_D", "E": "local_E", "F": "local_F"}
STROKE_COLORS = [(40, 40, 220), (30, 150, 30), (200, 90, 20), (0, 140, 230),
                 (170, 40, 170), (150, 150, 0), (90, 60, 160)]


def _blank(value: int | None) -> str:
    return "" if value is None else str(value)


def score_row(report: ItemReport) -> dict[str, str]:
    result = report.result
    row = {"item": str(report.item)}
    for code, name in FIELD_BY_CODE.items():
        row[name] = _blank(result.score(code))
    row["motricite_total"] = _blank(result.motricite)
    row["global_total"] = _blank(result.global_)
    row["local_total"] = _blank(result.local)
    return row


def write_csv(correction: Correction, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS + ["a_verifier"])
        writer.writeheader()
        for report in correction.items:
            writer.writerow(score_row(report) | {"a_verifier": "oui" if report.result.to_review else ""})


def annotate(report: ItemReport) -> np.ndarray:
    """Dessin de l'enfant avec les traits reconstruits en couleur et une échelle."""
    ppm = report.px_per_mm
    image = cv2.addWeighted(report.zone_image, 0.4, np.full_like(report.zone_image, 255), 0.6, 0)
    thickness = max(2, int(round(0.3 * ppm)))
    for i, stroke in enumerate(report.drawing.strokes):
        pts = np.round(stroke.points * ppm).astype(np.int32)
        cv2.polylines(image, [pts], stroke.closed, STROKE_COLORS[i % len(STROKE_COLORS)],
                      thickness, cv2.LINE_AA)
    for line in report.drawing.significant_lines():
        a, b = (tuple(int(v) for v in np.round(p * ppm)) for p in line.ends)
        cv2.line(image, a, b, (60, 60, 60), 1, cv2.LINE_AA)
    h = image.shape[0]
    x0, y0 = int(5 * ppm), h - int(5 * ppm)
    cv2.line(image, (x0, y0), (x0 + int(10 * ppm), y0), (0, 0, 0), 2)
    cv2.putText(image, "1 cm", (x0, y0 - int(1.5 * ppm)), cv2.FONT_HERSHEY_SIMPLEX,
                0.05 * ppm, (0, 0, 0), 1, cv2.LINE_AA)
    return image


def _png_data_uri(image: np.ndarray, max_width: int = 420) -> str:
    if image.shape[1] > max_width:
        scale = max_width / image.shape[1]
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".png", image)
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode()


def write_html(correction: Correction, path: Path) -> None:
    esc = html.escape
    rows = []
    for report in correction.items:
        row = score_row(report)
        cells = "".join(f"<td>{row[f]}</td>" for f in CSV_FIELDS[1:])
        review = "⚠ à vérifier" if report.result.to_review else ""
        rows.append(f'<tr><td><a href="#item{report.item}">{report.item}</a></td>{cells}'
                    f'<td class="warn">{review}</td></tr>')
    sections = []
    for report in correction.items:
        result = report.result
        criteria = []
        for code in CODES:
            criterion = result.criteria.get(code)
            if criterion is None:
                continue
            details = "".join(f"<li>{esc(d)}</li>" for d in criterion.details)
            criteria.append(f"<tr><th>{PROCESS_NAMES[code]}</th>"
                            f"<td class='score s{criterion.score}'>{criterion.score}</td>"
                            f"<td><ul>{details}</ul></td></tr>")
        notes = "".join(f"<p class='warn'>⚠ {esc(n)}</p>" for n in result.notes)
        sections.append(
            f"<section id='item{report.item}'><h2>Item {report.item}</h2>"
            f"<p class='source'>{esc(report.source)}, page {report.page} du cahier</p>{notes}"
            f'<div class="item"><img src="{_png_data_uri(annotate(report))}" '
            f'alt="Dessin de l’item {report.item}"><table>{"".join(criteria)}</table></div></section>')
    warnings = "".join(f"<p class='warn'>⚠ {esc(w)}</p>" for w in correction.warnings)
    headers = "".join(f"<th>{h}</th>" for h in
                      ["Item", "G", "A", "B", "Mot.", "C", "D", "Glob.", "E", "F", "Loc.", ""])
    path.write_text(f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Copie de figures – correction automatique</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 980px; padding: 0 1rem;
       color: #1d1d1f; background: #fff; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #ccc; padding: .3rem .5rem; vertical-align: top; text-align: left; }}
.summary td {{ text-align: center; }}
.item {{ display: flex; gap: 1.5rem; flex-wrap: wrap; align-items: flex-start; }}
.item img {{ border: 1px solid #ddd; max-width: 100%; }}
.score {{ font-weight: bold; text-align: center; }}
.s1 {{ background: #e3f4e3; }} .s0 {{ background: #fbe4e4; }}
.warn {{ color: #a15c00; }}
ul {{ margin: 0; padding-left: 0; list-style: none; }}
.source {{ color: #666; font-size: .9rem; }}
</style></head><body>
<h1>Copie de figures – correction automatique (prototype)</h1>
<p>Proposition de cotation à valider par l'ergothérapeute. Les mesures sont en mm,
d'après la résolution du scan.</p>
{warnings}
<table class="summary"><tr>{headers}</tr>{''.join(rows)}</table>
{''.join(sections)}
</body></html>
""", encoding="utf-8")


def summary_text(correction: Correction) -> str:
    lines = ["item  G  A  B  Mot  C  D  Glob  E  F  Loc"]
    for report in correction.items:
        row = score_row(report)
        values = [row[f] or "-" for f in CSV_FIELDS[1:]]
        flag = "  à vérifier" if report.result.to_review else ""
        lines.append(f"{report.item:>4}  {values[0]}  {values[1]}  {values[2]}  {values[3]:>3}  "
                     f"{values[4]}  {values[5]}  {values[6]:>4}  {values[7]}  {values[8]}  "
                     f"{values[9]:>3}{flag}")
    lines += [f"⚠ {w}" for w in correction.warnings]
    return "\n".join(lines)

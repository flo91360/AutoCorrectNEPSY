"""Instantané de la cotation sur des dessins synthétiques.

Chaque item est noté sur la copie de chaque modèle (le sien et ceux des autres
items, ce qui passe par les chemins « figure non reconnue »), avec un tremblement
réaliste, et sur la copie de son propre modèle sans tremblement et très déformée.
Une restructuration du code ne doit rien y changer. Un changement voulu de la
cotation apparaît ici item par item ; l'instantané est alors régénéré :

    python tests/test_instantane.py
"""

import json
import sys
from pathlib import Path

from autocorrect_nepsy.criteria import SUPPORTED_ITEMS, score_item
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

sys.path.insert(0, str(Path(__file__).parent))
from synth import PX_PER_MM, canvas, draw_model  # noqa: E402

SNAPSHOT = Path(__file__).with_name("instantane_cotation.json")
CROSS_WOBBLE = 0.6
OWN_WOBBLES = (0.0, 1.5)


def summary(result) -> str:
    """« G1 A0~ B1 … ⚠ » : note de chaque critère, « ~ » si la mesure est
    limite, « ⚠ » si l'item est à vérifier."""
    text = " ".join(f"{code}{c.score}{'~' if c.borderline else ''}"
                    for code, c in result.criteria.items())
    return text + (" ⚠" if result.to_review else "")


def current() -> dict[str, str]:
    """Résumé de chaque cotation, clé « item/modèle/tremblement »."""
    cases = {(item, model, CROSS_WOBBLE) for item in SUPPORTED_ITEMS for model in SUPPORTED_ITEMS}
    cases |= {(item, item, wobble) for item in SUPPORTED_ITEMS for wobble in OWN_WOBBLES}
    drawings = {(model, wobble): extract_drawing(
        ink_mask(draw_model(model, canvas(), wobble=wobble)), PX_PER_MM)
        for model, wobble in {(model, wobble) for _, model, wobble in cases}}
    return {f"{item}/{model}/{wobble}": summary(score_item(item, drawings[model, wobble]))
            for item, model, wobble in sorted(cases)}


def test_scores_match_the_snapshot():
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = current()
    changed = [f"item/modèle/tremblement {key} : {expected.get(key)} -> {value}"
               for key, value in actual.items() if expected.get(key) != value]
    assert not changed, "cotation changée (régénérer l'instantané si c'est voulu) :\n" + \
        "\n".join(changed[:40])
    assert set(expected) == set(actual)


if __name__ == "__main__":
    SNAPSHOT.write_text(json.dumps(current(), ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"Instantané écrit : {SNAPSHOT}")

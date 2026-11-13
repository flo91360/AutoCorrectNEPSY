"""Justesse des mesures : ce que lit l'outil est comparé à ce qu'une règle lit
sur l'encre (bout à bout du trait, vide entre deux traits), pour plusieurs
épaisseurs de stylo et plusieurs orientations."""

import numpy as np
import pytest

from autocorrect_nepsy.criteria import score_item
from autocorrect_nepsy.criteria.shapes import blank_length, ink_reach
from autocorrect_nepsy.ink import ink_mask
from autocorrect_nepsy.strokes import extract_drawing

from synth import PX_PER_MM, canvas, draw_model, flower, polyline, stairs_points

PENS = (0.3, 0.45, 0.7, 1.0)  # épaisseur du stylo (mm)


def drawing_of(image):
    return extract_drawing(ink_mask(image), PX_PER_MM)


def score(item, image):
    return score_item(item, drawing_of(image))


def line_image(length, pen, angle=0.0, center=(45.0, 55.0)):
    """Trait droit de ``length`` mm (entre les centres de la pointe du stylo)."""
    direction = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])
    center = np.asarray(center)
    return polyline(canvas(90, 110), [center - direction * length / 2,
                                      center + direction * length / 2], width_mm=pen), direction


def ink_extent(image, direction):
    """Étendue (mm) de l'encre le long d'une direction, bord à bord."""
    ys, xs = np.nonzero(ink_mask(image))
    along = np.column_stack([xs, ys]) @ direction / PX_PER_MM
    return float(along.max() - along.min()) + 1 / PX_PER_MM


@pytest.mark.parametrize("pen", PENS)
@pytest.mark.parametrize("angle", [0, 7, 33, 45, 90])
def test_line_length_is_the_ink_from_end_to_end(pen, angle):
    # Le squelette s'arrête au centre de la pointe du stylo : mesuré jusqu'à
    # lui, le trait perdait une épaisseur de trait (0,5 à 1,5 mm).
    for length in (7.0, 20.0, 70.0):
        image, direction = line_image(length, pen, angle)
        measured = drawing_of(image).lines[0].length
        assert measured == pytest.approx(ink_extent(image, direction), abs=0.3)
        assert measured > length + 0.2


@pytest.mark.parametrize("pen", PENS)
def test_stroke_width_does_not_depend_on_the_direction(pen):
    # Divisée par le nombre de pixels du squelette, l'épaisseur d'un trait à
    # 45° grossissait de 40 % : la barre grisée et les tolérances en dépendent.
    widths = [drawing_of(line_image(50.0, pen, angle)[0]).stroke_width
              for angle in (0, 15, 30, 45, 60, 90)]
    assert max(widths) / min(widths) < 1.15
    bands = [drawing_of(line_image(50.0, pen, angle)[0]).lines[0].width for angle in (0, 45)]
    assert bands[1] - bands[0] < 0.25


def test_item1_line_just_over_a_length_threshold_is_long_enough():
    # 20,4 mm d'encre bout à bout : Global D (au moins 20 mm) est réussi.
    image, direction = line_image(19.6, 0.45, 90, center=(32.0, 44.0))
    assert ink_extent(image, direction) > 20.2
    result = score(1, image)
    assert result.measures["longueur_mm"] > 20.0
    assert result.criteria["D"].score == 1


def t_shape(gap, pen):
    """Item 5 : l'horizontale s'arrête à ``gap`` mm (entre centres) de la verticale."""
    image = polyline(canvas(), [(20, 14), (20, 74)], width_mm=pen)
    return polyline(image, [(20 + gap, 44), (50, 44)], width_mm=pen)


def ink_void(image, y=44.0):
    """Vide (mm) entre les encres sur la rangée ``y``."""
    xs = np.nonzero(ink_mask(image)[int(round(y * PX_PER_MM))])[0]
    jumps = np.diff(xs)
    return float(jumps.max() - 1) / PX_PER_MM if len(jumps) and jumps.max() > 1 else 0.0


@pytest.mark.parametrize("pen", PENS[:3])
def test_item5_junction_gap_is_the_void_between_the_inks(pen):
    # Mesuré entre les milieux des traits, l'intervalle comptait une épaisseur
    # de trait en trop : un vide de 0,9 mm au stylo épais valait 2,0 mm (échec).
    assert score(5, t_shape(0.0, pen)).measures["intervalle_mm"] == 0.0
    for gap in (1.5, 2.0, 2.5, 3.0):
        image = t_shape(gap, pen)
        void = ink_void(image)
        if void < 0.5:  # micro-saut rebouché avec l'encre
            continue
        result = score(5, image)
        assert result.measures["intervalle_mm"] == pytest.approx(void, abs=0.2)
        if abs(void - 2.0) > 0.25:
            assert result.criteria["E"].score == int(void <= 2.0)


@pytest.mark.parametrize("item, key", [(5, "intervalle_mm"), (6, "intervalle_mm"),
                                       (10, "jonction_max_mm"), (11, "jonction_max_mm")])
def test_perfect_junctions_have_no_gap(item, key):
    # Jonctions du modèle, parfaites : l'outil y lisait 0,4 à 0,7 mm d'intervalle.
    assert score(item, draw_model(item, canvas())).measures[key] <= 0.2


@pytest.mark.parametrize("pen", PENS[:3])
def test_item5_overshoot_is_counted_from_the_edge_of_the_crossed_line(pen):
    for beyond in (1.5, 2.5, 3.0):
        image = polyline(canvas(), [(20, 14), (20, 74)], width_mm=pen)
        polyline(image, [(20 - beyond, 44), (50, 44)], width_mm=pen)
        mask = ink_mask(image)
        row = np.nonzero(mask[int(round(44 * PX_PER_MM))])[0]
        edge = np.nonzero(mask[int(round(30 * PX_PER_MM))])[0].min()
        truth = (edge - row.min()) / PX_PER_MM  # encre qui ressort à gauche de la verticale
        assert score(5, image).measures["depassement_mm"] == pytest.approx(truth, abs=0.25)


@pytest.mark.parametrize("pen", [0.3, 0.7])
def test_item18_small_overshoot_is_no_longer_erased(pen):
    # Un bout de trait de moins de 1,5 mm était effacé comme une barbe du
    # squelette : un dépassement de 1,4 mm restait invisible (seuil : 1 mm).
    points = stairs_points((7.5, 20))
    corner = np.array(points[-2], float)  # coin en bas à droite
    image = polyline(canvas(), points, closed=True, width_mm=pen)
    polyline(image, [corner, corner + (1.4, 0)], width_mm=pen)
    result = score(18, image)
    assert result.measures["jonction_max_mm"] > 1.0
    assert result.criteria["B"].score == 0
    clean = score(18, polyline(canvas(), points, closed=True, width_mm=pen))
    assert clean.criteria["B"].score == 1


@pytest.mark.parametrize("pen", PENS[:3])
@pytest.mark.parametrize("length", [27.6, 30.0, 32.4])
def test_item20_petal_length_is_the_ink_from_center_to_tip(pen, length):
    # Les bords d'un pétale se rejoignent en un trait épais à ses deux bouts :
    # la mesure s'arrêtait avant, 1 à 1,7 mm trop courte pour une plage de 27 à 33 mm.
    image = canvas(80, 100)
    for seed, petal in enumerate(flower((40, 50), petals=3, length=length, width=7.0)):
        polyline(image, petal, closed=True, seed=seed, width_mm=pen)
    result = score(20, image)
    for key in ("longueur_min_mm", "longueur_max_mm"):
        assert result.measures[key] == pytest.approx(length + 0.3, abs=0.5)


def test_ink_reach_and_blank_length():
    image = polyline(canvas(), [(10, 40), (30, 40)])
    polyline(image, [(33, 40), (50, 40)], seed=1)
    drawing = drawing_of(image)
    start, right = np.array([20.0, 40.0]), np.array([1.0, 0.0])
    assert ink_reach(drawing, start, right, 5.0) == 5.0
    assert ink_reach(drawing, start, right, 30.0) == pytest.approx(10.4, abs=0.2)
    assert ink_reach(drawing, np.array([20.0, 50.0]), right, 5.0) == 0.0
    void = ink_void(image, 40.0)
    assert 2.0 < void < 2.6
    assert blank_length(drawing, start, np.array([40.0, 40.0])) == pytest.approx(void, abs=0.15)
    assert blank_length(drawing, start, np.array([25.0, 40.0])) == 0.0

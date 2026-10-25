import numpy as np
import pytest

from autocorrect_nepsy import geometry as geo


def test_min_strip_width_of_rectangle():
    pts = np.array([(0, 0), (10, 0), (10, 3), (0, 3), (5, 1.5)], float)
    assert geo.min_strip_width(pts) == pytest.approx(3.0)


def test_min_strip_width_of_tilted_segment_is_zero():
    t = np.linspace(0, 1, 20)
    pts = np.column_stack([10 * t, 4 * t])
    assert geo.min_strip_width(pts) == pytest.approx(0.0, abs=1e-6)


def test_axis_angles():
    assert geo.angle_to_horizontal(np.array([1.0, 0.0])) == pytest.approx(0)
    assert geo.angle_to_horizontal(np.array([-1.0, 1.0])) == pytest.approx(45)
    assert geo.angle_to_vertical(np.array([0.0, -1.0])) == pytest.approx(0)


def test_line_intersection():
    p = geo.line_intersection(np.array([0.0, 0.0]), np.array([1.0, 0.0]),
                              np.array([3.0, -5.0]), np.array([0.0, 1.0]))
    assert p == pytest.approx([3.0, 0.0])
    assert geo.line_intersection(np.zeros(2), np.array([1.0, 0.0]),
                                 np.ones(2), np.array([1.0, 0.0])) is None


def test_principal_axis_points_right():
    pts = np.array([(5, 5), (0, 0), (10, 10)], float)
    center, direction = geo.principal_axis(pts)
    assert center == pytest.approx([5, 5])
    assert direction[0] > 0
    assert geo.angle_to_horizontal(direction) == pytest.approx(45)


def test_max_diameter():
    pts = np.array([(0, 0), (3, 4), (1, 1)], float)
    assert geo.max_diameter(pts) == pytest.approx(5.0)


@pytest.mark.parametrize("bumps, expected", [(0, 0), (1, 1), (2, 2), (4, 4)])
def test_count_direction_changes(bumps, expected):
    x = np.linspace(0, 40, 400)
    y = 2.0 * np.sin(np.pi * bumps * x / 40) if bumps else 0.1 * np.sin(x * 7)
    assert geo.count_direction_changes(np.column_stack([x, y]), 0.8) == expected


def test_max_cone_angle_ignores_points_near_apex():
    pts = np.array([(0, 0), (0.5, 0.5), (0, 10), (1, 20)], float)
    angle = geo.max_cone_angle(pts, np.zeros(2), np.array([0.0, 1.0]), min_distance=2.0)
    assert angle == pytest.approx(np.degrees(np.arctan2(1, 20)), abs=0.01)


def test_fraction_in_cone():
    pts = np.array([(0, 10), (0, 20), (20, 1)], float)
    assert geo.fraction_in_cone(pts, np.zeros(2), np.array([0.0, 1.0]), 30) == pytest.approx(2 / 3)


def test_rdp_keeps_corners():
    pts = np.array([(0, 0), (5, 0.1), (10, 0), (10, 5), (10, 10)], float)
    assert list(geo.rdp(pts, 0.5)) == [0, 2, 4]


def test_resample_step():
    pts = np.array([(0, 0), (10, 0)], float)
    out = geo.resample(pts, 1.0)
    assert len(out) == 11
    assert np.diff(out[:, 0]) == pytest.approx(np.ones(10))


def test_min_strip_rectangle_contains_points():
    rng = np.random.default_rng(1)
    pts = np.column_stack([rng.uniform(0, 30, 200), rng.uniform(-1, 1, 200)])
    pts = pts @ np.array([[0.8, 0.6], [-0.6, 0.8]])  # bande inclinée
    width, corners = geo.min_strip(pts)
    assert width == pytest.approx(geo.min_strip_width(pts))
    assert width <= 2.0
    assert np.linalg.norm(corners[1] - corners[0]) == pytest.approx(30, abs=1.0)
    assert np.linalg.norm(corners[3] - corners[0]) == pytest.approx(width, abs=1e-6)


def test_max_diameter_ends():
    pts = np.array([(0, 0), (3, 4), (1, 1)], float)
    a, b = geo.max_diameter_ends(pts)
    assert {tuple(a), tuple(b)} == {(0.0, 0.0), (3.0, 4.0)}

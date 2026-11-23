import math

from constant.constants import (
    MAT_TYPE,
    MAX_COORD_Z,
    MAX_R,
    MIN_COORD_Z,
    POS_MAX,
)


def _unit(vec):
    x, y, z = vec
    length = math.sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length)


def _general_objects(scene):
    spheres = []
    triangles = []
    index = 0
    for _, _, n_sph, n_tri in scene:
        for _ in range(n_sph):
            spheres.append(
                {
                    "radius": 128 + index,
                    "z": 256 + index,
                    "y": -64 + index,
                    "x": 64 + index,
                    "mat": MAT_TYPE,
                }
            )
            index += 1
        for _ in range(n_tri):
            triangles.append(
                {
                    "e2": (0, 128, 0),
                    "e1": (128, 0, 0),
                    "origin": (32 + index, -32 + index, 256 + index),
                    "mat": MAT_TYPE,
                }
            )
            index += 1
    return spheres, triangles


_GENERAL_SCENE = [
    (47, 5, 5, 0),
    (82, 3, 0, 3),
    (118, 2, 1, 1),
    (137, 4, 4, 0),
    (165, 1, 0, 1),
    (177, 3, 2, 1),
]
_GENERAL_SPHERES, _GENERAL_TRIANGLES = _general_objects(_GENERAL_SCENE)

TEST_INTERSECTION_UNIT_GENERAL = {
    "ray_origin": (0.0, 0.0, 0.0),
    "ray_dir": _unit((0.5, 0.5, 0.5)),
    "bv_num": 6,
    "scene": _GENERAL_SCENE,
    "bv_geometry": [
        (347, 549, -751, 953),
        (127, 987, -654, 321),
        (MAX_R, 456, 789, 101),
        (123, MAX_COORD_Z, 789, 0),
        (123, MIN_COORD_Z, POS_MAX, -101),
        (MAX_R, 127, POS_MAX, 101),
    ],
    "spheres": _GENERAL_SPHERES,
    "triangles": _GENERAL_TRIANGLES,
}

_ONE_BV_SCENE = [(22, 1, 1, 0)]
_UNIT_111 = _unit((1.0, 1.0, 1.0))

TEST_SPHERE_HIT_OUTSIDE = {
    "ray_origin": (0.0, 0.0, 0.0),
    "ray_dir": _UNIT_111,
    "bv_num": 1,
    "scene": _ONE_BV_SCENE,
    "bv_geometry": [(4.0, 10.0, 10.0, 10.0)],
    "spheres": [
        {"radius": 2.0, "z": 10.0, "y": 10.0, "x": 10.0, "mat": MAT_TYPE}
    ],
    "triangles": [],
}

TEST_SPHERE_HIT_INSIDE = {
    "ray_origin": (0.0, 0.0, 0.0),
    "ray_dir": _UNIT_111,
    "bv_num": 1,
    "scene": _ONE_BV_SCENE,
    "bv_geometry": [(8.0, 0.0, 0.0, 0.0)],
    "spheres": [
        {"radius": 8.0, "z": 0.0, "y": 0.0, "x": 0.0, "mat": MAT_TYPE}
    ],
    "triangles": [],
}

TEST_SPHERE_MISS = {
    "ray_origin": (0.0, 0.0, 0.0),
    "ray_dir": (0.0, 0.0, 1.0),
    "bv_num": 1,
    "scene": _ONE_BV_SCENE,
    "bv_geometry": [(30.0, 0.0, 0.0, 0.0)],
    "spheres": [
        {"radius": 2.0, "z": 0.0, "y": 0.0, "x": 20.0, "mat": MAT_TYPE}
    ],
    "triangles": [],
}

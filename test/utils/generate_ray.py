import math
import random

from utils.convert_u16_to_float import (
    convert_float_to_9_7_u16,
    convert_float_to_2_14_u16,
)


def _normalize(vec):
    x, y, z = vec
    length = math.sqrt(x * x + y * y + z * z)
    if length == 0.0:
        return None
    return (x / length, y / length, z / length)


def generate_ray(test_mode):
    """Return ((ox, oy, oz), (dx, dy, dz)) as raw u16 tuples (POS origin, DIR unit)."""
    if test_mode == "FIXED":
        origin_f = (0.0, 0.0, 0.0)
        direction_f = _normalize((0.5, 0.5, 0.5))
    else:
        origin_f = (
            float(random.randint(-255, 255)),
            float(random.randint(-255, 255)),
            float(random.randint(-255, 255)),
        )
        direction_f = None
        while direction_f is None:
            direction_f = _normalize(
                (random.random(), random.random(), random.random())
            )

    origin = tuple(convert_float_to_9_7_u16(part) for part in origin_f)
    direction = tuple(convert_float_to_2_14_u16(part) for part in direction_f)
    return origin, direction

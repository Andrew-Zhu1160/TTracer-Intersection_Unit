import math

from constant.macro_opcode import (
    M_ADD, M_SUB, M_EQ, M_NE, M_LT, M_GE,
    M_MUL, M_DIV, M_SQRT, M_COS, M_MAG,
    M_VADD, M_VSUB, M_SCAL_VEC, M_DOT, M_CROSS,
    M_NORM, M_SPHERE_NORM, M_VMUL,
)
from utils.convert_u16_to_float import (
    convert_u16_to_9_7_float,
    convert_u16_to_2_14_float,
)

_SCALAR_OPS = {M_ADD, M_SUB, M_EQ, M_NE, M_LT, M_GE, M_MUL, M_DIV, M_SQRT, M_COS}
_VECTOR_OPS = {M_VADD, M_VSUB, M_VMUL, M_CROSS, M_DOT, M_NORM, M_MAG}


def _lane(value, fmt):
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if fmt == "pos":
            return convert_u16_to_9_7_float(value)
        if fmt == "dir":
            return convert_u16_to_2_14_float(value)
        raise ValueError("raw 16-bit inputs need fmt='pos' (Q9.7) or fmt='dir' (Q2.14)")
    raise TypeError(f"lane must be int or float, got {type(value).__name__}")


def _scalar(value, fmt):
    if isinstance(value, (tuple, list)):
        return _lane(value[0], fmt)
    return _lane(value, fmt)


def _vec(value, fmt):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise TypeError("vector operand must be an (x, y, z) tuple")
    return tuple(_lane(part, fmt) for part in value)


def vector_algebra(macro_opcode, u, v=None, fmt=None):
    """Run one macro-op in real arithmetic.

    Returns an (x, y, z) tuple, or a float for dot, magnitude, and scalar ops.
    Compares return 1.0 or 0.0. Floats are used as-is; ints are raw lanes.
    """
    if macro_opcode in _SCALAR_OPS:
        a = _scalar(u, fmt)
        if macro_opcode == M_SQRT:
            return math.sqrt(a)
        if macro_opcode == M_COS:
            return math.cos(a)
        b = _scalar(v, fmt)
        if macro_opcode == M_ADD:
            return a + b
        if macro_opcode == M_SUB:
            return a - b
        if macro_opcode == M_MUL:
            return a * b
        if macro_opcode == M_DIV:
            return a / b
        if macro_opcode == M_EQ:
            return 1.0 if a == b else 0.0
        if macro_opcode == M_NE:
            return 1.0 if a != b else 0.0
        if macro_opcode == M_LT:
            return 1.0 if a < b else 0.0
        return 1.0 if a >= b else 0.0

    if macro_opcode == M_MAG:
        x, y, z = _vec(u, fmt)
        return math.sqrt(x * x + y * y + z * z)

    if macro_opcode == M_NORM:
        x, y, z = _vec(u, fmt)
        length = math.sqrt(x * x + y * y + z * z)
        if length == 0.0:
            return (0.0, 0.0, 0.0)
        return (x / length, y / length, z / length)

    if macro_opcode == M_SCAL_VEC:
        scale = _scalar(u, fmt)
        x, y, z = _vec(v, fmt)
        return (scale * x, scale * y, scale * z)

    if macro_opcode == M_SPHERE_NORM:
        # Instruction page: u1 is the radius, v is the vector.
        radius = _scalar(u, fmt)
        x, y, z = _vec(v, fmt)
        return (x / radius, y / radius, z / radius)

    if macro_opcode in (M_VADD, M_VSUB, M_VMUL, M_CROSS, M_DOT):
        ux, uy, uz = _vec(u, fmt)
        vx, vy, vz = _vec(v, fmt)
        if macro_opcode == M_VADD:
            return (ux + vx, uy + vy, uz + vz)
        if macro_opcode == M_VSUB:
            return (ux - vx, uy - vy, uz - vz)
        if macro_opcode == M_VMUL:
            return (ux * vx, uy * vy, uz * vz)
        if macro_opcode == M_DOT:
            return ux * vx + uy * vy + uz * vz
        return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)

    raise ValueError(f"unknown macro opcode {macro_opcode}")
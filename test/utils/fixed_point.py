"""16-bit POS/DIR arithmetic matching TinyTracer macro-op rules."""

import math

from utils.convert_u16_to_float import _signed16

INT16_MAX = 0x7FFF
INT16_MIN = -0x8000
FMT_POS = 0
FMT_DIR = 1
DIR_ONE = 0x4000  # 1.0 in Q2.14
POS_225 = 225 << 7  # 225.0 in Q9.7 (triangle |slid_s|^2 miss)
BEHIND_T = 2  # 2 POS steps
BEST_T_INIT = INT16_MAX


def signed16(raw):
    return _signed16(raw)


def u16(value):
    return int(value) & 0xFFFF


def clamp16(value):
    if value > INT16_MAX:
        return INT16_MAX
    if value < INT16_MIN:
        return INT16_MIN
    return int(value)


def round_ties_away(value):
    if value < 0:
        return -round_ties_away(-value)
    return int(math.floor(value + 0.5))


def quantize_pos(value):
    return clamp16(round_ties_away(float(value) * 128.0))


def quantize_dir(value):
    return clamp16(round_ties_away(float(value) * 16384.0))


def add(a, b):
    return clamp16(int(a) + int(b))


def sub(a, b):
    return clamp16(int(a) - int(b))


def bitnot16(a):
    """XOR every bit of the 16-bit lane: ~a == -a - 1."""
    return signed16((~u16(a)) & 0xFFFF)


def mul(a, b, fmt):
    prod = int(a) * int(b)
    shift = 7 if fmt == FMT_POS else 14
    half = 1 << (shift - 1)
    if prod >= 0:
        result = (prod + half) >> shift
    else:
        result = -(((-prod) + half) >> shift)
    return clamp16(result)


def div(a, b):
    if b == 0:
        return INT16_MAX
    num = int(a) << 14
    abs_q = abs(num) // abs(int(b))
    result = abs_q if (num >= 0) == (int(b) >= 0) else -abs_q
    return clamp16(result)


def sqrt_fmt(a, fmt):
    if a <= 0:
        return 0
    n = 7 if fmt == FMT_POS else 14
    return clamp16(round_ties_away(math.sqrt(int(a) * (1 << n))))


def mag(a, b):
    """M_MAG: sqrt(a^2 + b^2) on raw lanes, round-to-nearest ties-away."""
    ss = int(a) * int(a) + int(b) * int(b)
    if ss <= 0:
        return 0
    return clamp16(round_ties_away(math.sqrt(ss)))


def highest_one_bit(magnitude):
    if magnitude <= 0:
        return None
    return int(magnitude).bit_length() - 1


def k_radius(r_raw):
    if r_raw <= 0:
        return 0
    return highest_one_bit(r_raw) - 10


def k_triangle(e1, e2):
    largest = max(abs(part) for part in e1 + e2)
    if largest <= 0:
        return 0
    return highest_one_bit(largest) - 9


def shift_k(raw, k):
    raw = int(raw)
    if k > 0:
        return raw >> k
    if k < 0:
        return clamp16(raw << (-k))
    return raw


def shift_vec(vec, k):
    return tuple(shift_k(part, k) for part in vec)


def resize_pre_shift(vec):
    """Shift so the leading 1 of max(|xi|) sits at bit 13 (DIR 0.5 to 1)."""
    largest = max(abs(part) for part in vec)
    if largest == 0:
        return (0, 0, 0)
    k = highest_one_bit(largest) - 13
    return shift_vec(vec, k)


def vadd(u, v):
    return (add(u[0], v[0]), add(u[1], v[1]), add(u[2], v[2]))


def vsub(u, v):
    return (sub(u[0], v[0]), sub(u[1], v[1]), sub(u[2], v[2]))


def scal_vec(scale, vec, fmt):
    return (
        mul(scale, vec[0], fmt),
        mul(scale, vec[1], fmt),
        mul(scale, vec[2], fmt),
    )


def vdot(u, v, fmt):
    p0 = mul(u[0], v[0], fmt)
    p1 = mul(u[1], v[1], fmt)
    p2 = mul(u[2], v[2], fmt)
    return add(add(p0, p1), p2)


def vcross(u, v, fmt):
    ux, uy, uz = u
    vx, vy, vz = v
    t_uz_vy = mul(uz, vy, fmt)
    t_uz_vx = mul(uz, vx, fmt)
    t_ux_vy = mul(ux, vy, fmt)
    t_uy_vx = mul(uy, vx, fmt)
    t_uy_vz = mul(uy, vz, fmt)
    t_ux_vz = mul(ux, vz, fmt)
    return (
        sub(t_uy_vz, t_uz_vy),
        sub(t_uz_vx, t_ux_vz),
        sub(t_ux_vy, t_uy_vx),
    )


def m_norm(vec):
    shifted = resize_pre_shift(vec)
    if shifted == (0, 0, 0):
        return (0, 0, 0)
    ux, uy, uz = shifted
    length = mag(mag(ux, uy), uz)
    inv = div(DIR_ONE, length)
    return (
        mul(inv, ux, FMT_DIR),
        mul(inv, uy, FMT_DIR),
        mul(inv, uz, FMT_DIR),
    )


def sphere_norm(radius, vec):
    return (div(vec[0], radius), div(vec[1], radius), div(vec[2], radius))


def pack48(vec):
    x, y, z = vec
    return (u16(z) << 32) | (u16(y) << 16) | u16(x)

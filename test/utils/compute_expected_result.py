from constant.constants import (
    BV_START_ADDR,
    BV_WORD_COUNT,
    PRIM_SPH,
    SPHERE_WORD_COUNT,
    TRIANGLE_WORD_COUNT,
)
from constant.macro_opcode import (
    M_ADD,
    M_DIV,
    M_DOT,
    M_EQ,
    M_GE,
    M_LT,
    M_MUL,
    M_NE,
    M_SCAL_VEC,
    M_SPHERE_NORM,
    M_SQRT,
    M_SUB,
    M_VADD,
    M_VSUB,
)
from utils.convert_u16_to_float import (
    convert_float_to_2_14_u16,
    convert_float_to_9_7_u16,
    pack_vec3_u16,
)
from utils.fixed_point import (
    BEHIND_T,
    BEST_T_INIT,
    DIR_ONE,
    FMT_DIR,
    FMT_POS,
    POS_225,
    add,
    clamp16,
    div,
    k_radius,
    k_triangle,
    m_norm,
    mul,
    scal_vec,
    shift_k,
    shift_vec,
    signed16,
    sub,
    u16,
    vcross,
    vdot,
    vsub,
)
from utils.vector_algebra import vector_algebra

_COMPARE_OPS = {M_EQ, M_NE, M_LT, M_GE}
_C0156 = 0x0002
_SKY_T = 0x7FFF


def _sky():
    return {
        "hit": 0,
        "hit_ground": 0,
        "hit_addr": 0,
        "hit_point": 0,
        "n": 0,
        "checker": 0,
        "hit_flip": 0,
    }


def _checker_from_point(point):
    hx, hy, _ = point
    return ((u16(hx) >> 9) & 1) ^ ((u16(hy) >> 9) & 1)


def _read_zyx(sram, addr):
    z = signed16(sram[addr])
    y = signed16(sram[addr + 1])
    x = signed16(sram[addr + 2])
    return (x, y, z)


def _read_bv(sram, bv_index):
    addr = BV_START_ADDR + BV_WORD_COUNT * bv_index
    w0 = int(sram[addr]) & 0xFFFF
    radius = signed16(sram[addr + 1])
    centre = _read_zyx(sram, addr + 2)
    prim_start = (w0 >> 7) & 0x1FF
    prim_count = w0 & 0x7F
    return radius, centre, prim_start, prim_count


def _kshift(raw, k):
    """IU kshift: round-on-right-shift, clamp-on-left-shift."""
    v = signed16(raw)
    k = int(k)
    if k > 0:
        w = v + (1 << (k - 1))
        w = w >> k
    elif k < 0:
        w = v << (-k)
    else:
        w = v
    return clamp16(w)


def _kshift_vec(vec, k):
    return tuple(_kshift(part, k) for part in vec)


def _neg16(raw):
    return clamp16(-signed16(raw))


def _as_vec(value):
    if isinstance(value, (tuple, list)):
        return tuple(int(part) & 0xFFFF for part in value)
    return (int(value) & 0xFFFF, 0, 0)


def _encode_result(result, opcode, fmt):
    to_u16 = (
        convert_float_to_2_14_u16 if fmt == "dir" else convert_float_to_9_7_u16
    )
    if isinstance(result, (tuple, list)):
        x, y, z = result
        return pack_vec3_u16(to_u16(x), to_u16(y), to_u16(z))
    if opcode in _COMPARE_OPS:
        return pack_vec3_u16(1 if result else 0, 0, 0)
    return pack_vec3_u16(to_u16(result), 0, 0)


def _macro(opcode, u, v=0, fmt_dir=False, k=0, sh_u=0, sh_v=0, neg_v=False):
    """One IU request: kshift/neg on the way in, then the mock FU encode."""
    u = list(_as_vec(u))
    v = list(_as_vec(v))
    if sh_u:
        u = list(_kshift_vec(u, k if sh_u > 0 else -k))
    if sh_v:
        v = list(_kshift_vec(v, k if sh_v > 0 else -k))
    if neg_v:
        v = [_neg16(part) for part in v]
    u = tuple(int(part) & 0xFFFF for part in u)
    v = tuple(int(part) & 0xFFFF for part in v)
    fmt = "dir" if fmt_dir else "pos"
    return _encode_result(vector_algebra(opcode, u, v, fmt=fmt), opcode, fmt)


def _lane_x(packed):
    return int(packed) & 0xFFFF


def _lane_vec(packed):
    packed = int(packed) & ((1 << 48) - 1)
    x = packed & 0xFFFF
    y = (packed >> 16) & 0xFFFF
    z = (packed >> 32) & 0xFFFF
    return (x, y, z)


def _bit0(packed):
    return _lane_x(packed) & 1


def _hit_point(origin, direction, t):
    scaled = _lane_vec(_macro(M_SCAL_VEC, t, direction, fmt_dir=True))
    return _macro(M_VADD, origin, scaled, fmt_dir=False)


def _bv_reachable(origin, direction, centre, radius):
    k = k_radius(radius)
    r_s = _kshift(radius, k)
    r_s2 = _lane_x(_macro(M_MUL, r_s, r_s, fmt_dir=False))
    to_centre = _lane_vec(_macro(M_VSUB, centre, origin, fmt_dir=False))
    along = _lane_x(_macro(M_DOT, to_centre, direction, fmt_dir=True))
    tcsq = _lane_x(
        _macro(M_DOT, to_centre, to_centre, fmt_dir=False, k=k, sh_u=1, sh_v=1)
    )
    if _bit0(_macro(M_LT, tcsq, r_s2, fmt_dir=False)):
        return True
    if _bit0(_macro(M_LT, along, 0, fmt_dir=False)):
        return False
    scaled = _lane_vec(_macro(M_SCAL_VEC, along, direction, fmt_dir=True))
    offset = _lane_vec(_macro(M_VSUB, scaled, to_centre, fmt_dir=False))
    offsq = _lane_x(
        _macro(M_DOT, offset, offset, fmt_dir=False, k=k, sh_u=1, sh_v=1)
    )
    return bool(_bit0(_macro(M_LT, offsq, r_s2, fmt_dir=False)))


def _sphere_test(sram, addr, origin, direction, best_t):
    radius = signed16(sram[addr + 3])
    centre = _read_zyx(sram, addr + 4)
    k = k_radius(radius)
    r_s = _kshift(radius, k)
    r_s2 = _lane_x(_macro(M_MUL, r_s, r_s, fmt_dir=False))
    to_centre = _lane_vec(_macro(M_VSUB, centre, origin, fmt_dir=False))
    along = _lane_x(_macro(M_DOT, to_centre, direction, fmt_dir=True))
    scaled = _lane_vec(_macro(M_SCAL_VEC, along, direction, fmt_dir=True))
    offset = _lane_vec(_macro(M_VSUB, scaled, to_centre, fmt_dir=False))
    off_s2 = _lane_x(
        _macro(M_DOT, offset, offset, fmt_dir=False, k=k, sh_u=1, sh_v=1)
    )
    if not _bit0(_macro(M_LT, off_s2, r_s2, fmt_dir=False)):
        return None
    half2 = _lane_x(_macro(M_SUB, r_s2, off_s2, fmt_dir=False))
    half_s = _lane_x(_macro(M_SQRT, half2, 0, fmt_dir=False))
    t = _lane_x(_macro(M_SUB, along, half_s, fmt_dir=False, k=k, sh_v=-1))
    inside = False
    if not _bit0(_macro(M_LT, _C0156, t, fmt_dir=False)):
        t = _lane_x(_macro(M_ADD, along, half_s, fmt_dir=False, k=k, sh_v=-1))
        inside = True
        if not _bit0(_macro(M_LT, _C0156, t, fmt_dir=False)):
            return None
    if not _bit0(_macro(M_LT, t, best_t, fmt_dir=False)):
        return None
    return {
        "kind": "sphere",
        "t": t,
        "addr": addr,
        "inside": inside,
        "centre": centre,
        "radius": radius,
    }


def _offset_s(along, direction, to_vec, k):
    along_s = shift_k(along, k)
    to_s = shift_vec(to_vec, k)
    return vsub(scal_vec(along_s, direction, FMT_DIR), to_s)


def _triangle_test(sram, addr, origin, direction, best_t):
    e2 = _read_zyx(sram, addr + 3)
    e1 = _read_zyx(sram, addr + 6)
    v0 = _read_zyx(sram, addr + 9)
    k = k_triangle(e1, e2)
    e1_s = shift_vec(e1, k)
    e2_s = shift_vec(e2, k)
    to_corner = vsub(v0, origin)
    along = vdot(to_corner, direction, FMT_DIR)
    slid_s = _offset_s(along, direction, to_corner, k)
    if vdot(slid_s, slid_s, FMT_POS) > POS_225:
        return None

    p = vcross(direction, e2_s, FMT_DIR)
    det = vdot(e1_s, p, FMT_POS)
    alpha_top = vdot(slid_s, p, FMT_POS)
    backface = False
    if det < 0:
        det = sub(0, det)
        alpha_top = sub(0, alpha_top)
        backface = True
    if det <= 0 or alpha_top < 0 or alpha_top > det:
        return None

    q = vcross(slid_s, e1_s, FMT_POS)
    beta_top = vdot(direction, q, FMT_DIR)
    if backface:
        beta_top = sub(0, beta_top)
    if beta_top < 0 or add(alpha_top, beta_top) > det:
        return None

    alpha = div(alpha_top, det)
    beta = div(beta_top, det)
    t = add(
        along,
        add(
            mul(alpha, vdot(e1, direction, FMT_DIR), FMT_DIR),
            mul(beta, vdot(e2, direction, FMT_DIR), FMT_DIR),
        ),
    )
    if t <= BEHIND_T:
        return None
    if t >= best_t:
        return None
    return {
        "kind": "triangle",
        "t": t,
        "addr": addr,
        "inside": False,
        "offset_s": None,
        "half_s": None,
        "r_s": None,
        "backface": backface,
        "k": k,
    }


def _triangle_normal(sram, hit):
    addr = hit["addr"]
    e2 = shift_vec(_read_zyx(sram, addr + 3), hit["k"])
    e1 = shift_vec(_read_zyx(sram, addr + 6), hit["k"])
    if hit["backface"]:
        crossed = vcross(e2, e1, FMT_POS)
    else:
        crossed = vcross(e1, e2, FMT_POS)
    return m_norm(crossed)


def compute_expected_result(sram, ray, bv_num):
    origin_in, dir_in = ray
    origin = tuple(signed16(part) for part in origin_in)
    direction = tuple(signed16(part) for part in dir_in)

    best_t = BEST_T_INIT
    best = None

    for bv_index in range(bv_num):
        radius, centre, prim_start, prim_count = _read_bv(sram, bv_index)
        if not _bv_reachable(origin, direction, centre, radius):
            continue
        addr = prim_start
        for _ in range(prim_count):
            prim_type = int(sram[addr]) & 1
            if prim_type == PRIM_SPH:
                hit = _sphere_test(sram, addr, origin, direction, best_t)
                if hit is not None:
                    best_t = hit["t"]
                    best = hit
                addr += SPHERE_WORD_COUNT
            else:
                hit = _triangle_test(sram, addr, origin, direction, best_t)
                if hit is not None:
                    best_t = hit["t"]
                    best = hit
                addr += TRIANGLE_WORD_COUNT

    if best is None:
        if not _bit0(_macro(M_LT, direction[2], 0, fmt_dir=False)):
            return _sky()
        t = _lane_x(
            _macro(M_DIV, origin[2], direction[2], fmt_dir=False, neg_v=True)
        )
        if t == _SKY_T:
            return _sky()
        point_packed = _hit_point(origin, direction, t)
        point = _lane_vec(point_packed)
        return {
            "hit": 1,
            "hit_ground": 1,
            "hit_addr": 0,
            "hit_point": point_packed,
            "n": pack_vec3_u16(0, 0, DIR_ONE),
            "checker": _checker_from_point(point),
            "hit_flip": 0,
        }

    point_packed = _hit_point(origin, direction, best["t"])
    point = _lane_vec(point_packed)
    if best["kind"] == "triangle":
        n_packed = pack_vec3_u16(*_triangle_normal(sram, best))
        hit_flip = 1 if best["backface"] else 0
    else:
        if best["inside"]:
            diff = _lane_vec(
                _macro(M_VSUB, best["centre"], point, fmt_dir=False)
            )
        else:
            diff = _lane_vec(_macro(M_VSUB, point, best["centre"], fmt_dir=False))
        n_packed = _macro(M_SPHERE_NORM, best["radius"], diff, fmt_dir=False)
        hit_flip = 1 if best["inside"] else 0

    return {
        "hit": 1,
        "hit_ground": 0,
        "hit_addr": best["addr"],
        "hit_point": point_packed,
        "n": n_packed,
        "checker": 0,
        "hit_flip": hit_flip,
    }

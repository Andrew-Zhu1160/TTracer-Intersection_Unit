from constant.constants import (
    BV_START_ADDR,
    BV_WORD_COUNT,
    MAT_DIELEC,
    PRIM_SPH,
    SPHERE_WORD_COUNT,
    TRIANGLE_WORD_COUNT,
)
from utils.fixed_point import (
    BEHIND_T,
    BEST_T_INIT,
    DIR_ONE,
    FMT_DIR,
    FMT_POS,
    INT16_MAX,
    POS_225,
    add,
    bitnot16,
    div,
    k_radius,
    k_triangle,
    m_norm,
    mul,
    pack48,
    quantize_dir,
    quantize_pos,
    scal_vec,
    shift_k,
    shift_vec,
    signed16,
    sphere_norm,
    sqrt_fmt,
    sub,
    u16,
    vadd,
    vcross,
    vdot,
    vsub,
)


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


def _hit_point(origin, direction, t):
    return vadd(origin, scal_vec(t, direction, FMT_DIR))


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


def _offset_s(along, direction, to_vec, k):
    along_s = shift_k(along, k)
    to_s = shift_vec(to_vec, k)
    return vsub(scal_vec(along_s, direction, FMT_DIR), to_s)


def _bv_reachable(origin, direction, centre, radius):
    k = k_radius(radius)
    r_s = shift_k(radius, k)
    r_s2 = mul(r_s, r_s, FMT_POS)
    to_centre = vsub(centre, origin)
    along = vdot(to_centre, direction, FMT_DIR)
    to_centre_s = shift_vec(to_centre, k)
    if vdot(to_centre_s, to_centre_s, FMT_POS) < r_s2:
        return True
    if along < 0:
        return False
    offset_s = _offset_s(along, direction, to_centre, k)
    return vdot(offset_s, offset_s, FMT_POS) < r_s2


def _sphere_test(sram, addr, origin, direction):
    radius = signed16(sram[addr + 3])
    centre = _read_zyx(sram, addr + 4)
    k = k_radius(radius)
    r_s = shift_k(radius, k)
    r_s2 = mul(r_s, r_s, FMT_POS)
    to_centre = vsub(centre, origin)
    along = vdot(to_centre, direction, FMT_DIR)
    offset_s = _offset_s(along, direction, to_centre, k)
    off_s2 = vdot(offset_s, offset_s, FMT_POS)
    if off_s2 >= r_s2:
        return None
    half_s = sqrt_fmt(sub(r_s2, off_s2), FMT_POS)
    half = shift_k(half_s, -k)
    t = sub(along, half)
    inside = False
    if t <= BEHIND_T:
        t = add(along, half)
        inside = True
        if t <= BEHIND_T:
            return None
    return {
        "kind": "sphere",
        "t": t,
        "addr": addr,
        "inside": inside,
        "offset_s": offset_s,
        "half_s": half_s,
        "r_s": r_s,
        "backface": False,
        "k": k,
    }


def _triangle_test(sram, addr, origin, direction):
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


def _sphere_normal(hit, direction):
    half_d = scal_vec(hit["half_s"], direction, FMT_DIR)
    if hit["inside"]:
        vec = vadd(hit["offset_s"], half_d)
        n = sphere_norm(hit["r_s"], vec)
        return tuple(sub(0, part) for part in n)
    vec = vsub(hit["offset_s"], half_d)
    return sphere_norm(hit["r_s"], vec)


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
    origin = tuple(quantize_pos(part) for part in origin_in)
    direction = m_norm(tuple(quantize_dir(part) for part in dir_in))

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
                hit = _sphere_test(sram, addr, origin, direction)
                addr += SPHERE_WORD_COUNT
            else:
                hit = _triangle_test(sram, addr, origin, direction)
                addr += TRIANGLE_WORD_COUNT
            if hit is not None and hit["t"] < best_t:
                best_t = hit["t"]
                best = hit

    if best is None:
        if direction[2] < 0:
            t = div(bitnot16(origin[2]), direction[2])
            if t != INT16_MAX and t > BEHIND_T:
                point = _hit_point(origin, direction, t)
                return {
                    "hit": 1,
                    "hit_ground": 1,
                    "hit_addr": 0,
                    "hit_point": pack48(point),
                    "n": pack48((0, 0, DIR_ONE)),
                    "checker": _checker_from_point(point),
                    "hit_flip": 0,
                }
        return _sky()

    point = _hit_point(origin, direction, best["t"])
    mat = int(sram[best["addr"] + 2]) & 0x3
    if best["kind"] == "sphere":
        n = _sphere_normal(best, direction)
        hit_flip = 1 if best["inside"] and mat == MAT_DIELEC else 0
    else:
        n = _triangle_normal(sram, best)
        hit_flip = 0

    return {
        "hit": 1,
        "hit_ground": 0,
        "hit_addr": best["addr"],
        "hit_point": pack48(point),
        "n": pack48(n),
        "checker": 0,
        "hit_flip": hit_flip,
    }

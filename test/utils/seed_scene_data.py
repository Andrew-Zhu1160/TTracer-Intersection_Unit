from constant.constants import (
    SRAM_DEPTH,
    BV_START_ADDR,
    BV_WORD_COUNT,
    SPHERE_WORD_COUNT,
    TRIANGLE_WORD_COUNT,
    PRIM_TRI,
    PRIM_SPH,
    DUMMY_BLUE,
    DUMMY_RED_GREEN,
    DUMMY_STRENGTH,
    MAT_TYPE,
    MIN_R,
    MAX_R,
    MIN_COORD_Z,
    MAX_COORD_Z,
    POS_MIN,
    POS_MAX,
)
import random
from utils.convert_u16_to_float import _u16, convert_float_to_9_7_u16




def _pack_bv_w0(primitive_start, primitive_count):
    if not 0 <= primitive_start < SRAM_DEPTH:
        raise ValueError(f"primitive address {primitive_start} is outside SRAM")
    if not 1 <= primitive_count <= 127:
        raise ValueError(f"BV_COUNT {primitive_count} is outside 1..127")
    return (primitive_start << 7) | primitive_count


def _pack_primitive_w0(bv_index, primitive_type):
    return (
        (DUMMY_BLUE << 8)
        | ((bv_index & 0x7F) << 1)
        | primitive_type
    )


def _pack_w2(mat):
    return (DUMMY_STRENGTH << 2) | (mat & 0x3)


def _sphere_words(bv_index, radius, z, y, x, mat):
    return [
        _pack_primitive_w0(bv_index, PRIM_SPH),
        DUMMY_RED_GREEN,
        _pack_w2(mat),
        _u16(radius),
        _u16(z),
        _u16(y),
        _u16(x),
    ]


def _triangle_words(bv_index, e2, e1, origin, mat):
    e2_x, e2_y, e2_z = e2
    e1_x, e1_y, e1_z = e1
    x, y, z = origin
    return [
        _pack_primitive_w0(bv_index, PRIM_TRI),
        DUMMY_RED_GREEN,
        _pack_w2(mat),
        _u16(e2_z),
        _u16(e2_y),
        _u16(e2_x),
        _u16(e1_z),
        _u16(e1_y),
        _u16(e1_x),
        _u16(z),
        _u16(y),
        _u16(x),
    ]


def _random_sphere_words(bv_index):
    return _sphere_words(
        bv_index,
        random.randint(MIN_R, MAX_R),
        random.randint(MIN_COORD_Z, MAX_COORD_Z),
        random.randint(POS_MIN, POS_MAX),
        random.randint(POS_MIN, POS_MAX),
        random.randint(0, 3),
    )


def _random_triangle_words(bv_index):
    e2 = tuple(random.randint(POS_MIN, POS_MAX) for _ in range(3))
    e1 = tuple(random.randint(POS_MIN, POS_MAX) for _ in range(3))
    origin = (
        random.randint(POS_MIN, POS_MAX),
        random.randint(POS_MIN, POS_MAX),
        random.randint(MIN_COORD_Z, MAX_COORD_Z),
    )
    return _triangle_words(
        bv_index, e2, e1, origin, random.choice([0, 1, 3])
    )







def random_scene(sphere_only=False):
    """Generate legal BV counts, primitive mixes, and contiguous addresses."""
    bv_num = random.randint(1, 15)
    budget = (SRAM_DEPTH - BV_START_ADDR) - BV_WORD_COUNT * bv_num
    prim_addr = BV_START_ADDR + BV_WORD_COUNT * bv_num
    scene = []

    for i in range(bv_num):
        later = bv_num - i - 1
        # Reserve one minimum-size primitive (a sphere) for every later BV.
        max_words = budget - SPHERE_WORD_COUNT * later
        max_count = min(127, max_words // SPHERE_WORD_COUNT)
        bv_count = random.randint(1, max_count)

        if sphere_only:
            n_tri = 0
            n_sph = bv_count
        else:
            # Replacing a 7-word sphere with a triangle costs five extra words.
            max_tri = min(
                bv_count,
                (max_words - SPHERE_WORD_COUNT * bv_count)
                // (TRIANGLE_WORD_COUNT - SPHERE_WORD_COUNT),
            )
            n_tri = random.randint(0, max_tri)
            n_sph = bv_count - n_tri
        words = (
            SPHERE_WORD_COUNT * n_sph
            + TRIANGLE_WORD_COUNT * n_tri
        )

        scene.append((prim_addr, bv_count, n_sph, n_tri))
        prim_addr += words
        budget -= words

    return bv_num, scene


def _pos_word(value):
    if isinstance(value, float):
        return convert_float_to_9_7_u16(value)
    return _u16(value)


def generate_test_case_and_hydrate_sram(sram, test_mode, fix_scene_config=None):
    """Fill a 512-word SRAM image and return the generated BV count."""
    if len(sram) != SRAM_DEPTH:
        raise ValueError(f"SRAM image must contain {SRAM_DEPTH} words")

    # Header words 0..16 and all unused words are dummy zeroes.
    sram[:] = [0] * SRAM_DEPTH

    if test_mode == "FIXED":
        if fix_scene_config is None:
            raise ValueError("FIXED requires fix_scene_config")
        bv_num = fix_scene_config["bv_num"]
        scene = fix_scene_config["scene"]
        bv_geometry = fix_scene_config["bv_geometry"]
        sphere_iter = iter(fix_scene_config["spheres"])
        triangle_iter = iter(fix_scene_config["triangles"])
    elif test_mode == "RANDOM_SPHERE":
        bv_num, scene = random_scene(sphere_only=True)
        bv_geometry = [
            (
                random.randint(MIN_R, MAX_R),
                random.randint(MIN_COORD_Z, MAX_COORD_Z),
                random.randint(POS_MIN, POS_MAX),
                random.randint(POS_MIN, POS_MAX),
            )
            for _ in range(bv_num)
        ]
    else:
        bv_num, scene = random_scene(sphere_only=False)
        bv_geometry = [
            (
                random.randint(MIN_R, MAX_R),
                random.randint(MIN_COORD_Z, MAX_COORD_Z),
                random.randint(POS_MIN, POS_MAX),
                random.randint(POS_MIN, POS_MAX),
            )
            for _ in range(bv_num)
        ]

    # Bounding volumes are always packed from address 17 in five-word records.
    for bv_index, ((prim_addr, bv_count, _, _), geometry) in enumerate(
        zip(scene, bv_geometry)
    ):
        radius, z, y, x = geometry
        bv_addr = BV_START_ADDR + BV_WORD_COUNT * bv_index
        sram[bv_addr : bv_addr + BV_WORD_COUNT] = [
            _pack_bv_w0(prim_addr, bv_count),
            _pos_word(radius),
            _pos_word(z),
            _pos_word(y),
            _pos_word(x),
        ]

    # Primitive lists are contiguous within each BV and are stored in BV order.
    for bv_index, (prim_addr, _, n_sph, n_tri) in enumerate(scene):
        cursor = prim_addr

        for _ in range(n_sph):
            if test_mode == "FIXED":
                sph = next(sphere_iter)
                words = _sphere_words(
                    bv_index,
                    radius=_pos_word(sph["radius"]),
                    z=_pos_word(sph["z"]),
                    y=_pos_word(sph["y"]),
                    x=_pos_word(sph["x"]),
                    mat=sph["mat"],
                )
            else:
                words = _random_sphere_words(bv_index)

            sram[cursor : cursor + SPHERE_WORD_COUNT] = words
            cursor += SPHERE_WORD_COUNT

        for _ in range(n_tri):
            if test_mode == "FIXED":
                tri = next(triangle_iter)
                ox, oy, oz = tri["origin"]
                words = _triangle_words(
                    bv_index,
                    e2=tuple(_pos_word(part) for part in tri["e2"]),
                    e1=tuple(_pos_word(part) for part in tri["e1"]),
                    origin=(
                        _pos_word(ox),
                        _pos_word(oy),
                        _pos_word(oz),
                    ),
                    mat=tri["mat"],
                )
            else:
                words = _random_triangle_words(bv_index)

            sram[cursor : cursor + TRIANGLE_WORD_COUNT] = words
            cursor += TRIANGLE_WORD_COUNT

    return bv_num
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
from utils.convert_u16_to_float import _u16




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







def random_scene():
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


def generate_test_case_and_hydrate_sram(sram, test_mode):
    """Fill a 512-word SRAM image and return the generated BV count."""
    if len(sram) != SRAM_DEPTH:
        raise ValueError(f"SRAM image must contain {SRAM_DEPTH} words")

    # Header words 0..16 and all unused words are dummy zeroes.
    sram[:] = [0] * SRAM_DEPTH

    if test_mode == "FIXED":
        bv_num = 6
        scene = [
            (47, 5, 5, 0),
            (82, 3, 0, 3),
            (118, 2, 1, 1),
            (137, 4, 4, 0),
            (165, 1, 0, 1),
            (177, 3, 2, 1),
        ]
        bv_geometry = [
            (347, 549, -751, 953),
            (127, 987, -654, 321),
            (MAX_R, 456, 789, 101),
            (123, MAX_COORD_Z, 789, 0),
            (123, MIN_COORD_Z, POS_MAX, -101),
            (MAX_R, 127, POS_MAX, 101),
        ]
    else:
        bv_num, scene = random_scene()
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
            _u16(radius),
            _u16(z),
            _u16(y),
            _u16(x),
        ]

    # Primitive lists are contiguous within each BV and are stored in BV order.
    fixed_object_index = 0
    for bv_index, (prim_addr, _, n_sph, n_tri) in enumerate(scene):
        cursor = prim_addr

        for _ in range(n_sph):
            if test_mode == "FIXED":
                words = _sphere_words(
                    bv_index,
                    radius=128 + fixed_object_index,
                    z=256 + fixed_object_index,
                    y=-64 + fixed_object_index,
                    x=64 + fixed_object_index,
                    mat=MAT_TYPE,
                )
            else:
                words = _random_sphere_words(bv_index)

            sram[cursor : cursor + SPHERE_WORD_COUNT] = words
            cursor += SPHERE_WORD_COUNT
            fixed_object_index += 1

        for _ in range(n_tri):
            if test_mode == "FIXED":
                words = _triangle_words(
                    bv_index,
                    e2=(0, 128, 0),
                    e1=(128, 0, 0),
                    origin=(
                        32 + fixed_object_index,
                        -32 + fixed_object_index,
                        256 + fixed_object_index,
                    ),
                    mat=MAT_TYPE,
                )
            else:
                words = _random_triangle_words(bv_index)
            
            sram[cursor : cursor + TRIANGLE_WORD_COUNT] = words
            cursor += TRIANGLE_WORD_COUNT
            fixed_object_index += 1

    return bv_num
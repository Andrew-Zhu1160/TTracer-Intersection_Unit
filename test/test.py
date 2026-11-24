# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from constant.fix_scene_config import (
    TEST_INTERSECTION_UNIT_GENERAL,
    TEST_SPHERE_HIT_INSIDE,
    TEST_SPHERE_HIT_OUTSIDE,
    TEST_SPHERE_MISS,
)
from mocked_componenet.mock_rtu import MOCK_RTU
from mocked_componenet.mock_sram import MockSRAM
from utils.generate_ray import generate_ray
from utils.compute_expected_result import compute_expected_result
from utils.fixed_point import signed16
from utils import convert_u16_to_float

test_mode = os.environ.get("TEST_MODE", "FIXED")
LANE_EPS = 8

def _unpack_zyx(bits48):
    bits48 = int(bits48) & ((1 << 48) - 1)
    x = signed16(bits48 & 0xFFFF)
    y = signed16((bits48 >> 16) & 0xFFFF)
    z = signed16((bits48 >> 32) & 0xFFFF)
    return (x, y, z)


def _assert_lanes_close(expected, dut_val, eps=LANE_EPS):
    exp = _unpack_zyx(expected)
    got = _unpack_zyx(dut_val)
    for e, g in zip(exp, got):
        assert abs(e - g) <= eps, (exp, got)


async def _reset_dut(dut):
    dut.start.value = 0
    dut.ray_origin.value = 0
    dut.ray_dir.value = 0
    dut.bv_count.value = 0
    dut.sram_data.value = 0
    dut.sram_valid.value = 0
    dut.req_ready.value = 0
    dut.resp_valid.value = 0
    dut.resp_result.value = 0

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _pack_bv_w0(primitive_start, primitive_count):
    return (primitive_start << 7) | primitive_count

def _pack_primitive_w0(bv_index, primitive_type):
    return ((bv_index & 0x7F) << 1) | primitive_type

def _triangle_words(v0, e1, e2):
    # Vertex 
    x0, y0, z0 = v0
    # Edge 1
    e1_x, e1_y, e1_z = e1
    # Edge 2
    e2_x, e2_y, e2_z = e2
    return [_pack_primitive_w0(0, 0), 0, 0,
            convert_u16_to_float.convert_float_to_9_7_u16(e2_z),
            convert_u16_to_float.convert_float_to_9_7_u16(e2_y),
            convert_u16_to_float.convert_float_to_9_7_u16(e2_x),
            convert_u16_to_float.convert_float_to_9_7_u16(e1_z),
            convert_u16_to_float.convert_float_to_9_7_u16(e1_y),
            convert_u16_to_float.convert_float_to_9_7_u16(e1_x),
            convert_u16_to_float.convert_float_to_9_7_u16(z0),
            convert_u16_to_float.convert_float_to_9_7_u16(y0),
            convert_u16_to_float.convert_float_to_9_7_u16(x0)]

def _assert_full_result(expected, dut):
    assert expected["hit"] == int(dut.hit.value)
    assert expected["hit_ground"] == int(dut.hit_ground.value)
    assert expected["hit_addr"] == int(dut.hit_addr.value)
    _assert_lanes_close(expected["hit_point"], int(dut.hit_point.value))
    _assert_lanes_close(expected["n"], int(dut.n.value))
    assert expected["checker"] == int(dut.checker_bit.value)
    assert expected["hit_flip"] == int(dut.hit_flip.value)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_intersection_unit(dut):
    dut._log.info("Start intersection_unit_test")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    sram = MockSRAM(dut, test_mode, TEST_INTERSECTION_UNIT_GENERAL)
    rtu = MOCK_RTU(dut, sram.bv_num, test_mode)
    cocotb.start_soon(sram.run(test_mode))
    ray_origin, ray_dir = await rtu.init_request(
        test_mode, TEST_INTERSECTION_UNIT_GENERAL
    )

    expected_result = compute_expected_result(
        sram.sram, (ray_origin, ray_dir), sram.bv_num
    )

    assert expected_result["hit"] == int(dut.hit.value)
    assert expected_result["hit_ground"] == int(dut.hit_ground.value)
    assert expected_result["hit_addr"] == int(dut.hit_addr.value)
    _assert_lanes_close(expected_result["hit_point"], int(dut.hit_point.value))
    _assert_lanes_close(expected_result["n"], int(dut.n.value))
    assert expected_result["checker"] == int(dut.checker_bit.value)
    assert expected_result["hit_flip"] == int(dut.hit_flip.value)

#--------------------- BASELINE STATE TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_no_bv(dut):
    dut._log.info("Start no_bv")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    dut.bv_count.value = 0
    # Start pulse 
    dut.start.value = 1
    await ClockCycles(dut.clk, 1)
    dut.start.value = 0

    # state_q starts with S_RTU_LOAD
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 1
    assert int(dut.done.value) == 0
    
    # When bv_count == 0, state_q goes directly to S_CHECKOUT 
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 3
    assert int(dut.done.value) == 1

    # state_q ends with S_IDLE 
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 0


@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_bv_loop_progression(dut):
    dut._log.info("Start bv_loop_progression")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())

    for bv_count in range(1, 17):
        await _reset_dut(dut)

        dut.bv_count.value = bv_count
        # Start pulse
        dut.start.value = 1
        await ClockCycles(dut.clk, 1)
        dut.start.value = 0

        # state_q starts with S_RTU_LOAD
        await ClockCycles(dut.clk, 1)
        assert int(dut.state_q.value) == 1
        assert int(dut.done.value) == 0

        # For bv_count > 0, state_q remains in the active BV walk while the loop is progressing
        seen_active = False
        for _ in range(bv_count * 76 + 20):
            if int(dut.state_q.value) == 2:
                seen_active = True
            if int(dut.done.value) == 1:
                break
            await ClockCycles(dut.clk, 1)
        assert seen_active

        # Finished processing, state_q == S_CHECKOUT
        assert int(dut.state_q.value) == 3
        assert int(dut.done.value) == 1

        # state_q ends with S_IDLE
        await ClockCycles(dut.clk, 2)
        assert int(dut.state_q.value) == 0

#--------------------- SPHERE TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_sphere_hit_outside(dut):
    dut._log.info("Start sphere_hit_outside")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    sram = MockSRAM(dut, "FIXED", TEST_SPHERE_HIT_OUTSIDE)
    rtu = MOCK_RTU(dut, sram.bv_num, "FIXED")
    cocotb.start_soon(sram.run("FIXED"))
    ray_origin, ray_dir = await rtu.init_request("FIXED", TEST_SPHERE_HIT_OUTSIDE)
    expected_result = compute_expected_result(
        sram.sram, (ray_origin, ray_dir), sram.bv_num
    )

    assert expected_result["hit"] == int(dut.hit.value)
    assert expected_result["hit_ground"] == int(dut.hit_ground.value)
    assert expected_result["hit_addr"] == int(dut.hit_addr.value)
    _assert_lanes_close(expected_result["hit_point"], int(dut.hit_point.value))
    _assert_lanes_close(expected_result["n"], int(dut.n.value))
    assert expected_result["checker"] == int(dut.checker_bit.value)
    assert expected_result["hit_flip"] == int(dut.hit_flip.value)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_sphere_hit_inside(dut):
    dut._log.info("Start sphere_hit_inside")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    sram = MockSRAM(dut, "FIXED", TEST_SPHERE_HIT_INSIDE)
    rtu = MOCK_RTU(dut, sram.bv_num, "FIXED")
    cocotb.start_soon(sram.run("FIXED"))
    ray_origin, ray_dir = await rtu.init_request("FIXED", TEST_SPHERE_HIT_INSIDE)
    expected_result = compute_expected_result(
        sram.sram, (ray_origin, ray_dir), sram.bv_num
    )

    assert expected_result["hit"] == int(dut.hit.value)
    assert expected_result["hit_ground"] == int(dut.hit_ground.value)
    assert expected_result["hit_addr"] == int(dut.hit_addr.value)
    _assert_lanes_close(expected_result["hit_point"], int(dut.hit_point.value))
    _assert_lanes_close(expected_result["n"], int(dut.n.value))
    assert expected_result["checker"] == int(dut.checker_bit.value)
    assert expected_result["hit_flip"] == int(dut.hit_flip.value)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_sphere_miss(dut):
    dut._log.info("Start sphere_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    sram = MockSRAM(dut, "FIXED", TEST_SPHERE_MISS)
    rtu = MOCK_RTU(dut, sram.bv_num, "FIXED")
    cocotb.start_soon(sram.run("FIXED"))
    ray_origin, ray_dir = await rtu.init_request("FIXED", TEST_SPHERE_MISS)
    expected_result = compute_expected_result(
        sram.sram, (ray_origin, ray_dir), sram.bv_num
    )

    assert expected_result["hit"] == int(dut.hit.value)
    assert expected_result["hit_ground"] == int(dut.hit_ground.value)
    assert expected_result["hit_addr"] == int(dut.hit_addr.value)
    _assert_lanes_close(expected_result["hit_point"], int(dut.hit_point.value))
    _assert_lanes_close(expected_result["n"], int(dut.n.value))
    assert expected_result["checker"] == int(dut.checker_bit.value)
    assert expected_result["hit_flip"] == int(dut.hit_flip.value)

#--------------------- TRIANGLE TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_hit_front(dut):
    dut._log.info("Start triangle_hit_front")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    # Build triangle scene with one BV
    sram = MockSRAM(dut, "FIXED")
    scene_words = sram.sram
    scene_words[:] = [0] * 512
    bv_addr = 17
    prim_addr = 47
    scene_words[bv_addr] = _pack_bv_w0(prim_addr, 1)
    scene_words[bv_addr + 1] = convert_u16_to_float.convert_float_to_9_7_u16(30.0)
    scene_words[bv_addr + 2 : bv_addr + 5] = [convert_u16_to_float.convert_float_to_9_7_u16(0.0),
                                              convert_u16_to_float.convert_float_to_9_7_u16(5.0),
                                              convert_u16_to_float.convert_float_to_9_7_u16(5.0)]
    scene_words[prim_addr : prim_addr + 12] = _triangle_words((0, 0, 0), (10, 0, 0), (0, 10, 0))
    sram.bv_num = 1
    cocotb.start_soon(sram.run("FIXED"))
    rtu = MOCK_RTU(dut, 1, "FIXED")

    # Setup front-facing ray
    ray_origin = tuple(convert_u16_to_float.convert_float_to_9_7_u16(v) for v in (5.0, 5.0, -1.0))
    ray_dir = tuple(convert_u16_to_float.convert_float_to_2_14_u16(v) for v in (0.0, 0.0, 1.0))
    dut.bv_count.value = 1
    dut.ray_origin.value = convert_u16_to_float.pack_vec3_u16(*ray_origin)
    dut.ray_dir.value = convert_u16_to_float.pack_vec3_u16(*ray_dir)

    # Start pulse
    dut.start.value = 1
    await ClockCycles(dut.clk, 1)
    dut.start.value = 0

    # state_q starts with S_RTU_LOAD
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 1
    assert int(dut.done.value) == 0

    # 66 + 60 + 40 + 90 = 256 cycles for a front hit
    seen_active = False
    for _ in range(256):
        # Active BV processing should appear before checkout.
        if int(dut.state_q.value) == 2:
            seen_active = True
        if int(dut.done.value) == 1:
            break
        await ClockCycles(dut.clk, 1)
    assert seen_active

    # Finished processing, state_q == S_CHECKOUT
    assert int(dut.done.value) == 1
    assert int(dut.state_q.value) == 3

    # state_q ends with S_IDLE
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 0

    # Verify results  
    expected_result = compute_expected_result(sram.sram, (ray_origin, ray_dir), sram.bv_num)
    _assert_full_result(expected_result, dut)


@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_hit_back(dut):
    dut._log.info("Start triangle_hit_back")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    # Build triangle scene with one BV
    sram = MockSRAM(dut, "FIXED")
    scene_words = sram.sram
    scene_words[:] = [0] * 512
    bv_addr = 17
    prim_addr = 47
    scene_words[bv_addr] = _pack_bv_w0(prim_addr, 1)
    scene_words[bv_addr + 1] = convert_u16_to_float.convert_float_to_9_7_u16(30.0)
    scene_words[bv_addr + 2 : bv_addr + 5] = [convert_u16_to_float.convert_float_to_9_7_u16(0.0),
                                              convert_u16_to_float.convert_float_to_9_7_u16(5.0),
                                              convert_u16_to_float.convert_float_to_9_7_u16(5.0)]
    scene_words[prim_addr:prim_addr + 12] = _triangle_words((0, 0, 0), (10, 0, 0), (0, 10, 0))
    sram.bv_num = 1
    cocotb.start_soon(sram.run("FIXED"))
    rtu = MOCK_RTU(dut, 1, "FIXED")

    # Setup back-facing ray
    ray_origin = tuple(convert_u16_to_float.convert_float_to_9_7_u16(v) for v in (5.0, 5.0, 1.0))
    ray_dir = tuple(convert_u16_to_float.convert_float_to_2_14_u16(v) for v in (0.0, 0.0, -1.0))
    dut.bv_count.value = 1
    dut.ray_origin.value = convert_u16_to_float.pack_vec3_u16(*ray_origin)
    dut.ray_dir.value = convert_u16_to_float.pack_vec3_u16(*ray_dir)

    # Start pulse
    dut.start.value = 1
    await ClockCycles(dut.clk, 1)
    dut.start.value = 0

    # state_q starts with S_RTU_LOAD
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 1
    assert int(dut.done.value) == 0
    
    # 66 + 66 + 43 + 90 = 265 cycles for a back hit
    seen_active = False
    for _ in range(265):
        # Active BV processing should appear before checkout.
        if int(dut.state_q.value) == 2:
            seen_active = True
        if int(dut.done.value) == 1:
            break
        await ClockCycles(dut.clk, 1)
    assert seen_active
    
    # Finished processing, state_q == S_CHECKOUT
    assert int(dut.done.value) == 1
    assert int(dut.state_q.value) == 3
    
    # state_q ends with S_IDLE
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 0

    # Verify results  
    expected_result = compute_expected_result(sram.sram, (ray_origin, ray_dir), sram.bv_num)
    _assert_full_result(expected_result, dut)


@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_miss(dut):
    dut._log.info("Start triangle_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    # Build triangle scene with one BV
    sram = MockSRAM(dut, "FIXED")
    scene_words = sram.sram
    scene_words[:] = [0] * 512
    bv_addr = 17
    prim_addr = 47
    scene_words[bv_addr] = _pack_bv_w0(prim_addr, 1)
    scene_words[bv_addr + 1] = convert_u16_to_float.convert_float_to_9_7_u16(30.0)
    scene_words[bv_addr + 2:bv_addr + 5] = [convert_u16_to_float.convert_float_to_9_7_u16(0.0),
                                            convert_u16_to_float.convert_float_to_9_7_u16(5.0),
                                            convert_u16_to_float.convert_float_to_9_7_u16(5.0)]
    scene_words[prim_addr:prim_addr + 12] = _triangle_words((0, 0, 0), (10, 0, 0), (0, 10, 0))
    sram.bv_num = 1
    cocotb.start_soon(sram.run("FIXED"))
    rtu = MOCK_RTU(dut, 1, "FIXED")

    # Miss ray: no hit, no ground fallback.
    ray_origin = tuple(convert_u16_to_float.convert_float_to_9_7_u16(v) for v in (20.0, 20.0, -1.0))
    ray_dir = tuple(convert_u16_to_float.convert_float_to_2_14_u16(v) for v in (0.0, 0.0, 1.0))
    dut.bv_count.value = 1
    dut.ray_origin.value = convert_u16_to_float.pack_vec3_u16(*ray_origin)
    dut.ray_dir.value = convert_u16_to_float.pack_vec3_u16(*ray_dir)
    
    # Start pulse
    dut.start.value = 1
    await ClockCycles(dut.clk, 1)
    dut.start.value = 0
    
    # state_q starts with S_RTU_LOAD
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 1
    assert int(dut.done.value) == 0
    
    # 66, fails stage 1's slid_s^2 > 225 check 
    seen_active = False
    for _ in range(66):
        # Active BV processing should appear before checkout.
        if int(dut.state_q.value) == 2:
            seen_active = True
        if int(dut.done.value) == 1:
            break
        await ClockCycles(dut.clk, 1)
    assert seen_active
    
    # Finished processing, state_q == S_CHECKOUT
    assert int(dut.done.value) == 1
    assert int(dut.state_q.value) == 3
    
    # state_q ends with S_IDLE
    await ClockCycles(dut.clk, 1)
    assert int(dut.state_q.value) == 0

    # Verify results  
    expected_result = compute_expected_result(sram.sram, (ray_origin, ray_dir), sram.bv_num)
    _assert_full_result(expected_result, dut)


#--------------------- GROUND TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_ground_hit(dut):
    dut._log.info("Start ground_hit")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_ground_miss(dut):
    dut._log.info("Start ground_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_miss(dut):
    dut._log.info("Start triangle_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

#--------------------- BEST HIT TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_closest_wins(dut):
    dut._log.info("Start closest_wins")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_multi_bv(dut):
    dut._log.info("Start multi_bv")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_object_on_surface(dut):
    dut._log.info("Start object_on_surface")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)
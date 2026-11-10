# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from mocked_componenet.mock_rtu import MOCK_RTU
from mocked_componenet.mock_sram import MockSRAM
from utils.generate_ray import generate_ray
from utils.compute_expected_result import compute_expected_result

test_mode = os.environ.get("TEST_MODE", "FIXED")


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


@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_intersection_unit(dut):
    dut._log.info("Start intersection_unit_test")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

    sram = MockSRAM(dut, test_mode)
    rtu = MOCK_RTU(dut, sram.bv_num, test_mode)
    cocotb.start_soon(sram.run(test_mode))
    ray_origin, ray_dir = await rtu.init_request(test_mode)

    expected_result = compute_expected_result(sram, (ray_origin, ray_dir), sram.bv_num)

    assert expected_result.hit == dut.hit.value
    assert expected_result.hit_ground == dut.hit_ground.value
    assert expected_result.hit_addr == dut.hit_addr.value
    assert expected_result.hit_point == dut.hit_point.value
    assert expected_result.n == dut.n.value
    assert expected_result.checker == dut.checker.value
    assert expected_result.hit_flip == dut.hit_flip.value

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

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_sphere_hit_inside(dut):
    dut._log.info("Start sphere_hit_inside")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_sphere_miss(dut):
    dut._log.info("Start sphere_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

#--------------------- TRIANGLE TESTS ---------------------#
@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_hit_front(dut):
    dut._log.info("Start triangle_hit_front")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_hit_back(dut):
    dut._log.info("Start triangle_hit_back")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_triangle_miss(dut):
    dut._log.info("Start triangle_miss")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())
    await _reset_dut(dut)

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
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





@cocotb.test(timeout_time=5, timeout_unit="sec")
async def test_intersection_unit(dut):
    dut._log.info("Start intersection_unit_test")
    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())

    dut.start.value = 0
    dut.ray_origin.value = 0
    dut.ray_dir.value = 0
    dut.bv_count.value = 0
    dut.sram_data.value = 0
    dut.sram_valid.value = 0

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

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





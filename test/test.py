# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import os
import random



test_mode = os.environ.get("TEST_MODE", "FIXED")










@cocotb.test()
async def test_intersection_unit(dut):
    dut._log.info("Start intersection_unit_test")

    clock = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clock.start())

    dut.start.value = 0
    dut.ray_origin.value = 0
    dut.ray_dir.value = 0
    dut.bv_count.value = 0
    dut.sram_data.value = 0
    #pull down rst n


    dut.rst_n.value = 0















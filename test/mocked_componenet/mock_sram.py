import random

from cocotb.triggers import ClockCycles, RisingEdge

from constant.constants import *
from utils.seed_scene_data import *


class MockSRAM:
    # dut input
    # dut.sram_addr
    # dut.sram_rd

    # dut output
    # dut.sram_data
    # dut.sram_valid
    sram = None
    dut = None
    bv_num = None

    def __init__(self, dut, test_mode):
        self.dut = dut
        self.sram = [0] * 512
        self.bv_num = generate_test_case_and_hydrate_sram(
            self.sram, test_mode
        )

    async def run(self, test_mode):
        self.dut.sram_valid.value = 0
        self.dut.sram_data.value = 0

        while True:
            await RisingEdge(self.dut.clk)

            if int(self.dut.rst_n.value) == 0:
                self.dut.sram_valid.value = 0
                continue
            if int(self.dut.sram_rd.value) != 1:
                continue

            addr = int(self.dut.sram_addr.value)
            if test_mode == "FIXED":
                delay = 10
            else:
                delay = random.randint(0, 50)

            if delay:
                await ClockCycles(self.dut.clk, delay)

            await RisingEdge(self.dut.clk)
            self.dut.sram_data.value = self.sram[addr]
            self.dut.sram_valid.value = 1

            await RisingEdge(self.dut.clk)
            self.dut.sram_valid.value = 0

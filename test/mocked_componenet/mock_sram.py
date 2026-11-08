import random
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles



from test.utils.convert_u16_to_float import _u16
from test.utils.seed_scene_data import *
from test.constant.constants import *



class MockSRAM:
    # dut input
    #dut.sram_addr
    #dut.sram_rd

    #dut output
    #dut.sram_data
    #dut.sram_valid
    sram = None
    dut = None
    bv_num = None
    def __init__(self,dut,test_mode):
        self.dut = dut
        self.sram = [0] * 512
        self.bv_num = generate_test_case_and_hydrate_sram(
            self.sram, test_mode
        )


    async def run(self,test_mode):
        self.dut.sram_valid.value = 0
        self.dut.sram_data.value=0

        while True:
            await rising_edge(self.dut.clk)

            if int(self.dut.rst_n.value) == 0:
                self.dut.sram_valid.value = 0
                continue
            if int(self.dut.sram_rd.value) == 1:
            addr = int(self.dut.sram_addr.value)
            if test_mode == "FIXED":
                delay = 10
            else:
                delay = random.randint(0, 50)  # extra clocks after the rd pulse
            
            if delay:
                #make it unpredictable for IU, why not LOL
                await ClockCycles(self.dut.clk, delay)


            await RisingEdge(self.dut.clk)
            self.dut.sram_data.value = self.sram[addr]
            self.dut.sram_valid.value = 1

            await RisingEdge(self.dut.clk)
            self.dut.sram_valid.value = 0


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import os
import random


class MockSRAM:
    # dut input
    #dut.sram_addr
    #dut.sram_rd

    #dut output
    #dut.sram_data
    #dut.sram_valid
    sram = [0] * 512
    
    def __init__(self,dut):

    async def run(self,dut):


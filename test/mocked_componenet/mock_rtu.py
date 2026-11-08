import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import os
import random
from test.utils.convert_u16_to_float import _u16, convert_u16_to_9_7_float, convert_u16_to_2_14_float

from test.constant.macro_opcode import *
from test.utils.generate_ray import generate_ray
from test.utils.vector_algebra import vector_algebra


class MOCK_MACRO_OPS:
    #dut input
    #dut.req_valid
    #dut.req_op
    #dut.resp_ready

    #dut output
    #dut.req_ready
    #dut.resp_valid
    #dut.resp_result
    dut = None
    def __init__(self,dut):
        self.dut = dut
  

    async def run(self,test_mode):



class MOCK_RTU(MOCK_MACRO_OPS): 
    #dut input
    #dut.done

    #dut output
    #dut.start
    #dut.ray_origin
    #dut.ray_dir
    #dut.bv_count
    dut = None
    bv_num = None
    def __init__(self,dut,bv_num,test_mode):
        super().__init__(dut)
        self.dut = dut
        self.bv_num = bv_num
        self.dut.bv_num.value = bv_num

        self.run(test_mode)

    async def run(self,test_mode):
        super().run(test_mode)

    async def init_request(self,test_mode):

        

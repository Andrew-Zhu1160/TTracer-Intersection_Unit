# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import os
import random

#FIXED:use a fixed set of input
#RANDOM:use a random set of input
test_mode = os.environ.get("TEST_MODE", "FIXED")
is_fixed_mode = test_mode == "FIXED"

#fixed input no matter what the test mode is
word_size=16
BV_word_count=5
BV_start_addr = 17

SPHERE_WORD_COUNT = 7
TRIANGLE_WORD_COUNT = 12

SRAM_DEPTH = 512

#position and dimention max are all rnage of signed 16 bit integer
POS_MIN = -32768   # -256
POS_MAX =  32767   #  255.992
# Sphere centre, triangle corner v0, bounding-volume centre: x and y.
MIN_COORD_XY = POS_MIN
MAX_COORD_XY = POS_MAX
# Object z, and camera height. Ground is z = 0. Applies to sphere centres
# and triangle corners, not to a negative edge component.
MIN_COORD_Z = 0
MAX_COORD_Z = POS_MAX
# Sphere and bounding-volume radius. 0 has no highest 1-bit, so K is undefined.
MIN_R = 1          # 1/128
MAX_R = POS_MAX
# Any centre or triangle corner the chip subtracts from a ray origin
# must be less than 256 away in that axis.
MAX_DELTA = 32767  # 255.992, strictly below 256




if is_fixed_mode:
    #use a fixed set of input
    BV_count = 6
    #address of the first primitive
    Primitive_start_addr = 17 + BV_count*BV_word_count-1
    #address map
    #max 2^7-1
    P_count_in_BV=[5,3,2,4,1,3]
    BV=[
        #array of 5 words, each word is a 16 bit vector
        [
            #        [15:7]                [6:0]
            (Primitive_start_addr<<7) + P_count_in_BV[0],
            #R value
            347,
            #Z value
            549,
            #Y value
            -751,
            #X value
            953,
        ],
        [(Primitive_start_addr+5)<<7+P_count_in_BV[1],127,987,-654,321],
        [(Primitive_start_addr+10)<<7+P_count_in_BV[2],MAX_R,456-,789,101],
        [(Primitive_start_addr+15)<<7+P_count_in_BV[3],123,MAX_COORD_Z,789,MIN_COORD_Z],
        [(Primitive_start_addr+20)<<7+P_count_in_BV[4],123,MIN_COORD_Z,MAX_COORD_XY,-101],
        [(Primitive_start_addr+25)<<7+P_count_in_BV[5],MAX_R,127,MAX_COORD_XY,101]
    ]
    Primitive=[
        {
            #all sphere, trivial case
            "total_word_count": P_count_in_BV[0]*SPHERE_WORD_COUNT,
            "objects":[
                #array len dictate by P_count_in_BV[0]
                [],
                [],
                [],
                [],
                []
            ]
        },
        {}
    ]

    


else:
    #use a random set of input
    BV_count = random.randint(1, 16)
    Primitive_start_addr = 17 + BV_count*BV_word_count-1



class MOCK_MACRO_OPS:
    #dut input
    #dut.req_valid
    #dut.req_op
    #dut.resp_ready

    #dut output
    #dut.req_ready
    #dut.resp_valid
    #dut.resp_result

    def __init__(self,dut):

    async def run(self,dut):



class MOCK_RTU: 
    #dut input
    #dut.done

    #dut output
    #dut.start
    #dut.ray_origin
    #dut.ray_dir
    #dut.bv_count

    def __init__(self,dut):

    async def run(self,dut):


#output by the intersection unit under assertion
#dut.hit
#dut.hit_ground
#dut.hit_t
#dut.hit_addr
#dut.hit_flip


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















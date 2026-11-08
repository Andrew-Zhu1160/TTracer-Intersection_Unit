import random

import cocotb
from cocotb.triggers import ClockCycles, First, RisingEdge, Timer

from constant.constants import (
    CRV_MACRO_WAIT_MAX,
    TEST_TIMEOUT_MIN,
    WAIT_TILL_VALID,
)
from constant.macro_opcode import M_EQ, M_GE, M_LT, M_NE
from utils.convert_u16_to_float import (
    convert_float_to_2_14_u16,
    convert_float_to_9_7_u16,
    pack_vec3_u16,
)
from utils.generate_ray import generate_ray
from utils.vector_algebra import vector_algebra

_COMPARE_OPS = {M_EQ, M_NE, M_LT, M_GE}


def _unpack_vec3(bits48):
    bits48 = int(bits48) & ((1 << 48) - 1)
    x = bits48 & 0xFFFF
    y = (bits48 >> 16) & 0xFFFF
    z = (bits48 >> 32) & 0xFFFF
    return (x, y, z)


def _encode_result(result, opcode, fmt):
    to_u16 = (
        convert_float_to_2_14_u16 if fmt == "dir" else convert_float_to_9_7_u16
    )
    if isinstance(result, (tuple, list)):
        x, y, z = result
        return pack_vec3_u16(to_u16(x), to_u16(y), to_u16(z))
    if opcode in _COMPARE_OPS:
        return pack_vec3_u16(1 if result else 0, 0, 0)
    return pack_vec3_u16(to_u16(result), 0, 0)


class MOCK_MACRO_OPS:
    # dut input
    # dut.req_valid
    # dut.req_op
    # dut.resp_ready

    # dut output
    # dut.req_ready
    # dut.resp_valid
    # dut.resp_result
    dut = None

    def __init__(self, dut):
        self.dut = dut
        self._drive_idle()

    def _drive_idle(self):
        self.dut.req_ready.value = 1
        self.dut.resp_valid.value = 0
        self.dut.resp_result.value = 0

    async def _wait_cycles_or_reset(self, n):
        """Wait n posedges. Return True if rst_n dropped."""
        for _ in range(n):
            await RisingEdge(self.dut.clk)
            if int(self.dut.rst_n.value) == 0:
                return True
        return False

    async def run(self, test_mode):
        self._drive_idle()

        while True:
            await RisingEdge(self.dut.clk)

            if int(self.dut.rst_n.value) == 0:
                self._drive_idle()
                continue

            if int(self.dut.req_valid.value) != 1:
                continue

            req_op = int(self.dut.req_op.value)
            fmt_bit = (req_op >> 101) & 1
            u = _unpack_vec3(req_op >> 53)
            v = _unpack_vec3(req_op >> 5)
            opcode = req_op & 0x1F
            fmt = "dir" if fmt_bit else "pos"
            result = _encode_result(
                vector_algebra(opcode, u, v, fmt=fmt), opcode, fmt
            )

            wait_low = (
                WAIT_TILL_VALID
                if test_mode == "FIXED"
                else random.randint(0, CRV_MACRO_WAIT_MAX)
            )

            # Next posedge: IU samples req_ready=0; hold it low wait_low cycles.
            if wait_low > 0:
                self.dut.req_ready.value = 0
                if await self._wait_cycles_or_reset(wait_low):
                    self._drive_idle()
                    continue

            self.dut.req_ready.value = 1
            if await self._wait_cycles_or_reset(WAIT_TILL_VALID):
                self._drive_idle()
                continue

            self.dut.resp_result.value = result
            self.dut.resp_valid.value = 1

            saw_resp_ready = False
            while not saw_resp_ready:
                await RisingEdge(self.dut.clk)
                if int(self.dut.rst_n.value) == 0:
                    break
                if int(self.dut.resp_ready.value) == 1:
                    saw_resp_ready = True

            if int(self.dut.rst_n.value) == 0:
                self._drive_idle()
                continue

            await RisingEdge(self.dut.clk)
            if int(self.dut.rst_n.value) == 0:
                self._drive_idle()
                continue
            self.dut.resp_valid.value = 0


class MOCK_RTU(MOCK_MACRO_OPS):
    # dut input
    # dut.done

    # dut output
    # dut.start
    # dut.ray_origin
    # dut.ray_dir
    # dut.bv_count
    dut = None
    bv_num = None

    def __init__(self, dut, bv_num, test_mode):
        super().__init__(dut)
        self.dut = dut
        self.bv_num = bv_num
        self.dut.bv_count.value = bv_num
        cocotb.start_soon(self.run(test_mode))

    async def run(self, test_mode):
        await super().run(test_mode)

    async def init_request(self, test_mode):
        origin, direction = generate_ray(test_mode)
        self.dut.ray_origin.value = pack_vec3_u16(*origin)
        self.dut.ray_dir.value = pack_vec3_u16(*direction)

        self.dut.start.value = 1
        await ClockCycles(self.dut.clk, 1)
        self.dut.start.value = 0

        timeout = Timer(TEST_TIMEOUT_MIN, units="min")
        result = await First(RisingEdge(self.dut.done), timeout)
        if result is timeout:
            raise AssertionError(
                f"timed out after {TEST_TIMEOUT_MIN} min waiting for dut.done"
            )

        return self.dut.ray_origin.value, self.dut.ray_dir.value
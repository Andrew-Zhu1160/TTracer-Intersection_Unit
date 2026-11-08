def _signed16(raw):
    """16-bit two's complement. Accepts a bit pattern 0..65535 or a signed lane -32768..32767."""
    raw = int(raw)
    if raw < 0:
        if raw < -32768:
            raise ValueError(f"{raw} does not fit in a signed 16-bit lane")
        return raw
    raw &= 0xFFFF
    if raw & 0x8000:
        raw -= 0x10000
    return raw
def convert_u16_to_9_7_float(raw):
    """POS, Q9.7. value = raw / 2^7."""
    return _signed16(raw) / 128.0
def convert_u16_to_2_14_float(raw):
    """DIR, Q2.14. value = raw / 2^14."""
    return _signed16(raw) / 16384.0
def _u16(value):
    """Return the 16-bit SRAM representation of a signed or unsigned value."""
    return value & 0xFFFF


def _clamp_signed16(raw_int):
    """Clamp a signed integer to 16 bits: 16'h7FFF / 16'h8000."""
    if raw_int > 32767:
        return 0x7FFF
    if raw_int < -32768:
        return 0x8000
    return _u16(raw_int)


def convert_float_to_9_7_u16(value):
    """POS, Q9.7. raw = round(value * 2^7), clamped."""
    return _clamp_signed16(int(round(value * 128.0)))


def convert_float_to_2_14_u16(value):
    """DIR, Q2.14. raw = round(value * 2^14), clamped."""
    return _clamp_signed16(int(round(value * 16384.0)))


def pack_vec3_u16(x, y, z):
    """Pack three 16-bit lanes as IU resp_result: z [47:32], y [31:16], x [15:0]."""
    return (_u16(z) << 32) | (_u16(y) << 16) | _u16(x)
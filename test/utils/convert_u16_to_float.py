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
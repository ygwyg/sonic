"""Forward error correction: convolutional coding, CRC and interleaving."""

from sonic.fec import convolutional
from sonic.fec.crc import crc32, append_crc, verify_crc
from sonic.fec.interleaver import interleave, deinterleave, scramble, descramble_llr

__all__ = ["convolutional", "crc32", "append_crc", "verify_crc", "interleave", "deinterleave", "scramble", "descramble_llr"]

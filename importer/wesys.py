"""PES/eFootball WESYS zlib container."""

from __future__ import annotations

import struct
import zlib


WESYS_MAGIC = b"WESYS"


def is_wesys(data: bytes) -> bool:
    return data.startswith(WESYS_MAGIC)


def decompress_wesys(data: bytes) -> bytes:
    if not is_wesys(data):
        return data
    compressed_size, uncompressed_size = struct.unpack_from("<II", data, 5)
    payload = data[13 : 13 + compressed_size]
    out = zlib.decompress(payload)
    if uncompressed_size and len(out) != uncompressed_size:
        raise ValueError(
            f"WESYS size mismatch: got {len(out)}, expected {uncompressed_size}"
        )
    return out

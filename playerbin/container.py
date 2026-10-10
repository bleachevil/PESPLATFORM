"""Open an eFootball 2027 v6 table container.

The file is a 16-byte header plus a payload. The marker text starts at byte 3,
so a check at byte 0 never sees it. A 32-bit xorshift stream covers whole
words; any trailing 1–3 bytes are left unchanged. A normal table is zlib
after that stream. A stored table is the stream only.
"""

from __future__ import annotations

import zlib

# Low nibble of header byte 1 selects the triple. v6 tables on disk use nibble 2.
_KEY_TRIPLES = {
    1: (0x168EA000, 0x2E2AA6F2, 0x0CC8DCD3),
    2: (0xED5B2960, 0x4A523B4E, 0xF3A31BAD),
}

_HEADER = 16
_MARKER = b"WESYS"


class ContainerError(ValueError):
    pass


def looks_like_container(blob: bytes) -> bool:
    return len(blob) >= _HEADER and blob[3:8] == _MARKER


def _mix_word(x: int, y: int, z: int, w: int) -> tuple[int, int, int, int]:
    folded = (x ^ ((x << 11) & 0xFFFFFFFF)) & 0xFFFFFFFF
    x, y, z = y, z, w
    mixed = (w >> 11) ^ folded
    w = (w ^ (mixed >> 8) ^ folded) & 0xFFFFFFFF
    return x, y, z, w


def _apply_stream(payload: bytes, nibble: int, compressed: int, original: int) -> bytes:
    try:
        x, y, z = _KEY_TRIPLES[nibble]
    except KeyError as exc:
        raise ContainerError(f"unknown key nibble {nibble}") from exc
    if len(payload) != compressed:
        raise ContainerError(f"payload length {len(payload)} != header {compressed}")

    seed = ((original << 16) | compressed) & 0xFFFFFFFF
    out = bytearray(payload)
    covered = len(out) - (len(out) % 4)
    for offset in range(0, covered, 4):
        x, y, z, seed = _mix_word(x, y, z, seed)
        word = int.from_bytes(out[offset : offset + 4], "little") ^ seed
        out[offset : offset + 4] = word.to_bytes(4, "little")
    return bytes(out)


def open_container(blob: bytes) -> bytes:
    if not looks_like_container(blob):
        raise ContainerError("missing v6 table marker")

    shape = blob[2]
    nibble = blob[1] & 0x0F
    compressed = int.from_bytes(blob[8:12], "little")
    original = int.from_bytes(blob[12:16], "little")
    payload = blob[_HEADER:]

    if compressed == 0 and original == 0:
        if payload:
            raise ContainerError("empty table still has a payload")
        return b""

    clear = _apply_stream(payload, nibble, compressed, original)
    if shape == 0x02 and compressed == original:
        return clear

    try:
        unpacked = zlib.decompress(clear)
    except zlib.error as exc:
        raise ContainerError("payload did not decrypt to zlib") from exc
    if len(unpacked) != original:
        raise ContainerError(f"unpacked {len(unpacked)} bytes, header said {original}")
    return unpacked

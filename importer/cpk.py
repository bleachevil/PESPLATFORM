"""CRIWARE CPK reader (documented archive format, like zip)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


STORAGE_MASK = 0xF0
STORAGE_NONE = 0x00
STORAGE_ZERO = 0x10
STORAGE_CONSTANT = 0x30
STORAGE_PERROW = 0x50

TYPE_MASK = 0x0F
TYPE_U8 = 0x00
TYPE_S8 = 0x01
TYPE_U16 = 0x02
TYPE_S16 = 0x03
TYPE_U32 = 0x04
TYPE_S32 = 0x05
TYPE_U64 = 0x06
TYPE_S64 = 0x07
TYPE_FLOAT = 0x08
TYPE_STRING = 0x0A
TYPE_DATA = 0x0B

TYPE_SIZES = {
    TYPE_U8: 1,
    TYPE_S8: 1,
    TYPE_U16: 2,
    TYPE_S16: 2,
    TYPE_U32: 4,
    TYPE_S32: 4,
    TYPE_U64: 8,
    TYPE_S64: 8,
    TYPE_FLOAT: 4,
    TYPE_STRING: 4,
    TYPE_DATA: 8,
}


def decrypt_utf(data: bytes) -> bytes:
    """CRI UTF table obfuscation used by the CPK format (key 0x5F, mul 0x15)."""
    m = 0x5F
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ m
        m = (m * 0x15) & 0xFF
    return bytes(out)


def maybe_decrypt_utf(packet: bytes) -> bytes:
    if packet.startswith(b"@UTF"):
        return packet
    decrypted = decrypt_utf(packet)
    if decrypted.startswith(b"@UTF"):
        return decrypted
    raise ValueError("Not a CRI @UTF table")


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _read_cstring(data: bytes, off: int) -> str:
    end = data.find(b"\x00", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("utf-8", errors="replace")


def _read_value(kind: int, buf: bytes, off: int, strings_off: int, data_off: int) -> object:
    if kind == TYPE_U8:
        return buf[off]
    if kind == TYPE_S8:
        return struct.unpack_from(">b", buf, off)[0]
    if kind == TYPE_U16:
        return _u16(buf, off)
    if kind == TYPE_S16:
        return struct.unpack_from(">h", buf, off)[0]
    if kind == TYPE_U32:
        return _u32(buf, off)
    if kind == TYPE_S32:
        return struct.unpack_from(">i", buf, off)[0]
    if kind == TYPE_U64:
        return struct.unpack_from(">Q", buf, off)[0]
    if kind == TYPE_S64:
        return struct.unpack_from(">q", buf, off)[0]
    if kind == TYPE_FLOAT:
        return struct.unpack_from(">f", buf, off)[0]
    if kind == TYPE_STRING:
        return _read_cstring(buf, strings_off + _u32(buf, off))
    if kind == TYPE_DATA:
        rel, size = struct.unpack_from(">II", buf, off)
        start = data_off + rel
        return buf[start : start + size]
    raise ValueError(f"Unknown UTF type {kind}")


class UtfTable:
    def __init__(self, packet: bytes):
        packet = maybe_decrypt_utf(packet)
        if not packet.startswith(b"@UTF"):
            raise ValueError("Invalid UTF magic")
        self.raw = packet
        table_size = _u32(packet, 4)
        # Offsets are relative to byte 8 (table_size field).
        base = 8
        rows_off = base + _u32(packet, 8)
        strings_off = base + _u32(packet, 12)
        data_off = base + _u32(packet, 16)
        name_off = _u32(packet, 20)
        ncols = _u16(packet, 24)
        row_width = _u16(packet, 26)
        nrows = _u32(packet, 28)
        self.name = _read_cstring(packet, strings_off + name_off)
        self.columns: list[tuple[str, int, object]] = []
        pos = 32
        for _ in range(ncols):
            flag = packet[pos]
            pos += 1
            cname = _read_cstring(packet, strings_off + _u32(packet, pos))
            pos += 4
            storage = flag & STORAGE_MASK
            kind = flag & TYPE_MASK
            const = None
            if storage == STORAGE_CONSTANT:
                const = _read_value(kind, packet, pos, strings_off, data_off)
                pos += TYPE_SIZES.get(kind, 0)
            self.columns.append((cname, flag, const))
        self.rows: list[dict[str, object]] = []
        for r in range(nrows):
            row: dict[str, object] = {}
            cursor = rows_off + r * row_width
            for cname, flag, const in self.columns:
                storage = flag & STORAGE_MASK
                kind = flag & TYPE_MASK
                if storage == STORAGE_NONE or storage == STORAGE_ZERO:
                    row[cname] = 0 if kind != TYPE_STRING else ""
                elif storage == STORAGE_CONSTANT:
                    row[cname] = const
                else:
                    row[cname] = _read_value(kind, packet, cursor, strings_off, data_off)
                    cursor += TYPE_SIZES.get(kind, 0)
            self.rows.append(row)
        self.table_size = table_size


@dataclass
class CpkFile:
    dir_name: str
    file_name: str
    offset: int
    size: int
    extract_size: int

    @property
    def path(self) -> str:
        if self.dir_name and self.dir_name not in ("", "<NULL>"):
            return f"{self.dir_name}/{self.file_name}".replace("\\", "/")
        return self.file_name


class CpkArchive:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if self.data[:4] != b"CPK ":
            raise ValueError(f"Not a CPK file: {self.path}")
        packet_size = struct.unpack_from("<Q", self.data, 8)[0]
        header = UtfTable(self.data[16 : 16 + packet_size])
        row = header.rows[0]
        self.toc_offset = int(row.get("TocOffset") or 0)
        self.content_offset = int(row.get("ContentOffset") or 0)
        self.files: list[CpkFile] = []
        if self.toc_offset:
            self._read_toc()

    def _read_packet(self, offset: int) -> bytes:
        size = struct.unpack_from("<Q", self.data, offset + 8)[0]
        return self.data[offset + 16 : offset + 16 + size]

    def _read_toc(self) -> None:
        if self.data[self.toc_offset : self.toc_offset + 4] != b"TOC ":
            raise ValueError("TOC signature not found")
        toc = UtfTable(self._read_packet(self.toc_offset))
        add_offset = min(self.toc_offset, self.content_offset) if self.content_offset else self.toc_offset
        for row in toc.rows:
            self.files.append(
                CpkFile(
                    dir_name=str(row.get("DirName") or ""),
                    file_name=str(row.get("FileName") or ""),
                    offset=int(row.get("FileOffset") or 0) + add_offset,
                    size=int(row.get("FileSize") or 0),
                    extract_size=int(row.get("ExtractSize") or 0),
                )
            )

    def iter_files(self) -> Iterator[CpkFile]:
        yield from self.files

    def read_file(self, entry: CpkFile) -> bytes:
        return self.data[entry.offset : entry.offset + entry.size]

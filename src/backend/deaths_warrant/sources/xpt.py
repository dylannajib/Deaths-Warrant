"""Read SAS transport (XPORT v5) files, the format NHANES publishes, with the standard library.

Only what NHANES uses: one member per file, numeric variables as IBM/370 floating point and
character variables as fixed-width text. SAS missing values ("." and ".A"-".Z") become None.
"""

from __future__ import annotations

import struct
from pathlib import Path

_RECORD = 80
_NAMESTR = 140


def _ibm_to_float(raw: bytes) -> float | None:
    if raw[1:] == b"\x00" * (len(raw) - 1) and raw[0] in (0x2E, 0x5F, *range(0x41, 0x5B)):
        return None  # SAS missing value
    mantissa = int.from_bytes(raw[1:], "big")
    if mantissa == 0:
        return 0.0
    sign = -1.0 if raw[0] & 0x80 else 1.0
    exponent = (raw[0] & 0x7F) - 64
    return sign * mantissa / float(1 << (8 * (len(raw) - 1))) * 16.0**exponent


def read_xpt(path: Path) -> list[dict[str, float | str | None]]:
    data = path.read_bytes()
    if not data.startswith(b"HEADER RECORD*******LIBRARY HEADER RECORD"):
        raise ValueError(f"{path} is not a SAS transport file")
    marker = data.index(b"HEADER RECORD*******NAMESTR HEADER RECORD")
    count = int(data[marker + 54 : marker + 58])
    start = marker + _RECORD
    variables = []
    for k in range(count):
        ns = data[start + k * _NAMESTR : start + (k + 1) * _NAMESTR]
        ntype, _, length = struct.unpack(">hhh", ns[:6])
        name = ns[8:16].decode("ascii").strip()
        position = struct.unpack(">i", ns[84:88])[0]
        variables.append((name, ntype == 1, length, position))
    obs = data.index(b"HEADER RECORD*******OBS     HEADER RECORD", start) + _RECORD
    width = max(pos + length for _, _, length, pos in variables)
    rows = []
    for offset in range(obs, len(data) - width + 1, width):
        chunk = data[offset : offset + width]
        if chunk.strip(b" ") == b"":  # trailing padding
            break
        row: dict[str, float | str | None] = {}
        for name, numeric, length, pos in variables:
            raw = chunk[pos : pos + length]
            row[name] = _ibm_to_float(raw) if numeric else raw.decode("latin-1").strip()
        rows.append(row)
    return rows

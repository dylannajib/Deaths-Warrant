"""Read the first sheet of a simple .xlsx file with the standard library (no openpyxl)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET  # noqa: S405 - files from government sources only

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        strings = [
            "".join(t.text or "" for t in si.iter(f"{_NS}t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_NS}si")  # noqa: S314
        ]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))  # noqa: S314
    rows = []
    for row in sheet.iter(f"{_NS}row"):
        cells = []
        for c in row.iter(f"{_NS}c"):
            v = c.find(f"{_NS}v")
            text = "" if v is None or v.text is None else v.text
            cells.append(strings[int(text)] if c.get("t") == "s" and text else text)
        rows.append(cells)
    return rows

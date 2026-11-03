"""Build ``_shared/life_tables/us_2024.json`` from the NCHS United States Life Tables, 2024.

python -m deaths_warrant.sources.nchs_life_table

Source: Arias E, Xu JQ, Kochanek K. United States life tables, 2024. National Vital Statistics
Reports vol 75 no 5. NCHS. Public domain (U.S. Government work).
The open "100 and over" row has q = 1. It is replaced by the constant hazard 1/e(100) implied
by that row's life expectancy, so survival beyond 100 decays smoothly instead of dropping to 0.
"""

from __future__ import annotations

import json
import math

from ..registry import SHARED_DIR
from . import fetch
from .xlsx import read_rows

BASE = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/NVSR/75-05/"
TABLES = {"male": "Table02.xlsx", "female": "Table03.xlsx"}
SOURCE = "nchs_us_2024"


def probabilities(rows: list[list[str]], sex: str) -> list[float]:
    title = rows[0][0]
    if f"for {sex}s: United States, 2024" not in title:
        raise ValueError(f"unexpected table: {title!r}")
    q: list[float] = []
    for row in rows[3:]:
        age = row[0] if row else ""
        if age == f"{len(q)}-{len(q) + 1}":
            q.append(float(row[1]))
        elif age == "100 and over":
            q.append(1 - math.exp(-1 / float(row[6])))
            return q
    raise ValueError("no '100 and over' row")


def main() -> None:
    table = {"source": SOURCE}
    for sex, name in TABLES.items():
        table[sex] = probabilities(read_rows(fetch(BASE + name, f"nchs_2024_{name}")), sex)
        assert len(table[sex]) == 101
    out = SHARED_DIR / "life_tables" / "us_2024.json"
    out.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

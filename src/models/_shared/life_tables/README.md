# Population life tables

Each file holds `{source, female, male}`, where `female` and `male` are the annual probability
of death q(x) for whole ages x = 0, 1, … The last age repeats beyond the end of the table.
Models load a table with `deaths_warrant.registry.load_life_table(name)`.

| File | Source | Built by |
|---|---|---|
| `us_2024.json` | Arias E, Xu JQ, Kochanek K. *United States life tables, 2024.* National Vital Statistics Reports vol 75 no 5. NCHS, tables 2 (males) and 3 (females). U.S. Government work, public domain. | `python -m deaths_warrant.sources.nchs_life_table` |

In the source, the open-ended "100 and over" row has q = 1. It is replaced by
`1 − exp(−1/e(100))`, the constant hazard implied by that row's life expectancy, so survival
beyond 100 decays smoothly. `tests/test_models.py` checks that the stored table reproduces
the published life expectancy at ages 65 and 80 to within 0.02 years.

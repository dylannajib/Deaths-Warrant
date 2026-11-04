# Life tables

Each file holds `{source, female, male}`: the yearly chance of death q(x) for ages 0, 1, 2 and
so on. The last age repeats. Load one with `general.registry.load_life_table(name)`.

`us_2024.json`: Arias E, et al. *United States life tables, 2024.* NVSR 75(5), NCHS, tables 2
and 3. Public domain. Built by `python -m general.sources.nchs_life_table`. The "100 and over"
row (q = 1) is replaced by the constant hazard from its life expectancy.

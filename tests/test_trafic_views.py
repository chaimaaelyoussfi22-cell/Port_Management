# -*- coding: utf-8 -*-
"""Smoke tests — moteur trafic_views sur données synthétiques."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from datetime import datetime

from components.dashboard.trafic_views import (
    OP_ORDER, OP_COLORS, _bt, _cat, available_years, scope, present_types,
    period_label, period_prev, _fmt_tons, kpi_block, monthly_volume,
    daily_volume, volume_by_category_type, top_cats, fig_evolution,
    fig_grouped_type)

ok = []
fail = []
def check(name, cond):
    if cond:
        ok.append(name)
    else:
        fail.append(name)
        print(f"  FAIL  {name}")

# 1. Constantes
print("=== 1. Constantes ===")
check("OP_ORDER=3 types", OP_ORDER == ["Cabotage", "Import", "Export"])
check("OP_COLORS bleu/rouge/orange",
      OP_COLORS["Cabotage"] == "#56a8ff" and OP_COLORS["Import"] == "#ff6077"
      and OP_COLORS["Export"] == "#ff9d66")

# 2. _bt
print("=== 2. _bt ===")
df = pd.DataFrame({"year": [2025, 2025], "month": [1, 1],
                    "tonnage": ["100", "200"], "navire_name": ["A", "B"]})
check("tonnage->numeric", _bt(df)["tonnage"].tolist() == [100.0, 200.0])
df_bad = pd.DataFrame({"year": [2025], "month": [None], "tonnage": [50]})
check("drop NaN month", len(_bt(df_bad)) == 0)

# 3. scope
print("=== 3. scope ===")
df3 = pd.DataFrame({"year": [2025, 2025, 2025], "month": [1, 2, 3],
                     "tonnage": [1, 2, 3], "type_trafic": ["Import", "Export", "Cabotage"]})
check("scope all", len(scope(df3, 2025)) == 3)
check("scope months", len(scope(df3, 2025, [1, 2])) == 2)
check("scope missing year", len(scope(df3, 2024)) == 0)

df4 = pd.DataFrame({
    "year": [2025, 2025], "month": [3, 3],
    "date": [datetime(2025, 3, 5), datetime(2025, 3, 10)],
    "tonnage": [10, 20], "type_trafic": ["Import", "Export"]})
check("scope days", len(scope(df4, 2025, [3], [5])) == 1)
check("scope days match", scope(df4, 2025, [3], [5])["tonnage"].iloc[0] == 10.0)

# 4. present_types
print("=== 4. present_types ===")
check("3 types", sorted(present_types(df3, 2025)) == sorted(["Cabotage", "Export", "Import"]))
check("no data", present_types(df3, 2024) == [])

# 5. period_label / period_prev
print("=== 5. period_label / period_prev ===")
check("full year", period_label(2025) == "2025")
check("single month", period_label(2025, [3]) == "Mars 2025")
check("multi months", "Mars" in period_label(2025, [3, 6]))
check("with days", "jours" in period_label(2025, [3], [1, 15]))
check("prev year", period_prev("Mars 2025") == "Mars 2024")
check("prev full", period_prev("2025") == "2024")

# 6. _fmt_tons
print("=== 6. _fmt_tons ===")
check("fmt", _fmt_tons(1250000) == "1\u00a0250\u00a0000 t")
check("fmt zero", _fmt_tons(0) == "0 t")

# 7. kpi_block
print("=== 7. kpi_block ===")
df_big = pd.DataFrame({
    "year": [2025, 2025, 2025, 2024],
    "month": [1, 1, 2, 1],
    "tonnage": [100, 50, 100, 80],
    "type_trafic": ["Import", "Export", "Import", "Import"]})
kb = kpi_block(df_big, 2025)
check("kpi total", kb["total"] == 250.0)
check("kpi import", kb["Import"] == 200.0)
check("kpi export", kb["Export"] == 50.0)
check("kpi cabotage=0", kb["Cabotage"] == 0.0)
check("kpi prev", kb["prev_total"] == 80.0)
check("kpi evo", kb["evolution"] == round(100 * (250 - 80) / 80, 1))
kb2 = kpi_block(df_big, 2024)
check("kpi evo None", kb2["evolution"] is None)
kb3 = kpi_block(df_big, 2025, types=["Import"])
check("kpi filter type", kb3["total"] == 200.0 and kb3["Export"] == 0.0)

# 8. monthly_volume
print("=== 8. monthly_volume ===")
mv = monthly_volume(df_big, 2025, OP_ORDER, [])
check("mv only months with data", sorted(mv.index.tolist()) == [1, 2])
check("mv jan", mv[1] == 150.0)
check("mv feb", mv[2] == 100.0)
check("mv mar absent (no zero fill)", 3 not in mv.index)
mv_f = monthly_volume(df_big, 2025, ["Import"], [])
check("mv filter import", mv_f[1] == 100.0 and mv_f[2] == 100.0)
mv_2024 = monthly_volume(df_big, 2024, OP_ORDER, [])
check("mv 2024 only jan with data", sorted(mv_2024.index.tolist()) == [1]
      and mv_2024[1] == 80.0)

# 9. daily_volume (Feb leap year)
print("=== 9. daily_volume ===")
df_feb = pd.DataFrame({
    "year": [2024, 2023, 2024],
    "month": [2, 2, 2],
    "date": [datetime(2024, 2, 29), datetime(2023, 2, 28), datetime(2024, 2, 15)],
    "tonnage": [50, 30, 100],
    "type_trafic": ["Import", "Export", "Import"]})
dv, nd = daily_volume(df_feb, 2024, 2, OP_ORDER, [])
check("feb ndays=29", nd == 29)
check("feb day29 present", 29 in dv.index and dv[29] == 50.0)
check("feb day15=100", dv[15] == 100.0)
dv_prev, nd_prev = daily_volume(df_feb, 2023, 2, OP_ORDER, [])
check("feb 2023 ndays=28", nd_prev == 28)

# 10. volume_by_category_type
print("=== 10. volume_by_category_type ===")
df_cat = pd.DataFrame({
    "year": [2025] * 5, "month": [1] * 5,
    "marchandise_norm": ["A", "A", "B", "B", "C"],
    "type_trafic": ["Import", "Export", "Import", "Cabotage", "Import"],
    "tonnage": [100, 50, 80, 30, 20]})
piv = volume_by_category_type(df_cat, 2025, [1], OP_ORDER, "marchandise_norm")
check("piv columns", list(piv.columns) == ["marchandise_norm", "Cabotage", "Import", "Export"])
check("piv A row", piv.iloc[0]["marchandise_norm"] == "A" and piv.iloc[0]["Import"] == 100.0)
check("piv sorted desc", piv["marchandise_norm"].tolist() == ["A", "B", "C"])
check("piv C export=0", piv[piv["marchandise_norm"] == "C"]["Export"].iloc[0] == 0.0)

# 11. top_cats
print("=== 11. top_cats ===")
tc = top_cats(df_cat, 2025, [1], OP_ORDER, "marchandise_norm", 2)
check("top2", tc == ["A", "B"])

# 12. fig_evolution
print("=== 12. fig_evolution ===")
fig1 = fig_evolution(df_big, 2025, "Année complète", 1, OP_ORDER, [])
check("fig1 no march = 2 traces", len(fig1.data) == 2)

df_multi = pd.DataFrame({
    "year": [2025, 2025, 2025, 2024, 2024, 2024], "month": [1] * 3 + [1] * 3,
    "marchandise_norm": ["X", "Y", "Z", "X", "Y", "Z"],
    "tonnage": [10, 20, 30, 8, 15, 25],
    "type_trafic": ["Import", "Import", "Export", "Import", "Import", "Export"]})
fig2 = fig_evolution(df_multi, 2025, "Année complète", 1, OP_ORDER, ["X", "Y", "Z"])
check("fig2 3 marches N+N-1 = 6 traces", len(fig2.data) == 6)

fig3 = fig_evolution(df_feb, 2024, "Par jour", 2, OP_ORDER, [])
check("fig3 daily mode traces", len(fig3.data) == 2)

df_empty = pd.DataFrame(columns=["year", "month", "tonnage", "type_trafic", "marchandise_norm"])
fig4 = fig_evolution(df_empty, 2025, "Année complète", 1, OP_ORDER, [])
check("fig4 empty -> None", fig4 is None)

# 13. fig_grouped_type
print("=== 13. fig_grouped_type ===")
fig5 = fig_grouped_type(piv, "marchandise_norm", "2025")
check("fig5 bars = 3 (3 types)", len(fig5.data) == 3)
check("fig5 color Import red", fig5.data[1].marker.color == OP_COLORS["Import"])

fig6 = fig_grouped_type(piv, "marchandise_norm", "2025", piv)
check("fig6 compare = 6 traces", len(fig6.data) == 6)

check("fig6 empty -> None", fig_grouped_type(None, "x", "p") is None)

# 14. Type absent des donnees
print("=== 14. Regression type absent ===")
df_no_cab = pd.DataFrame({
    "year": [2025, 2025], "month": [1, 2],
    "tonnage": [100, 200], "type_trafic": ["Import", "Export"]})
kb_no_cab = kpi_block(df_no_cab, 2025, types=["Cabotage"])
check("type absent = 0", kb_no_cab["Cabotage"] == 0.0 and kb_no_cab["total"] == 0.0)

# 15. Real data sanity
print("=== 15. Real data sanity ===")
try:
    from database import db_manager
    from components.dashboard.analytics import prepare_operations
    ops = db_manager.get_operations()
    prep = prepare_operations(ops)
    kb_real = kpi_block(prep, 2025, types=sorted(prep["type_trafic"].unique()))
    check("real kpi runs", kb_real["total"] >= 0)
    check("real kpi types sum to total",
          abs(kb_real["total"] - (kb_real["Cabotage"] + kb_real["Import"] + kb_real["Export"])) < 0.1)
    piv_real = volume_by_category_type(prep, 2025, [], OP_ORDER, "marchandise_norm")
    check("real pivot runs", not piv_real.empty)
    fig_real = fig_evolution(prep, 2025, "Année complète", 1, OP_ORDER, [])
    check("real fig_evolution runs", fig_real is not None)
    check("real fig_grouped_type runs",
          fig_grouped_type(piv_real, "marchandise_norm", "2025") is not None)
except Exception as e:
    print(f"  WARN  real data skipped: {e}")

print()
total = len(ok) + len(fail)
print(f"RESULTAT : {len(ok)}/{total} passes")
if fail:
    print("ECHECS :", *fail, sep="\n  - ")
    sys.exit(1)
else:
    print("ALL PASS")

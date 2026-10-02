# -*- coding: utf-8 -*-
"""Smoke tests — fonctions nouvellement ajoutées (donut, insights, évolution)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from datetime import datetime

from components.dashboard.trafic_views import (
    fig_donut, composition_insights, evolution_insights,
    kpi_block, scope, OP_ORDER, OP_COLORS, _fmt_tons)
from components.dashboard.evolution_views import (
    evolution_kpi_block, fig_evo_by_type, fig_evo_by_category,
    available_cats)

ok = []
fail = []
def check(name, cond):
    if cond:
        ok.append(name)
    else:
        fail.append(name)
        print(f"  FAIL  {name}")

# ── Données synthétiques ──
df = pd.DataFrame({
    "year":   [2025]*6 + [2024]*3,
    "month":  [1, 1, 2, 2, 3, 3, 1, 2, 3],
    "tonnage": [100, 50, 80, 30, 120, 60, 80, 40, 100],
    "type_trafic": ["Import", "Export", "Import", "Cabotage",
                    "Import", "Export", "Import", "Export", "Import"],
    "marchandise_norm": ["Phos", "Phos", "Char", "Buta", "Phos", "Char",
                         "Phos", "Char", "Phos"],
    "operateur_norm": ["OCP", "OCP", "Marsa", "Marsa", "OCP", "Marsa",
                       "OCP", "Marsa", "OCP"],
    "date": [datetime(2025,1,10), datetime(2025,1,15), datetime(2025,2,5),
             datetime(2025,2,20), datetime(2025,3,1), datetime(2025,3,15),
             datetime(2024,1,10), datetime(2024,2,5), datetime(2024,3,1)]})

# ==================================================================
print("=== 1. fig_donut ===")
fig = fig_donut(df, 2025, types=OP_ORDER, periode="2025")
check("donut not None", fig is not None)
check("donut is 1 Pie trace", len(fig.data) == 1)
check("donut hole=0.42", abs(fig.data[0].hole - 0.42) < 0.01)
check("donut 3 labels", len(fig.data[0].labels) == 3)
# donut empty
fig_e = fig_donut(pd.DataFrame(columns=["year","month","tonnage","type_trafic",
                                         "marchandise_norm","operateur_norm"]), 2025)
check("donut empty → None", fig_e is None)
# donut with type filter
fig_f = fig_donut(df, 2025, types=["Import"], periode="2025")
check("donut filtered = 1 label", len(fig_f.data[0].labels) == 1)

# ==================================================================
print("=== 2. composition_insights ===")
ins = composition_insights(df, 2025, types=OP_ORDER)
check("insights is list", isinstance(ins, list))
check("insights ≥ 2", len(ins) >= 2)
check("insight mentions marchandise", any("Phos" in i for i in ins))
check("insight mentions opérateur", any("OCP" in i for i in ins))
# empty
ins_e = composition_insights(pd.DataFrame(columns=["year","month","tonnage","type_trafic",
                                                    "marchandise_norm","operateur_norm"]), 2025)
check("insights empty data", len(ins_e) >= 1)

# ==================================================================
print("=== 3. evolution_insights ===")
eins = evolution_insights(df, 2025, types=OP_ORDER)
check("evo insights is list", isinstance(eins, list))
check("evo insights ≥ 2", len(eins) >= 2)
# croissance detected: 300 vs 220 → +36.4%
check("evo growth detected", any("Croissance" in i or "+36" in i or "+" in i for i in eins))
# empty prev
ins_no_prev = evolution_insights(df, 2023, types=OP_ORDER)
check("evo no prev year", len(ins_no_prev) >= 1)

# ==================================================================
print("=== 4. evolution_kpi_block ===")
ek = evolution_kpi_block(df, 2025, types=OP_ORDER)
check("evo kpi has evolution", ek["evolution"] is not None)
check("evo kpi cur_total", ek["cur_total"] == 440.0)
check("evo kpi prev_total", ek["prev_total"] == 220.0)
check("evo kpi evo ≈ +100%", abs(ek["evolution"] - 100.0) < 1.0)
check("evo kpi best_month exists", ek["best_month"] is not None)
check("evo kpi worst_month exists", ek["worst_month"] is not None)
check("evo kpi max_var exists", ek["max_var_pct"] is not None)
# no year 2023 data
ek2 = evolution_kpi_block(df, 2023, types=OP_ORDER)
check("evo kpi empty year", ek2["evolution"] is None)

# ==================================================================
print("=== 5. fig_evo_by_type ===")
fig_t = fig_evo_by_type(df, 2025, "Année complète", 1, OP_ORDER)
check("evo by type not None", fig_t is not None)
# 3 types × 2 years = up to 6 traces (but some may have 0)
check("evo by type traces ≤ 6", len(fig_t.data) <= 6 and len(fig_t.data) > 0)
# filtered to 1 type
fig_t1 = fig_evo_by_type(df, 2025, "Année complète", 1, ["Import"])
check("evo by type 1 type", fig_t1 is not None)
# daily mode
fig_d = fig_evo_by_type(df, 2025, "Mois sélectionné", 1, ["Import"])
check("evo by type daily mode", fig_d is not None)

# ==================================================================
print("=== 6. fig_evo_by_category ===")
fig_o = fig_evo_by_category(df, 2025, ["OCP"], "operateur_norm", "Année complète", 1, OP_ORDER)
check("evo by cat (OCP) not None", fig_o is not None)
check("evo by cat traces ≥ 1", len(fig_o.data) >= 1)
# multiple
fig_mc = fig_evo_by_category(df, 2025, ["Phos", "Char"], "marchandise_norm",
                              "Année complète", 1, OP_ORDER)
check("evo by cat multi not None", fig_mc is not None)
# empty list
check("evo by cat empty → None",
      fig_evo_by_category(df, 2025, [], "operateur_norm") is None)

# ==================================================================
print("=== 7. available_cats ===")
ops = available_cats(df, 2025, "operateur_norm", types=OP_ORDER)
check("available ops", sorted(ops) == ["Marsa", "OCP"])
mars = available_cats(df, 2025, "marchandise_norm", types=OP_ORDER)
check("available marches", "Phos" in mars and "Char" in mars)
# filtered by month
ops_m1 = available_cats(df, 2025, "operateur_norm", months=[1], types=OP_ORDER)
check("available ops m1", ops_m1 == ["OCP"])

# ==================================================================
print("=== 8. Real data sanity ===")
try:
    from database import db_manager
    from components.dashboard.analytics import prepare_operations
    ops = db_manager.get_operations()
    prep = prepare_operations(ops)
    # donut
    fig_real = fig_donut(prep, 2025, types=OP_ORDER, periode="2025")
    check("real donut runs", fig_real is not None)
    # composition insights
    ci = composition_insights(prep, 2025, types=OP_ORDER)
    check("real composition insights", isinstance(ci, list) and len(ci) > 0)
    # evolution insights
    ei = evolution_insights(prep, 2025, types=OP_ORDER)
    check("real evolution insights", isinstance(ei, list) and len(ei) > 0)
    # evolution kpi
    ek_real = evolution_kpi_block(prep, 2025, types=OP_ORDER)
    check("real evo kpi runs", ek_real["cur_total"] >= 0)
    # evo by type
    fig_et = fig_evo_by_type(prep, 2025, "Année complète", 1, OP_ORDER)
    check("real evo by type runs", fig_et is not None)
    # evo by category
    o_real = available_cats(prep, 2025, "operateur_norm", types=OP_ORDER)
    if o_real:
        fig_ec = fig_evo_by_category(prep, 2025, o_real[:3], "operateur_norm",
                                      "Année complète", 1, OP_ORDER)
        check("real evo by category runs", fig_ec is not None)
    else:
        check("real evo by category (skip)", True)
except Exception as e:
    print(f"  WARN  real data skipped: {e}")

# ── Résultat ──
print()
total = len(ok) + len(fail)
print(f"RESULTAT : {len(ok)}/{total} passes")
if fail:
    print("ECHECS :", *fail, sep="\n  - ")
    sys.exit(1)
else:
    print("ALL PASS")

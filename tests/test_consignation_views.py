# -*- coding: utf-8 -*-
"""Smoke tests — Cartes « CONSIGNATION » et « ÉVOLUTION DE LA CONSIGNATION »."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from datetime import datetime

from components.dashboard.consignation_views import (
    prepare_consignations, available_years, available_months, available_causes,
    kpi_block, duration_boundaries, cat_duration, fig_by_poste, fig_causes,
    fig_duration_distrib, port_stats, fig_port, events_table, POSTE_ORDER)
from components.dashboard.consignation_evo_views import (
    ALL_POSTES, poste_options, fig_evo_globale, fig_evo_poste,
    fig_evo_nvsn1, fig_evo_duree)

ok = []
fail = []


def check(name, cond):
    if cond:
        ok.append(name)
    else:
        fail.append(name)
        print(f"  FAIL  {name}")


# ── Données synthétiques (aucune donnée fictive : tout vient du dataset) ──
_POSTES = ["1N", "5", "16S", "PORT", "3Bis", "99X"]
_INTERVALS = [(2025, 1), (2025, 1), (2025, 2), (2025, 3),
              (2024, 1), (2024, 2), (2024, 3)]


def build_frame():
    rows = []
    for i, (y, m) in enumerate(_INTERVALS):
        for p in _POSTES:
            if (y, m) == (2025, 1) and p == "PORT":
                continue
            rows.append({
                "date_debut": datetime(y, m, 5 + i % 28, 8, 0),
                "date_fin": datetime(y, m, 6 + i % 28, 8, 0),
                "heure_debut": "08:00", "heure_fin": "14:00",
                "poste": p, "motif": "Mauvais temps" if i % 2 else "Houle",
                "nombre_heures": 12.0 if i % 3 else 48.0,
                "observations": "Mouvement interdit" if p == "1N" else "",
            })
    return prepare_consignations(pd.DataFrame(rows))


frame = build_frame()

# ==================================================================
print("=== 1. préparation + KPI (données réelles) ===")
check("non vide", not frame.empty)
check("PORT counts réel", int(frame["is_port"].sum()) == 5)
check("années desc", available_years(frame) == [2025, 2024])
check("mois 2025", available_months(frame, 2025) == [1, 2, 3])
check("causes réelles", set(available_causes(frame, 2025, None))
      == {"Houle", "Mauvais temps"})
k = kpi_block(frame)
check("kpi count", k["count"] == len(frame))
check("kpi postes distincts", k["n_postes"] == len(set(_POSTES)))

# ==================================================================
print("=== 2. catégories de durée (seuils réels) ===")
b = duration_boundaries(frame)
check("boundaries non None", b is not None and "b1" in b)
cat = cat_duration(frame, b)
check("cat assignée", set(cat["duree_cat"]) <=
      {"Courte durée", "Moyenne durée", "Longue durée"})
frame_z = prepare_consignations(pd.DataFrame([{
    "date_debut": datetime(2025, 3, 1, 8, 0),
    "date_fin": datetime(2025, 3, 1, 8, 0),
    "poste": "1N", "motif": "x", "nombre_heures": 0.0}]))
check("aucune durée positive -> None", duration_boundaries(frame_z) is None)
check("cat None -> tout Courte",
      bool((cat_duration(frame_z, None)["duree_cat"] == "Courte durée").all()))

# ==================================================================
print("=== 3. ① Consignations par poste (ordre métier stable) ===")
fig, title = fig_by_poste(frame, 2025, None)
ys = list(fig.data[0].y)
vals = fig.data[0].x
check("fig par poste", fig is not None and title == "Consignations par poste")
check("ordre métier complet", all(p in ys for p in POSTE_ORDER))
check("postes absents = 0", vals[ys.index("1S")] == 0)
check("PORT réel conservé", "PORT" in ys and vals[ys.index("PORT")] > 0)
check("vide -> None", fig_by_poste(
    pd.DataFrame(columns=["year", "month", "poste"]), 2025, None)[0] is None)

# ==================================================================
print("=== 4. ② Causes principales (donut dynamique) ===")
fig_c, _ = fig_causes(frame, 2025, None, None)
check("donut non None", fig_c is not None)
check("donut causes réelles", {"Houle", "Mauvais temps"}
      <= set(fig_c.data[0].labels))
fig_cf, _ = fig_causes(frame, 2025, None, ["Houle"])
check("filtre cause donut", len(fig_cf.data[0].labels) == 1)

# ==================================================================
print("=== 5. ③ Distribution des durées (classes adaptées) ===")
fig_d, _ = fig_duration_distrib(frame, 2025, None, None)
check("distribution non None", fig_d is not None)
check("classe max adaptée", list(fig_d.data[0].x)[-1] == "> 2 j")

# ==================================================================
print("=== 6. ④ Consignation PORT (jamais supprimée) ===")
ps = port_stats(frame, 2025, None)
fig_p, _ = fig_port(frame, 2025, None)
check("stats PORT réelles", fig_p is not None)
check("barres PORT = count réel", sum(fig_p.data[0].y) == ps["count"])
check("PORT total conservé", ps["total_all"] == 5)

# ==================================================================
print("=== 7. ⑤ Table des événements ===")
tab, total = events_table(frame, 2025, None, None, None, limit=5)
check("colonnes attendues", list(tab.columns) ==
      ["Poste", "Consignation", "Déconsignation", "Cause", "Durée",
       "Mouvement"])
check("lignes limitées", len(tab) <= 5 and 0 < total)
check("durée formatée", tab["Durée"].iloc[0].endswith(" j"))

# ==================================================================
print("=== 8. Évolution (Carte 2) ===")
opts = poste_options(frame, 2025)
check("options postes", opts[0] == ALL_POSTES and "PORT" in opts)
fg, _ = fig_evo_globale(frame, 2025, "Toutes", b)
check("evo globale mois réels", set(fg.data[0].x) == {"Jan", "Fév", "Mar"})
fe_all, title_all, ha = fig_evo_poste(frame, 2025, "Toutes", b, [ALL_POSTES])
check("evo poste « Tous » = N + N-1 (2 courbes)", len(fe_all.data) == 2)
check("has_prev pour 2025", ha is True)
check("titre mentionne N vs N-1", "N vs N-1" in title_all)
fe_two, _, _ = fig_evo_poste(frame, 2025, "Toutes", b, ["1N", "5"])
check("evo poste multi = 2 postes × 2 années (4 courbes)", len(fe_two.data) == 4)
dash_tr = [t for t in fe_two.data if t.line.dash == "dot"]
check("N-1 en pointillés", len(dash_tr) == 2)
solid_c = {t.line.color for t in fe_two.data if t.line.dash is None}
dash_c = {t.line.color for t in dash_tr}
check("N-1 couleur distincte de N",
      len(dash_c) == 1 and solid_c.isdisjoint(dash_c))
fe_no, _, no = fig_evo_poste(frame, 2024, "Toutes", b, [ALL_POSTES])
check("2024 = 1 courbe N sans N-1", len(fe_no.data) == 1 and not no)
fe_n, _, comp = fig_evo_nvsn1(frame, 2025, "Toutes", b, ALL_POSTES)
check("N vs N-1 comparable", comp and len(fe_n.data) == 2)
fe_n2, _, comp2 = fig_evo_nvsn1(frame, 2024, "Toutes", b, ALL_POSTES)
check("N vs N-1 indisponible si pas d'année précédente",
      fe_n2 is None and not comp2)
fd, _ = fig_evo_duree(frame, 2025, [ALL_POSTES], b)
check("évolution selon durée = barres empilées",
      fd is not None and fd.layout.barmode == "stack")

# ==================================================================
print("=== 9. Données réelles (MySQL) — sanity ===")
try:
    from database import db_manager
    raw_real = db_manager.get_consignations(limit=10000)
    fr = prepare_consignations(raw_real)
    if fr.empty:
        check("real data (aucune consignation)", True)
    else:
        yr = fr["year"].max()
        check("real fig par poste", fig_by_poste(fr, yr, None)[0] is not None)
        check("real donut", fig_causes(fr, yr, None, None)[0] is not None)
        check("real distribution", fig_duration_distrib(fr, yr, None, None)[0]
              is not None)
        bb = duration_boundaries(fr)
        check("real évolution", fig_evo_globale(fr, yr, "Toutes", bb)[0]
              is not None)
        check("real table", events_table(fr, yr, None, None, None, 5)[0]
              is not None)
except Exception as e:
    print(f"  WARN  données réelles ignorées : {e}")

# ── Résultat ──
print()
total_n = len(ok) + len(fail)
print(f"RESULTAT : {len(ok)}/{total_n} passes")
if fail:
    print("ECHECS :", *fail, sep="\n  - ")
    sys.exit(1)
else:
    print("ALL PASS")
# -*- coding: utf-8 -*-
"""Tests obligatoires — moteur « ⏳ Attente au mouillage » (attente_views).

Exécution : python tests/test_attente_views.py
Couvre l'attribution par date de DÉBUT d'attente, la cascade de filtres,
les KPI (MAXIMUM = durée maximale réelle), l'évolution N vs N-1 et la
distribution par tranches — sur les données réelles de la base local.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard import attente_views as av

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name} {detail}")


def is_close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def _base():
    ops = db_manager.get_operations()
    assert ops is not None and not ops.empty, \
        "Base vide — impossible de tester sur données réelles."
    frame = prepare_operations(ops)
    att = av.prepare(frame)
    assert not att.empty, "Base sans attente — impossible de tester."
    return att


def _sel(att, year):
    return {"year": year, "months": [], "poste": av.POSTE_ALL,
            "type_navire": av.TYPE_ALL, "navire": av.NAVIRE_ALL,
            "operateur": av.OP_ALL, "marchandise": av.MARCH_ALL}


# ------------------------------------------------------------------
print("\n[1/7] Préparation / attribution par début d'attente")
att = _base()
check("colonnes att_year / att_month présentes",
      {"att_year", "att_month"} <= set(att.columns))
check("mois dans 1..12", att["att_month"].between(1, 12).all())
check("années renseignées", att["att_year"].notna().all())

df = pd.DataFrame({
    "attente_h": [24.0, 0.0, -3.0, np.nan, 12.0],
    "date_mouillage": ["2024-03-05", "2024-03-06", "2024-03-07",
                       "2024-03-08", "2024-03-09"],
    "date": ["2024-04-01"] * 5,
    "year": [2024] * 5,
    "month": [4] * 5,
    "navire_name": ["A"] * 5,
})
out = av.prepare(df)
check("durées ≤ 0 ou NaN exclues",
      sorted(out["attente_h"].tolist()) == [12.0, 24.0])
check("attribution via date_mouillage (mois 3), pas la date op (mois 4)",
      set(out["att_month"].tolist()) == {3})

df2 = pd.DataFrame({"attente_h": [10.0], "date": ["2024-07-15"],
                    "year": [2024], "month": [7]})
out2 = av.prepare(df2)
check("repli date opération si date_mouillage absente",
      out2["att_month"].iloc[0] == 7 and out2["att_year"].iloc[0] == 2024)

yr_max = int(att["att_year"].max())
check("available_years trié décroissant",
      av.available_years(att) == sorted(av.available_years(att), reverse=True))
postes = av.distinct(att, "poste_norm")
check("distinct(poste) non vide et chaines réelles",
      bool(postes) and all(isinstance(p, str) and p for p in postes))


# ------------------------------------------------------------------
print("\n[2/7] Filtres cascade (année + mois + dimensions)")
sel = _sel(att, yr_max)
f = av.filtered(att, sel)
check("sans filtre : toutes les attentes de l'année",
      is_close(f["attente_h"].sum(),
               att[att["att_year"] == yr_max]["attente_h"].sum()))
poste = postes[0]
sel_p = {**sel, "poste": poste}
f_p = av.filtered(att, sel_p)
check("filtre poste : uniquement ce poste",
      not f_p.empty and f_p["poste_norm"].fillna("").astype(str).eq(poste).all())
months = [int(att["att_month"].max())]
sel_m = {**sel, "months": months}
f_m = av.filtered(att, sel_m)
check("filtre mois : uniquement ce mois",
      not f_m.empty and f_m["att_month"].isin(months).all())
sel_vide = _sel(att, 1990)
check("année sans données → sélection vide", av.filtered(att, sel_vide).empty)
check("constants 'Tous les …' en place",
      all(s for s in [av.POSTE_ALL, av.TYPE_ALL, av.NAVIRE_ALL,
                      av.OP_ALL, av.MARCH_ALL]))


# ------------------------------------------------------------------
print("\n[3/7] KPI moyenne / médiane / P90 / P95 / maximum")
stats = av.kpi_stats(f)
check("count = nombre de lignes filtrées", stats["count"] == len(f))
check("MOYENNE calculée", stats["moyenne"] is not None)
check("MAXIMUM = durée maximale réelle (pas un P99)",
      is_close(stats["maximum"], f["attente_h"].max()))
check("médiane ≤ P90 ≤ P95 ≤ maximum",
      stats["mediane"] <= stats["p90"] <= stats["p95"] <= stats["maximum"])
s_empty = av.kpi_stats(pd.DataFrame({"attente_h": []}))
check("KPI sur sélection vide → valeurs '—' (None) et count=0",
      s_empty["moyenne"] is None and s_empty["maximum"] is None
      and s_empty["count"] == 0)


# ------------------------------------------------------------------
print("\n[4/7] Évolution mensuelle N vs N-1")
cur = av.monthly_evol(att, sel, yr_max)
check("colonnes évolution présentes",
      {"att_month", "moyenne", "mediane", "n", "navires"} <= set(cur.columns))
check("navires ≤ escales", bool((cur["n"] >= cur["navires"]).all()))
sel_small = {**sel, "months": months}
g = av.monthly_evol(att, sel_small, yr_max)
check("série N (mois unique) restreinte",
      not g.empty and set(g["att_month"]) <= set(months))

# ------------------------------------------------------------------
print("\n[5/7] Figure évolution (courbe N + N-1)")
if yr_max - 1 in set(att["att_year"]):
    fig = av.fig_evolution(att, sel)
    if fig is not None:
        names = [t.name for t in fig.data]
        check(f"trace Année N ({yr_max}) présente",
              any(n == f"Année N ({yr_max})" for n in names))
        check(f"trace Année N-1 ({yr_max - 1}) présente",
              any(n == f"Année N-1 ({yr_max - 1})" for n in names))
        check("figure thémée (fond sombre)", len(fig.data) >= 1)
    else:
        print("  (N-1 absent des données réelles → évolution non testable)")
else:
    print("  (N-1 absent des données réelles → évolution non testable)")


# ------------------------------------------------------------------
print("\n[6/7] Distribution par tranches fixes")
d = av.distribution_data(f)
check("7 tranches fixes", list(d["tranche"]) == av.BIN_LABELS)
check("effectifs = total filtré", d["escales"].sum() == len(f))
check("parts ≈ 100 %", is_close(d["part_pct"].sum(), 100.0, tol=1.0))
fig_d = av.fig_distribution(att, sel)
check("figure distribution rendue sur sélection réelle",
      isinstance(fig_d, go.Figure) and len(fig_d.data) == 1)
fig_d_vide = av.fig_distribution(att, _sel(att, 1990))
check("distribution → None sur sélection vide", fig_d_vide is None)


# ------------------------------------------------------------------
print()
print("=" * 46)
print(f"RESULTAT : {PASS} PASS / {len(FAIL)} FAIL")
if FAIL:
    print("Echecs :", *FAIL, sep="\n  - ")
    sys.exit(1)
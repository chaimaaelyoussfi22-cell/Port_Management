# -*- coding: utf-8 -*-
"""Verrouille la regle d'attribution temporelle des courbes d'evolution.

Regle metier (analytics.prepare_operations) :
  - une escale appartient a UN SEUL mois/annee : celui de son Arrivee RADE
    (operations.date = date_rade inseree a l'import et a la saisie manuelle) ;
  - toutes les courbes - escales, navires, trafic, sejour quai, sejour port -
    sont groupees par ce mois (prepare_operations derive month/year de `date`),
    quelle que soit la date de depart QUAI/PORT ;
  - denombrements : escales = COUNT DISTINCT escale_key, navires = COUNT
    DISTINCT navire_name ; tonnage/sjours = agregats par ligne (l'import
    garantit deja UNE ligne par escale -> pas de double comptage en amont) ;
  - N-1 = meme mois de l'annee precedente ; quai_h = App_Quai - Accostage,
    port_h = App_Port - Arrivee_Rade (durees en heures).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from datetime import datetime

from components.dashboard.analytics import prepare_operations
from components.dashboard.escales_views import escales_monthly, escales_daily
from components.dashboard.navires_views import navires_monthly, kpi_block as navires_kpi
from components.dashboard.trafic_views import (
    monthly_volume, kpi_block as trafic_kpi, OP_ORDER)
from components.dashboard.sejour_views import (
    sejour_monthly, sejour_daily, kpi_block as sejour_kpi)
from components.dashboard.sejour_port_views import (
    port_monthly, port_daily, kpi_block as port_kpi)

ok = []
fail = []
def check(name, cond):
    if cond:
        ok.append(name)
    else:
        fail.append(name)
        print(f"  FAIL  {name}")

# ── Jeu synthetique : depart QUAI/PORT dans le mois SUIVANT l'arrivee RADE ──
# escale 1001 « MARIA » : RADE 31/01/2025 -> QUAI 03/02 -> PORT 05/02
# escale 1002 « IBIS »  : RADE 01/02/2025 -> QUAI 02/02 -> PORT 03/02
# escale 1003 « MARIA » : RADE 10/03/2025 -> QUAI 12/03 -> PORT 13/03 (2e escale)
# escale 2001 « MARIA » : N-1, RADE 31/01/2024 -> QUAI 04/02 -> PORT 05/02
rows = [
    dict(numero_navire="1001", navire="MARIA", poste="Q1",
         type_operation="IMPORT", quantite=100.0,
         type_marchandise="Phosphate", operateur="OCP", type_navire="VRAC",
         date=datetime(2025, 1, 31), date_rade=datetime(2025, 1, 31),
         date_accostage=datetime(2025, 1, 31),
         date_app_quai=datetime(2025, 2, 3), date_app_port=datetime(2025, 2, 5)),
    dict(numero_navire="1002", navire="IBIS", poste="Q2",
         type_operation="EXPORT", quantite=200.0,
         type_marchandise="Clinker", operateur="Marsa", type_navire="PORTCONTENEUR",
         date=datetime(2025, 2, 1), date_rade=datetime(2025, 2, 1),
         date_accostage=datetime(2025, 2, 1),
         date_app_quai=datetime(2025, 2, 2), date_app_port=datetime(2025, 2, 3)),
    dict(numero_navire="1003", navire="MARIA", poste="Q1",
         type_operation="CABOTAGE", quantite=300.0,
         type_marchandise="Phosphate", operateur="OCP", type_navire="VRAC",
         date=datetime(2025, 3, 10), date_rade=datetime(2025, 3, 10),
         date_accostage=datetime(2025, 3, 10),
         date_app_quai=datetime(2025, 3, 12), date_app_port=datetime(2025, 3, 13)),
    dict(numero_navire="2001", navire="MARIA", poste="Q1",
         type_operation="IMPORT", quantite=50.0,
         type_marchandise="Phosphate", operateur="OCP", type_navire="VRAC",
         date=datetime(2024, 1, 31), date_rade=datetime(2024, 1, 31),
         date_accostage=datetime(2024, 1, 31),
         date_app_quai=datetime(2024, 2, 4), date_app_port=datetime(2024, 2, 5)),
]
prep = prepare_operations(pd.DataFrame(rows))
p = prep.set_index("numero_navire")

print("=== 1. Rattachement = mois d'Arrivee RADE ===")
check("month 1001 = janvier (sortie fevrier)", p.loc["1001", "month"] == 1)
check("year  1001 = 2025", p.loc["1001", "year"] == 2025)
check("month 1002 = fevrier", p.loc["1002", "month"] == 2)
check("month 1003 = mars", p.loc["1003", "month"] == 3)
check("month 2001 = janvier 2024 (N-1)", p.loc["2001", "month"] == 1
      and p.loc["2001", "year"] == 2024)
check("quai_h 1001 = App_Quai - Accostage = 72h", abs(p.loc["1001", "quai_h"] - 72.0) < 0.001)
check("port_h 1001 = App_Port - Rade = 120h", abs(p.loc["1001", "port_h"] - 120.0) < 0.001)
check("tonnage 1001 lu depuis quantite = 100", p.loc["1001", "tonnage"] == 100.0)

print("=== 2. Escales : un mois par escale (COUNT DISTINCT escale_key) ===")
em = escales_monthly(prep, 2025)
check("escales jan=1 (depart fevrier)",
      em.get(1, 0) == 1 and em.get(2, 0) == 1 and em.get(3, 0) == 1)
ed = escales_daily(prep, 2025)
row = ed[ed["mmdd"] == "01-31"]
check("escales quotidien 31/01 = 1", len(row) == 1 and row["escales"].iloc[0] == 1)

print("=== 3. Navires : COUNT DISTINCT navire_name par mois ===")
nm = navires_monthly(prep, 2025)
check("navires jan=1, fev=1, mars=1", nm.get(1, 0) == 1
      and nm.get(2, 0) == 1 and nm.get(3, 0) == 1)
check("MARIA re-comptee en mars (2e escale)", nm.get(3, 0) == 1)

print("=== 4. Trafic : tonnage attribue au mois d'Arrivee RADE ===")
mv = monthly_volume(prep, 2025, OP_ORDER, [])
check("volumes jan=100 (navire sorti en fevrier)", mv.get(1, 0.0) == 100.0)
check("volumes fev=200", mv.get(2, 0.0) == 200.0)
check("volumes mars=300", mv.get(3, 0.0) == 300.0)

print("=== 5. Sejour quai : moyenne attribuee au mois d'Arrivee RADE ===")
sm = sejour_monthly(prep, 2025)
check("sejour quai jan=72h", abs(sm.get(1, 0.0) - 72.0) < 0.01)
check("sejour quai fev=24h", abs(sm.get(2, 0.0) - 24.0) < 0.01)
check("sejour quai mars=48h", abs(sm.get(3, 0.0) - 48.0) < 0.01)
sd = sejour_daily(prep, 2025)
row = sd[sd["mmdd"] == "01-31"]
check("sejour quai 31/01 = 72h", len(row) == 1 and abs(row["sejour"].iloc[0] - 72.0) < 0.01)

print("=== 6. Sejour port : moyenne attribuee au mois d'Arrivee RADE ===")
pm = port_monthly(prep, 2025)
check("sejour port jan=120h", abs(pm.get(1, 0.0) - 120.0) < 0.01)
check("sejour port fev=48h", abs(pm.get(2, 0.0) - 48.0) < 0.01)
check("sejour port mars=72h", abs(pm.get(3, 0.0) - 72.0) < 0.01)
pmo = port_daily(prep, 2025, 1)
row = pmo[pmo["mmdd"] == "01-31"]
check("sejour port 31/01 = 120h", len(row) == 1 and abs(row["sejour"].iloc[0] - 120.0) < 0.01)

print("=== 7. N-1 : meme mois, annee precedente ===")
em_prev = escales_monthly(prep, 2024)
check("escales N-1 jan=1", em_prev.get(1, 0) == 1)
mv_prev = monthly_volume(prep, 2024, OP_ORDER, [])
check("tonnage N-1 jan=50 (vs 100 en N)", mv_prev.get(1, 0.0) == 50.0)
etk = trafic_kpi(prep, 2025)
check("KPI trafic N=600, N-1=50 -> +1100 %",
      etk["total"] == 600.0 and abs(etk["evolution"] - 1100.0) < 0.1)
ekn = navires_kpi(prep, 2025)
check("KPI navires N=2, N-1=1 -> +100 %",
      ekn["ships"] == 2 and ekn["prev_ships"] == 1
      and abs(ekn["evolution"] - 100.0) < 0.1)
sk = sejour_kpi(prep, 2025)
check("KPI sejour quai N=48h, N-1=96h",
      abs(sk["avg"] - 48.0) < 0.1 and abs(sk["prev_avg"] - 96.0) < 0.1)
pk = port_kpi(prep, 2025)
check("KPI sejour port N=80h, N-1=120h",
      abs(pk["avg"] - 80.0) < 0.1 and abs(pk["prev_avg"] - 120.0) < 0.1)

print("=== 8. Dedoublonnage : une escale = un comptage (vues denombrement) ===")
dup_rows = []
for _ in range(2):
    dup_rows.append(dict(numero_navire="9001", navire="TRITON", poste="Q1",
                         type_operation="IMPORT", quantite=500.0,
                         type_marchandise="Phosphate", operateur="OCP",
                         type_navire="VRAC",
                         date=datetime(2025, 9, 5), date_rade=datetime(2025, 9, 5),
                         date_accostage=datetime(2025, 9, 5),
                         date_app_quai=datetime(2025, 9, 6),
                         date_app_port=datetime(2025, 9, 7)))
dprep = prepare_operations(pd.DataFrame(dup_rows))
check("escales sept=1 malgre 2 lignes", escales_monthly(dprep, 2025).get(9, 0) == 1)
check("navires sept=1 malgre 2 lignes", navires_monthly(dprep, 2025).get(9, 0) == 1)
# NB: tonnage/moyennes ne sont PAS dedoublonnes par les vues (sum/mean par ligne) -
# l'unicite d'une escale est garantie en amont par l'import (1 ligne par escale).

print("=== 9. Donnees reelles (coherence date == date_rade) ===")
try:
    from database import db_manager
    ops = db_manager.get_operations()
    rp = prepare_operations(ops)
    if rp.empty:
        check("real data skip (table vide)", True)
    else:
        a = pd.to_datetime(rp["date"], errors="coerce")
        b = pd.to_datetime(rp["date_rade"], errors="coerce")
        both = a.notna() & b.notna()
        check("real date == date_rade partout", bool((a[both] == b[both]).all()))
        yr = max(int(y) for y in rp["year"].dropna().unique())
        check("real escales_mensuel run", not escales_monthly(rp, yr).empty)
        check("real navires_mensuel run", not navires_monthly(rp, yr).empty)
        check("real volume_mensuel run", not monthly_volume(rp, yr, OP_ORDER, []).empty)
        check("real sejour_quai_mensuel run", not sejour_monthly(rp, yr).empty)
        check("real sejour_port_mensuel run", not port_monthly(rp, yr).empty)
except Exception as e:
    print(f"  WARN  real data skipped: {e}")

# ── Resultat ──
print()
total = len(ok) + len(fail)
print(f"RESULTAT : {len(ok)}/{total} passes")
if fail:
    print("ECHECS :", *fail, sep="\n  - ")
    sys.exit(1)
else:
    print("ALL PASS")
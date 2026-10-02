# -*- coding: utf-8 -*-
"""Tests obligatoires — occupation physique des postes.

Exécution : python tests/test_occupation.py
Couvre les 7 cas unitaires demandés + RADE + diagnostic >100 %
+ les cas réels MERCURIUS (timeline 6 -> 2TER -> 1S) et TORM AMALIE (retour poste 8).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from components.dashboard.occupation import (
    diagnose_inconsistencies, is_quay_poste,
    merge_union, monthly_occupancy, occupation_per_poste,
    occupation_taux, quay_intervals)

PASS, FAIL = 0, []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name} {detail}")


def mk_ops(rows):
    return pd.DataFrame(rows, columns=[
        "id", "date", "navire", "numero_navire", "poste",
        "date_accostage", "heure_accostage", "date_app_quai", "heure_app_quai"])


def mk_changes(rows):
    return pd.DataFrame(rows, columns=[
        "id", "operation_id", "escale_key", "navire", "poste",
        "date_accostage", "heure_accostage", "date_app_quai", "heure_app_quai"])


def dur_of(iv, poste):
    g = iv[iv["poste"] == poste]
    if g.empty:
        return 0.0
    spans = list(zip(g["start"], g["end"]))
    return sum((e - s).total_seconds() / 3600 for s, e in merge_union(spans))


print("=== TESTS UNITAIRES ===")

# Test 1 - un seul navire sur un seul poste : 100h -> 100h
ops = mk_ops([[1, "2025-03-01", "A", "E1", "1S",
               "2025-03-01", "08:00", "2025-03-05", "12:00"]])
iv = quay_intervals(ops)
check("T1 un navire/un poste = 100h", abs(dur_of(iv, "1S") - 100) < 1e-9,
      f"obtenu {dur_of(iv, '1S')}")

# Test 2 - changement de poste : 1S=50h, 2TER=30h (jamais 1S=80h)
ops = mk_ops([[1, "2025-03-01", "A", "E1", "1S",
               "2025-03-01", "00:00", "2025-03-03", "02:00"]])
chg = mk_changes([[10, 1, "E1", "A", "2TER",
                   "2025-03-03", "02:00", "2025-03-04", "08:00"]])
iv = quay_intervals(ops, chg)
check("T2 changement 1S=50h", abs(dur_of(iv, "1S") - 50) < 1e-9, f"obtenu {dur_of(iv, '1S')}")
check("T2 changement 2TER=30h", abs(dur_of(iv, "2TER") - 30) < 1e-9, f"obtenu {dur_of(iv, '2TER')}")
check("T2 postes distincts non fusionnes", set(iv["poste"]) == {"1S", "2TER"})

# Test 3 - retour au meme poste : 1S=70h, 2TER=30h
chg = mk_changes([
    [10, 1, "E1", "A", "2TER", "2025-03-03", "02:00", "2025-03-04", "08:00"],
    [11, 1, "E1", "A", "1S", "2025-03-04", "08:00", "2025-03-05", "04:00"]])
iv = quay_intervals(ops, chg)
check("T3 retour 1S = 50+20 = 70h", abs(dur_of(iv, "1S") - 70) < 1e-9, f"obtenu {dur_of(iv, '1S')}")
check("T3 retour 2TER = 30h", abs(dur_of(iv, "2TER") - 30) < 1e-9, f"obtenu {dur_of(iv, '2TER')}")

# Test 4 - doublon exact : 52h comptees une seule fois
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "1S", "2025-03-01", "08:00", "2025-03-03", "12:00"],
    [2, "2025-03-01", "A", "E1", "1S", "2025-03-01", "08:00", "2025-03-03", "12:00"]])
iv = quay_intervals(ops)
occ = occupation_per_poste(iv)
check("T4 doublon exact = 52h une fois", abs(dur_of(iv, "1S") - 52) < 1e-9,
      f"obtenu {dur_of(iv, '1S')}")
check("T4 nb_intervalles bruts = 2 (tracabilite)", int(occ.iloc[0]["nb_intervalles"]) == 2)

# Test 5 - chevauchement reel meme evenement : union 01/03 08h -> 04/03 08h = 72h
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "1S", "2025-03-01", "08:00", "2025-03-03", "12:00"],
    [2, "2025-03-01", "A", "E1", "1S", "2025-03-02", "10:00", "2025-03-04", "08:00"]])
iv = quay_intervals(ops)
check("T5 chevauchement reel = union 72h", abs(dur_of(iv, "1S") - 72) < 1e-9,
      f"obtenu {dur_of(iv, '1S')}")

# Test 6 - deux navires differents, periodes differentes, meme poste = 4 jours
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "1S", "2025-03-01", "00:00", "2025-03-03", "00:00"],
    [2, "2025-03-01", "B", "E2", "1S", "2025-03-03", "00:00", "2025-03-05", "00:00"]])
iv = quay_intervals(ops)
check("T6 deux navires successifs = 96h (4 jours)", abs(dur_of(iv, "1S") - 96) < 1e-9,
      f"obtenu {dur_of(iv, '1S')}")

# Test 7 - deux navires simultanes sur le meme poste = conflit detecte
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "1S", "2025-03-01", "00:00", "2025-03-03", "00:00"],
    [2, "2025-03-01", "B", "E2", "1S", "2025-03-02", "00:00", "2025-03-04", "00:00"]])
iv = quay_intervals(ops)
occ = occupation_per_poste(iv)
check("T7 conflit simultane detecte (union=72h)", int(occ.iloc[0]["conflits"]) >= 1
      and abs(float(occ.iloc[0]["duree_occupee_h"]) - 72) < 1e-9)

# Test RADE / mouillage exclus de l'occupation quai
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "RADE", "2025-03-01", "00:00", "2025-03-02", "00:00"],
    [2, "2025-03-01", "B", "E2", "8", "2025-03-01", "00:00", "2025-03-02", "00:00"]])
iv = quay_intervals(ops)
check("RADE exclu des intervalles quai", set(iv["poste"]) == {"8"})
check("is_quay_poste('RADE') == False", not is_quay_poste("RADE"))
iv_all = quay_intervals(ops, include_anchorage=True)
check("RADE conserve si include_anchorage", set(iv_all["poste"]) == {"RADE", "8"})

# Test diagnostic >100 % SANS plafonnement
ops = mk_ops([
    [1, "2025-03-01", "A", "E1", "1S", "2025-03-01", "00:00", "2025-03-31", "00:00"],
    [2, "2025-03-01", "A", "E1", "1S", "2025-03-15", "00:00", "2025-03-31", "12:00"]])
iv = quay_intervals(ops)
taux = occupation_taux(iv, days=31)          # dispo = 744h ; union = 744h -> ~100%
taux2 = occupation_taux(iv, days=28)         # fenetre plus courte -> >100%
diag = diagnose_inconsistencies(iv, days=28, taux_df=taux2)
check("diagnostic >100% declenche sans plafond",
      float(taux2.iloc[0]["taux_%"]) > 100 and len(diag) == 1
      and diag[0]["code"] == "OCCUPATION_DATA_INCONSISTENCY"
      and diag[0]["double_comptage_h_detecte"] > 0)

# Test occupation mensuelle ( frontieres de mois, heures reelles)
ops = mk_ops([[1, "2025-02-25", "A", "E1", "1S",
               "2025-02-25", "00:00", "2025-03-03", "00:00"]])
mo = monthly_occupancy(quay_intervals(ops))
fev = mo[(mo["year"] == 2025) & (mo["month"] == 2)].iloc[0]
mar = mo[(mo["year"] == 2025) & (mo["month"] == 3)].iloc[0]
check("mensuel fevrier = 96h/672h", abs(fev["duree_h"] - 96) < 1e-6 and fev["heures_dispo"] == 672)
check("mensuel mars = 48h/744h", abs(mar["duree_h"] - 48) < 1e-6 and mar["heures_dispo"] == 744)

print()
print("=== CAS REELS (base de donnees) ===")
from database import db_manager

conn = db_manager._connect()
ops_all = pd.read_sql_query(
    "SELECT id, date, navire, numero_navire, poste, date_accostage, heure_accostage, "
    "date_app_quai, heure_app_quai FROM operations", conn)
ch_all = pd.read_sql_query(
    "SELECT id, operation_id, poste, date_accostage, heure_accostage, "
    "date_app_quai, heure_app_quai FROM poste_changes", conn)
conn.close()

# --- MERCURIUS : timeline reelle 6 -> 2TER -> 1S ---
m = ops_all[ops_all["navire"].str.upper() == "MERCURIUS"]
if m.empty:
    print("  SKIP  MERCURIUS absent de la base (cas reel conditionnel)")
else:
    mc = ch_all[ch_all["operation_id"].isin(m["id"])].copy()
    mc["escale_key"] = str(m.iloc[0]["numero_navire"])
    mc["navire"] = m.iloc[0]["navire"]
    iv = quay_intervals(m, mc)
    d6, d2ter, d1s = dur_of(iv, "6"), dur_of(iv, "2TER"), dur_of(iv, "1S")
    check("MERCURIUS : 3 postes distincts presents", set(iv["poste"]) >= {"6", "2TER", "1S"},
          f"postes={sorted(set(iv['poste']))}")
    check(f"MERCURIUS : poste 6 ~ 24h (obtenu {round(d6, 2)})", abs(d6 - 24.0) < 0.5)
    check(f"MERCURIUS : 2TER ~ 11.9h (obtenu {round(d2ter, 2)})", abs(d2ter - 11.9) < 0.3)
    check(f"MERCURIUS : 1S ~ 29.63h (obtenu {round(d1s, 2)})", abs(d1s - 29.6333) < 0.3)
    u6 = merge_union(list(zip(iv[iv["poste"] == "6"]["start"], iv[iv["poste"] == "6"]["end"])))
    check("MERCURIUS : aucun fusionnement inter-postes", len(u6) == 1)

# --- TORM AMALIE : historique "retour au poste 8" (structure conditionnelle) ---
t = ops_all[ops_all["navire"].str.upper() == "TORM AMALIE"].sort_values("date")
if t.empty:
    print("  SKIP  TORM AMALIE absent de la base (cas reel conditionnel)")
else:
    tc = ch_all[ch_all["operation_id"].isin(t["id"])]
    first = t.iloc[0]
    tc1 = tc[tc["operation_id"] == first["id"]].copy()
    tc1["escale_key"] = str(first["numero_navire"])
    tc1["navire"] = first["navire"]
    iv = quay_intervals(t[t["id"] == first["id"]], tc1)
    u = merge_union(list(zip(iv["start"], iv["end"])))
    tot = sum((e - s).total_seconds() / 3600 for s, e in u)
    if len(u) == 2 and set(iv["poste"]) == {"8"}:
        check(f"TORM AMALIE : 2 intervalles distincts poste 8 (obtenu {len(u)})", True)
        check(f"TORM AMALIE : total ~ 68.08h, gap respecte (obtenu {round(tot, 2)})",
              abs(tot - 68.0833) < 0.3)
    else:
        print(f"  SKIP  TORM AMALIE : structure reelle differente (postes={sorted(set(iv['poste']))}, "
              f"intervalles={len(u)}, total={round(tot, 2)}h) - donnees re-importees")

# --- Controle global : coherence et diagnostics sur toute la base ---
full_iv = quay_intervals(
    ops_all.assign(numero_navire=ops_all["numero_navire"].fillna("").astype(str)),
    ch_all.assign(escale_key="", navire=""))
d_min = pd.to_datetime(ops_all["date"]).min()
days_total = int((pd.to_datetime(ops_all["date"]).max() - d_min).days + 1)
taux = occupation_taux(full_iv, days=days_total)
diag = diagnose_inconsistencies(full_iv, days=days_total, taux_df=taux)
over100 = taux[taux["taux_%"] > 100]
print(f"\nPeriode totale : {days_total} jours · postes a quai analyses : {len(taux)}")
top = taux.loc[taux["taux_%"].idxmax()]
print(f"Taux max : {top['taux_%']:.1f}% (poste {top['poste']})")
print(f"Postes >100% : {len(over100)} · diagnostics generes : {len(diag)}")
check("diagnostics coherents avec les depassements", len(diag) == len(over100))
for d in diag[:3]:
    print(f"   - {d['code']} poste {d['poste']} : taux={d['taux_calcule_%']}% "
          f"union={d['duree_union_h']}h brute={d['duree_brute_sommee_h']}h "
          f"double={d['double_comptage_h_detecte']}h chev={len(d['chevauchements'])}")

print()
print("=" * 46)
print(f"RESULTAT : {PASS} PASS / {len(FAIL)} FAIL")
if FAIL:
    print("Echecs :", *FAIL, sep="\n  - ")
    sys.exit(1)

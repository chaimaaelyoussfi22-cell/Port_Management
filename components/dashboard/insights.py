# -*- coding: utf-8 -*-
"""Détection d'anomalies et génération d'insights — 100 % calculés depuis
les données réelles du contexte analytique. Aucune phrase pré-écrite ne
peut produire un chiffre qui ne vient pas des KPI."""

from typing import Dict, List

import pandas as pd

from components.dashboard.thresholds import ANOMALIES, poste_status


def detect_anomalies(ctx: Dict, occ_cur: pd.DataFrame, occ_prev: pd.DataFrame,
                     mo: pd.DataFrame) -> List[Dict]:
    """Liste d'anomalies : type, gravité, valeur, seuil, période, concerné."""
    out: List[Dict] = []
    kpis = ctx["kpis"]

    # 1. Incohérences d'occupation (taux > 100 % sans plafonnement)
    for d in ctx.get("occ_diagnostics", []):
        out.append({"type": "Incohérence de données", "gravité": "🔴 Critique",
                    "valeur": f"{d['taux_calcule_%']} %",
                    "seuil": "≤ 100 %",
                    "période": "Période filtrée",
                    "concerné": f"Poste {d['poste']}",
                    "détail": f"{d['double_comptage_h_detecte']} h de chevauchement détecté"})

    # 2. Occupation anormale par poste + évolution inhabituelle
    prev_map = dict(zip(occ_prev["poste"], occ_prev["duree_occupee_h"])) \
        if not occ_prev.empty else {}
    days = ctx["period"]["days"]
    if not occ_cur.empty:
        for _, r in occ_cur.iterrows():
            taux = r["duree_occupee_h"] / max(days, 1) / 24 * 100
            st_ = poste_status(taux)
            if st_["label"] == "Critique":
                out.append({"type": "Occupation critique", "gravité": "🔴 Critique",
                            "valeur": f"{taux:.1f} %", "seuil": "≥ 90 %",
                            "période": "Période filtrée",
                            "concerné": f"Poste {r['poste']}",
                            "détail": f"{r['nb_navires']} navires · {r['duree_occupee_h']:.0f} h occupées"})
            elif st_["label"] == "Sous tension" and r["poste"] in prev_map:
                prev_taux = prev_map[r["poste"]] / max(days, 1) / 24 * 100
                delta = taux - prev_taux
                if abs(delta) >= ANOMALIES["occupation_delta_pts"]:
                    out.append({"type": "Évolution inhabituelle de l'occupation",
                                "gravité": "🟠 Majeure" if delta > 0 else "🟡 Mineure",
                                "valeur": f"{delta:+.1f} pts",
                                "seuil": f"±{ANOMALIES['occupation_delta_pts']} pts",
                                "période": "vs N-1",
                                "concerné": f"Poste {r['poste']}",
                                "détail": f"{taux:.1f} % vs {prev_taux:.1f} % en N-1"})

    # 3. Pic d'attente par poste (moyenne poste vs moyenne port)
    prepared = ctx["prepared"]
    if not prepared.empty and "attente_h" in prepared:
        att = prepared.dropna(subset=["attente_h"])
        port_mean = float(att["attente_h"].mean()) if len(att) else 0.0
        if port_mean > 0:
            by_poste = att.groupby("poste_norm")["attente_h"].agg(["mean", "count"])
            for poste, row in by_poste.iterrows():
                if not poste or row["count"] < 3:
                    continue
                ratio = row["mean"] / port_mean
                if (ratio >= ANOMALIES["attente_ratio_port"]
                        or row["mean"] >= ANOMALIES["attente_poste_critique_h"]):
                    out.append({"type": "Pic d'attente", "gravité": "🟠 Majeure",
                                "valeur": f"{row['mean']:.1f} h",
                                "seuil": f"> {ANOMALIES['attente_ratio_port']}× port ({port_mean:.0f} h)"
                                         f" ou ≥ {ANOMALIES['attente_poste_critique_h']} h",
                                "période": "Période filtrée",
                                "concerné": f"Poste {poste}" if poste else "Poste non renseigné",
                                "détail": f"{row['count']} escales concernées"})

    # 4. Anomalies mensuelles : tonnage / escales / pic d'attente
    if not mo.empty and not prepared.empty:
        cur_year = int(mo["year"].max())
        m_cur = mo[mo["year"] == cur_year].set_index("month")
        m_prev = mo[mo["year"] == cur_year - 1].set_index("month")
        for month in sorted(set(m_cur.index)):
            ton_c = float(m_cur.loc[month, "tonnage"]) if month in m_cur.index else None
            ton_p = float(m_prev.loc[month, "tonnage"]) if month in m_prev.index else None
            esc_c = float(m_cur.loc[month, "escales"]) if month in m_cur.index else None
            esc_p = float(m_prev.loc[month, "escales"]) if month in m_prev.index else None
            label = f"{cur_year} · mois {int(month)}"
            if ton_c and ton_p and ton_p > 0:
                var = (ton_c - ton_p) / ton_p * 100
                if var <= ANOMALIES["tonnage_baisse_mensuelle_pct"]:
                    out.append({"type": "Baisse brutale du tonnage", "gravité": "🟠 Majeure",
                                "valeur": f"{var:+.1f} %", "seuil": f"≤ {ANOMALIES['tonnage_baisse_mensuelle_pct']} %",
                                "période": label, "concerné": "Trafic global",
                                "détail": f"{ton_c:,.0f} t vs {ton_p:,.0f} t en N-1"})
            if esc_c and esc_p and esc_p > 0:
                var = (esc_c - esc_p) / esc_p * 100
                if abs(var) >= ANOMALIES["escales_swing_pct"]:
                    out.append({"type": "Swing du nombre d'escales", "gravité": "🟡 Mineure",
                                "valeur": f"{var:+.1f} %", "seuil": f"±{ANOMALIES['escales_swing_pct']} %",
                                "période": label, "concerné": "Trafic global",
                                "détail": f"{esc_c:.0f} escales vs {esc_p:.0f}"})
            att_c = float(m_cur.loc[month, "attente_moyenne"]) \
                if "attente_moyenne" in m_cur.columns and month in m_cur.index else None
            med = float(mo["attente_moyenne"].median()) \
                if "attente_moyenne" in mo.columns and len(mo) else None
            if att_c and med and med > 0 and att_c / med >= ANOMALIES["attente_pic_ratio_mediane"]:
                out.append({"type": "Pic d'attente mensuel", "gravité": "🟠 Majeure",
                            "valeur": f"{att_c:.1f} h",
                            "seuil": f"≥ {ANOMALIES['attente_pic_ratio_mediane']}× médiane ({med:.0f} h)",
                            "période": label,                             "concerné": "Attente au mouillage",
                            "détail": "Congestion potentielle sur le mois"})

    # 5. Conflits physiques (deux navires simultanés sur un même poste)
    iv = ctx.get("intervals")
    if iv is not None and not iv.empty:
        from components.dashboard.occupation import occupation_per_poste
        occ_full = occupation_per_poste(iv)
        conflits = int(occ_full["conflits"].sum()) if not occ_full.empty else 0
        if conflits:
            worst = occ_full.loc[occ_full["conflits"].idxmax()]
            out.append({"type": "Doublons / chevauchements temporels",
                        "gravité": "🟡 Mineure",
                        "valeur": f"{conflits} chevauchement(s)",
                        "seuil": "0 attendu",
                        "période": "Période filtrée",
                        "concerné": f"Poste {worst['poste']} en premier",
                        "détail": "Navires différents simultanément sur un même poste "
                                  "(multi-escale ou donnée à vérifier)"})

    order = {"🔴 Critique": 0, "🟠 Majeure": 1, "🟡 Mineure": 2}
    out.sort(key=lambda a: order.get(a["gravité"], 3))
    return out


def generate_insights(ctx: Dict, occ_cur: pd.DataFrame, occ_prev: pd.DataFrame,
                      mo: pd.DataFrame) -> List[str]:
    """Phrases courtes générées depuis les chiffres réels uniquement."""
    tips: List[str] = []
    kpis, kpis_prev = ctx["kpis"], ctx["kpis_prev"]
    postes = ctx["postes"]
    days = ctx["period"]["days"]

    # Insight 1 — poste le plus sollicité + Δ pts N-1
    if not occ_cur.empty and days:
        tmp = occ_cur.copy()
        tmp["taux"] = tmp["duree_occupee_h"] / max(days, 1) / 24 * 100
        top = tmp.loc[tmp["taux"].idxmax()]
        line = (f"Le poste {top['poste']} présente le taux d'occupation le plus élevé "
                f"avec {top['taux']:.1f} %")
        if not occ_prev.empty and top["poste"] in set(occ_prev["poste"]):
            p = occ_prev[occ_prev["poste"] == top["poste"]].iloc[0]
            pt = p["duree_occupee_h"] / max(days, 1) / 24 * 100
            line += f", soit {top['taux'] - pt:+.1f} points par rapport à N-1"
        tips.append(line + ".")

    # Insight 2 — croissance tonnage vs escales (efficacité par escale)
    var_t = ctx["variations"].get("tonnage")
    var_e = ctx["variations"].get("escales")
    if var_t is not None and var_e is not None and kpis_prev["escales"] > 0:
        t_per_call = kpis["tonnage"] / max(kpis["escales"], 1)
        t_per_call_prev = kpis_prev["tonnage"] / max(kpis_prev["escales"], 1)
        if t_per_call_prev > 0:
            tips.append(
                f"Le tonnage évolue de {var_t:+.1f} % pour {var_e:+.1f} % d'escales : "
                f"le tonnage moyen par escale passe de {t_per_call_prev:,.0f} t à "
                f"{t_per_call:,.0f} t.".replace(",", " "))

    # Insight 3 — concentration du trafic sur la première marchandise
    prepared = ctx["prepared"]
    if not prepared.empty:
        g = prepared.groupby("marchandise_norm")["tonnage"].sum()
        g = g[g > 0].sort_values(ascending=False)
        total = float(g.sum())
        if len(g) >= 2 and total > 0:
            share = float(g.iloc[0]) / total * 100
            tips.append(f"La marchandise « {g.index[0]} » concentre {share:.1f} % du tonnage "
                        f"({g.iloc[0]:,.0f} t).".replace(",", " "))

    # Insight 4 — attente : moyenne vs médiane (distribution asymétrique)
    if not prepared.empty:
        att = prepared["attente_h"].dropna()
        if len(att) >= 10:
            mean_v, med_v = float(att.mean()), float(att.median())
            skew = "supérieure" if mean_v > med_v * 1.15 else (
                "proche" if mean_v > med_v * 0.85 else "inférieure")
            tips.append(f"L'attente moyenne ({mean_v:.1f} h) est {skew} à la médiane "
                        f"({med_v:.1f} h) — "
                        + ("une minorité d'escales tire la moyenne vers le haut."
                           if skew == "supérieure" else
                           "la distribution est relativement symétrique."
                           if skew == "proche" else
                           "la majorité des escales attendent plus que la moyenne suggérée."))

    # Insight 5 — saisonnalité : meilleur / plus faible mois de l'année N
    if not mo.empty:
        years = sorted(mo["year"].unique())
        last = mo[mo["year"] == years[-1]]
        if len(last) >= 6:
            best = last.loc[last["tonnage"].idxmax()]
            worst = last.loc[last["tonnage"].idxmin()]
            tips.append(f"En {int(years[-1])}, le mois {int(best['month']):02d} est le plus actif "
                        f"({best['tonnage']:,.0f} t) et le mois {int(worst['month']):02d} le plus creux "
                        f"({worst['tonnage']:,.0f} t).".replace(",", " "))

    # Insight 6 — productivité extrêmes par poste
    if not postes.empty and float(postes["productivite"].max()) > 0:
        best_p = postes.loc[postes["productivite"].idxmax()]
        flop_p = postes[postes["productivite"] > 0]
        if len(flop_p):
            worst_p = flop_p.loc[flop_p["productivite"].idxmin()]
            ratio = best_p["productivite"] / max(worst_p["productivite"], 1e-9)
            tips.append(f"L'écart de productivité entre postes atteint ×{ratio:.1f} "
                        f"(poste {best_p['poste']} : {best_p['productivite']:.0f} t/h vs "
                        f"poste {worst_p['poste']} : {worst_p['productivite']:.0f} t/h).")

    return tips[:6]

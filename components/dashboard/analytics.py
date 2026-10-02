# -*- coding: utf-8 -*-
"""
Moteur analytique du Port Performance Intelligence.

Toutes les relations mathématiques du dashboard sont centralisées ici :
  - Escales      : COUNT(DISTINCT numero d'escale)
  - Navires      : COUNT(DISTINCT navire) (+ répétitifs si >= 2 escales)
  - Trafic       : SUM(tonnage) / Import / Export / Cabotage
  - Séjour quai  : Appareillage_Quai - Accostage            (heures)
  - Séjour port  : Appareillage_Port - Arrivée_Rade         (heures)
  - Attente      : Sortie_Mouillage - Mouillage             (heures)
  - Productivité : SUM(Tonnage) / SUM(Durée_quai)           (t/h, pondérée)
  - Occupation   : SUM(Durée_quai au poste) / (jours * 24)  (%)

Règle de répartition du tonnage entre postes (changements de poste) :
chaque segment réel de quai (opération principale + poste_changes) reçoit
    Tonnage_attribué = Tonnage_total_de_l'escale / nombre_de_postes_utilisés
Le tonnage global n'est jamais dupliqué : la règle ne s'applique qu'aux
analyses PAR POSTE.

Aucune valeur fictive : chaque indicateur provient des données réelles.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ------------------------------------------------------------------
# Constantes visuelles partagées (couleurs métier)
# ------------------------------------------------------------------
CLASS_COLORS = {
    "underused": "#56a8ff",   # bleu  — sous-utilisé (< 50 %)
    "optimal": "#32d2a4",     # vert  — optimisé (50–70 %)
    "busy": "#f2b84b",        # orange— très sollicité (70–80 %)
    "saturated": "#ff6077",   # rouge — saturation (>= 80 %)
}
CLASS_LABELS = {
    "underused": "Sous-utilisé",
    "optimal": "Optimisé",
    "busy": "Très sollicité",
    "saturated": "Saturation",
}

TRAFFIC_MAP = {"import": "Import", "export": "Export",
               "cabotage": "Cabotage", "cab": "Cabotage"}

MONTHS_FR = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
             "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


# ==================================================================
# PRÉPARATION DES DONNÉES
# ==================================================================
def _dt(frame: pd.DataFrame, date_col: str, time_col: str) -> pd.Series:
    """Construit une série datetime depuis des colonnes date + heure."""
    from components.dashboard.occupation import format_hhmmss
    if date_col not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index)
    dates = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    times = (frame[time_col].map(format_hhmmss)
             if time_col in frame.columns
             else pd.Series("00:00:00", index=frame.index))
    stamp = dates + " " + times
    out = pd.to_datetime(stamp, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    loose = out.isna() & dates.notna()
    if loose.any():
        out.loc[loose] = pd.to_datetime(stamp[loose], errors="coerce")
    return out


def _num(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def prepare_operations(ops: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les clés et durées calculées à partir des horaires réels."""
    f = ops.copy()
    if f.empty:
        return f
    # Identité d'escale : numéro d'escale (numero_navire) sinon clé dérivée réelle
    num = f.get("numero_navire", pd.Series("", index=f.index)).fillna("").astype(str).str.strip()
    fallback = f["navire"].astype(str) + "|" + f["date"].astype(str) + "|" + f["poste"].astype(str)
    f["escale_key"] = num.where(num != "", fallback)
    f["navire_name"] = f["navire"].fillna("").astype(str)

    # Durées (heures) depuis les horaires réels ; repli sur les valeurs stockées
    attente_calc = (_dt(f, "date_sortie_mouillage", "heure_sortie_mouillage")
                    - _dt(f, "date_mouillage", "heure_mouillage")).dt.total_seconds() / 3600
    quai_calc = (_dt(f, "date_app_quai", "heure_app_quai")
                 - _dt(f, "date_accostage", "heure_accostage")).dt.total_seconds() / 3600
    port_calc = (_dt(f, "date_app_port", "heure_app_port")
                 - _dt(f, "date_rade", "heure_rade")).dt.total_seconds() / 3600

    def _resolve(calc: pd.Series, stored_col: str) -> pd.Series:
        stored = _num(f, stored_col, 0.0)
        out = calc.where(calc.notna() & (calc >= 0))
        return out.fillna(stored.where(stored > 0))

    f["attente_h"] = _resolve(attente_calc, "temps_attente")
    f["quai_h"] = _resolve(quai_calc, "temps_sejour")
    f["port_h"] = _resolve(port_calc, "temps_sejour")

    f["tonnage"] = _num(f, "quantite")
    trafic = f.get("type_operation", pd.Series("", index=f.index)).fillna("").astype(str).str.strip().str.lower()
    f["type_trafic"] = trafic.map(lambda v: TRAFFIC_MAP.get(v[:4], v.title() if v else ""))
    f["poste_norm"] = f.get("poste", pd.Series("", index=f.index)).fillna("").astype(str).str.upper().replace({"NAN": ""})
    f["operateur_norm"] = f.get("operateur", pd.Series("", index=f.index)).fillna("").astype(str)
    f["marchandise_norm"] = f.get("type_marchandise", pd.Series("", index=f.index)).fillna("").astype(str)
    # « Autre » = UNE seule catégorie : on regroupe toutes les variantes de casse
    tn = f.get("type_navire", pd.Series("", index=f.index)).fillna("").astype(str).str.strip()
    f["type_navire_norm"] = tn.mask(tn.str.lower() == "autre", "Autre")

    d = pd.to_datetime(f["date"], errors="coerce")
    f["year"] = d.dt.year
    f["month"] = d.dt.month
    return f


def fetch_poste_changes(ids: List[Any]) -> pd.DataFrame:
    """Changements de poste bruts pour une liste d'opérations (RAW DATA, lecture seule)."""
    if not ids:
        return pd.DataFrame()
    try:
        from database import db_manager
        conn = db_manager._connect()
        if conn is None:
            return pd.DataFrame()
        try:
            placeholders = ",".join(["%s"] * len(ids))
            return pd.read_sql_query(
                "SELECT id, operation_id, poste, date_accostage, heure_accostage, "
                f"date_app_quai, heure_app_quai FROM poste_changes "
                f"WHERE operation_id IN ({placeholders})", conn, params=tuple(ids))
        finally:
            conn.close()
    except Exception:
        return pd.DataFrame()


def load_poste_segments(prepared: pd.DataFrame,
                        changes: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Segments réels d'occupation des postes : opération principale + changements.
    Chaque segment porte le tonnage attribué (règle Tonnage/n postes).

    Durées : contribution MARGINALE de chaque événement à la couverture temporelle
    du couple (escale, poste). Un chevauchement ou doublon même-poste n'est donc
    compté qu'une seule fois (frontières de changement respectées, postes
    différents jamais fusionnés, retours sur un même poste conservés distincts).

    Optimisation : horaires parsés de façon vectorisée sur tout le DataFrame
    (aucune construction de DataFrame par ligne) ; les changements de poste
    peuvent être injectés par l'appelant (évite une requête SQL redondante).
    """
    from components.dashboard import occupation as occ

    cols = ["id", "escale_key", "poste_norm", "quai_h", "tonnage", "type_trafic",
            "operateur_norm", "marchandise_norm", "type_navire_norm", "month", "year"]
    if prepared.empty:
        return pd.DataFrame(columns=cols + ["seg_start", "seg_dur_h"])

    if changes is None:
        changes = fetch_poste_changes(prepared["id"].tolist())

    # ---- Parsing vectorisé des horaires (1 passe au lieu de N) ----
    base_starts = _dt(prepared, "date_accostage", "heure_accostage").tolist()
    base_ends = _dt(prepared, "date_app_quai", "heure_app_quai").tolist()

    changes_by_op: Dict[Any, List[Dict[str, Any]]] = {}
    if changes is not None and not changes.empty:
        ch = changes.copy()
        ch["_s"] = _dt(ch, "date_accostage", "heure_accostage")
        ch["_e"] = _dt(ch, "date_app_quai", "heure_app_quai")
        for op_id, g in ch.groupby("operation_id", sort=False):
            recs = sorted(g.to_dict("records"),
                          key=lambda c: (c.get("date_accostage"), c.get("heure_accostage")))
            changes_by_op[op_id] = recs

    rows: List[Dict[str, Any]] = []
    placed: Dict[Tuple[str, str], List[Tuple[pd.Timestamp, pd.Timestamp]]] = {}

    def marginal(escale_key: str, poste_norm: str,
                 s: pd.Timestamp, e: pd.Timestamp) -> float:
        """Durée non encore couverte de (s,e) dans le couple (escale, poste)."""
        key = (str(escale_key), str(poste_norm))
        spans = placed.setdefault(key, [])
        covered = occ._overlap(spans, s, e)
        total = max((e - s).total_seconds() / 3600 - covered, 0.0)
        spans.append((s, e))
        return total

    records = prepared.to_dict("records")
    for i, op in enumerate(records):
        start = base_starts[i]
        end = base_ends[i]
        base = {c: op[c] for c in cols if c in op}
        ch_list = changes_by_op.get(op["id"], [])
        n_postes = 1 + len(ch_list)
        tonnage_part = float(base.get("tonnage", 0.0) or 0.0) / n_postes
        dur = base.get("quai_h")
        dur = float(dur) if pd.notna(dur) else 0.0
        if pd.notna(start) and pd.notna(end) and end > start:
            seg_dur = marginal(base.get("escale_key"), base.get("poste_norm"), start, end)
        else:
            seg_dur = max(dur, 0.0)
        rows.append({**base, "segment": "principale", "seg_start": start,
                     "seg_dur_h": seg_dur, "tonnage_attr": tonnage_part,
                     "n_postes": n_postes})
        for chg in ch_list:
            s = chg.get("_s")
            e = chg.get("_e")
            d_h = ((e - s).total_seconds() / 3600) if (pd.notna(s) and pd.notna(e)) else 0.0
            if pd.notna(s) and pd.notna(e) and e > s:
                seg_dur_c = marginal(base.get("escale_key"), norm_poste_label(chg.get("poste")),
                                     s, e)
            else:
                seg_dur_c = max(d_h, 0.0)
            m = pd.Timestamp(s).month if pd.notna(s) else base.get("month")
            y = pd.Timestamp(s).year if pd.notna(s) else base.get("year")
            rows.append({**base, "segment": "changement",
                         "poste_norm": norm_poste_label(chg.get("poste")),
                         "seg_start": s, "seg_dur_h": seg_dur_c,
                         "tonnage_attr": tonnage_part, "n_postes": n_postes,
                         "month": m, "year": y})
    seg = pd.DataFrame(rows)
    if seg.empty:
        seg = pd.DataFrame(columns=cols + ["segment", "seg_start", "seg_dur_h", "tonnage_attr", "n_postes"])
    return seg


def norm_poste_label(val) -> str:
    """Libellé de poste normalisé (majuscules, sans NaN)."""
    s = str(val or "").strip().upper()
    return "" if s in ("NAN", "NONE") else s


# ==================================================================
# PÉRIODES ET COMPARAISONS N / N-1
# ==================================================================
def resolve_period(filters: Dict[str, Any], frame: pd.DataFrame) -> Tuple[Optional[date], Optional[date], int]:
    """Retourne (début, fin, nb_jours) de la période analysée."""
    start, end = filters.get("start"), filters.get("end")
    if start and end:
        days = max((end - start).days + 1, 1)
        return start, end, days
    if frame.empty or "date" not in frame.columns:
        return None, None, 365
    d = pd.to_datetime(frame["date"], errors="coerce").dropna()
    if d.empty:
        return None, None, 365
    start = d.min().date(); end = d.max().date()
    days = max((end - start).days + 1, 1)
    return start, end, days


def previous_year_window(start: Optional[date], end: Optional[date]) -> Tuple[Optional[date], Optional[date]]:
    """Même fenêtre décalée d'un an (29/02 reporté au 28/02)."""
    def back(d: Optional[date]) -> Optional[date]:
        if not d:
            return None
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            return d.replace(year=d.year - 1, day=28)
    return back(start), back(end)


def slice_period(frame: pd.DataFrame, start: Optional[date], end: Optional[date]) -> pd.DataFrame:
    if frame.empty or "date" not in frame.columns:
        return frame
    d = pd.to_datetime(frame["date"], errors="coerce").dt.date
    mask = d.notna()
    dd = d[mask]
    if start:
        mask &= dd >= start
    if end:
        mask &= dd <= end
    return frame[mask]


def variation(current: float, previous: float) -> Optional[float]:
    """Variation (%) N vs N-1 ; None si non calculable."""
    if previous is None or previous == 0 or pd.isna(previous):
        return None
    return round((current - previous) / abs(previous) * 100, 2)


# ==================================================================
# KPI GLOBAUX
# ==================================================================
def compute_kpis(prepared: pd.DataFrame, segments: pd.DataFrame, days: int,
                 intervals: Optional[pd.DataFrame] = None,
                 occ_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """KPI globaux de la période (aucune donnée fictive).

    occ_df : table d'occupation pré-calculée (colonnes poste/occupation) —
    évite de recalculer l'union des intervalles lorsqu'elle est déjà connue.
    """
    k: Dict[str, Any] = {
        "escales": 0, "navires": 0, "repetitifs": 0, "tonnage": 0.0,
        "import": 0.0, "export": 0.0, "cabotage": 0.0,
        "attente": 0.0, "sejour_quai": 0.0, "sejour_port": 0.0,
        "productivite": 0.0, "occupation": 0.0, "days": days,
    }
    if prepared.empty:
        return k
    k["escales"] = int(prepared["escale_key"].nunique())
    k["navires"] = int(prepared["navire_name"].nunique())
    per_ship = prepared.groupby("navire_name")["escale_key"].nunique()
    k["repetitifs"] = int((per_ship >= 2).sum())
    k["tonnage"] = float(prepared["tonnage"].sum())
    for key in ("Import", "Export", "Cabotage"):
        k[key.lower()] = float(prepared.loc[prepared["type_trafic"] == key, "tonnage"].sum())

    for src, dst in (("attente_h", "attente"), ("quai_h", "sejour_quai"), ("port_h", "sejour_port")):
        vals = prepared[src].dropna()
        k[dst] = round(float(vals.mean()), 1) if len(vals) else 0.0

    total_quai_h = float(prepared["quai_h"].fillna(0).clip(lower=0).sum())
    k["productivite"] = round(k["tonnage"] / total_quai_h, 1) if total_quai_h > 0 else 0.0

    if occ_df is not None and not occ_df.empty:
        poste_occ = occ_df
    else:
        poste_occ = occupation_par_poste(intervals if intervals is not None else segments, days)
    k["occupation"] = round(float(poste_occ["occupation"].mean()), 1) if not poste_occ.empty else 0.0
    return k


def compare_kpis(cur: Dict[str, Any], prev: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Variations N vs N-1 pour tous les KPI (sens métier géré côté UI)."""
    keys = ["escales", "navires", "tonnage", "attente", "sejour_quai",
            "sejour_port", "productivite", "occupation"]
    return {k: variation(float(cur.get(k, 0) or 0), float(prev.get(k, 0) or 0)) for k in keys}


# ==================================================================
# SÉRIES MENSUELLES
# ==================================================================
def monthly_series(prepared: pd.DataFrame, value: str = "tonnage",
                   agg: str = "sum") -> pd.DataFrame:
    """Série mensuelle (1..12) par année : courbes N vs N-1."""
    if prepared.empty or "month" not in prepared.columns:
        return pd.DataFrame(columns=["month", "year", "value"])
    f = prepared.dropna(subset=["month"])
    if agg == "sum":
        ser = f.groupby(["year", "month"])[value].sum()
    elif agg == "mean":
        ser = f.groupby(["year", "month"])[value].mean()
    else:
        ser = f.groupby(["year", "month"])[value].nunique()
    ser = ser.reset_index(name="value")
    return ser


def yearly_totals_by_category(prepared: pd.DataFrame, category: str,
                              value: str = "tonnage") -> pd.DataFrame:
    """Totaux annuels par catégorie (marchandise, opérateur, poste...)."""
    if prepared.empty:
        return pd.DataFrame(columns=[category, "cur", "prev"])
    cur_year = prepared["year"].max()
    g = prepared.groupby([category, "year"])[value].sum().reset_index()
    piv = g.pivot_table(index=category, columns="year", values=value, fill_value=0.0)
    piv.columns = [int(c) for c in piv.columns]
    piv["cur"] = piv.get(cur_year, 0.0)
    piv["prev"] = piv.get(cur_year - 1, 0.0)
    return piv.reset_index()


# ==================================================================
# ANALYSE PAR POSTE
# ==================================================================
def occupation_par_poste(intervals: pd.DataFrame, days: int) -> pd.DataFrame:
    """Taux d'occupation physique par poste.

    Temps réellement occupé (union des intervalles, tous navires, dédupliqué)
    ÷ temps disponible (jours × 24) × 100. Aucun plafonnement : un taux > 100
    est une incohérence de données signalée via diagnose_inconsistencies().
    """
    from components.dashboard.occupation import occupation_taux
    cols = ["poste", "occupation"]
    if intervals is None or intervals.empty:
        return pd.DataFrame(columns=cols)
    taux = occupation_taux(intervals, days)
    if taux.empty:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame({
        "poste": taux["poste"],
        "occupation": taux["taux_%"].round(2),
    })


def occupancy_class(occ: float) -> str:
    if occ < 50:
        return "underused"
    if occ < 70:
        return "optimal"
    if occ < 80:
        return "busy"
    return "saturated"


def poste_stats(prepared: pd.DataFrame, segments: pd.DataFrame, days: int,
                intervals: Optional[pd.DataFrame] = None,
                occ_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Matrice intelligente par poste : occupation, séjour, productivité, diagnostic.

    occ_df : table d'occupation pré-calculée (poste/occupation) — réutilisée
    telle quelle si fournie (une seule union des intervalles pour tout le ctx).

    Lazy mode : sans segments, les agrégats par poste proviennent directement
    des lignes préparées (mêmes formules ; les segments raffinent seulement
    l'attribution en cas de changements de poste).
    """
    port_sej = float(prepared["quai_h"].dropna().mean()) if not prepared.empty else 0.0
    total_quai_h = float(prepared["quai_h"].fillna(0).clip(lower=0).sum()) if not prepared.empty else 0.0
    total_ton = float(prepared["tonnage"].sum()) if not prepared.empty else 0.0
    port_prod = total_ton / total_quai_h if total_quai_h > 0 else 0.0

    if occ_df is not None and not occ_df.empty:
        occ_src = occ_df.set_index("poste")
    elif not segments.empty:
        occ_src = occupation_par_poste(
            intervals if intervals is not None else segments, days).set_index("poste")
    elif intervals is not None and not intervals.empty:
        occ_src = occupation_par_poste(intervals, days).set_index("poste")
    else:
        occ_src = pd.DataFrame()

    if segments.empty:
        if prepared.empty or "poste_norm" not in prepared.columns:
            return pd.DataFrame(columns=[
                "poste", "occupation", "classe", "escales", "tonnage",
                "sejour_moyen", "productivite", "ecart_sejour", "diagnostic", "diag_classe"])
        grp = prepared.groupby("poste_norm")
        rows = []
        for poste, g in grp:
            if not str(poste):
                continue
            occ = float(occ_src.loc[poste, "occupation"]) if poste in occ_src.index else 0.0
            escales = int(g["escale_key"].nunique())
            tonnage = float(g["tonnage"].sum())
            q_vals = g.loc[g["quai_h"] > 0, "quai_h"]
            sejour = float(q_vals.mean()) if len(q_vals) else 0.0
            dur_sum = float(g["quai_h"].fillna(0).clip(lower=0).sum())
            prod = tonnage / dur_sum if dur_sum > 0 else 0.0
            ecart = variation(sejour, port_sej) if port_sej else None
            diag, diag_cls = diagnose_poste(occ, sejour, prod, port_sej, port_prod)
            rows.append({
                "poste": poste, "occupation": round(occ, 1), "classe": occupancy_class(occ),
                "escales": escales, "tonnage": round(tonnage, 0),
                "sejour_moyen": round(sejour, 1), "productivite": round(prod, 1),
                "ecart_sejour": ecart, "diagnostic": diag, "diag_classe": diag_cls,
            })
        if not rows:
            return pd.DataFrame(columns=[
                "poste", "occupation", "classe", "escales", "tonnage",
                "sejour_moyen", "productivite", "ecart_sejour", "diagnostic", "diag_classe"])
        return pd.DataFrame(rows).sort_values("occupation", ascending=False).reset_index(drop=True)

    grp = segments.groupby("poste_norm")
    rows = []
    for poste, g in grp:
        occ = float(occ_src.loc[poste, "occupation"]) if poste in occ_src.index else 0.0
        escales = int(g["escale_key"].nunique())
        tonnage = float(g["tonnage_attr"].sum())
        sej_vals = g.loc[g["seg_dur_h"] > 0, "seg_dur_h"]
        sejour = float(sej_vals.mean()) if len(sej_vals) else 0.0
        dur_sum = float(g["seg_dur_h"].clip(lower=0).sum())
        prod = tonnage / dur_sum if dur_sum > 0 else 0.0
        ecart = variation(sejour, port_sej) if port_sej else None
        diag, diag_cls = diagnose_poste(occ, sejour, prod, port_sej, port_prod)
        rows.append({
            "poste": poste, "occupation": round(occ, 1), "classe": occupancy_class(occ),
            "escales": escales, "tonnage": round(tonnage, 0),
            "sejour_moyen": round(sejour, 1), "productivite": round(prod, 1),
            "ecart_sejour": ecart, "diagnostic": diag, "diag_classe": diag_cls,
        })
    df = pd.DataFrame(rows).sort_values("occupation", ascending=False).reset_index(drop=True)
    return df


def diagnose_poste(occ: float, sejour: float, prod: float,
                   port_sejour: float, port_prod: float) -> Tuple[str, str]:
    """Diagnostic automatique f(Occupation, Séjour, Productivité)."""
    sej_high = sejour > port_sejour if port_sejour else sejour > 0
    prod_low = prod < port_prod * 0.8 if port_prod else False
    if occ >= 80 and sej_high:
        return "Risque de congestion", "critical"
    if occ >= 80:
        return "Poste très sollicité mais performant", "warning"
    if occ >= 70:
        return "Poste sous tension", "warning"
    if occ < 50 and sej_high:
        return "Sous-utilisation avec séjour élevé", "watch"
    if occ < 50:
        return "Sous-utilisé", "underused"
    if 50 <= occ < 70 and not sej_high and not prod_low:
        return "Performance optimale", "optimal"
    return "Performance opérationnelle à analyser", "watch"


DIAG_STYLE = {
    "critical": ("🔴", "Risque de congestion"),
    "warning": ("🟠", "Très sollicité"),
    "watch": ("⚠️", "À analyser"),
    "underused": ("🔵", "Sous-utilisé"),
    "optimal": ("🟢", "Performance optimale"),
}


# ==================================================================
# SCORE GLOBAL COMPOSITE
# ==================================================================
def _sub(v: float, worst: float) -> float:
    return max(0.0, min(100.0, 100.0 - (max(v, 0.0) / worst) * 100))


def compute_composite_score(kpis: Dict[str, Any],
                            variations: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Score 0-100 dynamique à partir des indicateurs réels disponibles."""
    sub = {
        "Attente": _sub(float(kpis.get("attente") or 0), 48),
        "Séjour à quai": _sub(float(kpis.get("sejour_quai") or 0), 96),
        "Séjour au port": _sub(float(kpis.get("sejour_port") or 0), 144),
        "Productivité": max(0.0, min(100.0, (float(kpis.get("productivite") or 0) / 1500) * 100)),
        "Occupation": max(0.0, min(100.0, 100 - abs(float(kpis.get("occupation") or 0) - 60) / 40 * 100)),
        "Évolution trafic": max(0.0, min(100.0, 50 + (variations.get("tonnage") or 0))),
        "Évolution escales": max(0.0, min(100.0, 50 + (variations.get("escales") or 0))),
    }
    # Pondération uniforme de 1/7 pour les 7 sous-indicateurs, afin d'éviter
    # d'attribuer une importance subjective à un indicateur plutôt qu'à un
    # autre, en l'absence de justification empirique ou réglementaire
    # permettant de différencier les poids.
    n = len(sub)            # 7 indicateurs
    w = 1.0 / n             # 14,2857 % par indicateur
    score = round(sum(sub[k] * w for k in sub))
    if score >= 85:
        etat = "Excellent"
    elif score >= 70:
        etat = "Bon"
    elif score >= 55:
        etat = "Correct"
    elif score >= 40:
        etat = "À améliorer"
    else:
        etat = "Critique"
    return {"score": score, "etat": etat, "subscores": sub}


SCORE_TONE = {"Critique": "low", "À améliorer": "medium", "Correct": "medium",
              "Bon": "good", "Excellent": "good"}

_SCORE_WEIGHT = 1.0 / 7


def score_details(kpis: Dict[str, Any], kpis_prev: Dict[str, Any],
                  variations: Dict[str, Optional[float]],
                  score_block: Dict[str, Any]) -> list:
    """Décomposition complète du score pour le panneau transparent."""
    subs = score_block["subscores"]

    def _v(key):
        return float(kpis.get(key) or 0)

    def _vp(key):
        return float(kpis_prev.get(key) or 0)

    def _fmt(val, unit):
        if val is None or (isinstance(val, float) and val == 0 and unit not in ("%",)):
            return "N/D"
        if unit == "t":
            if abs(val) >= 1_000_000:
                return f"{val / 1_000_000:.2f} Mt"
            if abs(val) >= 1_000:
                return f"{val / 1_000:.1f} kt"
            return f"{val:,.0f} t".replace(",", " ")
        if unit == "h":
            return f"{val:.1f} h"
        if unit == "%":
            return f"{val:.1f} %"
        if unit == "t/h":
            return f"{val:.1f} t/h"
        return f"{val:,.0f}".replace(",", " ")

    def _delta_abs(cur, prev):
        if prev is None or prev == 0:
            return None
        return cur - prev

    def _delta_pct(cur, prev):
        if prev is None or prev == 0:
            return None
        return round((cur - prev) / abs(prev) * 100, 1)

    def _fmt_delta(val, unit, prev_val=None, ref=None):
        if val is None:
            return "N/D", "neutral"
        if unit == "h":
            cls = "good" if val < 0 else "bad"
            return f"{'+' if val >= 0 else ''}{val:.1f} h", cls
        if unit == "pts" and prev_val is not None and ref is not None:
            prev_dist = abs(prev_val - ref)
            curr_dist = abs(_v("occupation") - ref)
            cls = "good" if curr_dist < prev_dist else "bad" if curr_dist > prev_dist else "neutral"
            label = f"{'+' if val >= 0 else ''}{val:.1f} pts"
            return label, cls
        if unit == "pts":
            return f"{'+' if val >= 0 else ''}{val:.1f} pts", "neutral"
        cls = "good" if val > 0 else "bad"
        return f"{'+' if val >= 0 else ''}{val:.1f} %", cls

    def _interp_occupation(val):
        if val < 50:
            return "Sous-utilisation des postes."
        if val <= 65:
            return "Occupation proche de l'optimum."
        if val <= 75:
            return "Poste sollicité, vigilance requise."
        if val <= 85:
            return "Forte sollicitation, risque de saturation."
        return "Saturation critique des postes."

    def _interp_duration(val, ref, label):
        if val == 0:
            return f"Aucune donnée de {label} disponible."
        if val <= ref * 0.5:
            return f"{label.capitalize()} très courte, performance excellente."
        if val <= ref:
            return f"{label.capitalize()} dans la plage acceptable."
        if val <= ref * 1.5:
            return f"{label.capitalize()} au-dessus de la référence, à surveiller."
        return f"{label.capitalize()} très élevée, impact négatif sur la performance."

    prod = _v("productivite")
    occ = _v("occupation")
    att = _v("attente")
    sq = _v("sejour_quai")
    sp = _v("sejour_port")
    tonn = _v("tonnage")
    esc = _v("escales")
    tonn_p = _vp("tonnage")
    esc_p = _vp("escales")
    var_t = variations.get("tonnage")
    var_e = variations.get("escales")

    def _contrib(name):
        return round(subs[name] * _SCORE_WEIGHT, 1)

    return [
        {
            "name": "Productivité", "icon": "⚙️", "weight": _SCORE_WEIGHT,
            "raw": _fmt(prod, "t/h"), "raw_prev": _fmt(_vp("productivite"), "t/h"),
            "score": subs["Productivité"], "contribution": _contrib("Productivité"),
            "formula": f"({prod:.1f} / 1500) × 100 = {subs['Productivité']:.0f}/100",
            "reference": "1 500 t/h",
            "rule": "Plus la productivité (t/h) est élevée, meilleure est la performance.",
            "interpretation": (
                "Productivité très faible." if prod < 300 else
                "Productivité en dessous des attentes." if prod < 750 else
                "Productivité correcte." if prod < 1200 else
                "Bonne productivité." if prod < 1500 else
                "Excellente productivité."
            ),
            "delta": _fmt_delta(_delta_pct(prod, _vp("productivite")), "%"),
        },
        {
            "name": "Occupation", "icon": "🏗", "weight": _SCORE_WEIGHT,
            "raw": _fmt(occ, "%"), "raw_prev": _fmt(_vp("occupation"), "%"),
            "score": subs["Occupation"], "contribution": _contrib("Occupation"),
            "formula": f"100 − |{occ:.1f} − 60| / 40 × 100 = {subs['Occupation']:.0f}/100",
            "reference": "Optimum = 60 %",
            "rule": "L'optimum est 60 %. Plus on s'en éloigne (sous-utilisation ou saturation), plus le score baisse.",
            "interpretation": _interp_occupation(occ),
            "delta": _fmt_delta(_delta_abs(occ, _vp("occupation")), "pts",
                                prev_val=_vp("occupation"), ref=60),
        },
        {
            "name": "Attente", "icon": "⏳", "weight": _SCORE_WEIGHT,
            "raw": _fmt(att, "h"), "raw_prev": _fmt(_vp("attente"), "h"),
            "score": subs["Attente"], "contribution": _contrib("Attente"),
            "formula": f"100 − ({att:.1f} / 48) × 100 = {subs['Attente']:.0f}/100",
            "reference": "48 h",
            "rule": "Moins d'attente = meilleur score. La référence est 48 h.",
            "interpretation": _interp_duration(att, 48, "attente"),
            "delta": _fmt_delta(_delta_abs(att, _vp("attente")), "h"),
        },
        {
            "name": "Séjour à quai", "icon": "⚓", "weight": _SCORE_WEIGHT,
            "raw": _fmt(sq, "h"), "raw_prev": _fmt(_vp("sejour_quai"), "h"),
            "score": subs["Séjour à quai"], "contribution": _contrib("Séjour à quai"),
            "formula": f"100 − ({sq:.1f} / 96) × 100 = {subs['Séjour à quai']:.0f}/100",
            "reference": "96 h",
            "rule": "Plus le séjour à quai est court, meilleure est la rotation et la performance.",
            "interpretation": _interp_duration(sq, 96, "séjour à quai"),
            "delta": _fmt_delta(_delta_abs(sq, _vp("sejour_quai")), "h"),
        },
        {
            "name": "Séjour au port", "icon": "🛳", "weight": _SCORE_WEIGHT,
            "raw": _fmt(sp, "h"), "raw_prev": _fmt(_vp("sejour_port"), "h"),
            "score": subs["Séjour au port"], "contribution": _contrib("Séjour au port"),
            "formula": f"100 − ({sp:.1f} / 144) × 100 = {subs['Séjour au port']:.0f}/100",
            "reference": "144 h",
            "rule": "Plus le séjour global au port est court, meilleure est la fluidité.",
            "interpretation": _interp_duration(sp, 144, "séjour au port"),
            "delta": _fmt_delta(_delta_abs(sp, _vp("sejour_port")), "h"),
        },
        {
            "name": "Évolution trafic", "icon": "📦", "weight": _SCORE_WEIGHT,
            "raw": _fmt(tonn, "t"), "raw_prev": _fmt(tonn_p, "t"),
            "score": subs["Évolution trafic"], "contribution": _contrib("Évolution trafic"),
            "formula": f"50 + ({var_t or 0:+.1f}) = {subs['Évolution trafic']:.0f}/100",
            "reference": "50 = trafic stable",
            "rule": "50 = stable, > 50 = hausse, < 50 = baisse du tonnage vs N-1.",
            "interpretation": (
                "Données N-1 insuffisantes." if var_t is None else
                "Trafic en forte baisse vs N-1." if var_t < -20 else
                "Trafic en baisse vs N-1." if var_t < 0 else
                "Trafic stable vs N-1." if var_t < 5 else
                "Trafic en hausse vs N-1."
            ),
            "delta": _fmt_delta(var_t, "%") if var_t is not None else ("N/D", "neutral"),
        },
        {
            "name": "Évolution escales", "icon": "🚢", "weight": _SCORE_WEIGHT,
            "raw": _fmt(esc, ""), "raw_prev": _fmt(esc_p, ""),
            "score": subs["Évolution escales"], "contribution": _contrib("Évolution escales"),
            "formula": f"50 + ({var_e or 0:+.1f}) = {subs['Évolution escales']:.0f}/100",
            "reference": "50 = activité stable",
            "rule": "50 = stable, > 50 = hausse, < 50 = baisse du nombre d'escales vs N-1.",
            "interpretation": (
                "Données N-1 insuffisantes." if var_e is None else
                "Forte baisse d'activité vs N-1." if var_e < -20 else
                "Activité en baisse vs N-1." if var_e < 0 else
                "Activité stable vs N-1." if var_e < 5 else
                "Activité en hausse vs N-1."
            ),
            "delta": _fmt_delta(var_e, "%") if var_e is not None else ("N/D", "neutral"),
        },
    ]


# ==================================================================
# ALERTES INTELLIGENTES
# ==================================================================
def generate_alerts(kpis: Dict[str, Any], prev_kpis: Dict[str, Any],
                    postes: pd.DataFrame,
                    diagnostics: Optional[List[Dict]] = None) -> List[Dict[str, str]]:
    """Top alertes/priorités calculées automatiquement (section 17)."""
    alerts: List[Dict[str, str]] = []
    for d in (diagnostics or [])[:2]:
        alerts.append({
            "severity": "critique", "icon": "🟠",
            "title": f"Données incohérentes — poste {d['poste']} ({d['taux_calcule_%']:.0f} %)",
            "detail": f"OCCUPATION_DATA_INCONSISTENCY · {d['nb_intervalles']} intervalles, "
                      f"{d['double_comptage_h_detecte']:.1f} h de chevauchement détecté",
            "action": "Vérifier les lignes sources listées dans la vue Occupation."})

    if not postes.empty:
        sat = postes[postes["occupation"] >= 80]
        for _, r in sat.head(3).iterrows():
            alerts.append({"severity": "critique", "icon": "🔴",
                           "title": f"Poste {r['poste']} en début de saturation",
                           "detail": f"Occupation {r['occupation']:.0f}% · {r['diagnostic']}",
                           "action": "Réaffecter les prochaines escales vers les postes moins occupés."})
        slow = postes[(postes["ecart_sejour"].notna()) & (postes["ecart_sejour"] > 20)]
        for _, r in slow.head(2).iterrows():
            alerts.append({"severity": "critique", "icon": "🔴",
                           "title": f"Poste {r['poste']} : séjour anormal",
                           "detail": f"Séjour moyen {r['sejour_moyen']:.1f} h (+{r['ecart_sejour']:.0f}% vs moyenne port)",
                           "action": "Analyser la productivité et le processus opérationnel du poste."})

    var_prod = variation(float(kpis.get("productivite") or 0), float(prev_kpis.get("productivite") or 0))
    if var_prod is not None and var_prod <= -15:
        alerts.append({"severity": "critique", "icon": "🔴",
                       "title": "Productivité en baisse significative",
                       "detail": f"{var_prod:.1f}% vs N-1 ({kpis['productivite']} t/h)",
                       "action": "Identifier les postes et marchandises les moins performants."})
    var_att = variation(float(kpis.get("attente") or 0), float(prev_kpis.get("attente") or 0))
    if var_att is not None and var_att >= 25 and float(kpis.get("attente") or 0) >= 6:
        alerts.append({"severity": "critique", "icon": "🔴",
                       "title": "Attente au mouillage en forte hausse",
                       "detail": f"{kpis['attente']} h en moyenne ({var_att:+.1f}% vs N-1)",
                       "action": "Prioriser les navires déjà en rade et lisser les arrivées."})

    if not postes.empty:
        opt = postes[(postes["occupation"] >= 50) & (postes["occupation"] < 70)]
        if not opt.empty:
            best = opt.sort_values("productivite", ascending=False).iloc[0]
            alerts.append({"severity": "positive", "icon": "🟢",
                           "title": f"Poste {best['poste']} dans la zone optimale",
                           "detail": f"Occupation {best['occupation']:.0f}% · {best['productivite']:.0f} t/h · séjour {best['sejour_moyen']:.1f} h",
                           "action": "Maintenir cette cadence de planification."})
    if var_prod is not None and var_prod >= 15:
        alerts.append({"severity": "positive", "icon": "🟢",
                       "title": "Productivité en hausse",
                       "detail": f"{var_prod:+.1f}% vs N-1 ({kpis['productivite']} t/h)"})
    var_sq = variation(float(kpis.get("sejour_quai") or 0), float(prev_kpis.get("sejour_quai") or 0))
    if var_sq is not None and var_sq <= -10:
        alerts.append({"severity": "positive", "icon": "🟢",
                       "title": "Séjour à quai réduit",
                       "detail": f"{kpis['sejour_quai']} h en moyenne ({var_sq:.1f}% vs N-1)"})

    order = {"critique": 0, "positive": 1}
    alerts.sort(key=lambda a: order[a["severity"]])
    return alerts[:5]


# ==================================================================
# CONTEXTE UNIQUE DU DASHBOARD
# ==================================================================
def build_context(filtered: pd.DataFrame, filters: Dict[str, Any]) -> Dict[str, Any]:
    """Calcule tout le contexte analytique à partir des données filtrées."""
    from components.dashboard.occupation import (
        attach_ship_info, diagnose_inconsistencies, quay_intervals)

    prepared = prepare_operations(filtered)
    start, end, days = resolve_period(filters, prepared)
    p_start, p_end = previous_year_window(start, end)

    cur = slice_period(prepared, start, end)
    prev = slice_period(prepared, p_start, p_end)

    # Couche OCCUPATION INTERVALS (RAW -> NORMALIZED -> intervalles physiques quai)
    changes_cur = fetch_poste_changes(cur["id"].tolist()) if not cur.empty else pd.DataFrame()
    changes_prev = fetch_poste_changes(prev["id"].tolist()) if not prev.empty else pd.DataFrame()
    intervals_cur = quay_intervals(cur, changes_cur) if not cur.empty else pd.DataFrame()
    intervals_prev = quay_intervals(prev, changes_prev) if not prev.empty else pd.DataFrame()
    if not intervals_cur.empty:
        intervals_cur = attach_ship_info(intervals_cur, cur)
    if not intervals_prev.empty:
        intervals_prev = attach_ship_info(intervals_prev, prev)

    segments_cur = load_poste_segments(cur)
    kpis = compute_kpis(cur, segments_cur, days, intervals=intervals_cur)
    segments_prev = load_poste_segments(prev)
    kpis_prev = compute_kpis(prev, segments_prev, days, intervals=intervals_prev)
    variations = compare_kpis(kpis, kpis_prev)
    score_block = compute_composite_score(kpis, variations)
    postes = poste_stats(cur, segments_cur, days, intervals=intervals_cur)
    occ_diagnostics = diagnose_inconsistencies(intervals_cur, days) \
        if not intervals_cur.empty else []
    alerts = generate_alerts(kpis, kpis_prev, postes, diagnostics=occ_diagnostics)

    return {
        "prepared": cur, "prepared_prev": prev, "segments": segments_cur,
        "segments_prev": segments_prev,
        "intervals": intervals_cur, "intervals_prev": intervals_prev,
        "occ_diagnostics": occ_diagnostics,
        "kpis": kpis, "kpis_prev": kpis_prev, "variations": variations,
        "score": score_block, "postes": postes, "alerts": alerts,
        "period": {"start": start, "end": end, "days": days},
        "prev_period": {"start": p_start, "end": p_end},
    }

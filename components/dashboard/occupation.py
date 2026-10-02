# -*- coding: utf-8 -*-
"""Occupation physique réelle des postes à quai.

Pipeline imposé :
    RAW DATA (operations / poste_changes, jamais modifiées)
        ↓ NORMALIZED EVENTS (1 ligne = 1 événement horodaté)
        ↓ OCCUPATION INTERVALS (1 ligne = 1 intervalle physique navire×poste)
        ↓ UNION PAR POSTE (temps réellement occupé, sans double comptage)
        ↓ KPI + DIAGNOSTICS

Règles fondamentales (aucune valeur inventée, aucun plafonnement à 100 %) :
- Un événement n'est PAS une durée de compteur : seule la timeline reconstruite compte.
- L'occupation d'un poste = temps pendant lequel AU MOINS un navire l'occupait
  → union des intervalles de tous les navires SUR CE POSTE UNIQUEMENT.
- Deux postes différents ne sont jamais fusionnés (frontières de changement).
- Un retour sur un même poste reste une période distincte ; les durées s'additionnent
  uniquement si les intervalles sont disjoints.
- Doublons exacts et chevauchements réels même-poste : la couverture temporelle
  est comptée UNE SEULE FOIS (union).
- RADE / postes vides = mouillage : jamais inclus dans l'occupation des quais.
- Taux > 100 % ⇒ diagnostic OCCUPATION_DATA_INCONSISTENCY détaillé, jamais min(t, 100).
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd
import re as _re

#: Postes qui ne sont pas des postes à quai physiques (mouillage / non renseigné)
ANCHORAGE_POSTES = {"RADE", "", "MOUILLAGE", "NAN", "NONE"}

EVENT_MAIN = "principale"
EVENT_CHANGE = "changement"


def format_hhmmss(x) -> str:
    """Normalise tout représentant d'heure (str/time/timedelta/secondes) en HH:MM:SS."""
    from datetime import time as _dtime, timedelta as _tdelta
    if x is None:
        return "00:00:00"
    try:
        if pd.isna(x):
            return "00:00:00"
    except (TypeError, ValueError):
        pass
    if isinstance(x, _tdelta):
        sec = int(x.total_seconds()) % 86400
        return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
    if isinstance(x, _dtime):
        return x.strftime("%H:%M:%S")
    s = str(x).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return "00:00:00"
    if ":" in s and " " in s:          # ex. « 0 days 00:10:00 » (TIME MySQL)
        s = s.split()[-1]
    if ":" not in s:
        try:                            # entier = secondes depuis minuit
            sec = int(float(s)) % 86400
            return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
        except ValueError:
            return "00:00:00"
    return s


def _to_dt(dates: pd.Series, times: pd.Series) -> pd.Series:
    """Datetime depuis colonnes date+heure (heure absente -> 00:00).

    Tolère les types renvoyés par MySQL/MariaDB : datetime.date,
    datetime.time, timedelta, chaînes libres.
    """
    d = pd.to_datetime(dates, errors="coerce").dt.strftime("%Y-%m-%d")
    t = times.map(format_hhmmss) if times is not None else pd.Series(
        ["00:00:00"] * len(d), index=d.index)
    stamp = d + " " + t
    out = pd.to_datetime(stamp, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    loose = out.isna() & d.notna()
    if loose.any():
        out.loc[loose] = pd.to_datetime(stamp[loose], errors="coerce")
    return out


def norm_poste(val) -> str:
    """Normalisation légère et traçable d'un libellé de poste."""
    s = str(val or "").strip().upper()
    return "" if s.upper() in ("NAN", "NONE") else s


def is_quay_poste(poste: str) -> bool:
    """Vrai si le poste est un poste à quai (hors rade/mouillage/non renseigné)."""
    return norm_poste(poste) not in ANCHORAGE_POSTES


#: Postes qui ne sont pas des postes à quai physiques (mouillage / non renseigné)
#: Classement affichage des postes selon l'ordre naturel du quai.

_SUFFIX_RANK = {"": 0, "N": 1, "TER": 2, "BIS": 3, "S": 4}


def poste_sort_key(poste: str):
    """Clé de tri « ordre du quai » : numéro puis suffixe (N, TER, BIS, S).

    Exemple : 1N, 1TER, 1BIS, 1S, 2N, 2TER, 2BIS, 3, 4, 4BIS, 5, …, 9, 10.
    Le tri alphabétique naïf donnerait « 10, 11_12, 13, …, 1BIS, 1N… ».
    """
    s = str(poste or "").strip().upper()
    m = _re.match(r"(\d+)(.*)$", s)
    base = int(m.group(1)) if m else 999999
    suffix = m.group(2).strip() if m else ""
    return (base, _SUFFIX_RANK.get(suffix, 99), suffix)


def poste_order(postes) -> list[str]:
    """Postes triés par ordre naturel du quai (numéro, puis suffixe)."""
    return sorted({norm_poste(p) for p in postes if is_quay_poste(norm_poste(p))},
                  key=poste_sort_key)


def normalize_events(ops: pd.DataFrame, changes: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Couche NORMALIZED : événements horodatés depuis RAW DATA.

    - opération principale : fenêtre Accostage → Appareillage_Quai sur son poste ;
    - chaque changement : sa propre fenêtre Accostage → Appareillage_Quai.
    Les lignes illisibles (dates absentes) sont conservées avec durée nulle
    pour la traçabilité, sans aucune reconstruction inventée.
    """
    frames: List[pd.DataFrame] = []

    def _mk(source_table: str, source_id, escale_key, navire, poste, start, end,
            event_type: str) -> pd.DataFrame:
        n = len(poste)
        return pd.DataFrame({
            "source_table": [source_table] * n,
            "source_id": list(pd.Series(source_id).reset_index(drop=True)),
            "escale_key": list(pd.Series(escale_key).reset_index(drop=True)),
            "navire": list(pd.Series(navire).reset_index(drop=True)),
            "poste": list(pd.Series(poste).reset_index(drop=True)),
            "start": list(pd.Series(start).reset_index(drop=True)),
            "end": list(pd.Series(end).reset_index(drop=True)),
            "type_evenement": [event_type] * n,
        })

    if ops is not None and not ops.empty:
        o = ops
        start = _to_dt(o.get("date_accostage"), o.get("heure_accostage"))
        end = _to_dt(o.get("date_app_quai"), o.get("heure_app_quai"))
        num = o.get("numero_navire")
        num = num.fillna("").astype(str).str.strip() if num is not None else ""
        fallback = (o["navire"].astype(str) + "|" + o["date"].astype(str)
                    + "|" + o["poste"].astype(str))
        frames.append(_mk(
            "operations", o["id"],
            num.where(num != "", fallback),
            o["navire"].astype(str), o["poste"].map(norm_poste), start, end, EVENT_MAIN))

    if changes is not None and not changes.empty:
        c = changes
        escale_col = (c["escale_key"] if "escale_key" in c.columns
                      else pd.Series("", index=c.index))
        nav_col = (c["navire"].astype(str) if "navire" in c.columns
                   else pd.Series("", index=c.index))
        frames.append(_mk(
            "poste_changes", c["id"],
            escale_col, nav_col, c["poste"].map(norm_poste),
            _to_dt(c["date_accostage"], c["heure_accostage"]),
            _to_dt(c["date_app_quai"], c["heure_app_quai"]),
            EVENT_CHANGE))

    if not frames:
        return pd.DataFrame(columns=[
            "source_table", "source_id", "escale_key", "navire",
            "poste", "start", "end", "type_evenement"])
    ev = pd.concat(frames, ignore_index=True)
    ev["valide"] = ev["start"].notna() & ev["end"].notna() & (ev["end"] > ev["start"])
    return ev


def quay_intervals(ops: pd.DataFrame, changes: Optional[pd.DataFrame] = None,
                   include_anchorage: bool = False) -> pd.DataFrame:
    """Couche OCCUPATION INTERVALS : 1 ligne = 1 intervalle physique.

    Par défaut exclut RADE/mouillage/postes vides (occupation des quais).
    `duree_h` est la durée brute de l'événement (0 si illisible) — la déduplication
    n'est pas faite ici mais au niveau de l'union par poste.
    """
    ev = normalize_events(ops, changes)
    if not include_anchorage:
        ev = ev[ev["poste"].map(is_quay_poste)]
    iv = ev.copy()
    iv["duree_h"] = 0.0
    ok = iv["valide"]
    iv.loc[ok, "duree_h"] = (
        (iv.loc[ok, "end"] - iv.loc[ok, "start"]).dt.total_seconds() / 3600)
    return iv.reset_index(drop=True)


def attach_ship_info(intervals: pd.DataFrame, ops: pd.DataFrame) -> pd.DataFrame:
    """Complète escale_key/navire des changements via leur opération principale."""
    if intervals.empty or ops is None or ops.empty:
        return intervals
    num = ops.get("numero_navire")
    num = num.fillna("").astype(str).str.strip() if num is not None else ""
    fallback = (ops["navire"].astype(str) + "|" + ops["date"].astype(str)
                + "|" + ops["poste"].astype(str))
    info = pd.DataFrame({
        "id": ops["id"],
        "escale_key": num.where(num != "", fallback),
        "navire": ops["navire"].astype(str),
    })
    mask = intervals["source_table"] == "poste_changes"
    if mask.any():
        m = intervals.loc[mask, ["source_id"]].merge(info, left_on="source_id",
                                                    right_on="id", how="left")
        intervals = intervals.copy()
        intervals.loc[mask, "escale_key"] = m["escale_key"].values
    return intervals


# ==================================================================
# GÉOMÉTRIE TEMPORELLE (union, chevauchements, frontières)
# ==================================================================
def merge_union(spans: List[Tuple[pd.Timestamp, pd.Timestamp]]
                ) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """Union d'intervalles fermés-chevauchants : couverture comptée une seule fois."""
    valid = sorted((s, e) for s, e in spans if s is not None and e is not None and e > s)
    out: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    for s, e in valid:
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def _overlap(spans: List[Tuple[pd.Timestamp, pd.Timestamp]],
             s: pd.Timestamp, e: pd.Timestamp) -> float:
    """Heures de (s,e) déjà couvertes par l'union de `spans`."""
    tot = 0.0
    for cs, ce in merge_union(list(spans)):
        lo, hi = max(cs, s), min(ce, e)
        if hi > lo:
            tot += (hi - lo).total_seconds() / 3600
    return tot


def split_by_month(iv: pd.DataFrame) -> pd.DataFrame:
    """Explose les intervalles aux frontières de mois calendaires.

    Sortie : 1 ligne par (intervalle × mois traversé), colonnes year/month/start/end.
    """
    rows = []
    for _, r in iv.iterrows():
        if not r["valide"]:
            continue
        cur = r["start"]
        while cur < r["end"]:
            nxt = (cur + pd.offsets.MonthBegin(1)).normalize()
            piece_end = min(r["end"], nxt)
            rows.append({"poste": r["poste"], "navire": r["navire"],
                         "escale_key": r["escale_key"], "type_evenement": r["type_evenement"],
                         "year": cur.year, "month": cur.month,
                         "start": cur, "end": piece_end})
            cur = piece_end
    cols = ["poste", "navire", "escale_key", "type_evenement", "year", "month", "start", "end"]
    return pd.DataFrame(rows, columns=cols)


# ==================================================================
# KPI D'OCCUPATION
# ==================================================================
def occupation_per_poste(intervals: pd.DataFrame,
                         period_start=None, period_end=None) -> pd.DataFrame:
    """Temps RÉELLEMENT occupé par poste (union tous navires) sur la période.

    Retourne : poste, duree_occupee_h, nb_intervalles, nb_navires, conflits.
    Les intervalles sont intersectés avec [period_start, period_end] si fournis.
    """
    cols = ["poste", "duree_occupee_h", "nb_intervalles", "nb_navires", "conflits"]
    if intervals is None or intervals.empty:
        return pd.DataFrame(columns=cols)

    per_poste: Dict[str, List] = {}
    meta: Dict[str, dict] = {}
    clip_start = pd.Timestamp(period_start) if period_start is not None else None
    clip_end = pd.Timestamp(period_end) if period_end is not None else None
    clip = clip_start is not None or clip_end is not None
    for row in intervals.itertuples(index=False):
        if clip:
            s, e = row.start, row.end
            if clip_start is not None:
                s = max(s, clip_start)
            if clip_end is not None:
                e = min(e, clip_end)
            span = (s, e) if e > s else None
        else:
            span = (row.start, row.end)
        if span is None:
            continue
        p = row.poste
        per_poste.setdefault(p, []).append(span)
        m = meta.setdefault(p, {"iv": 0, "ships": set(), "spans_by_ship": {}})
        m["iv"] += 1
        m["ships"].add(str(row.navire))
        m["spans_by_ship"].setdefault(str(row.navire), []).append(span)

    rows = []
    for p, spans in per_poste.items():
        m = meta[p]
        union_dur = sum((e - s).total_seconds() / 3600 for s, e in merge_union(spans))
        ships = m["ships"]
        conflits = 0
        if len(ships) > 1:
            ship_spans = {sh: merge_union(sl) for sh, sl in m["spans_by_ship"].items()}
            names = sorted(ship_spans)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    for sa, ea in ship_spans[a]:
                        for sb, eb in ship_spans[b]:
                            if min(ea, eb) > max(sa, sb):
                                conflits += 1
        rows.append({"poste": p, "duree_occupee_h": round(union_dur, 3),
                     "nb_intervalles": m["iv"], "nb_navires": len(ships),
                     "conflits": conflits})
    return pd.DataFrame(rows, columns=cols).sort_values("poste").reset_index(drop=True)


def occupation_taux(intervals: pd.DataFrame, days: int,
                    period_start=None, period_end=None) -> pd.DataFrame:
    """Taux d'occupation (%) par poste = occupé ÷ disponible × 100.

    AUCUN plafonnement : un taux > 100 doit déclencher le diagnostic.
    """
    occ = occupation_per_poste(intervals, period_start, period_end)
    occ["taux_%"] = occ["duree_occupee_h"] / max(days, 1) / 24 * 100
    return occ


def monthly_occupancy(intervals: pd.DataFrame) -> pd.DataFrame:
    """Taux mensuel par poste : union par (poste, année, mois) ÷ heures réelles du mois."""
    import calendar
    pieces = split_by_month(intervals)
    if pieces.empty:
        return pd.DataFrame(columns=["poste", "year", "month", "duree_h", "heures_dispo", "taux_%"])
    out = []
    for (p, y, m), g in pieces.groupby(["poste", "year", "month"]):
        spans = list(zip(g["start"], g["end"]))
        dur = sum((e - s).total_seconds() / 3600 for s, e in merge_union(spans))
        hours = calendar.monthrange(int(y), int(m))[1] * 24
        out.append({"poste": p, "year": int(y), "month": int(m),
                    "duree_h": round(dur, 3), "heures_dispo": hours,
                    "taux_%": dur / hours * 100})
    return pd.DataFrame(out)


# ==================================================================
# DIAGNOSTIC D'INCOHÉRENCE (>100 %) — JAMAIS DE PLAFONNEMENT
# ==================================================================
def diagnose_inconsistencies(intervals: pd.DataFrame, days: int,
                             taux_df: Optional[pd.DataFrame] = None) -> List[Dict]:
    """Rapport OCCUPATION_DATA_INCONSISTENCY pour tout poste dont le taux > 100 %.

    Identifie poste, période, intervalles responsables (navire, début, fin,
    source), chevauchements détectés et durée double-comptée. Ne corrige rien.
    """
    if intervals is None or intervals.empty:
        return []
    if taux_df is None:
        taux_df = occupation_taux(intervals, days)
    report: List[Dict] = []
    for _, r in taux_df[taux_df["taux_%"] > 100].iterrows():
        poste = r["poste"]
        sub = intervals[intervals["poste"] == poste].copy()
        spans_by_ship: Dict[str, List] = {}
        for _, ivr in sub.iterrows():
            spans_by_ship.setdefault(str(ivr["navire"]), []).append((ivr["start"], ivr["end"]))
        union_dur = sum((e - s).total_seconds() / 3600
                        for s, e in merge_union([sp for sl in spans_by_ship.values()
                                                 for sp in sl]))
        brut = float(sub["duree_h"].sum())
        chev: List[Dict] = []
        recs = sub.sort_values("start")
        lst = list(recs.itertuples(index=False))
        for i, a in enumerate(lst):
            for b in lst[i + 1:]:
                lo, hi = max(a.start, b.start), min(a.end, b.end)
                if hi > lo:
                    chev.append({
                        "navire_a": str(a.navire), "navire_b": str(b.navire),
                        "debut": str(lo), "fin": str(hi),
                        "heures_chevauche_es": round((hi - lo).total_seconds() / 3600, 2),
                        "sources": f"{a.source_table}#{a.source_id} / "
                                   f"{b.source_table}#{b.source_id}",
                    })
        report.append({
            "code": "OCCUPATION_DATA_INCONSISTENCY",
            "poste": poste,
            "taux_calcule_%": round(float(r["taux_%"]), 2),
            "heures_dispo_periode": round(max(days, 1) * 24, 1),
            "duree_union_h": round(union_dur, 2),
            "duree_brute_sommee_h": round(brut, 2),
            "double_comptage_h_detecte": round(max(brut - union_dur, 0.0), 2),
            "nb_intervalles": int(len(sub)),
            "intervalles": [
                {"navire": str(x.navire), "debut": str(x.start), "fin": str(x.end),
                 "duree_h": round(float(x.duree_h), 2),
                 "source": f"{x.source_table}#{x.source_id}"}
                for x in lst],
            "chevauchements": chev[:50],
        })
    return report

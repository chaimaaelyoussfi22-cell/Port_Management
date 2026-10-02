# -*- coding: utf-8 -*-
"""Filtrage des données du dashboard (période + dimensions)."""

from datetime import date, timedelta

import pandas as pd


def apply_filters(operations: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Applique période, poste, opérateur, marchandise, type navire et trafic."""
    frame = operations.copy()
    if frame.empty:
        return frame
    d = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame[d.notna()].copy()
    frame["date"] = d[frame.index].dt.date

    start, end = filters.get("start"), filters.get("end")
    today = date.today()
    period = filters.get("period", "Toutes les données")
    if period == "Aujourd’hui":
        start = end = today
    elif period == "Cette semaine":
        start, end = today - timedelta(days=today.weekday()), today
    elif period == "Ce mois":
        start, end = today.replace(day=1), today
    elif period == "Cette année":
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    if start:
        frame = frame[frame["date"] >= start]
    if end:
        frame = frame[frame["date"] <= end]

    columns = {"poste": "poste", "operateur": "operateur",
               "marchandise": "type_marchandise", "type_navire": "type_navire"}
    for key, column in columns.items():
        value = filters.get(key)
        if value and not str(value).startswith(("Tous", "Toutes")) and column in frame:
            frame = frame[frame[column].fillna("").astype(str) == value]

    trafic = filters.get("type_trafic")
    if trafic and trafic != "Tous types" and "type_operation" in frame:
        frame = frame[frame["type_operation"].fillna("").astype(str).str.lower().str.startswith(trafic.lower()[:4])]

    return frame


def apply_auxiliary_filters(frame: pd.DataFrame, filters: dict,
                            date_column: str, poste_column: str = "poste") -> pd.DataFrame:
    """Périmètre temporel + poste pour les tables auxiliaires."""
    if frame is None or frame.empty:
        return frame if frame is not None else pd.DataFrame()
    result = frame.copy()
    if date_column in result:
        result[date_column] = pd.to_datetime(result[date_column], errors="coerce").dt.date
        start, end = filters.get("start"), filters.get("end")
        if start:
            result = result[result[date_column] >= start]
        if end:
            result = result[result[date_column] <= end]
    poste = filters.get("poste")
    if poste and poste != "Tous les postes" and poste_column in result:
        result = result[result[poste_column].fillna("").astype(str) == poste]
    return result


def calculate_kpis(*_args, **_kwargs):  # compat ascendante — remplacé par analytics.compute_kpis
    from components.dashboard.analytics import compute_kpis  # pragma: no cover
    raise NotImplementedError("Utiliser analytics.build_context()")


def calculate_postes(*_args, **_kwargs):
    raise NotImplementedError("Utiliser analytics.build_context()")

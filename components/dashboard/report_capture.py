# -*- coding: utf-8 -*-
"""Capture d'éléments du dashboard pour le rapport (« Ma sélection »).

PERMET d'ajouter n'importe quelle visualisation du dashboard (graphique Plotly,
carte KPI, tableau, section) à un rapport en cours de construction, puis de
l'exporter.

Chaque élément ajouté mémorise :
  - son titre et sa section d'origine ;
  - les filtres / période appliqués au moment de l'ajout (texte descriptif) ;
  - la figure Plotly réelle (sérialisée en JSON) — si applicable ;
  - la donnée associée réelle (DataFrame) — pour export Excel/CSV.

Aucune donnée artificielle : tout provient du contexte du dashboard.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


# ==================================================================
# ACCÈS AU PANIER (session_state)
# ==================================================================
KEY = "report_items"

_ITEM_KEYS = ("id", "title", "section", "filter_text", "fig_json",
              "data", "added_at", "kind", "uid")


def cart_has_uid(uid: str) -> bool:
    """Vrai si un élément possède déjà cet identifiant logique (anti-doublon)."""
    return any(i.get("uid") == uid for i in cart_items())


def _new_id() -> str:
    return f"rp_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{np.random.randint(0, 99999)}"


def cart_items() -> list[dict]:
    import streamlit as st
    items = st.session_state.get(KEY)
    if items is None:
        items = st.session_state.setdefault(KEY, [])
    return items


def cart_count() -> int:
    return len(cart_items())


def clear_cart():
    import streamlit as st
    st.session_state[KEY] = []


def remove_item(item_id: str):
    import streamlit as st
    st.session_state[KEY] = [i for i in cart_items()
                             if i.get("id") != item_id]


def move_item(item_id: str, direction: int):
    """Réordonne un élément dans le panier (direction = -1 monter, +1 descendre)."""
    import streamlit as st
    items = cart_items()
    idx = next((i for i, it in enumerate(items) if it.get("id") == item_id), None)
    if idx is None:
        return
    target = idx + direction
    if target < 0 or target >= len(items):
        return
    items[idx], items[target] = items[target], items[idx]
    st.session_state[KEY] = items


def _store_dataframe(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """DataFrame copié et allégé (aucune colonne d'objet lourd)."""
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return None
    return df.copy(deep=True) if isinstance(df, pd.DataFrame) else None


def add_item(*, title: str, section: str, filter_text: str = "",
             fig=None, data: pd.DataFrame | None = None,
             kind: str = "figure", uid: str = "") -> str:
    """Ajoute un élément au panier et renvoie son id."""
    if uid and cart_has_uid(uid):
        return ""
    fig_json = _fig_to_json(fig) if fig is not None else None
    item = {
        "id": _new_id(),
        "title": str(title),
        "section": str(section),
        "filter_text": str(filter_text),
        "fig_json": fig_json,
        "data": _store_dataframe(data),
        "added_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "kind": kind,
        "uid": uid,
    }
    cart_items().append(item)
    return item["id"]


def add_figure(title: str, section: str, fig, data: pd.DataFrame | None = None,
               filter_text: str = "", kind: str = "figure",
               uid: str = "") -> str:
    return add_item(title=title, section=section, filter_text=filter_text,
                    fig=fig, data=data, kind=kind, uid=uid)


def add_table(title: str, section: str, data: pd.DataFrame | None,
              filter_text: str = "", kind: str = "table",
              uid: str = "") -> str:
    return add_item(title=title, section=section, filter_text=filter_text,
                    data=data, kind=kind, uid=uid)


# ==================================================================
# SÉRIALISATION (figure Plotly ↔ JSON, dataframe ↔ CSV)
# ==================================================================
def _fig_to_json(fig) -> str | None:
    try:
        return fig.to_json()
    except Exception:
        return None


def json_to_fig(s: str | None):
    if not s:
        return None
    try:
        import plotly.io as pio
        return pio.from_json(s)
    except Exception:
        return None


def df_to_csv(df: pd.DataFrame | None) -> str | None:
    if df is None or df.empty:
        return None
    return df.to_csv(index=False)


# ==================================================================
# IMAGE PNG d'un graphique (rendu réel via kaleido)
# ==================================================================
def fig_to_png_bytes(fig, width: int = 900, height: int = 450,
                     scale: float = 2.0) -> bytes | None:
    """Rendu PNG de la figure (rendu réel, aucune donnée artificielle)."""
    if fig is None:
        return None
    try:
        import plotly.io as pio
        return pio.to_image(fig, format="png", width=width, height=height,
                            scale=scale)
    except Exception:
        return None


def item_png(item: dict, width: int = 900, height: int = 450) -> bytes | None:
    if not item.get("fig_json"):
        return None
    return fig_to_png_bytes(json_to_fig(item["fig_json"]), width, height)


# ==================================================================
# EXPORT DONNÉES (CSV / Excel) D'UN ÉLÉMENT
# ==================================================================
def item_csv_bytes(item: dict) -> bytes | None:
    df = item.get("data")
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return None
    return df.to_csv(index=False).encode("utf-8-sig")


def item_excel_bytes(item: dict) -> bytes | None:
    df = item.get("data")
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return None
    try:
        from xlsxwriter import Workbook
        from io import BytesIO
        buf = BytesIO()
        wb = Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Données")
        fmt_h = wb.add_format({"bold": True, "font_color": "#FFFFFF",
                               "bg_color": "#0B315A", "border": 1})
        for j, col in enumerate(df.columns):
            ws.write(0, j, str(col), fmt_h)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            for j, val in enumerate(row):
                if isinstance(val, (float, np.floating)):
                    v = float(val)
                    ws.write(i, j, "n/d" if (np.isnan(v) or np.isinf(v)) else v)
                elif isinstance(val, (int, np.integer, np.bool_)):
                    ws.write(i, j, int(val))
                else:
                    ws.write(i, j, str(val))
        wb.close()
        return buf.getvalue()
    except Exception:
        return None


# ==================================================================
# EXPORTS GLOBAUX DU PANIER (ensemble d'éléments)
# ==================================================================
def cart_excel_bytes(items: list[dict], generated: str = "") -> bytes:
    """Un classeur Excel : une feuille par élément ajouté + feuille Synthèse."""
    from xlsxwriter import Workbook
    from io import BytesIO
    buf = BytesIO()
    wb = Workbook(buf, {"in_memory": True})
    fmt_head = wb.add_format({"bold": True, "font_color": "#FFFFFF",
                              "bg_color": "#0B315A", "border": 1, "align": "center"})
    fmt_txt = wb.add_format({"border": 1})
    fmt_num = wb.add_format({"num_format": "#,##0.00", "border": 1})

    def _sheet(name: str, df: pd.DataFrame | None):
        safe = _sanitize_sheet(name)
        ws = wb.add_worksheet(safe[:31] or "Feuille")
        if df is None or df.empty:
            ws.write(0, 0, "Aucune donnée.", fmt_txt)
            return
        for j, col in enumerate(df.columns):
            ws.write(0, j, str(col), fmt_head)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            for j, val in enumerate(row):
                if isinstance(val, (float, np.floating)):
                    v = float(val)
                    ws.write(i, j, "n/d" if (np.isnan(v) or np.isinf(v)) else v, fmt_num)
                elif isinstance(val, (int, np.integer, np.bool_)):
                    ws.write(i, j, int(val), fmt_txt)
                else:
                    ws.write(i, j, str(val), fmt_txt)

    # --- Feuille Synthèse ---
    ws = wb.add_worksheet("Synthèse")
    lines = ["SMART PORT — RAPPORT DU DASHBOARD (MA SÉLECTION)",
             "Port Jorf Lasfar · ANP",
             f"Généré le : {generated or datetime.now().strftime('%d/%m/%Y %H:%M')}",
             "", f"Nombre d'éléments : {len(items)}", ""]
    for i, l in enumerate(lines):
        ws.write(i, 0, l, fmt_head if i == 0 else fmt_txt)
    base = len(lines) + 1
    if items:
        for i, it in enumerate(items):
            ws.write(base + i, 0, f"• {it.get('section','')} — {it.get('title','')}", fmt_txt)
            ws.write(base + i, 1, it.get("filter_text", ""), fmt_txt)

    # --- Une feuille par élément ---
    for it in items:
        _sheet(it.get("title", "Élément"), it.get("data"))

    wb.close()
    return buf.getvalue()


def _sanitize_sheet(name: str) -> str:
    import re
    s = re.sub(r"[\[\]:*?/\\]", "_", str(name))
    return (s[:31]) or "Feuille"


def cart_pdf_bytes(items: list[dict], generated: str = "") -> bytes:
    """PDF professionnel : chaque élément ajouté = image PNG (si graphique)
    + tableau de la donnée associée. Mise en page type Power BI."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    from io import BytesIO

    NAVY = colors.HexColor("#0B315A")
    BLUE = colors.HexColor("#1c8ccd")
    GREY = colors.HexColor("#5a6b7d")

    def _st(name, sz, col, leading=None):
        return ParagraphStyle(name=name, fontSize=sz,
                              textColor=col if col is not None else colors.black,
                              leading=leading or sz + 4)

    s_brand = _st("brand", 13, NAVY, 16)
    s_date = _st("date", 8, GREY, 10)
    s_h1 = _st("h1", 16, NAVY, 20)
    s_h2 = _st("h2", 12, NAVY, 15)
    s_body = _st("body", 9, None, 13)
    s_muted = _st("muted", 8, GREY, 10)

    story = []
    brand = Table(
        [[Paragraph("<b>ANP — PORT JORF LASFAR</b><br/>"
                    "Rapport du dashboard · Ma sélection", s_brand),
          Paragraph(f"Généré le : {generated or datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    s_date)]],
        colWidths=[120 * mm, 82 * mm])
    brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLUE),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(brand)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"Rapport composé de <b>{len(items)}</b> élément(s) du dashboard", s_h1))
    story.append(Spacer(1, 4 * mm))

    for idx, it in enumerate(items, start=1):
        story.append(Paragraph(
            f"{idx}. {it.get('title', 'Élément')}",
            s_h2))
        story.append(Paragraph(it.get("section", ""), s_muted))
        if it.get("filter_text"):
            story.append(Paragraph(f"<b>Filtres :</b> {it['filter_text']}", s_muted))
        story.append(Spacer(1, 2 * mm))

        png = item_png(it)
        if png:
            try:
                from reportlab.lib.utils import ImageReader
                from io import BytesIO as _BIO
                img = ImageReader(_BIO(png))
                iw, ih = img.getSize()
                avail = 180 * mm
                ratio = min(1.0, avail / iw)
                story.append(Image(_BIO(png), width=iw * ratio, height=ih * ratio))
                story.append(Spacer(1, 3 * mm))
            except Exception:
                pass

        df = it.get("data")
        if df is not None and not (isinstance(df, pd.DataFrame) and df.empty):
            cols = df.columns.tolist()
            widths = [max(14, min(44, 180 / max(len(cols), 1))) * mm
                      for _ in cols]
            data = [[str(c) for c in cols]]
            for r in df.head(25).itertuples(index=False):
                data.append(["" if pd.isna(v) else str(v) for v in r])
            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bcd6ef")),
            ]))
            story.append(t)
        story.append(Spacer(1, 5 * mm))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(
            A4[0] / 2, 8 * mm,
            "Document généré automatiquement — Port Analytics Studio · ANP")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"p. {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm,
                            rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


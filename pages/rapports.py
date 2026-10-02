# -*- coding: utf-8 -*-
"""🎯 RAPPORT DU DASHBOARD — Page unique / catalogue interactif.

La page RAPPORT est un « Dashboard personnalisé » :
  1. 8 filtres globaux (Année, Mois, Poste, Type navire, Navire, Opérateur,
     Marchandise, Type opération) → 📄 GÉNÉRER.
  2. 12 cartes/KPI cliquables (exactes du Dashboard) servent de catalogue.
  3. Clic sur une carte → titres + cases à cocher de SES visualisations réelles
     (aucun graphique rendu avant sélection).
  4. ➕ AJOUTER AU RAPPORT → les visualisations cochées (sans doublons).
  5. 📑 ÉLÉMENTS DU RAPPORT → ordonner/supprimer.
  6. 📄 RAPPORT FINAL → rend UNIQUEMENT les visualisations sélectionnées,
     dans leur ordre → exports PDF / Excel / CSV / PNG.

TOUTE la logique provient du Dashboard (build_context + builders réels) :
aucune donnée fictive, aucune logique recalculée ailleurs.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from database import db_manager
from components.dashboard import report_capture as rc
from components.dashboard import rapport_views as rv
from components.dashboard import report_dashboard as rd
from components.dashboard import kpi_cards
from components.dashboard.analytics import build_context
from components.dashboard.helpers import apply_filters

_MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
         "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
_ALL_YEARS = "Toutes les années"
_ALL_MOIS = "Tous les mois"


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except OSError:
            pass


def _stamp():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _hero():
    st.markdown(
        '<div class="an-card rp-hero"><div class="rp-hero-title">🎯 RAPPORT DU '
        'DASHBOARD — Dashboard personnalisé / catalogue interactif</div>'
        '<div class="rp-hero-sub">Choisissez vos filtres → GÉNÉRER → composez un '
        'rapport à partir des 12 cartes du Dashboard · exports PDF / Excel / CSV / '
        'PNG · calculs 100 % alignés (aucune donnée inventée)</div></div>',
        unsafe_allow_html=True)


def _fmt_int(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


# ==================================================================
# FILTRES GLOBAUX
# ==================================================================
def _render_filters(ops: pd.DataFrame) -> dict:
    choices = rv.choices(ops)
    postes = ["Tous les postes"] + choices["postes"]
    navires = ["Tous"] + choices["navires"]
    marchandises = ["Toutes"] + choices["marchandises"]
    types_nav = ["Tous"] + choices.get("type_navires", [])
    operateurs = ["Tous"] + choices.get("operateurs", [])

    rep: dict = {}
    st.markdown("#### 🔎 FILTRES GLOBAUX DU RAPPORT")
    st.caption("Les filtres sont appliqués aux données AVANT le calcul des KPI "
               "et des graphiques (source unique : le Dashboard).")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        rep["year"] = st.selectbox("🗓️ Année", [_ALL_YEARS] + choices["years"],
                                   key="rds_year")
    with c2:
        months_sel = st.multiselect(
            "📅 Mois", list(range(1, 13)),
            format_func=lambda m: _MOIS[m - 1],
            placeholder="Tous les mois", key="rds_months")
        rep["months"] = months_sel
    with c3:
        rep["poste"] = st.selectbox("⚓ Poste", postes, key="rds_poste")
    with c4:
        rep["type_navire"] = st.selectbox("🚢 Type navire", types_nav,
                                          key="rds_tn")
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        rep["navire"] = st.selectbox("Navire", navires, key="rds_navire")
    with c6:
        rep["operateur"] = st.selectbox("🏢 Opérateur", operateurs, key="rds_op")
    with c7:
        rep["marchandise"] = st.selectbox("📦 Marchandise", marchandises,
                                          key="rds_mc")
    with c8:
        rep["type_trafic"] = st.selectbox(
            "↔ Type opération", ["Tous types", "Import", "Export", "Cabotage"],
            key="rds_tt")
    return rep


# ==================================================================
# CONSTRUCTION DU CONTEXTE (source Dashboard)
# ==================================================================
def _build_res(ops, consig, inc, rep) -> dict:
    """Construit le contexte réel filtré (aucune donnée inventée)."""
    all_years = rep.get("year") == _ALL_YEARS
    months = list(rep.get("months") or [])

    if all_years:
        start = end = None
        period = "Toutes les données"
    else:
        start, end = rv.period_bounds(int(rep["year"]), months)
        period = "Période rapport"

    filters = {
        "period": period, "start": start, "end": end,
        "poste": rep.get("poste"), "operateur": rep.get("operateur"),
        "marchandise": rep.get("marchandise"),
        "type_navire": rep.get("type_navire"),
        "type_trafic": rep.get("type_trafic"),
    }
    filtered = apply_filters(ops, filters)

    if filtered.empty:
        return {"error": "Aucune donnée ne correspond aux filtres sélectionnés."}

    ctx = build_context(filtered, filters)
    prepared = ctx["prepared"]
    if prepared.empty:
        return {"error": "Aucune donnée exploitable pour les filtres choisis."}

    if all_years:
        year = int(prepared["year"].max())
    else:
        year = int(rep["year"])

    res = rd.Res(ctx=ctx, prepared=prepared, year=year, months=months,
                 consig=consig, incidents=inc,
                 filter_text=rv.period_label(start, end) if start else "Toutes les données")
    return {"res": res, "rep": rep, "generated": _stamp(), "filtered": filtered}


# ==================================================================
# CACHE DE PERFORMANCE (réutilise le contexte déjà filtré)
# ==================================================================
@st.cache_data(ttl=600, show_spinner=False)
def _load_ops():
    """Opérations brutes (lecture DB unique, mise en cache 10 min)."""
    return db_manager.get_operations()


@st.cache_data(ttl=600, show_spinner=False)
def _load_aux():
    """Tables auxiliaires préparées (consignations + incidents hors consignation).

    Chargées une seule fois puis mises en cache : évite de relire la base à
    chaque clic (GÉNÉRER / carte / AJOUTER / réordonner / exporter).
    """
    return (rd.prepare_consig(limit=100000),
            rd.prepare_incidents(limit=200000))


def _rep_key(rep: dict) -> tuple:
    return (rep["year"], tuple(rep["months"] or []), rep["poste"],
            rep["type_navire"], rep["navire"], rep["operateur"],
            rep["marchandise"], rep["type_trafic"])


@st.cache_resource(ttl=600, show_spinner=False)
def _build_res_cached(ops, consig, incidents, key: tuple) -> dict:
    """Contexte réel filtré, mis en cache par tuple de filtres.

    GÉNÉRER ne calcule ici QUE les 12 KPI (build_context) — jamais les
    graphiques. Les cartes restantes ne sont calculées qu'au clic, à la
    sélection. Un même jeu de filtres ne recalcule jamais deux fois.
    """
    rep = {"year": key[0], "months": list(key[1]), "poste": key[2],
           "type_navire": key[3], "navire": key[4], "operateur": key[5],
           "marchandise": key[6], "type_trafic": key[7]}
    return _build_res(ops, consig, incidents, rep)


# ==================================================================
# VALEUR KPI D'UNE CARTE (mêmes règles que le Dashboard kpi_cards)
# ==================================================================
def _card_kpi(res, key):
    ctx = res.ctx
    if key in ("consignation", "consignation_evo"):
        from components.dashboard.kpi_cards import _consignation_card
        value_txt, var, _spark = _consignation_card(key)
        return value_txt, var
    if key == "incidents":
        from components.dashboard.kpi_cards import _incidents_card
        value_txt, var, _spark = _incidents_card()
        return value_txt, var
    variations = ctx["variations"]
    if key == "evolution_trafic":
        var = variations.get("tonnage")
        value = f"{var:+.1f} %".replace(".", ",") if var is not None else "—"
        return value, var
    src, mode = kpi_cards._VALUE_MODE[key]
    from components.dashboard.performance_score import _fmt
    value = _fmt(ctx["kpis"].get(src), mode)
    return value, variations.get(key)


# ==================================================================
# RENDU DES 12 CARTES (catalogue cliquable)
# ==================================================================
def _render_cards(res):
    st.markdown("#### 🗂️ CATALOGUE — 12 CARTES DU DASHBOARD")
    st.caption("Cliquez sur une carte pour voir et sélectionner SES visualisations. "
               "Aucun graphique n'est rendu avant la sélection.")
    from components.dashboard.kpi_cards import DIMENSIONS, _HIGHER_POSITIVE
    from components.dashboard.performance_score import _variation_chip

    cols = st.columns(3, gap="small")
    for idx, dim in enumerate(DIMENSIONS):
        key = dim["key"]
        value_txt, var = _card_kpi(res, key)
        chip = _variation_chip(var, _HIGHER_POSITIVE.get(key))
        with cols[idx % 3]:
            active = st.session_state.get("rds_active") == key
            border = "#1c8ccd" if active else "rgba(140,207,255,.25)"
            st.markdown(
                f'<div class="ops-card" style="border:1.5px solid {border}">'
                f'<span>{dim["title"]}</span>'
                f'<div class="tile-icon">{dim["icon"]}</div>'
                f'<div class="ops-card-body"><div>'
                f'<small>PÉRIODE FILTRÉE</small><strong>{value_txt}</strong> {chip}'
                f'</div></div></div>', unsafe_allow_html=True)
            if st.button(f"Ouvrir · {len(rd.visuals_for_card(key))} graphique(s)",
                         key=f"rds_open_{key}", use_container_width=True):
                st.session_state["rds_active"] = key
                st.rerun()


# ==================================================================
# VISUALISATIONS D'UNE CARTE (titres + cases à cocher, pas de figures)
# ==================================================================
def _render_card_visuals(res):
    key = st.session_state.get("rds_active")
    if not key or key not in rd.CARD_VISUALS:
        return
    dim = next((d for d in kpi_cards.DIMENSIONS if d["key"] == key), {})
    st.markdown(f"###### {dim.get('icon','')} {dim.get('title')}")
    st.markdown("Sélectionnez les visualisations à ajouter, puis cliquez sur "
                "➕ AJOUTER AU RAPPORT.")
    visuals = rd.visuals_for_card(key)
    selected = set(st.session_state.get(f"rds_sel_{key}", []))
    for spec in visuals:
        checked = st.checkbox(spec["title"], key=f"rds_cb_{spec['vid']}",
                              value=spec["vid"] in selected)
        if checked:
            selected.add(spec["vid"])
        else:
            selected.discard(spec["vid"])
    st.session_state[f"rds_sel_{key}"] = sorted(selected)

    col_a, col_b = st.columns([1, 4])
    with col_a:
        if st.button("➕ AJOUTER AU RAPPORT", type="primary",
                     use_container_width=True):
            _add_selected_to_cart(res, key)
            st.rerun()
    with col_b:
        if st.button("Fermer cette carte", use_container_width=True):
            st.session_state["rds_active"] = None
            st.rerun()


def _add_selected_to_cart(res, card_key):
    selected = st.session_state.get(f"rds_sel_{card_key}", [])
    dim = next((d for d in kpi_cards.DIMENSIONS if d["key"] == card_key), {})
    section = f"{dim.get('icon','')} {dim.get('title','')}".strip()
    added = 0
    for spec in rd.CARD_VISUALS.get(card_key, []):
        vid = spec["vid"]
        if vid not in selected:
            continue
        if rc.cart_has_uid(f"{card_key}::{vid}"):
            continue
        try:
            fig, data = spec["builder"](res)
        except Exception:
            fig, data = None, None
        if fig is None and data is None:
            st.warning(f"Pas de données pour « {spec['title']} » sur cette "
                       f"sélection (élément ignoré).")
            continue
        title = spec["title"]
        uid = f"{card_key}::{vid}"
        rc.add_figure(title, section, fig, data, filter_text=res.filter_text,
                      uid=uid)
        added += 1
    st.session_state[f"rds_sel_{card_key}"] = []
    if added:
        st.success(f"{added} visualisation(s) ajoutée(s) au rapport.")
    else:
        st.info("Tout est déjà ajouté ou aucune sélection.")


# ==================================================================
# ÉLÉMENTS DU RAPPORT (ordonner / supprimer)
# ==================================================================
def _render_cart(rep_text: str, generated: str):
    items = rc.cart_items()
    st.markdown(f"#### 📑 ÉLÉMENTS DU RAPPORT "
                f"<span style='color:#1c8ccd'>({len(items)})</span>",
                unsafe_allow_html=True)
    if not items:
        st.info("Aucun élément ajouté pour l'instant — choisissez une carte puis "
                "AJOUTER AU RAPPORT.")
        return
    st.caption("Ordre = ordre d'apparition dans le rapport final. Utilisez ↑ ↓ pour "
               "réordonner et 🗑 pour supprimer.")
    for idx, it in enumerate(items):
        c_up, c_title, c_dn, c_rm = st.columns([0.7, 6, 0.7, 0.9])
        with c_up:
            if st.button("↑", key=f"rdup_{it['id']}", disabled=idx == 0,
                         use_container_width=True):
                rc.move_item(it["id"], -1)
                st.rerun()
        with c_title:
            st.markdown(f"**{it.get('section','')}** — {it.get('title','')}")
            if it.get("filter_text"):
                st.caption(it["filter_text"])
        with c_dn:
            if st.button("↓", key=f"rddn_{it['id']}",
                         disabled=idx == len(items) - 1,
                         use_container_width=True):
                rc.move_item(it["id"], 1)
                st.rerun()
        with c_rm:
            if st.button("🗑", key=f"rdrm_{it['id']}", use_container_width=True):
                rc.remove_item(it["id"])
                st.rerun()


# ==================================================================
# RAPPORT FINAL (uniquement les éléments sélectionnés, dans l'ordre)
# ==================================================================
def _render_final(items, rep_text: str, generated: str):
    st.markdown("#### 📄 RAPPORT FINAL")
    st.caption(f"Filtres : {rep_text} · Généré le {generated}")
    if not items:
        st.info("Composez votre rapport en ajoutant des visualisations.")
        return

    # --- Exports (uniquement la composition) ---
    st.markdown('<div class="an-head"><span>⬇️</span> Exporter le rapport</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        try:
            pdf = rc.cart_pdf_bytes(items, generated)
        except Exception:
            pdf = None
        st.download_button("📕 Export PDF", data=pdf or b"",
                           file_name=f"rapport_dashboard_{datetime.now():%Y%m%d_%H%M}.pdf",
                           mime="application/pdf", use_container_width=True)
    with c2:
        try:
            xl = rc.cart_excel_bytes(items, generated)
        except Exception:
            xl = None
        st.download_button("📗 Export Excel", data=xl or b"",
                           file_name=f"rapport_dashboard_{datetime.now():%Y%m%d_%H%M}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with c3:
        zips = []
        for i, it in enumerate(items):
            csv = rc.item_csv_bytes(it)
            if csv:
                zips.append((f"{i+1:02d}_{it.get('title','element')}.csv", csv))
        if zips:
            import zipfile
            from io import BytesIO
            buf = BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data in zips:
                    z.writestr(name, data)
            st.download_button("📄 Export CSV (zip)", data=buf.getvalue(),
                               file_name=f"rapport_dashboard_{datetime.now():%Y%m%d_%H%M}.zip",
                               mime="application/zip", use_container_width=True)
        else:
            st.button("📄 Export CSV", disabled=True, use_container_width=True)
    with c4:
        if st.button("🖼️ Export PNG", use_container_width=True):
            st.session_state["rds_export_png"] = True
        if st.session_state.get("rds_export_png"):
            pngs = [(it.get("title", "graphique"), rc.item_png(it))
                    for it in items]
            any_ok = False
            for t, p in pngs:
                if p:
                    any_ok = True
                    st.download_button(f"PNG — {t}", data=p,
                                       file_name=f"{t}.png", mime="image/png")
            if not any_ok:
                st.warning("Aucun graphique à exporter en PNG.")
            st.session_state["rds_export_png"] = False

    # --- Rendu des figures sélectionnées, dans l'ordre ---
    for it in items:
        st.markdown(f"##### {it.get('section','')} — {it.get('title','')}")
        if it.get("filter_text"):
            st.caption(f"Filtres : {it['filter_text']}")
        fig = rc.json_to_fig(it.get("fig_json"))
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            df = it.get("data")
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("Pas d'élément visuel à afficher.")


# ==================================================================
# PAGE PRINCIPALE
# ==================================================================
def show_rapports():
    _load_css()
    _hero()

    ops = _load_ops()
    if ops is None or ops.empty:
        st.warning("Aucune opération dans la base. Importez des escales pour "
                   "composer un rapport.")
        return
    rep = _render_filters(ops)

    if st.button("📄 GÉNÉRER", type="primary", use_container_width=True):
        consig, incidents = _load_aux()
        out = _build_res_cached(ops, consig, incidents, _rep_key(rep))
        st.session_state["rds_data"] = out
        st.rerun()

    data = st.session_state.get("rds_data")
    if not data:
        st.info("Choisissez vos filtres puis cliquez sur 📄 GÉNÉRER.")
        return
    if "error" in data:
        st.warning(data["error"])
        st.session_state["rds_data"] = None
        return

    res = data["res"]
    rep_text = data["rep"].get("year", _ALL_YEARS)
    if data["rep"].get("months"):
        rep_text += " · " + ", ".join(_MOIS[m - 1]
                                      for m in data["rep"]["months"])
    generated = data["generated"]
    st.caption(f"Contexte généré le {generated} · Année de référence : {res.year} · "
               f"{len(res.prepared)} opérations filtrées")

    _render_cards(res)
    _render_card_visuals(res)

    st.markdown("---")
    _render_cart(rep_text, generated)

    st.markdown("---")
    _render_final(rc.cart_items(), rep_text, generated)

# -*- coding: utf-8 -*-
"""Port Performance Score : score circulaire + détail transparent du calcul."""

import html
import streamlit as st

from components.dashboard.analytics import SCORE_TONE, score_details

# (clé, libellé, icône, unité, format, hausse_positive) — mini-KPIs bruts
MINI_KPIS = [
    ("escales", "Escales", "⚓", "", "int", True),
    ("navires", "Navires", "🚢", "", "int", True),
    ("tonnage", "Tonnage traité", "📦", "", "tonnage", True),
    ("attente", "Attente moyenne", "⏳", " h", "d1", False),
    ("sejour_quai", "Séjour à quai", "⚓", " h", "d1", False),
    ("sejour_port", "Séjour au port", "🛳", " h", "d1", False),
    ("productivite", "Productivité", "⚙️", " t/h", "d1", True),
    ("occupation", "Taux d'occupation", "🏗", " %", "d1", None),
]


def _fmt(value, mode: str) -> str:
    if value is None or pd_isna(value):
        return "—"
    if mode == "int":
        return f"{value:,.0f}".replace(",", " ")
    if mode == "tonnage":
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f} Mt"
        if value >= 1_000:
            return f"{value / 1_000:.1f} kt"
        return f"{value:.0f} t"
    if mode == "d1":
        return f"{value:,.1f}".replace(",", " ")
    return str(value)


def pd_isna(v) -> bool:
    try:
        import pandas as pd
        return pd.isna(v)
    except Exception:
        return False


def _variation_chip(var, higher_positive):
    """Puce ↑/↓ colorée selon le SENS MÉTIER."""
    if var is None:
        return '<em class="var-chip neutral">— vs N-1</em>'
    up = var >= 0
    if higher_positive is None:
        good = abs(var) <= 5
    else:
        good = up if higher_positive else not up
    arrow = "▲" if up else "▼"
    cls = "good" if good else "bad"
    return f'<em class="var-chip {cls}">{arrow} {abs(var):.1f}% <small>vs N-1</small></em>'


def _subscore_rows(subscores: dict) -> str:
    rows = ""
    for name, val in subscores.items():
        cls = "good" if val >= 70 else "medium" if val >= 45 else "low"
        rows += (f'<div class="subscore"><span>{html.escape(name)}</span>'
                 f'<div class="sub-bar"><i class="{cls}" style="width:{max(val,2):.0f}%"></i></div>'
                 f'<b>{val:.0f}</b></div>')
    return rows


def _detail_table(details: list) -> str:
    """Tableau HTML détaillé de la décomposition du score."""
    rows = ""
    for d in details:
        delta_text, delta_cls = d["delta"]
        score_cls = "sd-good" if d["score"] >= 70 else "sd-medium" if d["score"] >= 45 else "sd-low"
        rows += f'''<tr>
            <td class="sd-name">{d["icon"]} {html.escape(d["name"])}</td>
            <td class="sd-raw">{d["raw"]}</td>
            <td class="sd-score {score_cls}">{d["score"]:.0f}/100</td>
            <td class="sd-weight">{d["weight"]*100:.2f} %</td>
            <td class="sd-contrib">{d["contribution"]:.1f} pts</td>
            <td class="sd-delta {delta_cls}">{delta_text}</td>
        </tr>'''
    return rows


def _formula_rows(details: list) -> str:
    """Lignes de formules pour chaque indicateur."""
    rows = ""
    for d in details:
        rows += f'''<tr>
            <td class="sd-name">{d["icon"]} {html.escape(d["name"])}</td>
            <td class="sd-formula">{html.escape(d["formula"])}</td>
            <td class="sd-ref">{html.escape(d["reference"])}</td>
        </tr>'''
    return rows


def _interp_rows(details: list) -> str:
    """Lignes d'interprétation métier."""
    rows = ""
    for d in details:
        rows += f'''<tr>
            <td class="sd-name">{d["icon"]} {html.escape(d["name"])}</td>
            <td class="sd-rule">{html.escape(d["rule"])}</td>
            <td class="sd-interp">{html.escape(d["interpretation"])}</td>
        </tr>'''
    return rows


def render_performance_score(ctx: dict):
    """Score circulaire + panneau détaillé transparent."""
    kpis = ctx["kpis"]
    variations = ctx["variations"]
    score_block = ctx["score"]
    score = score_block["score"]
    etat = score_block["etat"]
    tone = SCORE_TONE.get(etat, "medium")
    prev_kpis = ctx["kpis_prev"]

    # Évolution du score vs même période N-1
    prev_score_block = None
    try:
        from components.dashboard.analytics import compute_composite_score
        prev_variations = {k: None for k in variations}
        prev_score_block = compute_composite_score(prev_kpis, prev_variations)
    except Exception:
        pass
    delta_score = (score - prev_score_block["score"]
                   if prev_score_block
                   and (prev_score_block["score"] or prev_score_block["score"] == 0)
                   and any(prev_kpis.values()) else None)
    delta_html = (
        f'<span class="score-delta {"up" if delta_score >= 0 else "down"}">'
        f'{"▲" if delta_score >= 0 else "▼"} {abs(delta_score)} pts vs N-1</span>'
    ) if delta_score is not None else '<span class="score-delta">référence établie</span>'

    # ─── Carte principale ───
    st.markdown(f'''<section class="score-panel vts-score {tone}">
        <header><div><span class="eyebrow">VTS · PERFORMANCE ENGINE</span>
        <h3>Port Performance Score</h3></div>
        <span class="score-live"><i></i> LIVE</span></header>
        <div class="score-core">
            <div class="score-radar">
                <div class="score-ring {tone}" style="--score:{score}">
                    <b>{score}</b><small>/100</small>
                </div>
            </div>
            <div class="score-copy">
                <strong>{html.escape(etat)}</strong>
                <p>Indice agrégé multi-dimensions<br>
                (trafic · productivité · séjours · attente · occupation)</p>
                {delta_html}
            </div>
        </div>
        <div class="subscores">{_subscore_rows(score_block["subscores"])}</div>
    </section>''', unsafe_allow_html=True)

    # ─── Panneau détail du calcul ───
    details = score_details(kpis, prev_kpis, variations, score_block)

    with st.expander("Voir le détail du calcul", expanded=False):
        # ① Score global + formule
        st.markdown(f'''<div class="sd-header">
            <div class="sd-global">
                <span class="sd-global-score">{score}<small>/100</small></span>
                <span class="sd-global-etat {tone}">{html.escape(etat)}</span>
            </div>
            <div class="sd-formula-sum">
                <span>Score = </span>{' + '.join(
                    f'<b>{d["name"]}</b> × {d["weight"]*100:.2f} %'
                    for d in details
                )} = <b>{score} pts</b>
            </div>
        </div>''', unsafe_allow_html=True)

        # ② Tableau de décomposition
        st.markdown('<div class="sd-section"><h4>② Décomposition</h4></div>',
                    unsafe_allow_html=True)
        st.markdown(f'''<table class="sd-table">
            <thead><tr>
                <th>Indicateur</th><th>Valeur réelle</th><th>Score /100</th>
                <th>Poids</th><th>Contribution</th><th>Variation N-1</th>
            </tr></thead>
            <tbody>{_detail_table(details)}</tbody>
        </table>''', unsafe_allow_html=True)

        # ③ Formules
        st.markdown('<div class="sd-section"><h4>③ Formules utilisées</h4></div>',
                    unsafe_allow_html=True)
        st.markdown(f'''<table class="sd-table sd-formula-table">
            <thead><tr>
                <th>Indicateur</th><th>Formule de normalisation</th><th>Référence</th>
            </tr></thead>
            <tbody>{_formula_rows(details)}</tbody>
        </table>''', unsafe_allow_html=True)

        # ④ Interprétation métier
        st.markdown('<div class="sd-section"><h4>④ Interprétation métier</h4></div>',
                    unsafe_allow_html=True)
        st.markdown(f'''<table class="sd-table sd-interp-table">
            <thead><tr>
                <th>Indicateur</th><th>Règle</th><th>Interprétation</th>
            </tr></thead>
            <tbody>{_interp_rows(details)}</tbody>
        </table>''', unsafe_allow_html=True)

        # ⑤ Comparaison N-1
        if delta_score is not None:
            prev_s = prev_score_block["score"] if prev_score_block else "—"
            st.markdown(f'''<div class="sd-section"><h4>⑤ Comparaison N-1</h4></div>
            <div class="sd-compare">
                <div class="sd-compare-item">
                    <span class="sd-compare-label">Score N</span>
                    <span class="sd-compare-val">{score}</span>
                </div>
                <div class="sd-compare-item">
                    <span class="sd-compare-label">Score N-1</span>
                    <span class="sd-compare-val">{prev_s}</span>
                </div>
                <div class="sd-compare-item">
                    <span class="sd-compare-label">Variation</span>
                    <span class="sd-compare-val sd-compare-{"up" if delta_score >= 0 else "down"}">
                        {"▲" if delta_score >= 0 else "▼"} {abs(delta_score)} pts
                    </span>
                </div>
            </div>''', unsafe_allow_html=True)
        else:
            st.markdown('''<div class="sd-section"><h4>⑤ Comparaison N-1</h4></div>
            <div class="sd-compare sd-no-data">Données N-1 insuffisantes pour comparer.</div>
            ''', unsafe_allow_html=True)

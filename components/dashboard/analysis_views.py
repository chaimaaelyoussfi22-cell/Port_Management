# -*- coding: utf-8 -*-
"""Vues d'analyse détaillées ouvertes par les boutons « Analyser ».

Chaque vue est synchronisée avec les filtres globaux (ctx déjà filtré)
et construite uniquement à partir des données réelles.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.dashboard.analytics import (
    DIAG_STYLE, MONTHS_FR, monthly_series, yearly_totals_by_category,
    variation)

MARITIME = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#cfe8ff", "size": 12},
            "margin": {"l": 10, "r": 10, "t": 40, "b": 10}}
COLOR_SEQ = ["#62ddff", "#2dd4bf", "#f2b84b", "#ff6077", "#56a8ff",
             "#9d7bff", "#32d2a4", "#ff9d66", "#6ee7b7", "#93c5fd"]


def _apply_theme(fig):
    fig.update_layout(**MARITIME)
    fig.update_xaxes(gridcolor="#1d3a5c", zerolinecolor="#1d3a5c")
    fig.update_yaxes(gridcolor="#1d3a5c", zerolinecolor="#1d3a5c")
    return fig


def _series_fig(s_cur: pd.DataFrame, s_prev: pd.DataFrame, y_title: str):
    """Figure courbes année N vs N-1 depuis deux séries (year, month, value)."""
    fig = go.Figure()
    if s_cur is not None and not s_cur.empty:
        years = sorted(s_cur["year"].unique())
        latest = int(years[-1])
        d = s_cur[s_cur["year"] == latest].set_index("month")["value"]
        idx = [m for m in range(1, 13) if m in d.index]
        fig.add_trace(go.Scatter(x=[MONTHS_FR[m - 1] for m in idx], y=[d[m] for m in idx],
                                 name=f"Année N ({latest})", mode="lines+markers",
                                 line={"color": "#62ddff", "width": 3}))
    if s_prev is not None and not s_prev.empty:
        prev_years = sorted(s_prev["year"].unique())
        if prev_years:
            py = int(prev_years[-1])
            d = s_prev[s_prev["year"] == py].set_index("month")["value"]
            idx = [m for m in range(1, 13) if m in d.index]
            fig.add_trace(go.Scatter(x=[MONTHS_FR[m - 1] for m in idx], y=[d[m] for m in idx],
                                     name=f"Année N-1 ({py})", mode="lines+markers",
                                     line={"color": "#f2b84b", "width": 2, "dash": "dot"}))
    if not fig.data:
        return None
    fig.update_layout(height=320, yaxis_title=y_title, legend=dict(orientation="h"))
    return _apply_theme(fig)


def _dual_year_lines(ctx, value_col: str, agg: str, y_title: str):
    """Courbes année N vs N-1 par mois (escales/tonnage/durées...)."""
    cur, prev = ctx["prepared"], ctx["prepared_prev"]
    if cur.empty:
        return None
    s_cur = monthly_series(cur, value_col, agg)
    s_prev = monthly_series(prev, value_col, agg) if not prev.empty else pd.DataFrame()
    return _series_fig(s_cur, s_prev, y_title)


def _weighted_prod_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    """Productivité mensuelle pondérée : Σ tonnage ÷ Σ durée quai."""
    if frame is None or frame.empty or "month" not in frame.columns:
        return pd.DataFrame()
    f = frame.dropna(subset=["month"])
    f = f[f["quai_h"].fillna(0) > 0]
    if f.empty:
        return pd.DataFrame()
    g = f.groupby(["year", "month"]).agg(t=("tonnage", "sum"), h=("quai_h", "sum"))
    g = g[g["h"] > 0]
    g["value"] = g["t"] / g["h"]
    return g.reset_index()


def _bar_by(frame: pd.DataFrame, cat: str, val: str, title: str,
            n_top: int = 12, horizontal: bool = True):
    if frame is None or frame.empty:
        return None
    if cat == "poste_norm":
        from components.dashboard.sejour_views import (
            POSTE_REFERENTIEL, _poste_label)
        labels = [_poste_label(p) for p in POSTE_REFERENTIEL]
        g = (frame.groupby("poste_norm")[val].sum()
             .reindex(POSTE_REFERENTIEL, fill_value=0).reset_index())
        g["poste_norm"] = [_poste_label(p) for p in g["poste_norm"]]
        fig = px.bar(g, x=val, y="poste_norm", orientation="h",
                     color_discrete_sequence=["#2dd4bf"])
        fig.update_layout(
            height=max(280, 30 * len(g)), title=title, showlegend=False,
            yaxis=dict(categoryorder="array", categoryarray=labels,
                       autorange="reversed"))
        return _apply_theme(fig)
    g = frame.groupby(cat)[val].sum().sort_values(ascending=False).head(n_top).reset_index()
    if g.empty:
        return None
    orientation = "h" if horizontal else "v"
    fig = px.bar(g, x=val if horizontal else cat, y=cat if horizontal else val,
                 orientation=orientation, color_discrete_sequence=["#2dd4bf"])
    fig.update_layout(height=max(280, 30 * len(g)), title=title, showlegend=False)
    return _apply_theme(fig)


def _kpi_banner(label, value_txt, sub_html=""):
    st.markdown(f'''<div class="analysis-kpi"><span>{label}</span><strong>{value_txt}</strong>{sub_html}</div>''',
                unsafe_allow_html=True)


def _var_chip(var):
    if var is None:
        return '<em class="var-chip neutral">— vs N-1</em>'
    cls = "good" if var >= 0 else "bad"
    return f'<em class="var-chip {cls}">{"▲" if var >= 0 else "▼"} {abs(var):.1f}% vs N-1</em>'


# ==================================================================
# VUE : ESCALES
# ==================================================================
def view_escales(ctx):
    kpis, prev, var = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]["escales"]
    _kpi_banner("⚓ Nombre d'escales", f"{kpis['escales']:,}".replace(",", " "),
                f'{_var_chip(var)} <span class="mk-prev">N-1 : {prev["escales"]:,}</span>'.replace(",", " "))
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = _dual_year_lines(ctx, "escale_key", "nunique", "Escales")
        if fig: st.plotly_chart(fig, use_container_width=True)
        else: st.info("Aucune escale sur la période.")
    with c2:
        fig = _bar_by(ctx["prepared"], "type_navire_norm", "escale_key",
                      "Escales par type de navire")
        if fig: st.plotly_chart(fig, use_container_width=True)
        else: st.info("—")
    c3, c4 = st.columns(2)
    with c3:
        fig = _bar_by(ctx["prepared"], "marchandise_norm", "escale_key",
                      "Top 10 escales par marchandise", n_top=10)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        search = st.text_input("🔎 Rechercher une marchandise", key="esc_mrch_search")
        table = _category_table(ctx, "marchandise_norm", "escale_key", search)
        if table is not None and not table.empty:
            show_all = st.toggle("Afficher toutes les marchandises", key="esc_show_all")
            st.dataframe(table.head(None if show_all else 10), use_container_width=True, hide_index=True)
    with c4:
        fig = _bar_by(ctx["prepared"], "operateur_norm", "escale_key",
                      "Escales par opérateur", n_top=10)
        if fig: st.plotly_chart(fig, use_container_width=True)


def _category_table(ctx, cat: str, metric_col: str, search: str = "") -> pd.DataFrame | None:
    """Table Top : valeur, part %, évolution N vs N-1."""
    prepared, prev = ctx["prepared"], ctx["prepared_prev"]
    if prepared.empty:
        return None
    total_cur = ctx["kpis"]["tonnage"] if metric_col == "tonnage" else prepared["escale_key"].nunique()
    g_cur = prepared.groupby(cat)["escale_key"].nunique() if metric_col == "escale_key" \
        else prepared.groupby(cat)["tonnage"].sum()
    g_prev = prev.groupby(cat)["escale_key"].nunique() if not prev.empty else pd.Series(dtype=float)
    rows = []
    for cat_val, cur_val in g_cur.items():
        name = str(cat_val) if str(cat_val).strip() else "Non renseigné"
        if search and search.lower() not in name.lower():
            continue
        p_val = float(g_prev.get(cat_val, 0))
        rows.append({cat: name, "Valeur": float(cur_val),
                     "Part (%)": round(float(cur_val) / total_cur * 100, 1) if total_cur else 0,
                     "Évolution (%)": variation(float(cur_val), p_val)})
    df = pd.DataFrame(rows)
    return df.sort_values("Valeur", ascending=False) if not df.empty else df


# ==================================================================
# VUE : NAVIRES
# ==================================================================
def view_navires(ctx):
    kpis, prev, var = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]["navires"]
    prepared = ctx["prepared"]
    per_ship = prepared.groupby("navire_name")["escale_key"].nunique() if not prepared.empty else pd.Series(dtype=int)
    repet = int((per_ship >= 2).sum())
    _kpi_banner("🚢 Navires distincts", f"{kpis['navires']:,}".replace(",", " "),
                f'{_var_chip(var)} · <b>{repet}</b> navires répétitifs (≥2 escales) · '
                f'<b>{kpis["escales"]}</b> escales au total')
    c1, c2 = st.columns(2)
    with c1:
        fig = _dual_year_lines(ctx, "navire_name", "nunique", "Navires")
        if fig: st.plotly_chart(fig, use_container_width=True)
        else: st.info("Aucun navire sur la période.")
    with c2:
        fig = _bar_by(prepared, "type_navire_norm", "navire_name", "Navires par type")
        if fig: st.plotly_chart(fig, use_container_width=True)
    if repet:
        top_repeat = per_ship[per_ship >= 2].sort_values(ascending=False).head(10)
        st.markdown("**Navires les plus fréquents**")
        st.dataframe(pd.DataFrame({"Navire": top_repeat.index,
                                   "Escales": top_repeat.values}),
                     use_container_width=True, hide_index=True)


# ==================================================================
# VUE : TRAFIC TRAITÉ
# ==================================================================
def view_trafic(ctx):
    kpis, prev, var = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]["tonnage"]
    prepared = ctx["prepared"]
    _kpi_banner("📦 Tonnage traité", f"{kpis['tonnage']:,.0f} t".replace(",", " "),
                f'{_var_chip(var)} <span class="mk-prev">N-1 : {prev["tonnage"]:,.0f} t</span>')
    c1, c2 = st.columns([3, 2])
    with c1:
        if prepared.empty:
            st.info("Aucun trafic sur la période.")
        else:
            pm = prepared.dropna(subset=["month"])
            piv = pm.pivot_table(index="month", columns="type_trafic",
                                 values="tonnage", aggfunc="sum", fill_value=0)
            piv.index = [MONTHS_FR[int(m) - 1] for m in piv.index]
            fig = px.bar(piv, barmode="group", color_discrete_sequence=COLOR_SEQ)
            fig.update_layout(height=340, legend_title=None, xaxis_title=None, yaxis_title="Tonnes")
            st.plotly_chart(_apply_theme(fig), use_container_width=True)
    with c2:
        fig = _bar_by(prepared, "type_trafic", "tonnage", "Répartition Import / Export / Cabotage")
        if fig: st.plotly_chart(fig, use_container_width=True)
    fig = _bar_by(prepared, "marchandise_norm", "tonnage", "Trafic par marchandise (Top 12)")
    if fig: st.plotly_chart(fig, use_container_width=True)
    # Table Top 10 marchandises : tonnage, part, évolution
    table = _category_table(ctx, "marchandise_norm", "tonnage")
    if table is not None and not table.empty:
        st.markdown("**Top 10 marchandises**")
        st.dataframe(table.rename(columns={
            "marchandise_norm": "Marchandise", "Valeur": "Tonnage (t)"}),
            use_container_width=True, hide_index=True, height=380)


# ==================================================================
# VUE : ÉVOLUTION DU TRAFIC
# ==================================================================
def view_evolution(ctx):
    prepared, prev = ctx["prepared"], ctx["prepared_prev"]
    var = ctx["variations"]["tonnage"]
    _kpi_banner("📈 Évolution du trafic",
                f"{var:+.1f} %" if var is not None else "—",
                f'<span class="mk-prev">N : {ctx["kpis"]["tonnage"]:,.0f} t · N-1 : {prev["tonnage"]:,.0f} t</span>')
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = _dual_year_lines(ctx, "tonnage", "sum", "Tonnes")
        if fig: st.plotly_chart(fig, use_container_width=True)
        else: st.info("Aucune donnée.")
    with c2:
        if not prev.empty:
            contrib = (prepared.groupby("marchandise_norm")["tonnage"].sum()
                       - prev.groupby("marchandise_norm")["tonnage"].sum()).fillna(0).sort_values()
            contrib = contrib[(contrib.abs() > 0)]
            if not contrib.empty:
                colors = ["#32d2a4" if v > 0 else "#ff6077" for v in contrib]
                fig = px.bar(x=contrib.values, y=contrib.index, orientation="h")
                fig.update_traces(marker_color=colors)
                fig.update_layout(height=max(300, 26 * len(contrib)),
                                  title="Contribution à la hausse / baisse (t)",
                                  xaxis_title="Δ Tonnes", yaxis_title=None)
                st.plotly_chart(_apply_theme(fig), use_container_width=True)
            else:
                st.info("Pas de contribution nette détectée.")
        else:
            st.info("Pas de données N-1 comparables.")
    fig = _operator_variation(ctx)
    if fig: st.plotly_chart(fig, use_container_width=True)


def _operator_variation(ctx):
    prepared, prev = ctx["prepared"], ctx["prepared_prev"]
    if prepared.empty or prev.empty:
        return None
    cur_g = prepared.groupby("operateur_norm")["tonnage"].sum()
    prev_g = prev.groupby("operateur_norm")["tonnage"].sum()
    delta = (cur_g - prev_g).fillna(0)
    delta = delta[delta.abs() > 0].sort_values().head(15)
    if delta.empty:
        return None
    fig = px.bar(x=delta.values, y=delta.index, orientation="h")
    fig.update_traces(marker_color=["#32d2a4" if v > 0 else "#ff6077" for v in delta])
    fig.update_layout(height=max(280, 26 * len(delta)), title="Variation du trafic par opérateur (t)",
                      xaxis_title="Δ Tonnes", yaxis_title=None)
    return _apply_theme(fig)


# ==================================================================
# VUES SÉJOURS & ATTENTE (quai / port / mouillage)
# ==================================================================
def _duration_view(ctx, col: str, label: str, icon: str, formula: str):
    """Vue commune séjours/attente : KPI, N vs N-1, mensuel, poste, marchandise, type."""
    kpis = ctx["kpis"]
    key_map = {"quai_h": "sejour_quai", "port_h": "sejour_port", "attente_h": "attente"}
    var = ctx["variations"].get(key_map[col])
    if var is not None:
        chip = (f'<em class="var-chip {"good" if var < 0 else "bad"}">'
                f'{"▼ amélioration" if var < 0 else "▲ dégradation"} {abs(var):.1f}% vs N-1</em>')
    else:
        chip = '<em class="var-chip neutral">— vs N-1</em>'
    value = kpis.get(key_map[col], 0)
    st.markdown(f'''<div class="analysis-kpi"><span>{icon} {label} — moyenne port</span>
        <strong>{value:,.1f} h</strong>{chip}<code class="formula">{formula}</code></div>'''.replace(",", " "),
        unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        fig = _dual_year_lines(ctx, col, "mean", "Heures")
        if fig: st.plotly_chart(fig, use_container_width=True)
        else: st.info("Aucune donnée de durée sur la période.")
    with c2:
        fig = _bar_by(ctx["prepared"], "poste_norm", col, f"{label} moyen par poste")
        if fig: st.plotly_chart(fig, use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        fig = _bar_by(ctx["prepared"], "marchandise_norm", col, f"{label} par marchandise (Top 10)")
        if fig: st.plotly_chart(fig, use_container_width=True)
    with c4:
        fig = _bar_by(ctx["prepared"], "type_navire_norm", col, f"{label} par type de navire")
        if fig: st.plotly_chart(fig, use_container_width=True)
    # Détection intelligente des postes anormaux (séjour quai)
    postes = ctx["postes"]
    if col == "quai_h" and not postes.empty:
        abnormal = postes[(postes["ecart_sejour"].notna()) & (postes["ecart_sejour"] > 20)]
        if not abnormal.empty:
            st.warning("⚠️ " + " · ".join(
                f"Poste {r['poste']} : séjour +{r['ecart_sejour']:.0f}% vs moyenne du port"
                for _, r in abnormal.iterrows()))


def view_sejour_quai(ctx):
    prepared = ctx["prepared"]
    _duration_view(ctx, "quai_h", "Séjour à quai", "⏱",
                   "Durée_quai = Appareillage_Quai − Accostage (heures)")
    if not prepared.empty and len(prepared.dropna(subset=["quai_h"])) >= 3:
        sc = prepared.dropna(subset=["quai_h"])
        fig = px.scatter(sc, x="quai_h", y="tonnage", hover_data=[
            "navire_name", "poste_norm", "marchandise_norm"],
            color_discrete_sequence=["#62ddff"],
            labels={"quai_h": "Durée de séjour à quai (h)", "tonnage": "Tonnage (t)"})
        fig.update_layout(height=380, title="Tonnage vs durée de séjour — chaque point = une escale")
        st.plotly_chart(_apply_theme(fig), use_container_width=True)
        st.caption("Objectif : repérer gros navires à séjour anormalement long, petits navires très longs, escales atypiques.")


def view_sejour_port(ctx):
    _duration_view(ctx, "port_h", "Séjour au port", "🛳",
                   "Durée_port = Appareillage_Port − Arrivée_Rade (heures)")


def view_attente(ctx):
    _duration_view(ctx, "attente_h", "Attente / Mouillage", "⏳",
                   "Attente = Sortie_Mouillage − Mouillage (heures) — une hausse = dégradation")


# ==================================================================
# VUE : PRODUCTIVITÉ
# ==================================================================
def view_productivite(ctx):
    kpis, prev_k, var = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]["productivite"]
    _kpi_banner("⚙️ Productivité globale (pondérée)", f"{kpis['productivite']:,.1f} t/h".replace(",", " "),
                f'{_var_chip(var)} <span class="mk-prev">N-1 : {prev_k["productivite"]} t/h</span>'
                f'<code class="formula">Productivité = Σ Tonnage ÷ Σ Durée_quai</code>')
    postes = ctx["postes"]
    if postes.empty:
        st.info("Aucune donnée de productivité sur la période."); return
    seg = ctx["segments"]

    def _prod_by(col_cat: str):
        if seg.empty:
            return None
        g = seg.groupby(col_cat).agg(t=("tonnage_attr", "sum"), h=("seg_dur_h", "sum"))
        g = g[g["h"] > 0]
        g["prod"] = g["t"] / g["h"]
        g = g.sort_values("prod", ascending=False).head(12).reset_index()
        return g if not g.empty else None

    c1, c2 = st.columns(2)
    with c1:
        s_cur = _weighted_prod_monthly(ctx["prepared"])
        s_prev = _weighted_prod_monthly(ctx["prepared_prev"])
        fig = _series_fig(s_cur, s_prev, "t/h")
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Productivité pondérée : Σ Tonnage ÷ Σ Durée_quai du mois.")
        else:
            st.info("Durées insuffisantes pour une productivité mensuelle.")
    with c2:
        g_poste = _prod_by("poste_norm")
        if g_poste is not None:
            fig = px.bar(g_poste, x="prod", y="poste_norm", orientation="h",
                         color_discrete_sequence=["#62ddff"],
                         labels={"prod": "t/h", "poste_norm": ""})
            fig.update_layout(height=330, title="Productivité par poste (t/h)")
            st.plotly_chart(_apply_theme(fig), use_container_width=True)
        else:
            st.info("Segments de poste insuffisants.")

    c3, c4 = st.columns(2)
    with c3:
        top5 = postes.nlargest(5, "productivite")
        flop5 = postes.nsmallest(5, "productivite").iloc[::-1]
        st.markdown("**🏆 Top 5 meilleurs postes**")
        st.dataframe(top5[["poste", "productivite", "sejour_moyen", "occupation"]],
                     use_container_width=True, hide_index=True)
        st.markdown("**🔻 5 postes les moins performants**")
        st.dataframe(flop5[["poste", "productivite", "sejour_moyen", "occupation"]],
                     use_container_width=True, hide_index=True)
    with c4:
        g_march = _prod_by("marchandise_norm")
        if g_march is not None:
            fig = px.bar(g_march, x="prod", y="marchandise_norm", orientation="h",
                         color_discrete_sequence=["#2dd4bf"],
                         labels={"prod": "t/h", "marchandise_norm": ""})
            fig.update_layout(height=330, title="Productivité par marchandise (t/h)")
            st.plotly_chart(_apply_theme(fig), use_container_width=True)

    g_op = _prod_by("operateur_norm")
    if g_op is not None:
        fig = px.bar(g_op, x="prod", y="operateur_norm", orientation="h",
                     color_discrete_sequence=["#56a8ff"],
                     labels={"prod": "t/h", "operateur_norm": ""})
        fig.update_layout(height=max(300, 28 * len(g_op)), title="Productivité par opérateur (t/h)")
        st.plotly_chart(_apply_theme(fig), use_container_width=True)
    st.caption("⚖️ Règle de répartition appliquée aux analyses par poste : "
               "Tonnage_attribué = Tonnage_escale ÷ nombre_de_postes_utilisés. "
               "Le tonnage global n'est jamais dupliqué.")


# ==================================================================
# VUE : OCCUPATION
# ==================================================================
def view_occupation(ctx):
    kpis, prev_k, var = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]["occupation"]
    days = ctx["period"]["days"]
    _kpi_banner("🏗 Taux d'occupation global", f"{kpis['occupation']:.1f} %",
                f'{_var_chip(var)} <span class="mk-prev">N-1 : {prev_k["occupation"]} %</span>'
                f'<code class="formula">Occupation = Σ Durée_quai(poste) ÷ ({days} jours × 24 h)</code>')
    postes = ctx["postes"]
    if postes.empty:
        st.info("Aucune occupation mesurable sur la période."); return

    def occ_color(o):
        return "#56a8ff" if o < 50 else "#32d2a4" if o < 70 else "#f2b84b" if o < 80 else "#ff6077"

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(postes.sort_values("occupation"), x="occupation", y="poste",
                     orientation="h", color="occupation",
                     color_continuous_scale=[occ_color(v) for v in
                                             [min(postes['occupation']), max(postes['occupation'])]] or ["#32d2a4"])
        fig.update_traces(marker_color=[occ_color(v) for v in postes.sort_values("occupation")["occupation"]])
        fig.update_layout(height=max(300, 28 * len(postes)), title="Occupation par poste (%)",
                          xaxis_title="%", yaxis_title=None, coloraxis_showscale=False)
        st.plotly_chart(_apply_theme(fig), use_container_width=True)
    with c2:
        from components.dashboard.occupation import monthly_occupancy
        intervals_all = ctx.get("intervals")
        if intervals_all is not None and not intervals_all.empty:
            mo = monthly_occupancy(intervals_all)
            mo_prev = pd.DataFrame()
            iv_prev = ctx.get("intervals_prev")
            if iv_prev is not None and not iv_prev.empty:
                mo_prev = monthly_occupancy(iv_prev)

            def _pct(frame):
                if frame.empty:
                    return pd.DataFrame()
                g = frame.groupby(["year", "month"]).apply(
                    lambda x: x["duree_h"].sum() / x["heures_dispo"].iloc[0] * 100,
                    include_groups=False).reset_index(name="value")
                return g

            fig = _series_fig(_pct(mo), _pct(mo_prev), "% occupation")
            if fig:
                fig.update_layout(title="Évolution mensuelle de l'occupation")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Temps réellement occupé (union dédupliquée) ÷ heures du mois.")
    st.markdown("**Heatmap Poste × Mois**")
    intervals = ctx.get("intervals")
    if intervals is not None and not intervals.empty:
        from components.dashboard.occupation import monthly_occupancy
        mo = monthly_occupancy(intervals)
        if not mo.empty:
            years = sorted(mo["year"].unique())
            latest_y = int(years[-1]) if years else None
            mgy = mo[mo["year"] == latest_y] if latest_y else mo
            heat = mgy.pivot_table(index="poste", columns="month",
                                   values="taux_%", aggfunc="first")
            heat = heat.reindex(columns=range(1, 13)).dropna(how="all", axis=1)
            heat.columns = [MONTHS_FR[int(m) - 1] for m in heat.columns]
            fig = px.imshow(heat, aspect="auto", color_continuous_scale=["#0e2a47", "#2dd4bf", "#f2b84b", "#ff6077"],
                            labels=dict(color="Occupation %"))
            fig.update_layout(height=max(300, 34 * len(heat)),
                              title=f"Heatmap Poste × Mois (%) — année {latest_y}")
            st.plotly_chart(_apply_theme(fig), use_container_width=True)
            st.caption("Union dédupliquée des intervalles ÷ heures réelles du mois.")
    diagnostics = ctx.get("occ_diagnostics") or []
    if diagnostics:
        with st.expander(f"🟠 Diagnostic d'incohérence — {len(diagnostics)} poste(s) > 100 % "
                         "(aucun plafonnement appliqué)"):
            for d in diagnostics:
                st.markdown(
                    f"**{d['code']} — poste {d['poste']}** : taux calculé "
                    f"**{d['taux_calcule_%']} %** · union réelle {d['duree_union_h']} h "
                    f"vs somme brute {d['duree_brute_sommee_h']} h "
                    f"(double comptage détecté : {d['double_comptage_h_detecte']} h)")
                iv_df = pd.DataFrame(d["intervalles"])
                if not iv_df.empty:
                    st.dataframe(iv_df, use_container_width=True, hide_index=True)
                ch_df = pd.DataFrame(d["chevauchements"])
                if not ch_df.empty:
                    st.markdown("Chevauchements détectés :")
                    st.dataframe(ch_df, use_container_width=True, hide_index=True)
    st.markdown("**Postes critiques et capacité disponible**")
    crit = postes[postes["occupation"] >= 80]
    free = postes[postes["occupation"] < 50]
    cc1, cc2 = st.columns(2)
    with cc1:
        if crit.empty: st.success("✓ Aucun poste en saturation.")
        else:
            for _, r in crit.iterrows():
                st.error(f"🔴 Poste {r['poste']} — {r['occupation']:.0f}% ({r['diagnostic']})")
    with cc2:
        if free.empty: st.caption("Aucun poste sous-utilisé.")
        else:
            for _, r in free.iterrows():
                st.info(f"🔵 Poste {r['poste']} — {r['occupation']:.0f}% · capacité disponible")
    st.markdown("**Matrice Occupation × Séjour × Productivité**")
    matrix = postes.copy()
    matrix["Diagnostic"] = matrix.apply(
        lambda r: f"{DIAG_STYLE[r['diag_classe']][0]} {r['diagnostic']}", axis=1)
    st.dataframe(matrix[["poste", "occupation", "sejour_moyen", "productivite",
                         "escales", "tonnage", "Diagnostic"]]
                 .rename(columns={"poste": "Poste", "occupation": "Occupation %",
                                  "sejour_moyen": "Séjour moy. (h)",
                                  "productivite": "Prod. (t/h)", "escales": "Escales",
                                  "tonnage": "Tonnage attribué (t)"}),
                 use_container_width=True, hide_index=True)


# ==================================================================
# ROUTAGE
# ==================================================================
VIEWS = {
    "escales": ("⚓ Analyse des escales", view_escales),
    "navires": ("🚢 Analyse des navires", view_navires),
    "tonnage": ("📦 Analyse du trafic traité", view_trafic),
    "evolution_trafic": ("📈 Évolution du trafic", view_evolution),
    "sejour_quai": ("⏱ Séjour à quai", view_sejour_quai),
    "sejour_port": ("🛳 Séjour au port", view_sejour_port),
    "attente": ("⏳ Attente / Mouillage", view_attente),
    "productivite": ("⚙️ Productivité", view_productivite),
    "occupation": ("🏗 Taux d'occupation", view_occupation),
}


def render_analysis_area(ctx):
    key = st.session_state.get("analysis_view")
    if not key or key not in VIEWS:
        return
    title, fn = VIEWS[key]
    with st.container(border=True):
        head_l, head_r = st.columns([6, 1])
        head_l.markdown(f'<div class="analysis-title">{title}'
                        f'<small>· synchronisé avec les filtres actifs</small></div>', unsafe_allow_html=True)
        if head_r.button("✖ Fermer", key="close_analysis"):
            st.session_state.pop("analysis_view", None)
            st.rerun()
        fn(ctx)

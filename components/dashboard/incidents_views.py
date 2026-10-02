# -*- coding: utf-8 -*-
"""Carte « 🚨 Incidents » — analyse opérationnelle des événements portuaires.

Mini-dashboard Power BI maritime, alimenté exclusivement par la table
`incidents` (données réelles — aucune valeur fictive) :

  - en-tête « 🚨 INCIDENTS » + ligne d'information dynamique ;
  - ◉ Incidents par nature (donut · filtres Année / Mois propres) ;
  - 📈 Évolution des incidents (aire · filtres Année / Mois propres) ;
  - 📍 Incidents par lieu / poste (barres horizontales · filtre Lieu + Année/Mois) ;
  - 📋 Registre détaillé (recherche, détail complet, export CSV).

Règles essentielles :

  * Les événements Consignation / Déconsignation (toutes variantes d'écriture)
    sont EXCLUS de toutes les représentations — la consignation possède déjà
    sa carte dédiée. Ils ne sont jamais supprimés de la table source.
  * Aucun filtre global imposé : chaque visualisation possède ses propres
    filtres intégrés à sa card, strictement indépendants.
  * Périodes, lieux et natures détectés automatiquement à chaque rendu.
  * « — » lorsque l'information n'existe pas.
"""

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.dashboard.filters import MONTHS_FR

# Couleurs du langage visuel maritime de l'app.
COLORS = ["#62ddff", "#2dd4bf", "#f2b84b", "#ff6077", "#56a8ff",
          "#9d7bff", "#32d2a4", "#ff9d66", "#6ee7b7", "#f472b6",
          "#7ac9ff"]

_THEME = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
          "font": {"color": "#cfe8ff", "size": 12},
          "margin": {"l": 10, "r": 10, "t": 20, "b": 10}}


def _theme(fig):
    fig.update_layout(**_THEME)
    fig.update_xaxes(gridcolor="#1d3a5c", zerolinecolor="#1d3a5c")
    fig.update_yaxes(gridcolor="#1d3a5c", zerolinecolor="#1d3a5c")
    return fig


def _fmt0(v):
    return f"{int(v):,}".replace(",", " ")


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass
    # Encadrés propres à la carte (indépendants du thème de la page).
    st.markdown("""
    <style>
    .inc-card {
        background: linear-gradient(160deg, rgba(16,41,67,.96), rgba(10,26,48,.96));
        border: 1px solid #8ccfff55; border-radius: 18px;
        padding: 15px 17px; margin-bottom: 16px;
        box-shadow: inset 0 1px rgba(200,237,255,.14), 0 14px 26px rgba(7,20,40,.18);
    }
    .inc-card-head { display:flex; align-items:center; gap:9px; margin-bottom:10px; }
    .inc-card-head h4 { margin:0; color:#eaf6ff; font-size:.9rem;
        letter-spacing:.02em; font-weight:700; }
    .inc-card-badge {
        display:inline-flex; align-items:center; background:rgba(98,221,255,.1);
        border:1px solid #62ddff44; color:#62ddff; border-radius:999px;
        padding:2px 9px; font-size:.6rem; font-weight:600; white-space:nowrap;
    }
    </style>
    """, unsafe_allow_html=True)


# ==================================================================
# RÈGLE MÉTIER : EXCLUSION CONSIGNATION / DÉCONSIGNATION
# ==================================================================
def est_consignation(nature) -> bool:
    """Vrai si la nature décrit une consignation/déconsignation.

    Robuste aux variantes : « Consignation », « Déconsignation »,
    « Consignation/Déconsignation », casse ou espaces — toutes contiennent
    bien le terme « consignation » après normalisation.
    """
    txt = re.sub(r"\s+", " ", str(nature or "")).lower().strip()
    return "consignation" in txt


def sans_consignations(df: pd.DataFrame) -> pd.DataFrame:
    """Incidents réels uniquement — consignations/déconsignations exclues du
    comptage (elles restent présentes dans la table source)."""
    if df is None or df.empty or "nature" not in df:
        return df
    return df[~df["nature"].map(est_consignation)].reset_index(drop=True)


# ==================================================================
# EXTRACTION NAVIRE / ÉLÉMENT CONCERNÉ (depuis la donnée réelle)
# ==================================================================
_STOPS = {"par", "au", "aux", "à", "et", "de", "du", "des", "le", "la",
          "les", "l", "vers", "pour", "lors", "sur", "dans", "avec",
          "déclare", "déclaré", "après", "avant", "son", "sa", "ses",
          "puis", "a", "été", "est", "aurait", "accosté", "appareillé"}
_VSL_RE = re.compile(r"\bM\s*/\s*[VT]\b\s*[:]?\s*[“\"'”]?\s*([A-Za-z0-9 .•\-]{1,60})", re.I)
_QT_RE = re.compile(r"[“\"'”]([^“\"'”]{3,60})[“\"'”]")
_REM_RE = re.compile(r"remorqueur\s+['\"“”]?([A-Za-z0-9 .\-]{2,30})['\"“”]?", re.I)


def entite_concernee(nature, consistance):
    """Nom de navire / remorqueur ou élément concerné, sinon chaîne vide."""
    texte = f"{consistance} {nature}"
    m = _VSL_RE.search(texte)
    if m:
        nom = _nettoyer_nom(m.group(1))
        if nom:
            return nom
    m = _QT_RE.search(consistance or "")
    if m:
        nom = re.sub(r"^\s*(M\s*/\s*[VT]|NAVIRE|MT)\s*[:]?\s*", "", m.group(1),
                     flags=re.I)
        nom = _nettoyer_nom(nom.strip("'\"“”"))
        if nom:
            return nom
    m = _REM_RE.search(nature or "")
    if m:
        nom = _nettoyer_nom(m.group(1))
        if nom:
            return nom
    return ""


def _nettoyer_nom(nom):
    if not nom:
        return ""
    words = []
    for w in re.split(r"\s+", nom.strip()):
        w0 = re.sub(r"[^A-Za-z0-9\-]+$", "", w)
        if not w0 or w0.lower() in _STOPS:
            break
        words.append(w0)
        if len(words) == 3:
            break
    return " ".join(words)


# ==================================================================
# PRÉPARATION DU DATAFRAME (dimensions analytiques dynamiques)
# ==================================================================
def prepare_incidents(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if df.empty:
        return df
    df["nature"] = df["nature"].fillna("").astype(str).str.strip()
    df["lieu"] = df["lieu"].fillna("").astype(str).str.strip()
    df["consistance"] = df["consistance"].fillna("").astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date_incident"], errors="coerce")
    df = df[df["date"].notna()].copy()
    df["year"] = df["date"].dt.year.astype(int)
    df["month"] = df["date"].dt.month.astype(int)
    df["entite"] = [entite_concernee(n, c)
                    for n, c in zip(df["nature"], df["consistance"])]
    df["resume"] = df["consistance"].map(_resume)
    return df.sort_values("date").reset_index(drop=True)


def _resume(consistance, maxlen=120):
    if not consistance:
        return ""
    txt = re.sub(r"\s+", " ", consistance).strip()
    if len(txt) <= maxlen:
        return txt
    return txt[:maxlen].rsplit(" ", 1)[0] + "…"


# ==================================================================
# HELPERS FILTRES (indépendants par visualisation)
# ==================================================================
def _annee_options(df):
    return ["Toutes les années"] + sorted(df["year"].unique().tolist())


def _mois_options(df, year):
    if year == "Toutes les années":
        months = sorted(df["month"].unique().tolist())
    else:
        months = sorted(df[df["year"] == year]["month"].unique().tolist())
    return ["Tous les mois"] + [MONTHS_FR[m - 1] for m in months]


def _filtre_annee_mois(df, prefix):
    """Selectboxs Année + Mois liés à une visualisation (clés propres)."""
    c1, c2 = st.columns(2)
    annee_opts = _annee_options(df)
    with c1:
        year = st.selectbox("Année", annee_opts, key=f"{prefix}_year")
    with c2:
        mois_opts = _mois_options(df, year)
        mois = st.selectbox("Mois", mois_opts, key=f"{prefix}_month")
    sub = df.copy()
    if year != "Toutes les années":
        sub = sub[sub["year"] == year]
    if mois != "Tous les mois":
        sub = sub[sub["month"] == MONTHS_FR.index(mois) + 1]
    return sub


# ==================================================================
# SECTION : EN-TÊTE + CHIPS
# ==================================================================
def _chip(txt):
    return f'<span class="an-chip">{txt}</span>'


def _section(title, subtitle=""):
    st.markdown(
        f'<div class="an-section-title"><h3>{title}</h3>'
        f'<span>{subtitle}</span></div>', unsafe_allow_html=True)


# ==================================================================
# VISUALISATION 1 — ◉ INCIDENTS PAR NATURE (DONUT)
# ==================================================================
def render_nature_donut(df):
    if df.empty:
        st.info("Aucun incident à représenter.")
        return
    sub = _filtre_annee_mois(df, "inc_dnat")
    if sub.empty:
        st.info("Aucun incident sur cette sélection.")
        return

    g = sub["nature"].value_counts().sort_values(ascending=False)
    display = g.head(10)
    rest = int(g.iloc[10:].sum()) if len(g) > 10 else 0
    labels = display.index.tolist() + (["Autres"] if rest else [])
    values = display.values.tolist() + ([rest] if rest else [])
    pct = np.array(values, dtype=float) / sum(values) * 100
    short = [l.replace("Autres", "Autres natures (10+)" if rest else l)
             for l in labels]
    # Légende : Nature · Nombre · % (demande Power BI)
    legend = [f"<b>{l}</b> · {n} ({p:.0f} %)" if len(l) < 30
              else f"<b>{l[:28]}…</b> · {n} ({p:.0f} %)"
              for l, n, p in zip(labels, values, pct)]

    fig = go.Figure(go.Pie(
        labels=legend, values=values, hole=0.62,
        marker={"colors": COLORS[:len(labels)]},
        textinfo="none", sort=False,
        customdata=np.stack([np.array(values), pct, np.array(short, dtype=object)],
                            axis=-1),
        hovertemplate=("<b>%{customdata[2]}</b><br>Incidents : %{customdata[0]}"
                       "<br>Part : %{customdata[1]:.1f} %<extra></extra>")))
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "x": 0, "y": -0.02,
                "xanchor": "left", "yanchor": "top",
                "font": {"color": "#a9cae8", "size": 10}},
        annotations=[dict(text=f"<b>{_fmt0(len(sub))}</b>"
                              "<br><span style='font-size:11px'>INCIDENTS</span>",
                          x=0.5, y=0.5, showarrow=False,
                          font={"color": "#eaf6ff"})],
        margin={"l": 8, "r": 8, "t": 8, "b": 8}, height=330)
    st.plotly_chart(_theme(fig), use_container_width=True,
                    config={"displayModeBar": False})
    st.caption("Donut des natures après exclusion des consignations/"
               "déconsignations — les 10 premières, le reste regroupé.")


# ==================================================================
# VISUALISATION 2 — 📈 ÉVOLUTION DES INCIDENTS (AIRE)
# ==================================================================
def render_evolution(df):
    if df.empty:
        st.info("Aucun incident à représenter.")
        return
    sub = _filtre_annee_mois(df, "inc_evo")
    if sub.empty:
        st.info("Aucun incident sur cette sélection.")
        return

    if st.session_state.get("inc_evo_year") in (None, "Toutes les années"):
        g = sub.groupby(["year", "month"]).size().reset_index(name="nb")
        g["_o"] = g["year"] * 100 + g["month"]
        g = g.sort_values("_o")
        g["label"] = [f"{MONTHS_FR[m - 1][:4]} {y}"
                      for y, m in zip(g["year"], g["month"])]
    else:
        g = sub.groupby("month").size().reset_index(name="nb").sort_values("month")
        g["label"] = [MONTHS_FR[m - 1][:4] for m in g["month"]]

    dom = sub.groupby(["year", "month"])["nature"].agg(
        lambda s: s.value_counts().index[0])
    nd = sub.groupby(["year", "month"])["nature"].nunique()
    dom_map = dom.to_dict()
    nd_map = nd.to_dict()
    custom = np.stack([
        np.array([dom_map.get((y, m), "") for y, m in
                  zip(g.get("year", [2026] * len(g)), g["month"])], dtype=object),
        np.array([nd_map.get((y, m), 0) for y, m in
                  zip(g.get("year", [2026] * len(g)), g["month"])], dtype=object)],
        axis=-1)

    fig = go.Figure(go.Scatter(
        x=g["label"], y=g["nb"], mode="lines+markers",
        line={"color": "#62ddff", "width": 2.8}, marker={"size": 7},
        fill="tozeroy", fillcolor="rgba(98,221,255,.16)",
        customdata=custom,
        hovertemplate=("<b>%{x}</b><br>Incidents : %{y}<br>"
                       "Nature dominante : %{customdata[0]}<br>"
                       "Natures distinctes : %{customdata[1]}<extra></extra>")))
    fig.update_layout(height=330, margin={"l": 8, "r": 8, "t": 8, "b": 8},
                      xaxis_title=None, yaxis_title="Incidents",
                      showlegend=False)
    st.plotly_chart(_theme(fig), use_container_width=True,
                    config={"displayModeBar": False})
    st.caption("Périodes générées automatiquement depuis la colonne DATE — "
               "seules les périodes réelles sont affichées.")


# ==================================================================
# VISUALISATION 3 — 📍 INCIDENTS PAR LIEU / POSTE (BARRES HORIZONTALES)
# ==================================================================
def render_lieux(df):
    if df.empty:
        st.info("Aucun incident à représenter.")
        return

    lieu_opts = sorted(df["lieu"].unique().tolist())
    c1, c2, c3 = st.columns([1.5, 1, 1])
    with c1:
        lieu = st.selectbox("Lieu / Poste", ["Tous", *lieu_opts],
                            key="inc_lx_lieu")
    with c2:
        year = st.selectbox("Année", _annee_options(df), key="inc_lx_year")
    with c3:
        mois = st.selectbox("Mois", _mois_options(df, year), key="inc_lx_month")

    sub = df.copy()
    if lieu != "Tous":
        sub = sub[sub["lieu"] == lieu]
    if year != "Toutes les années":
        sub = sub[sub["year"] == year]
    if mois != "Tous les mois":
        sub = sub[sub["month"] == MONTHS_FR.index(mois) + 1]
    if sub.empty:
        st.info("Aucun incident sur cette sélection.")
        return

    g = sub["lieu"].value_counts().sort_values(ascending=False)
    if len(g) > 12:
        show_all = st.toggle("Afficher tous les lieux", key="inc_lx_all")
        top = g if show_all else g.head(12)
    else:
        top = g

    fig = go.Figure(go.Bar(
        y=top.index.tolist(), x=top.values.tolist(), orientation="h",
        text=top.values.tolist(), textposition="outside",
        cliponaxis=False, textfont={"color": "#eaf6ff", "size": 11},
        marker={"color": "#56a8ff"},
        customdata=np.stack([np.array(top.index.tolist())], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>Incidents : %{x}"
                      "<extra></extra>"))
    fig.update_layout(height=max(320, 36 * len(top)),
                      margin={"l": 8, "r": 40, "t": 8, "b": 8},
                      xaxis_title="Incidents", yaxis_title=None, showlegend=False)
    fig.update_yaxes(automargin=True)
    st.plotly_chart(_theme(fig), use_container_width=True,
                    config={"displayModeBar": False})
    st.caption("Lieux triés du plus d'incidents au moins — filtre Lieu "
               "indépendant des autres graphiques.")


# ==================================================================
# VISUALISATION 4 — 📋 REGISTRE DÉTAILLÉ
# ==================================================================
def render_register(df):
    if df.empty:
        st.info("Aucun événement à afficher.")
        return
    tbl = pd.DataFrame({
        "Date": df["date"].dt.date,
        "Nature": df["nature"],
        "Lieu": df["lieu"].replace("", "—"),
        "Élément / Navire concerné": df["entite"].replace("", "—"),
        "Détail": df["consistance"].replace("", "—"),
    }).sort_values("Date", ascending=False)

    search = st.text_input("🔎 Rechercher (navire, nature, lieu, détail…)",
                           key="inc_reg_search")
    if search:
        mask = tbl.astype(str).apply(
            lambda r: r.str.lower().str.contains(search.lower(), na=False).any(),
            axis=1)
        tbl = tbl[mask]

    cfg = {
        "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Élément / Navire concerné": st.column_config.TextColumn(width="medium"),
        "Détail": st.column_config.TextColumn(width="large"),
    }
    st.dataframe(tbl, use_container_width=True, hide_index=True,
                 column_config=cfg, height=420)

    opts = [f"{r['Date']:%d/%m/%Y} · {r['Nature']} · {r['Lieu']}"
            for _, r in tbl.iterrows()]
    sel = st.selectbox("👁 Voir le détail complet",
                       ["— Sélectionner un incident —", *opts],
                       key="inc_detail_sel")
    if sel and not sel.startswith("—"):
        row = tbl.iloc[opts.index(sel)]
        st.markdown(
            f'<div class="insight-card"><b class="icn">📄</b>'
            f'<b>{row["Date"]:%d/%m/%Y}</b> · {row["Nature"]} · '
            f'Lieu : {row["Lieu"]}<br>'
            f'Élément / navire : {row["Élément / Navire concerné"]}'
            f'<hr style="opacity:.2;margin:8px 0">{row["Détail"]}</div>',
            unsafe_allow_html=True)
    csv = tbl.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ Exporter le registre en CSV", data=csv,
                       file_name="registre_incidents.csv", mime="text/csv",
                       key="inc_csv")


# ==================================================================
# CARTE COMPLÈTE
# ==================================================================
def render_incidents_card(raw):
    _load_css()
    if raw is None or raw.empty:
        st.markdown('<div class="an-title"><h1>🚨 INCIDENTS</h1>'
                    '<p>Analyse des événements et perturbations portuaires · '
                    'source : table incidents (données réelles)</p></div>',
                    unsafe_allow_html=True)
        st.info("Aucun incident enregistré dans la base.")
        return

    df = prepare_incidents(raw)
    if df.empty:
        st.warning("Aucun incident datable dans la base.")
        return
    # Consignations / déconsignations exclues de TOUTES les représentations.
    incidents = sans_consignations(df)

    # ---------- En-tête ----------
    c_left, c_right = st.columns([5.2, 1])
    with c_left:
        st.markdown('<div class="an-title"><h1>🚨 INCIDENTS</h1>'
                    '<p>Analyse des événements et perturbations portuaires · '
                    'source : table incidents (données réelles)</p></div>',
                    unsafe_allow_html=True)
    with c_right:
        if st.button("↺ Réinitialiser", key="inc_reset",
                     use_container_width=True):
            for k in list(st.session_state):
                if k.startswith("inc_"):
                    del st.session_state[k]
            st.rerun()

    # ---------- Ligne d'information ----------
    st.markdown('<div class="an-chips">' +
                _chip("🗓 Toutes les données") +
                _chip("⚓ Postes : tous") +
                _chip(f"🚨 Incidents : {_fmt0(len(incidents))}") +
                "</div>", unsafe_allow_html=True)

    # ---------- Rangée 1 : donut | évolution (même niveau, même hauteur) ----------
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        st.markdown('<div class="inc-card"><div class="inc-card-head">'
                    '<h4>◉ Incidents par nature</h4>'
                    '<span class="inc-card-badge">filtres indépendants</span>'
                    '</div>', unsafe_allow_html=True)
        render_nature_donut(incidents)
        st.markdown("</div>", unsafe_allow_html=True)
    with col_b:
        st.markdown('<div class="inc-card"><div class="inc-card-head">'
                    '<h4>📈 Évolution des incidents</h4>'
                    '<span class="inc-card-badge">périodes réelles</span>'
                    '</div>', unsafe_allow_html=True)
        render_evolution(incidents)
        st.markdown("</div>", unsafe_allow_html=True)

    # ---------- Rangée 2 : lieux / postes ----------
    st.markdown('<div class="inc-card"><div class="inc-card-head">'
                '<h4>📍 Incidents par lieu / poste</h4>'
                '<span class="inc-card-badge">filtre Lieu</span>'
                '</div>', unsafe_allow_html=True)
    render_lieux(incidents)
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------- Registre détaillé ----------
    _section("📋 Registre détaillé des incidents",
             "Recherche, sélection d'un incident, export CSV")
    render_register(incidents)

    st.markdown(
        '<div class="an-methodo">Méthodologie — Incidents : table `incidents` '
        '(données réelles : nature, date, lieu, consistance). Les événements '
        'Consignation / Déconsignation / Consignation-Déconsignation sont '
        'exclus du comptage (carte dédiée existante) mais restent dans la '
        'table source. Navire / élément extrait de la CONSISTANCE quand il '
        'est identifiable, sinon « — ». Périodes, lieux et natures détectés '
        'dynamiquement à chaque rendu ; aucune valeur calculée n’est codée en '
        'dur.</div>',
        unsafe_allow_html=True)
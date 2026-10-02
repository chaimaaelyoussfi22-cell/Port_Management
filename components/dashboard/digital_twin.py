# -*- coding: utf-8 -*-
"""Jumeau numérique du Port de Jorf Lasfar — postes connectés aux données réelles.

Chaque marqueur est coloré par son taux d'occupation réel :
  🔵 <50 % sous-utilisé · 🟢 50-70 % optimisé · 🟠 70-80 % très sollicité · 🔴 >=80 % saturation
Le survol affiche occupation / escales / séjour / productivité ;
le clic sur un poste le sélectionne visuellement et ouvre son panneau de détail
(fonction réutilisée via la liste déroulante « Sélectionner un poste ») ;
la sélection (clic ou sélecteur) ouvre le panneau d'intelligence du poste.
"""

import base64
import html
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html as st_html

from components.dashboard.analytics import CLASS_COLORS, CLASS_LABELS, DIAG_STYLE

# Coordonnées cartographiques en %, indépendantes des données métier.
PLAN_POSITIONS = {
    "1N": (30, 31), "1S": (30, 45), "1BIS": (30, 55), "1TER": (30, 67), "2N": (38, 40),
    "2BIS": (38, 53), "2TER": (38, 66), "3": (43, 47), "3BIS": (43, 62), "4": (50, 49),
    "4BIS": (50, 63), "5": (53, 51), "6": (58, 52), "7": (60, 59), "8N": (71, 21),
    "8": (71, 21), "9": (89, 42), "10": (71, 47), "11-12": (74, 66), "13": (74, 77),
    "14S": (65, 59), "15": (30, 45), "16N": (89, 55), "16S": (89, 70),
}

CSS_BY_CLASS = {"underused": "available-blue", "optimal": "optimal",
                "busy": "busy", "saturated": "saturated"}

# JavaScript exécuté dans une iframe sandbox (même origine) : il relie le clic
# sur un marqueur à la liste déroulante Streamlit existante, ce qui déclenche
# un rerun et l'ouverture automatique du panneau de détail — sans rechargement.
_MARKER_JS = """
<script>
function __anpNorm(s){ return String(s||'').trim().toUpperCase().replace(/\\s+/g,''); }
function __anpSelect(poste){
  var root = window.parent.document;
  window.parent.__anpScrollToPanel = poste;
  root.querySelectorAll('.port-marker').forEach(function(m){
    m.classList.toggle('selected', __anpNorm(m.getAttribute('data-poste'))===__anpNorm(poste));
  });
  var boxes = root.querySelectorAll('[data-testid="stSelectbox"]');
  var box = null;
  for (var i=0;i<boxes.length;i++){
    if ((boxes[i].innerText||'').indexOf('Sélectionner un poste')>=0){ box = boxes[i]; break; }
  }
  if (!box) return;
  var ctl = box.querySelector('[data-baseweb="select"]') || box.querySelector('[role="combobox"]') || box;
  ['mousedown','mouseup','click'].forEach(function(t){
    ctl.dispatchEvent(new (window.MouseEvent||Event)(t, {bubbles:true,cancelable:true}));
  });
  setTimeout(function(){
    var opts = root.querySelectorAll('[role="option"]');
    var target = null;
    for (var i=0;i<opts.length;i++){
      var txt = __anpNorm((opts[i].innerText||'').trim());
      var base = txt.split('·')[0].trim();
      if (txt===__anpNorm(poste) || base===__anpNorm(poste)){ target = opts[i]; break; }
    }
    if (target){ target.click(); }
  }, 200);
}
window.addEventListener('load', function(){
  var root = window.parent.document;
  var ms = root.querySelectorAll('.port-marker');
  for (var i=0;i<ms.length;i++){
    ms[i].addEventListener('click', function(e){
      e.preventDefault(); e.stopPropagation();
      __anpSelect(this.getAttribute('data-poste'));
    });
  }
});
</script>
"""


def _key(value):
    return str(value).upper().replace("_", "-").replace(" ", "")


def render_digital_twin(ctx):
    postes = ctx["postes"]
    selected = st.session_state.get("selected_poste")
    st.markdown('<div class="twin-heading"><h2>Port de Jorf Lasfar</h2></div>',
                unsafe_allow_html=True)
    if postes.empty:
        st.info("Aucun poste actif sur la période filtrée."); return st_html(_MARKER_JS, height=1)

    markers = []
    for _, quay in postes.iterrows():
        position = PLAN_POSITIONS.get(_key(quay["poste"]))
        if not position:
            continue
        cls = CSS_BY_CLASS.get(quay["classe"], "optimal")
        is_sel = (str(selected or "").strip().upper() == str(quay["poste"]).strip().upper())
        sel_cls = " selected" if is_sel else ""
        diag_icon = DIAG_STYLE.get(quay["diag_classe"], ("⚠️",))[0]
        tooltip = (
            f"POSTE {quay['poste']}"
            f"%0AOccupation : {quay['occupation']:.0f} % · {CLASS_LABELS[quay['classe']]}"
            f"%0AEscales : {quay['escales']}"
            f"%0ASéjour moyen : {quay['sejour_moyen']:.1f} h"
            f"%0AProductivité : {quay['productivite']:.0f} t/h"
            f"%0A{diag_icon} {quay['diagnostic']}")
        color = CLASS_COLORS[quay["classe"]]
        markers.append(
            f'<a class="port-marker {cls}{sel_cls}" data-poste="{html.escape(str(quay["poste"]))}" '
            f'style="left:{position[0]}%;top:{position[1]}%;'
            f'background:{color};box-shadow:0 0 0 4px {color}33,0 0 14px {color}" '
            f'title="{tooltip}" href="#poste-{html.escape(str(quay["poste"]))}">'
            f'<span>{html.escape(str(quay["poste"]))}</span></a>')
    image = Path("assets/jorf_lasfar_aerial.png")
    source = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode() if image.exists() else ""
    st.markdown(f'''<div class="port-plan aerial-map"><img src="{source}" alt="Vue aérienne du Port de Jorf Lasfar">
        <div class="radar"><i></i><b></b><em></em></div><div class="sea-route route-one"></div>
        <div class="sea-route route-two"></div>
        <div class="facility terminal">TERMINAL<br>ROULIER</div>
        <div class="facility shipyard">CHANTIER<br>NAVAL</div>{"".join(markers)}</div>''',
                unsafe_allow_html=True)

    st.markdown('<div class="twin-tip">💡 <b>Cliquez sur un poste</b> de la carte pour ouvrir son analyse détaillée.</div>',
                unsafe_allow_html=True)

    # Interaction : sélection directe des postes actifs (clic marqueur ⇄ sélecteur)
    labels = [f"{r['poste']} · {r['occupation']:.0f}%"
              for _, r in postes.head(24).iterrows()]
    selected = st.selectbox("",
                            options=postes["poste"].tolist(),
                            format_func=lambda p: next((l for l in labels if l.startswith(str(p))), str(p)),
                            index=None,
                            placeholder="Choisir un poste…",
                            key="digital_twin_poste",
                            label_visibility="collapsed")
    if selected:
        st.session_state.selected_poste = str(selected)

    st.markdown('''<div class="twin-legend">
        <span class="legend-item"><i style="background:#56a8ff"></i>Sous-utilisé &lt;50 %</span>
        <span class="legend-item"><i style="background:#32d2a4"></i>Optimisé 50-70 %</span>
        <span class="legend-item"><i style="background:#f2b84b"></i>Très sollicité 70-80 %</span>
        <span class="legend-item"><i style="background:#ff6077"></i>Saturation ≥80 %</span></div>''',
                unsafe_allow_html=True)

    # Récupération clic → sélecteur : aucun rechargement, juste un rerun Streamlit.
    st_html(_MARKER_JS, height=1)
    return None
"""
Sliding Panel - Dashboard ANP
Affiche les détails du KPI sélectionné.
"""

import streamlit as st


def init_sliding_panel():
    """Initialise l'état du panneau."""

    if "selected_kpi" not in st.session_state:
        st.session_state.selected_kpi = None


def close_panel():
    """Ferme le panneau."""

    st.session_state.selected_kpi = None


def show_sliding_panel():

    if st.session_state.selected_kpi is None:
        return

    st.markdown("---")

    col1, col2 = st.columns([4, 1])

    with col1:

        st.markdown(
            f"""
            <div class="panel-title">

            📊 Analyse détaillée :
            <b>{st.session_state.selected_kpi.replace('_',' ').title()}</b>

            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        if st.button("✖ Fermer"):
            close_panel()
            st.rerun()

    st.markdown("")

    st.info(
        "Cette zone affichera automatiquement les graphiques et analyses "
        "du KPI sélectionné."
    )

    # ===========================
    # Exemple d'affichage
    # ===========================

    if st.session_state.selected_kpi == "trafic":

        st.subheader("📦 Trafic Portuaire")

        st.metric("Trafic Total", "2 350 000 T")

        st.write("Evolution mensuelle")

        st.bar_chart(
            {
                "Trafic": [
                    120,
                    180,
                    220,
                    190,
                    260,
                    300
                ]
            }
        )

    elif st.session_state.selected_kpi == "occupation":

        st.subheader("🏭 Occupation des quais")

        st.metric("Occupation moyenne", "74 %")

        st.progress(74)

        st.write("Répartition par quai")

        st.bar_chart(
            {
                "Occupation": [
                    55,
                    63,
                    74,
                    81,
                    67,
                    92
                ]
            }
        )

    elif st.session_state.selected_kpi == "attente":

        st.subheader("⏳ Délai moyen d'attente")

        st.metric("Attente", "5.2 h")

        st.line_chart(
            {
                "Attente": [
                    4,
                    5,
                    6,
                    5,
                    4,
                    3
                ]
            }
        )

    else:

        st.write(
            "Les visualisations détaillées de ce KPI seront ajoutées "
            "dans les prochaines étapes."
        )
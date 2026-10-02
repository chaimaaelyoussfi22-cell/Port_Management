"""
Interface utilisateur pour l'importation Excel
"""
import hashlib

import streamlit as st
import pandas as pd
from datetime import datetime

from import_engine import EscaleImporter, ConsignationImporter


def format_duration(seconds: float) -> str:
    """Formate une durée"""
    if seconds < 60:
        return f"{seconds:.1f} secondes"
    elif seconds < 3600:
        return f"{seconds/60:.1f} minutes"
    else:
        return f"{seconds/3600:.2f} heures"


def render_escale_import():
    """Affiche l'interface d'importation des escales"""
    st.markdown("""
    <style>
    .import-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 20px;
        margin: 16px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .import-card h3 {
        color: #0a1a2f;
        font-size: 1.1rem;
        font-weight: 700;
        margin-bottom: 12px;
    }
    .import-stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin: 16px 0;
    }
    .import-stat {
        background: #f8fafc;
        padding: 12px 16px;
        border-radius: 8px;
        text-align: center;
    }
    .import-stat .number {
        font-size: 1.5rem;
        font-weight: 800;
        color: #0a1a2f;
    }
    .import-stat .label {
        font-size: 0.7rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .import-success {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-left: 4px solid #10b981;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .import-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 4px solid #ef4444;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="import-card">
        <h3>📥 Importer des escales</h3>
        <p style="color: #6b7280; font-size: 0.9rem;">
            Sélectionnez un fichier Excel contenant les données d'escales.
            Les lignes ayant la même <strong>Escale</strong> seront automatiquement regroupées.
        </p>
        <p style="color: #6b7280; font-size: 0.85rem; margin-top: 8px;">
            ⚠️ Utilisez le champ <strong>Vérifier</strong> (0) ou <strong>N°</strong> (0) pour indiquer un changement de poste.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "📁 Choisir un fichier Excel",
        type=['xlsx', 'xls'],
        key="escale_uploader",
        help="Le fichier doit contenir une feuille avec les données d'escales"
    )
    
    if uploaded_file is None:
        st.info("👆 Veuillez sélectionner un fichier Excel pour commencer l'importation")
        return
        
    importer = EscaleImporter()
    
    with st.spinner("📖 Lecture du fichier..."):
        excel_data, sheet_names = importer.read_file(uploaded_file)
        if excel_data is None or not sheet_names:
            st.error("❌ Impossible de lire le fichier.")
            return
            
    # Sélection de la feuille
    default_sheet = None
    for sheet in sheet_names:
        sheet_lower = sheet.lower()
        if any(kw in sheet_lower for kw in ["n f", "n2", "escale", "navire"]):
            default_sheet = sheet
            break
            
    selected_sheet = st.selectbox(
        "Choisissez la feuille contenant les escales",
        sheet_names,
        index=sheet_names.index(default_sheet) if default_sheet in sheet_names else 0
    )
    
    with st.spinner(f"📖 Lecture de la feuille '{selected_sheet}'..."):
        df = importer.read_sheet(excel_data, selected_sheet)
        if df is None or df.empty:
            st.warning("⚠️ La feuille sélectionnée ne contient pas de données.")
            return
            
    st.caption(f"Colonnes détectées: {', '.join(df.columns.tolist())}")
    
    with st.expander("👁️ Aperçu des données brutes"):
        st.dataframe(df.head(10), use_container_width=True)
        st.caption(f"Total: {len(df)} lignes")
    
    # Empreinte du fichier analysé (nom + feuille + contenu) pour
    # invalider automatiquement un état d'analyse obsolète.
    file_fingerprint = hashlib.sha1(uploaded_file.getvalue()).hexdigest()
    analysis_key = f"{uploaded_file.name}|{selected_sheet}|{file_fingerprint}"

    # Analyse : le résultat est mémorisé dans st.session_state afin que
    # le bouton « Importer les escales » fonctionne au run Streamlit
    # suivant, sans dépendre du clic sur « Analyser ».
    if st.button("🚀 Analyser les données", type="primary", use_container_width=True):
        with st.spinner("🔍 Analyse des données..."):
            importer.process_dataframe(df)
            st.session_state["escale_importer"] = importer
            st.session_state["escale_import_key"] = analysis_key
            st.session_state.pop("escale_import_result", None)

    stored_importer = st.session_state.get("escale_importer")

    # Fichier ou feuille modifié depuis l'analyse → état obsolète
    if stored_importer is not None and st.session_state.get("escale_import_key") != analysis_key:
        st.session_state.pop("escale_importer", None)
        st.session_state.pop("escale_import_result", None)
        stored_importer = None

    if stored_importer is None:
        return

    # ===================== RÉSULTATS D'ANALYSE =====================
    report = stored_importer.report

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Lignes totales", report.nb_lignes)
    with col2:
        st.metric("✅ Lignes valides", report.nb_lignes_valides,
                 delta=f"{report.nb_lignes_valides/report.nb_lignes*100:.0f}%" if report.nb_lignes > 0 else None)
    with col3:
        st.metric("❌ Lignes invalides", report.nb_lignes_invalides)
    with col4:
        st.metric("⚠️ Doublons", report.nb_doublons)

    # Aperçu groupé par escale
    st.markdown("### 📋 Aperçu groupé par Escale")
    grouped_df = stored_importer.get_grouped_preview()
    st.dataframe(grouped_df, use_container_width=True)

    # Aperçu détaillé
    with st.expander("📋 Détail des lignes"):
        preview_df = stored_importer.get_preview_data()
        st.dataframe(preview_df, use_container_width=True)

    # Erreurs
    if report.errors:
        with st.expander(f"❌ Erreurs ({len(report.errors)})"):
            for error in report.errors[:20]:
                st.error(f"Ligne {error.get('row', '?')} (Escale {error.get('escale', '?')}): {error.get('error', '')}")
            if len(report.errors) > 20:
                st.warning(f"... et {len(report.errors) - 20} autres erreurs")

    # Hors référentiel Type E (ANP / RADE) - exclues de l'import
    if report.hors_referentiel_type_e:
        with st.expander(f"🚫 Hors référentiel Type E ({len(report.hors_referentiel_type_e)})", expanded=True):
            hr_df = pd.DataFrame(report.hors_referentiel_type_e)
            hr_df = hr_df.rename(columns={
                "escale": "Escale",
                "navire": "Navire",
                "type_e": "Type E original",
                "poste": "Poste",
                "tonnage": "Tonnage",
            })
            st.dataframe(hr_df, use_container_width=True)
            st.caption(
                "Escales exclues de l'import : les valeurs Type E « ANP » et « RADE » du fichier officiel "
                "ne font pas partie du référentiel de l'application (IMP / EXP / CAB / CAB EXP uniquement). "
                "Elles ne sont ni converties en IMP/EXP/CAB ni insérées dans la base."
            )

    # Avertissements
    if report.warnings:
        with st.expander(f"⚠️ Avertissements ({len(report.warnings)})"):
            for warning in report.warnings[:20]:
                st.warning(f"Ligne {warning.get('row', '?')}: {warning.get('warning', '')}")

    # ===================== IMPORTATION =====================
    nb_importables = report.nb_escales - len(report.hors_referentiel_type_e)
    if nb_importables > 0:
        st.info(f"ℹ️ {nb_importables} escale(s) prête(s) à être importées.")

        if st.button("✅ Importer les escales", type="primary", use_container_width=True):
            with st.spinner("💾 Importation en cours..."):
                nb_escales, nb_ops, errors = stored_importer.import_escales()

                # Rafraîchit les escales existantes : si l'utilisateur
                # reclique sur Importer sans réanalyser, les escales déjà
                # insérées sont détectées comme doublons et ignorées.
                try:
                    stored_importer._existing_escales = stored_importer.get_existing_escales()
                except Exception:
                    pass

                st.session_state["escale_import_result"] = {
                    "nb_escales": nb_escales,
                    "nb_ops": nb_ops,
                    "errors": list(errors),
                    "nb_lignes": report.nb_lignes,
                    "nb_valides": report.nb_lignes_valides,
                    "nb_ignorees": report.nb_lignes_invalides + report.nb_doublons,
                    "duree": report.duration_seconds,
                }

    else:
        st.warning("⚠️ Aucune escale valide à importer. Vérifiez les erreurs.")

    result = st.session_state.get("escale_import_result")
    if result is not None:
        if result["nb_escales"] > 0:
            st.markdown(f"""
            <div class="import-success">
                ✅ <strong>{result['nb_escales']} escale(s) importée(s) avec succès !</strong><br>
                📊 {result['nb_ops']} opération(s) créée(s)
            </div>
            """, unsafe_allow_html=True)
            st.balloons()
        else:
            st.markdown("""
            <div class="import-error">
                ❌ Aucune escale n'a été importée.
            </div>
            """, unsafe_allow_html=True)

        if result["errors"]:
            with st.expander(f"⚠️ Erreurs ({len(result['errors'])})"):
                for error in result["errors"][:20]:
                    st.error(error)

        # Rapport
        st.markdown(f"""
        <div style="background: #f8fafc; padding: 16px; border-radius: 8px; margin-top: 16px;">
            <strong>📊 Rapport d'importation</strong><br>
            Escales importées: {result['nb_escales']}<br>
            Lignes traitées: {result['nb_lignes']}<br>
            Lignes valides: {result['nb_valides']}<br>
            Lignes ignorées: {result['nb_ignorees']}<br>
            Durée: {format_duration(result['duree'])}
        </div>
        """, unsafe_allow_html=True)

    if report.errors:
        error_df = pd.DataFrame(report.errors)
        csv = error_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger le rapport d'erreurs",
            data=csv,
            file_name=f"rapport_import_escales_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )


def render_consignation_import():
    """Affiche l'interface d'importation des consignations"""
    st.markdown("""
    <div class="import-card">
        <h3>📥 Importer des consignations</h3>
        <p style="color: #6b7280; font-size: 0.9rem;">
            Sélectionnez un fichier Excel contenant les données de consignation des postes.
            Les dates et heures seront automatiquement extraites des colonnes <strong>Consignation</strong> et <strong>Déconsignation</strong>.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "📁 Choisir un fichier Excel",
        type=['xlsx', 'xls'],
        key="consignation_uploader",
        help="Le fichier doit contenir une feuille avec les données de consignation"
    )
    
    if uploaded_file is None:
        st.info("👆 Veuillez sélectionner un fichier Excel pour commencer l'importation")
        return
        
    importer = ConsignationImporter()
    
    with st.spinner("📖 Lecture du fichier..."):
        excel_data, sheet_names = importer.read_file(uploaded_file)
        if excel_data is None or not sheet_names:
            st.error("❌ Impossible de lire le fichier.")
            return
            
    # Sélection de la feuille
    default_sheet = None
    for sheet in sheet_names:
        sheet_lower = sheet.lower()
        if any(kw in sheet_lower for kw in ["consign", "bd consignation"]):
            default_sheet = sheet
            break
            
    selected_sheet = st.selectbox(
        "Choisissez la feuille contenant les consignations",
        sheet_names,
        index=sheet_names.index(default_sheet) if default_sheet in sheet_names else 0,
        key="consignation_sheet"
    )
    
    with st.spinner(f"📖 Lecture de la feuille '{selected_sheet}'..."):
        df = importer.read_sheet(excel_data, selected_sheet)
        if df is None or df.empty:
            st.warning("⚠️ La feuille sélectionnée ne contient pas de données.")
            return
            
    st.caption(f"Colonnes détectées: {', '.join(df.columns.tolist())}")
    
    with st.expander("👁️ Aperçu des données brutes"):
        st.dataframe(df.head(10), use_container_width=True)
        st.caption(f"Total: {len(df)} lignes")
    
    # Empreinte du fichier analysé (nom + feuille + contenu) pour
    # invalider automatiquement un état d'analyse obsolète.
    file_fingerprint = hashlib.sha1(uploaded_file.getvalue()).hexdigest()
    analysis_key = f"{uploaded_file.name}|{selected_sheet}|{file_fingerprint}"

    # Analyse : le résultat est mémorisé dans st.session_state afin que
    # le bouton « Importer les consignations » fonctionne au run Streamlit
    # suivant, sans dépendre du clic sur « Analyser ».
    if st.button("🚀 Analyser les données", type="primary", use_container_width=True, key="consignation_analyze"):
        with st.spinner("🔍 Analyse des données..."):
            rows = importer.process_dataframe(df)
            st.session_state["consignation_importer"] = importer
            st.session_state["consignation_import_key"] = analysis_key
            st.session_state.pop("consignation_import_result", None)

    stored_importer = st.session_state.get("consignation_importer")

    # Fichier ou feuille modifié depuis l'analyse → état obsolète
    if stored_importer is not None and st.session_state.get("consignation_import_key") != analysis_key:
        st.session_state.pop("consignation_importer", None)
        st.session_state.pop("consignation_import_result", None)
        stored_importer = None

    if stored_importer is None:
        return

    # ===================== RÉSULTATS D'ANALYSE =====================
    report = stored_importer.report
    rows = stored_importer.rows

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Lignes totales", report.nb_lignes)
    with col2:
        st.metric("✅ Lignes valides", report.nb_lignes_valides,
                 delta=f"{report.nb_lignes_valides/report.nb_lignes*100:.0f}%" if report.nb_lignes > 0 else None)
    with col3:
        st.metric("❌ Lignes invalides", report.nb_lignes_invalides)

    st.markdown("### 📋 Aperçu des données")
    preview_df = stored_importer.get_preview_data(rows)
    st.dataframe(preview_df, use_container_width=True)

    if report.errors:
        with st.expander(f"❌ Erreurs ({len(report.errors)})"):
            for error in report.errors[:20]:
                st.error(f"Ligne {error.get('row', '?')} (Poste {error.get('poste', '?')}): {error.get('error', '')}")

    valid_count = sum(1 for r in rows if r.is_valid)
    if valid_count > 0:
        st.info(f"ℹ️ {valid_count} consignation(s) prête(s) à être importées.")

        if st.button("✅ Importer les consignations", type="primary", use_container_width=True, key="confirm_consignation"):
            with st.spinner("💾 Importation en cours..."):
                imported, errors = stored_importer.import_consignations()

                # Marque comme doublons les lignes réellement présentes en
                # base : un second clic sans nouvelle analyse n'insère rien.
                try:
                    existing_now = stored_importer.get_existing_consignations()
                    for r in stored_importer.rows:
                        if r.is_valid and not r.is_duplicate:
                            d = r.cleaned_data or {}
                            h = d.get("heure_debut")
                            hpart = h.strftime("%H:%M:%S") if h is not None else "00:00"
                            key = f"{d.get('poste', '')}|{d.get('date_debut', '')}|{hpart}"
                            if key in existing_now:
                                r.is_duplicate = True
                except Exception:
                    pass

                st.session_state["consignation_import_result"] = {
                    "imported": imported,
                    "errors": list(errors),
                    "nb_lignes": report.nb_lignes,
                    "nb_valides": report.nb_lignes_valides,
                    "duree": report.duration_seconds,
                }

    else:
        st.warning("⚠️ Aucune consignation valide à importer.")

    result = st.session_state.get("consignation_import_result")
    if result is not None:
        if result["imported"] > 0:
            st.markdown(f"""
            <div class="import-success">
                ✅ <strong>{result['imported']} consignation(s) importée(s) avec succès !</strong>
            </div>
            """, unsafe_allow_html=True)
            st.balloons()
        else:
            st.markdown("""
            <div class="import-error">
                ❌ Aucune consignation n'a été importée.
            </div>
            """, unsafe_allow_html=True)

        if result["errors"]:
            with st.expander(f"⚠️ Erreurs ({len(result['errors'])})"):
                for error in result["errors"][:20]:
                    st.error(error)

        st.markdown(f"""
        <div style="background: #f8fafc; padding: 16px; border-radius: 8px; margin-top: 16px;">
            <strong>📊 Rapport d'importation</strong><br>
            Consignations importées: {result['imported']}<br>
            Lignes traitées: {result['nb_lignes']}<br>
            Lignes valides: {result['nb_valides']}<br>
            Durée: {format_duration(result['duree'])}
        </div>
        """, unsafe_allow_html=True)
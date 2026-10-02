# -*- coding: utf-8 -*-
"""Seuils et statuts centralisés (configurables en un seul endroit).

Aucun seuil métier ne doit être dispersé dans le code des vues :
tout passe par ce module.
"""

from typing import Dict

# ------------------------------------------------------------------
# Statut intelligent des postes selon le taux d'occupation (%)
# Seuil haut EXCLUSIF : occ < seuil => statut
# ------------------------------------------------------------------
OCCUPATION_STATUS: list = [
    {"max": 60, "label": "Normal", "icon": "🟢", "color": "#32d2a4"},
    {"max": 75, "label": "Élevé", "icon": "🟡", "color": "#f2d94b"},
    {"max": 90, "label": "Sous tension", "icon": "🟠", "color": "#ff9d66"},
    {"max": float("inf"), "label": "Critique", "icon": "🔴", "color": "#ff6077"},
]


def poste_status(occupation_pct: float) -> Dict:
    """Statut BI d'un poste pour un taux d'occupation donné."""
    for s in OCCUPATION_STATUS:
        if occupation_pct < s["max"]:
            return s
    return OCCUPATION_STATUS[-1]


# ------------------------------------------------------------------
# Seuils d'anomalies / alertes analytiques
# ------------------------------------------------------------------
ANOMALIES = {
    # Variation de l'occupation d'un poste jugée inhabituelle (points)
    "occupation_delta_pts": 10,
    # Attente moyenne d'un poste au-delà de laquelle on alerte (heures)
    "attente_poste_critique_h": 96,
    # Attente poste vs moyenne port (ratio) considérée comme anormale
    "attente_ratio_port": 1.5,
    # Baisse mensuelle du tonnage vs même mois N-1 (%)
    "tonnage_baisse_mensuelle_pct": -18,
    # Swing mensuel du nombre d'escales (%)
    "escales_swing_pct": 25,
    # Pic d'attente mensuel : ratio vs médiane des mois
    "attente_pic_ratio_mediane": 1.6,
}

# ------------------------------------------------------------------
# Bornes KPI (contexte tooltips / objectifs affichés)
# ------------------------------------------------------------------
KPI_CONTEXT = {
    "escales": "Nombre d'escales distinctes (COUNT DISTINCT n° d'escale) sur la période filtrée.",
    "navires": "Navires distincts ayant effectué au moins une escale sur la période.",
    "tonnage": "Tonnage total traité (Import + Export + Cabotage) sur la période.",
    "attente": "Attente moyenne = Sortie_Mouillage − Mouillage (heures). Une hausse est une dégradation.",
    "occupation": "Taux d'occupation RÉEL des postes à quai : temps physique occupé "
                  "(union dédupliquée des intervalles, changements de poste reconstruits, "
                  "RADE exclu) ÷ temps disponible.",
}


def fmt_period(start, end) -> str:
    """Libellé de période compact pour en-têtes/tooltips."""
    if not start or not end:
        return "Toutes les données"
    return f"{start:%d/%m/%Y} → {end:%d/%m/%Y}"

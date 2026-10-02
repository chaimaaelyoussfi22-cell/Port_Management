"""
Utilitaires pour l'application ANP
Calculs de temps, validation, formatage
"""
from datetime import datetime, time, date, timedelta
from typing import Optional, Tuple


def calculer_temps_attente(
    heure_arrivee: time,
    heure_accostage: time,
    date_arrivee: Optional[date] = None,
    date_accostage: Optional[date] = None
) -> Optional[float]:
    """
    Calcule le temps d'attente = heure accostage - heure arrivée
    """
    if not heure_arrivee or not heure_accostage:
        return None

    today = datetime.today().date()

    if date_arrivee:
        t1 = datetime.combine(date_arrivee, heure_arrivee)
    else:
        t1 = datetime.combine(today, heure_arrivee)

    if date_accostage:
        t2 = datetime.combine(date_accostage, heure_accostage)
    else:
        t2 = datetime.combine(today, heure_accostage)

    if t2 < t1:
        t2 = t2 + timedelta(days=1)

    return round((t2 - t1).total_seconds() / 3600, 2)


def calculer_temps_sejour(
    heure_accostage: time,
    heure_appareillage: time,
    date_accostage: Optional[date] = None,
    date_appareillage: Optional[date] = None
) -> Optional[float]:
    """
    Calcule le temps de séjour = date départ - date arrivée
    """
    if not heure_accostage or not heure_appareillage:
        return None

    today = datetime.today().date()

    if date_accostage:
        t1 = datetime.combine(date_accostage, heure_accostage)
    else:
        t1 = datetime.combine(today, heure_accostage)

    if date_appareillage:
        t2 = datetime.combine(date_appareillage, heure_appareillage)
    else:
        t2 = datetime.combine(today, heure_appareillage)

    if t2 < t1:
        t2 = t2 + timedelta(days=1)

    return round((t2 - t1).total_seconds() / 3600, 2)


def formater_duree(heures: float) -> str:
    """Formate une durée en heures en format lisible"""
    if heures is None:
        return "N/A"

    jours = int(heures // 24)
    heures_restantes = int(heures % 24)
    minutes = int((heures % 1) * 60)

    parties = []
    if jours > 0:
        parties.append(f"{jours}j")
    if heures_restantes > 0:
        parties.append(f"{heures_restantes}h")
    if minutes > 0:
        parties.append(f"{minutes}min")

    return " ".join(parties) if parties else "0h"


def valider_heures(
    heure_arrivee: time,
    heure_accostage: time,
    heure_appareillage: time
) -> Tuple[bool, str]:
    """Valide la cohérence des horaires"""
    if heure_accostage <= heure_arrivee:
        return False, "⚠️ L'heure d'accostage doit être postérieure à l'heure d'arrivée"

    if heure_appareillage <= heure_accostage:
        return False, "⚠️ L'heure d'appareillage doit être postérieure à l'heure d'accostage"

    return True, "✓ Horaires valides"
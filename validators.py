"""
VALIDATION - SOURCE UNIQUE DE VÉRITÉ POUR TOUT LE PROJET
==========================================================
Ce module est la SEULE source de vérité pour toute règle métier de
l'application ANP (Saisie ET Import Excel).

Contient :
  - validate_complete_operation()     → pour les escales (Saisie + Import)
  - validate_complete_consignation()  → pour les consignations (Saisie + Import)
  - Fonctions communes (dates, postes, etc.)

Principes :
  - Toutes les dates/heures sont optionnelles
  - Les validations chronologiques ne s'appliquent que si les DEUX dates existent
  - Chaque erreur porte le NOM DU CHAMP concerné
  - Collection de TOUTES les erreurs avant de lever une exception
"""
import re
import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Union, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ============================================================
# EXCEPTIONS
# ============================================================

class ValidationError(Exception):
    """Erreur de validation portant le nom du champ concerné."""
    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field or ""
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class MultiValidationError(ValidationError):
    """Regroupe plusieurs erreurs de validation."""
    def __init__(self, errors: List[Tuple[str, str]]):
        self.errors = errors
        message = " | ".join(f"{champ}: {msg}" for champ, msg in errors) if errors else "Erreur de validation"
        super().__init__(message)


# ============================================================
# RÉFÉRENTIELS OFFICIELS
# ============================================================

POSTES_VALIDES = [
    "1N", "1S", "1BIS", "1TER",
    "2N", "2BIS", "2TER",
    "4", "4BIS", "5", "6", "7",
    "3", "3BIS",
    "9",
    "14S",
    "8", "14N", "16N", "16S", "11_12", "13",
    "10",
]
POSTES_VALIDES_UPPER = [p.upper() for p in POSTES_VALIDES]

MODE_CONDITIONNEMENT_AUTORISES = ["V", "L", "C", "ANP"]

TYPE_OPERATION_MAP = {
    "IMP": "import", "IMPORT": "import",
    "EXP": "export", "EXPORT": "export",
    "CAB": "cabotage", "CABOTAGE": "cabotage",
    "CAB EXP": "cabotage",
}

UNITE_OFFICIELLE = "Tonnes"

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    "%d-%m-%y %H:%M:%S", "%d-%m-%y %H:%M",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y",
    "%d/%m/%y", "%d-%m-%y",
]

EXCEL_EPOCH = datetime(1899, 12, 30)


def parse_excel_datetime(value: Any) -> Optional[datetime]:
    """Convertit une valeur Excel/Pandas en datetime complet (date + heure).

    Règles :
    - None / vide / NaN            -> None (jamais 0000-00-00)
    - datetime / pandas.Timestamp / numpy.datetime64 -> conservé TEL QUEL (l'heure est gardée)
    - date (sans heure)            -> datetime à minuit
    - numéro de série Excel        -> fraction = heure/minute (conservée)
    - chaîne date+heure            -> datetime complet (jamais tronqué en date)
    - chaîne date seule            -> datetime à minuit

    Ne lève JAMAIS d'exception : retourne None si la valeur est ininterprétable.
    """
    import math
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
        if value.__class__.__module__.startswith("numpy") and "datetime64" in type(value).__name__:
            converted = value.astype("datetime64[us]").astype(object)
            if isinstance(converted, datetime):
                return converted
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and math.isnan(value):
                return None
            return EXCEL_EPOCH + timedelta(days=float(value))
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return None
            for fmt in DATE_FORMATS:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            return None
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    return None


# ============================================================
# NORMALISATION DES POSTES - VERSION CORRIGÉE
# ============================================================

def normalize_poste(value: Any) -> str:
    """
    Normalise un libellé de poste :
    - Insensible à la casse et aux espaces
    - Supprime les caractères invisibles (Unicode)
    - Conserve les underscores (ex: 11_12)
    - 'Poste 10' → '10'
    - 'Poste 5' → '5'
    - 'Port' / 'PORT' / 'port' → 'PORT'
    - '11' → '11_12'
    - '12' → '11_12'
    - '16' → '16N'
    - '1 bis', '1Bis', '1 BIS' → '1BIS'
    - '1 ter', '1Ter', '1 TER' → '1TER'
    """
    if not value:
        return ""
    
    original = str(value)
    
    # 1. Nettoyer : supprimer les caractères invisibles (Unicode)
    cleaned = re.sub(r'[\u200B\u200C\u200D\uFEFF\u00A0\u202F]', '', original)
    
    # 2. Supprimer les espaces et les tirets, mais GARDER les underscores !
    #    (les underscores font partie des noms de postes comme 11_12)
    cleaned = re.sub(r'[\s\-]+', '', cleaned).upper()
    
    # 3. Nettoyer les caractères parasites restants
    cleaned = cleaned.strip()
    
    # 4. Normaliser les underscores multiples en un seul
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # 5. Supprimer les underscores en début/fin
    cleaned = cleaned.strip('_')
    
    logger.debug(f"normalize_poste - '{original}' → '{cleaned}'")
    
    # === NORMALISATIONS SPÉCIALES ===
    
    # Cas A : "Poste 10" → "10", "Poste 5" → "5", etc.
    # Détecte "POSTE" suivi d'un nombre
    match_poste = re.match(r'^POSTE(\d+)$', cleaned)
    if match_poste:
        result = match_poste.group(1)
        logger.debug(f"normalize_poste - 'POSTE X' → '{result}'")
        return result
    
    # Cas B : PORT (consignation globale)
    if cleaned in ["PORT", "PORTS"]:
        logger.debug(f"normalize_poste - 'PORT' → 'PORT'")
        return "PORT"
    
    # Cas C et D : 11 et 12 → 11_12
    if cleaned in ["11", "12"]:
        logger.debug(f"normalize_poste - '11/12' → '11_12'")
        return "11_12"
    
    # Cas E : 16 → 16N
    if cleaned == "16":
        logger.debug(f"normalize_poste - '16' → '16N'")
        return "16N"
    
    # === POSTES AVEC UNDERSCORE ===
    if cleaned == "11_12":
        return "11_12"
    
    # === NORMALISATIONS STANDARD ===
    
    # Postes avec suffixe
    if cleaned in ["1BIS", "1TER", "2BIS", "2TER", "3BIS", "4BIS"]:
        return cleaned
    
    if cleaned in ["11_12", "14S", "14N", "16N", "16S", "RADE", "PORT"]:
        return cleaned
    
    # Postes numériques avec suffixe
    match = re.match(r'^(\d+)([A-Z]*)$', cleaned)
    if match:
        num, suffix = match.group(1), match.group(2) or ""
        result = f"{num}{suffix}" if suffix else num
        logger.debug(f"normalize_poste - '{cleaned}' → '{result}'")
        return result
    
    # Si rien ne correspond, retourner la valeur nettoyée
    return cleaned


def validate_poste(value: Any, field_name: str = "Poste", optional: bool = True) -> str:
    """
    Valide le poste.
    - Applique d'abord normalize_poste()
    - Vérifie ensuite si le poste normalisé est dans la liste des postes valides
    - 'PORT' est toujours considéré comme valide
    """
    if not value:
        if optional:
            return ""
        raise ValidationError("est obligatoire", field=field_name)
    
    poste = normalize_poste(value)
    
    # 'PORT' est toujours valide (consignation globale)
    if poste == "PORT":
        return poste
    
    # Vérifier si le poste est valide
    if poste != "RADE" and poste not in POSTES_VALIDES_UPPER:
        # Tentative de normalisation supplémentaire
        poste_clean = re.sub(r'[^A-Z0-9_]', '', poste)
        if poste_clean in POSTES_VALIDES_UPPER:
            return poste_clean
        raise ValidationError(f'"{value}" non reconnu', field=field_name)
    
    return poste


# ============================================================
# FONCTIONS COMMUNES
# ============================================================

def sanitize_text(text: Any, max_length: int = 500) -> str:
    """Nettoie et sécurise un texte."""
    if text is None:
        return ""
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[<>"\']', '', text)
    if len(text) > max_length:
        text = text[:max_length]
    return text


def validate_required(value: Union[str, None], field_name: str) -> str:
    """Vérifie qu'un champ n'est pas vide."""
    if value is None or not str(value).strip():
        raise ValidationError(f"{field_name} est obligatoire", field=field_name)
    return sanitize_text(str(value))


def validate_date_format(value: Any, field_name: str = "Date", optional: bool = True) -> Optional[datetime]:
    """Valide une date. Accepte les formats standard et les numéros de série Excel."""
    if value is None or value == "":
        if optional:
            return None
        raise ValidationError("est obligatoire", field=field_name)

    try:
        if isinstance(value, str) and not value.strip():
            if optional:
                return None
            raise ValidationError("est obligatoire", field=field_name)
        dt = parse_excel_datetime(value)
        if dt is None:
            raise ValueError(f'format non reconnu: "{value}"')
        return dt
    except (ValueError, TypeError) as e:
        raise ValidationError(str(e), field=field_name)


def validate_time_format(value: Any, field_name: str = "Heure", optional: bool = True) -> Optional[time]:
    """Valide une heure au format HH:MM ou HH:MM:SS."""
    if value is None or value == "":
        if optional:
            return None
        raise ValidationError("est obligatoire", field=field_name)

    if isinstance(value, time):
        return value

    value = str(value).strip()
    if not value:
        if optional:
            return None
        raise ValidationError("est obligatoire", field=field_name)

    match = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$', value)
    if not match:
        raise ValidationError(
            f'"{value}" doit être au format HH:MM (ex: 08:30)',
            field=field_name
        )

    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)

    if not (0 <= hour <= 23):
        raise ValidationError(f"heure invalide: {hour}h", field=field_name)
    if not (0 <= minute <= 59):
        raise ValidationError(f"minutes invalides: {minute}min", field=field_name)
    if not (0 <= second <= 59):
        raise ValidationError(f"secondes invalides: {second}sec", field=field_name)

    return time(hour, minute, second)


def validate_quantite(value: Union[str, float, None], field_name: str = "Quantité",
                       min_value: float = 0, max_value: float = 1_000_000) -> float:
    """Valide une quantité."""
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        quantite = float(value)
    except (ValueError, TypeError):
        raise ValidationError("doit être un nombre valide", field=field_name)
    if quantite < min_value:
        raise ValidationError(f"ne peut pas être négative (minimum: {min_value})", field=field_name)
    if quantite > max_value:
        raise ValidationError(f"trop élevée (maximum: {max_value:,.0f})", field=field_name)
    return quantite


def validate_mode_conditionnement(value: Any, field_name: str = "Mode de conditionnement") -> str:
    """Valide le mode de conditionnement."""
    if not value:
        return "V"
    v = str(value).strip().upper()
    if v not in MODE_CONDITIONNEMENT_AUTORISES:
        raise ValidationError(
            f'"{value}" invalide (autorisés: {", ".join(MODE_CONDITIONNEMENT_AUTORISES)})',
            field=field_name,
        )
    return v


def validate_type_operation(value: Any, field_name: str = "Type d'opération") -> str:
    """Valide le type d'opération."""
    if not value:
        raise ValidationError("est obligatoire", field=field_name)
    v = str(value).strip().upper()
    if v not in TYPE_OPERATION_MAP:
        raise ValidationError(
            f'"{value}" invalide (autorisés: IMP/IMPORT, EXP/EXPORT, CAB/CABOTAGE, CAB EXP)',
            field=field_name,
        )
    return TYPE_OPERATION_MAP[v]


def validate_motif_consignation(value: Any, field_name: str = "Motif") -> str:
    """Valide le motif de consignation."""
    if not value:
        return "Mauvais temps"
    return sanitize_text(value)


# ============================================================
# VALIDATEUR POUR LES ESCALES
# ============================================================

def validate_marchandises(marchandises: List[Dict[str, Any]],
                           field_name: str = "Marchandises") -> Tuple[List[str], List[str], float]:
    """Valide une liste de marchandises."""
    type_m_list: List[str] = []
    marchandise_list: List[str] = []
    total = 0.0

    for i, m in enumerate(marchandises, start=1):
        type_m = sanitize_text(m.get("type_m", "")).upper()
        marchandise = sanitize_text(m.get("marchandise", "")).upper()
        quantite = validate_quantite(m.get("quantite", 0), field_name=f"{field_name} #{i} - Quantité")

        if type_m and type_m not in type_m_list:
            type_m_list.append(type_m)
        if marchandise and marchandise not in marchandise_list:
            marchandise_list.append(marchandise)
        total += quantite

    return type_m_list, marchandise_list, total


def validate_complete_operation(data: Dict[str, Any], horaires: Dict[str, Any]) -> Dict[str, Any]:
    """Validation complète d'une opération d'escale.

    Navire / Opérateur / Consignataire sont traités comme texte libre
    (aucune règle d'obligation) : l'obligation de saisie n'est gérée que par
    l'interface de saisie manuelle, pas ici.
    """
    cleaned: Dict[str, Any] = {}
    errors: List[Tuple[str, str]] = []

    def _try(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValidationError as e:
            errors.append((e.field or fn.__name__, e.message))
            return None

    # CHAMPS IDENTITÉ : texte libre, aucune règle d'obligation.
    navire = sanitize_text(data.get("navire", ""))
    operateur = sanitize_text(data.get("operateur", ""))
    consignataire = sanitize_text(data.get("consignataire", ""))
    type_operation = _try(validate_type_operation, data.get("type_operation"))

    cleaned["navire"] = navire or ""
    cleaned["operateur"] = operateur or ""
    cleaned["consignataire"] = consignataire or ""
    cleaned["type_operation"] = type_operation or ""

    # CHAMPS OPTIONNELS
    cleaned["poste"] = _try(validate_poste, data.get("poste"), "Poste", True) or ""
    cleaned["pavillon"] = sanitize_text(data.get("pavillon", ""))
    cleaned["type_navire"] = sanitize_text(data.get("type_navire", ""))
    cleaned["mode_conditionnement"] = _try(validate_mode_conditionnement, data.get("mode_conditionnement")) or "V"
    cleaned["unite"] = UNITE_OFFICIELLE

    # MARCHANDISES
    if data.get("marchandises"):
        result = _try(validate_marchandises, data["marchandises"])
        type_m_list, marchandise_list, total_quantite = result if result else ([], [], 0.0)
    else:
        type_m = sanitize_text(data.get("type_marchandise", "")).upper()
        quantite = _try(validate_quantite, data.get("quantite", 0), "Quantité")
        type_m_list = [type_m] if type_m else []
        marchandise_list = [type_m] if type_m else []
        total_quantite = quantite if quantite is not None else 0.0

    cleaned["type_m_list"] = type_m_list
    cleaned["marchandise_list"] = marchandise_list
    cleaned["type_marchandise"] = type_m_list[0] if type_m_list else ""
    cleaned["quantite"] = total_quantite

    # HORAIRES
    date_rade = _try(validate_date_format, horaires.get("date_rade"), "Date Rade", True)
    heure_rade = _try(validate_time_format, horaires.get("heure_rade"), "Heure Rade", True)
    date_mouillage = _try(validate_date_format, horaires.get("date_mouillage"), "Date Mouillage", True)
    heure_mouillage = _try(validate_time_format, horaires.get("heure_mouillage"), "Heure Mouillage", True)
    date_sortie_mouillage = _try(validate_date_format, horaires.get("date_sortie_mouillage"), "Date Sortie Mouillage", True)
    heure_sortie_mouillage = _try(validate_time_format, horaires.get("heure_sortie_mouillage"), "Heure Sortie Mouillage", True)
    date_accostage = _try(validate_date_format, horaires.get("date_accostage"), "Date Accostage", True)
    heure_accostage = _try(validate_time_format, horaires.get("heure_accostage"), "Heure Accostage", True)
    date_app_quai = _try(validate_date_format, horaires.get("date_app_quai"), "Date Appareillage Quai", True)
    heure_app_quai = _try(validate_time_format, horaires.get("heure_app_quai"), "Heure Appareillage Quai", True)
    date_app_port = _try(validate_date_format, horaires.get("date_app_port"), "Date Appareillage Port", True)
    heure_app_port = _try(validate_time_format, horaires.get("heure_app_port"), "Heure Appareillage Port", True)

    # VALIDATION CHRONOLOGIQUE
    def _check_order(d1, t1, d2, t2, label1, label2, field_name):
        if d1 and d2:
            dt1 = datetime.combine(d1.date() if isinstance(d1, datetime) else d1, t1 or time(0, 0))
            dt2 = datetime.combine(d2.date() if isinstance(d2, datetime) else d2, t2 or time(0, 0))
            if dt2 < dt1:
                errors.append((field_name, f"{label2} est antérieur(e) à {label1}"))

    _check_order(date_rade, heure_rade, date_mouillage, heure_mouillage,
                 "la rade", "le mouillage", "Chronologie Mouillage")
    _check_order(date_mouillage, heure_mouillage, date_sortie_mouillage, heure_sortie_mouillage,
                 "le mouillage", "la sortie de mouillage", "Chronologie Sortie Mouillage")
    _check_order(date_accostage, heure_accostage, date_app_quai, heure_app_quai,
                 "l'accostage", "l'appareillage quai", "Chronologie Appareillage Quai")
    _check_order(date_app_quai, heure_app_quai, date_app_port, heure_app_port,
                 "l'appareillage quai", "l'appareillage port", "Chronologie Appareillage Port")
    if date_accostage and date_app_port and not date_app_quai:
        _check_order(date_accostage, heure_accostage, date_app_port, heure_app_port,
                     "l'accostage", "l'appareillage port", "Chronologie Appareillage Port")
    if date_rade and date_app_port:
        _check_order(date_rade, heure_rade, date_app_port, heure_app_port,
                     "la rade", "l'appareillage port", "Chronologie Appareillage Port")

    if errors:
        raise MultiValidationError(errors)

    cleaned["date_rade"] = date_rade.date() if date_rade else None
    cleaned["heure_rade"] = heure_rade
    cleaned["date_mouillage"] = date_mouillage.date() if date_mouillage else None
    cleaned["heure_mouillage"] = heure_mouillage
    cleaned["date_sortie_mouillage"] = date_sortie_mouillage.date() if date_sortie_mouillage else None
    cleaned["heure_sortie_mouillage"] = heure_sortie_mouillage
    cleaned["date_accostage"] = date_accostage.date() if date_accostage else None
    cleaned["heure_accostage"] = heure_accostage
    cleaned["date_app_quai"] = date_app_quai.date() if date_app_quai else None
    cleaned["heure_app_quai"] = heure_app_quai
    cleaned["date_app_port"] = date_app_port.date() if date_app_port else None
    cleaned["heure_app_port"] = heure_app_port

    return cleaned


# ============================================================
# VALIDATEUR POUR LES CONSIGNATIONS
# ============================================================

def validate_complete_consignation(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validation complète d'une consignation.
    Utilisée par la Saisie ET par l'Importation Excel.
    
    La validation du poste utilise normalize_poste() qui gère :
    - PORT → consignation globale
    - 11 → 11_12
    - 12 → 11_12
    - 16 → 16N
    - Poste 10 → 10
    - etc.
    """
    cleaned: Dict[str, Any] = {}
    errors: List[Tuple[str, str]] = []

    def _try(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValidationError as e:
            errors.append((e.field or fn.__name__, e.message))
            return None

    # CHAMPS OBLIGATOIRES
    poste = _try(validate_poste, data.get("poste"), "Poste", False)
    date_debut = _try(validate_date_format, data.get("date_debut"), "Date début", False)
    date_fin = _try(validate_date_format, data.get("date_fin"), "Date fin", False)

    cleaned["poste"] = poste or ""
    cleaned["date_debut"] = date_debut.date() if date_debut else None
    cleaned["date_fin"] = date_fin.date() if date_fin else None

    # CHAMPS OPTIONNELS
    heure_debut = _try(validate_time_format, data.get("heure_debut"), "Heure début", True)
    heure_fin = _try(validate_time_format, data.get("heure_fin"), "Heure fin", True)

    cleaned["heure_debut"] = heure_debut
    cleaned["heure_fin"] = heure_fin
    cleaned["motif"] = _try(validate_motif_consignation, data.get("motif")) or "Mauvais temps"
    cleaned["observations"] = sanitize_text(data.get("observations", ""))

    # VALIDATION CHRONOLOGIQUE
    if date_debut and date_fin:
        dt_debut = datetime.combine(date_debut, heure_debut or time(0, 0))
        dt_fin = datetime.combine(date_fin, heure_fin or time(0, 0))

        if dt_fin < dt_debut:
            errors.append(("Chronologie", "La date de fin est antérieure à la date de début"))

        if date_debut == date_fin and heure_fin and heure_debut and heure_fin <= heure_debut:
            errors.append(("Chronologie", "L'heure de fin doit être postérieure à l'heure de début"))

        # Calcul du nombre d'heures
        if dt_fin <= dt_debut:
            dt_fin = dt_fin + timedelta(days=1)
        diff = (dt_fin - dt_debut).total_seconds() / 3600
        cleaned["nombre_heures"] = max(1, int(diff) if diff == int(diff) else int(diff) + 1)

    if errors:
        raise MultiValidationError(errors)

    return cleaned
"""
MOTEUR D'IMPORTATION EXCEL - UNIQUE POUR TOUT LE PROJET
=========================================================
Contient :
  - EscaleImporter      → Import des escales
  - ConsignationImporter → Import des consignations

Les deux importateurs utilisent le même validateur (validators.py).
Aucune règle métier n'est implémentée ici : tout est délégué au validateur.
"""
import logging
import re
import time as time_module
from datetime import datetime, date, time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd

from database import DBManager, OperationRow
from validators import (
    ValidationError,
    MultiValidationError,
    validate_complete_operation,
    validate_complete_consignation,
    validate_date_format,
    parse_excel_datetime,
    normalize_poste,
    sanitize_text,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ============================================================
# PARTIE 1 - IMPORTATION DES ESCALES
# ============================================================

# Mapping officiel Excel -> Escales
ESCALE_COLUMN_MAP = {
    "escale": "Escale",
    "navire": "Navire",
    "pavillon": "Pavillon",
    "type_navire": "Type navire",
    "poste": "Poste",
    "consignataire": "Consignataire",
    "operateur": "Operateur",
    "rade": "RADE",
    "mouillage": "MOUILLAGE",
    "sortie_mouillage": "S MOUILLAGE",
    "accostage": "ACCOSTAGE",
    "app_quai": "APP QUAI",
    "app_port": "APP PORT",
    "type_operation": "type E",
    "type_m": "Type M",
    "marchandise": "Marchandise",
    "quantite": "Tonnage F",
    "mode_conditionnement": "Type N",
    "verifier": "Vérifier",
    "n_ligne": "N°",
}

# ============================================================
# DÉTECTION DES MARQUEURS 2ND OP - NORMALISÉ ET ROBUSTE
# ============================================================

# Pattern regex pour détecter "2ND OP" avec toutes ses variantes
# Accepte (insensible à la casse, espaces/tirets tolérés) :
#   2ND OP, 2nd op, 2EME OP, 2ème op, 2-ND OP, 2/ND OP,
#   2END OPERATEUR, 2ND OPERATEUR, 2END OP, 2eme esc, 2ème escale,
#   DEUXIÈME OP, DEUXIEME, etc.
SECOND_OP_PATTERN = re.compile(
    r'(?i)'  # Insensible à la casse
    r'(?:^|\s|-)'  # Borne gauche : début de chaîne, espace ou tiret
    r'(?:'
    r'2(?:END|NDE?|EME|ÈME|I[ÈE]?ME?|ND|EM|E|È)'  # 2END, 2ND(E), 2EME, 2ÈME, 2IÈME, 2EM, 2E
    r'|DEUXI?[ÈE]?ME?'  # DEUXIÈME / DEUXIEME / DEUXIME / DEUXME
    r')'
    r'(?:\s*(?:OP|OPÉRATEUR|OPERATEUR|OPERATION|OPÉRATION|OPÉRATRICE|OPERATRICE|ESCALE|ESC))?'  # Mots associés optionnels
    r'(?:$|\s|-)'  # Borne droite : fin de chaîne, espace ou tiret
)


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def _normalize_escale(value: Any) -> str:
    """Normalise une clé d'escale pour comparaison."""
    if value is None:
        return ""
    return re.sub(r'\s+', '', str(value)).strip().upper()


def _is_second_operation(text: str) -> bool:
    """
    Détecte si un texte contient une indication de deuxième opération.
    Utilise une expression régulière robuste pour toutes les variantes.
    """
    if not text:
        return False
    return bool(SECOND_OP_PATTERN.search(str(text)))


def _extract_numeric_value(text: str) -> str:
    """
    Extrait la valeur numérique d'une chaîne.
    Ex: "1" → "1", "1 2ND OP" → "1", "0" → "0"
    """
    if not text:
        return ""
    # Extrait le premier nombre trouvé
    match = re.search(r'^(\d+)', str(text).strip())
    return match.group(1) if match else ""


def _split_datetime(value: Any) -> Tuple[Optional[date], Optional[time]]:
    """
    Convertit une valeur Excel brute (chaîne "jj/mm/aaaa HH:MM", datetime,
    numéro de série Excel, ...) en couple (date, time).

    Retourne (None, None) si la valeur est absente ou non interprétable.
    Utilise validate_date_format : aucune règle métier n'est redéfinie ici.
    """
    if value is None or value == "":
        return None, None
    try:
        dt = validate_date_format(value, optional=True)
    except Exception:
        return None, None
    if dt is None:
        return None, None
    return dt.date(), dt.time()


# Format de date STRICT pour l'import Excel : uniquement JJ/MM/AA HH:MM.
# Appliqué exclusivement au flux d'importation (jamais à la saisie manuelle).
_IMPORT_DATETIME_FORMAT = "%d/%m/%y %H:%M"


def _parse_strict_import_datetime(value: Any) -> Optional[datetime]:
    """Parse STRICTEMENT une date d'import au format JJ/MM/AA HH:MM.

    - None / vide -> None (champ absent, accepté)
    - Chaîne au format "JJ/MM/AA HH:MM" -> datetime complet (heure conservée)
    - datetime / pandas.Timestamp / numéro de série Excel -> datetime complet
    - Tout autre format illisible -> ValidationError avec la valeur problématique.

    L'heure et les minutes ne sont JAMAIS supprimées : un datetime reste complet.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return datetime.strptime(v, _IMPORT_DATETIME_FORMAT)
        except ValueError:
            pass
        # Format non strict : on délègue au parseur général (ISO, JJ/MM/AAAA,
        # JJ/MM/AA HH:MM:SS, etc.). Une valeur restée illisible est rejetée.
        dt = parse_excel_datetime(value)
        if dt is not None:
            return dt
        raise ValidationError(
            f"format non reconnu : \"{value}\" (attendu JJ/MM/AA HH:MM)",
            field="Date",
        )
    # Objet datetime / pandas.Timestamp / numérique Excel → conservé tel quel.
    dt = parse_excel_datetime(value)
    if dt is not None:
        return dt
    raise ValidationError(
        f"type non supporté : \"{value}\" (attendu JJ/MM/AA HH:MM)",
        field="Date",
    )


def _build_movement_entry(raw: Dict[str, Any], row_index: int) -> Dict[str, Any]:
    """
    Construit l'entrée d'un mouvement (opération principale N°=1 ou changement
    de poste N°=0) compatible avec les DEUX contrats de consommation :

    - Contrat "reconstruction horaires" (clés *_raw) : consommé par
      build_operation_from_escale() pour alimenter operations. Les données
      de mouillage / sortie mouillage sont préservées ici.
    - Contrat "base de données" (poste, date_accostage, heure_accostage,
      date_app_quai, heure_app_quai) : attendu par
      DBManager.insert_operation() pour la table poste_changes, identique
      au contrat produit par la saisie manuelle.

    Aucune valeur fictive : si une composante date/heure est absente ou
    illisible dans l'Excel, la clé correspondante vaut None et l'entrée ne
    sera pas retenue pour insertion dans poste_changes (voir
    build_operation_from_escale).
    """
    acc_date, acc_time = _split_datetime(raw.get("accostage"))
    aq_date, aq_time = _split_datetime(raw.get("app_quai"))

    return {
        "row_index": row_index,
        # --- Contrat reconstruction horaires (préservé) ---
        "poste_raw": raw.get("poste", ""),
        "mouillage_raw": raw.get("mouillage"),
        "sortie_mouillage_raw": raw.get("sortie_mouillage"),
        "accostage_raw": raw.get("accostage"),
        "app_quai_raw": raw.get("app_quai"),
        # --- Contrat base de données (table poste_changes) ---
        "poste": normalize_poste(raw.get("poste", "")),
        "date_accostage": acc_date,
        "heure_accostage": acc_time,
        "date_app_quai": aq_date,
        "heure_app_quai": aq_time,
    }


def _main_operation_signature(raw: Dict[str, Any]) -> Tuple[str, ...]:
    """
    Signature d'une opération principale (N°=1) au sein d'une escale.

    Utilisée pour distinguer, dans une même escale, deux lignes N°=1 qui
    représentent DEUX OPÉRATIONS DISTINCTES (import + export, second
    opérateur, ...) d'une ligne N°=1 réellement DUPLIQUÉE.

    - Deux lignes N°=1 avec la même signature → vraie doublure (incohérence)
    - Deux lignes N°=1 avec des signatures différentes → opérations distinctes
      présentes dans le fichier officiel ANP : elles ne sont pas une erreur.
    """
    def _norm(v: Any) -> str:
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).strip().lower()

    return (
        _norm(raw.get("poste")),
        _norm(raw.get("type_operation")),
        _norm(raw.get("type_m")),
        _norm(raw.get("marchandise")),
        _norm(raw.get("quantite")),
        _norm(raw.get("operateur")),
        _norm(raw.get("consignataire")),
        _norm(raw.get("mode_conditionnement")),
        _norm(raw.get("rade")),
        _norm(raw.get("mouillage")),
        _norm(raw.get("sortie_mouillage")),
        _norm(raw.get("accostage")),
        _norm(raw.get("app_quai")),
        _norm(raw.get("app_port")),
    )


# ============================================================
# STRUCTURES DE DONNÉES
# ============================================================

@dataclass
class EscaleImportRow:
    row_index: int
    raw_data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_valid: bool = False
    is_duplicate: bool = False
    escale_key: str = ""
    row_type: Optional[str] = None
    original_order: int = 0


@dataclass
class EscaleImportReport:
    nb_lignes: int = 0
    nb_lignes_valides: int = 0
    nb_lignes_invalides: int = 0
    nb_escales: int = 0
    nb_operations_importees: int = 0
    nb_doublons: int = 0
    nb_marchandises: int = 0
    nb_changements_poste: int = 0
    nb_second_operations: int = 0
    hors_referentiel_type_e: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class ReconstructedEscale:
    escale: str
    navire: str = ""
    pavillon: str = ""
    type_navire: str = ""
    consignataire: str = ""
    operateur: str = ""
    type_operation_raw: str = ""
    mode_conditionnement_raw: str = ""
    poste_principal_raw: str = ""
    main_operation: Optional[Dict[str, Any]] = None
    poste_changes: List[Dict[str, Any]] = field(default_factory=list)
    second_operations: List[Dict[str, Any]] = field(default_factory=list)
    marchandises: List[Dict[str, Any]] = field(default_factory=list)
    date_rade_raw: Any = None
    date_app_port_raw: Any = None
    source_rows: List[int] = field(default_factory=list)

    def add_marchandise(self, type_m: str, marchandise: str, quantite: Any):
        if not type_m and not marchandise:
            return
        self.marchandises.append({"type_m": type_m, "marchandise": marchandise, "quantite": quantite})


# ============================================================
# CLASSE PRINCIPALE - ESCALE IMPORTER
# ============================================================

class EscaleImporter:
    """Importateur d'escales - Utilise validators.validate_complete_operation()"""

    def __init__(self):
        self.db = DBManager()
        self.report = EscaleImportReport()
        self.rows: List[EscaleImportRow] = []
        self._existing_escales: set = set()
        self._reconstructed_escales: Dict[str, ReconstructedEscale] = {}
        self._hors_referentiel_escales: set = set()

    # ============================================================
    # LECTURE DU FICHIER EXCEL
    # ============================================================

    def read_file(self, file) -> Tuple[Optional[pd.ExcelFile], List[str]]:
        try:
            excel_data = pd.ExcelFile(file)
            return excel_data, excel_data.sheet_names
        except Exception as e:
            logger.exception("Erreur lecture fichier Excel")
            return None, [f"Impossible de lire le fichier : {e}"]

    def read_sheet(self, excel_data: pd.ExcelFile, sheet_name: str) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_excel(excel_data, sheet_name=sheet_name, header=0)
            return df
        except Exception as e:
            logger.exception(f"Erreur lecture feuille '{sheet_name}'")
            return None

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.strip()
            return value if value != "" else None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    def get_existing_escales(self) -> set:
        try:
            conn = self.db._connect()
            if conn is None:
                return set()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT numero_navire FROM operations WHERE numero_navire IS NOT NULL")
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return {_normalize_escale(r[0]) for r in results}
        except Exception:
            logger.exception("Erreur récupération escales existantes")
            return set()

    # ============================================================
    # DÉTECTION DES TYPES DE LIGNES - VERSION PROFESSIONNELLE
    # ============================================================

    def _determine_row_type(self, raw: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Détermine le type de ligne en analysant N° et Vérifier.
        
        RÈGLES MÉTIER :
        ===============
        
        1. OPÉRATION PRINCIPALE (main)
           - N° = 1
           - ET aucune indication "2ND OP" dans N° ou Vérifier
           - Exemple : N°=1, Vérifier=vide
           
        2. CHANGEMENT DE POSTE (change)
           - N° = 0
           - ET (Poste renseigné OU Accostage renseigné OU App Quai renseigné)
           
        3. FIN D'ESCALE / DÉPART PORT (change - sans validation poste)
           - N° = 0
           - ET Poste vide
           - ET Accostage vide
           - ET App Quai vide
           - ET App Port renseigné
           - Ce cas est traité comme un changement de poste mais sans
             validation du poste (poste non obligatoire)
           
         4. DEUXIÈME OPÉRATION (second_operation)
           - Accepter TOUTES les variantes suivantes :
             a) N° = "1 2ND OP", Vérifier = vide
             b) N° = "1", Vérifier = "2ND OP"
             c) N° = "1 2nd op", Vérifier = vide
             d) N° = "1-2ND OP", Vérifier = vide
             e) N° = "1 / 2ND OP", Vérifier = vide
             f) N° = "1", Vérifier = "2EME OP"
             g) N° = "1", Vérifier = "2ème op"
             h) N° = "2ND OP", Vérifier = vide (cas rare)
             i) N° = "1", Vérifier = "2ND"
             j) N° = "1", Vérifier = "2EME"
             k) N° = "1", Vérifier = "2END OPERATEUR"   (fiche officielle ANP)
             l) N° = "1", Vérifier = "2ND OPERATEUR"    (fiche officielle ANP)
             m) N° = "1", Vérifier = "2eme esc"         (fiche officielle ANP)

        La détection est insensible à la casse, ignore les espaces avant/après
        et tolère les espaces ou tirets manquants (ex: "2ENDOPERATEUR").

        5. CHANGEMENT DE POSTE AVEC MARQUEUR 2ND OP (change)
           - N° = 0
           - ET un marqueur de deuxième opération dans Vérifier
             (ex: N°=0, Vérifier="2END OPERATEUR", Poste=16S)
           - Le marqueur annote simplement l'opération concernée : la ligne
             reste un changement de poste et doit être importée comme telle.
        """
        n_value = raw.get("n_ligne")
        verifier = raw.get("verifier")
        
        # Nettoyer et normaliser
        n_str = str(n_value).strip() if n_value is not None else ""
        v_str = str(verifier).strip() if verifier is not None else ""
        
        # Extraire la valeur numérique de N°
        n_num = _extract_numeric_value(n_str)
        
        # Détecter si c'est une deuxième opération
        is_second_in_n = _is_second_operation(n_str)
        is_second_in_v = _is_second_operation(v_str)
        is_second = is_second_in_n or is_second_in_v
        
        # Cas spécial : N° contient "2ND OP" sans chiffre
        if not n_num and is_second_in_n:
            return "second_operation", None
        
        # La combinaison N° / Vérifier n'est jamais un motif de rejet :
        # elle sert uniquement de classification. Les cas non reconnus
        # retombent sur "main" (ligne traitée comme opération principale),
        # sans jamais invalider la ligne.
        if n_num == "":
            return "main", None
        
        # === OPÉRATION PRINCIPALE ===
        if n_num == "1" and not is_second:
            return "main", None
        
        # === DEUXIÈME OPÉRATION ===
        if n_num == "1" and is_second:
            return "second_operation", None
        
        # === N° = 0 : Changement de poste OU Départ du port ===
        # Un marqueur 2ND OP dans Vérifier (ex: "2END OPERATEUR") ne change
        # rien au rôle de la ligne : N°=0 avec un poste = changement de poste
        # (du second opérateur le cas échéant). La ligne doit être importée.
        if n_num == "0":
            has_poste = bool(raw.get("poste"))
            has_accostage = bool(raw.get("accostage"))
            has_app_quai = bool(raw.get("app_quai"))
            has_app_port = bool(raw.get("app_port"))
            
            # Changement de poste (avec poste ou accostage ou app quai)
            if has_poste or has_accostage or has_app_quai:
                return "change", None
            
            # Départ du port / événement de mouillage seul
            if has_app_port or raw.get("mouillage") or raw.get("sortie_mouillage"):
                return "change", None
            
            # N°=0 sans aucune information
            return "main", None
        
        # Aucun type reconnu : la ligne est tout de même importée (main).
        return "main", None

    def _extract_raw_data(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {key: self._clean_value(record.get(col)) for key, col in ESCALE_COLUMN_MAP.items()}

    def process_dataframe(self, df: pd.DataFrame) -> List[EscaleImportRow]:
        self.rows = []
        self.report = EscaleImportReport()
        self.report.start_time = datetime.now()
        self.report.nb_lignes = len(df)
        self._existing_escales = self.get_existing_escales()

        try:
            records = df.to_dict(orient="records")
        except Exception as e:
            logger.exception("Erreur conversion DataFrame")
            self.report.errors.append({"row": None, "escale": "", "champ": "Fichier", "error": str(e)})
            return self.rows

        for idx, record in enumerate(records):
            excel_row_number = idx + 2
            try:
                raw_data = self._extract_raw_data(record)
                row_type, type_error = self._determine_row_type(raw_data)

                escale_val = str(raw_data.get("escale") or "")
                import_row = EscaleImportRow(
                    row_index=excel_row_number,
                    raw_data=raw_data,
                    row_type=row_type,
                    original_order=idx,
                    escale_key=escale_val if escale_val else f"__ligne_{excel_row_number}",
                )

                if type_error:
                    import_row.errors.append(type_error)

                # Validation du poste pour changement de poste
                # Note : row_type peut être "change" même sans poste
                # dans le cas d'un départ de port. On ne valide le poste
                # que s'il y a effectivement un poste.
                if row_type == "change" and raw_data.get("poste"):
                    # Le poste est présent, on le laisse passer
                    pass

                if row_type == "second_operation" and not (raw_data.get("type_m") or raw_data.get("marchandise")):
                    import_row.errors.append("Type M ou Marchandise obligatoire pour une seconde opération")

                escale = raw_data.get("escale")
                if escale:
                    escale_norm = _normalize_escale(escale)
                    if escale_norm in self._existing_escales:
                        import_row.is_duplicate = True
                        import_row.warnings.append(f"L'Escale {escale} existe déjà en base")

                import_row.is_valid = not import_row.errors

            except Exception as e:
                logger.exception(f"Erreur ligne {excel_row_number}")
                import_row = EscaleImportRow(
                    row_index=excel_row_number, raw_data=record, is_valid=False, original_order=idx,
                )
                import_row.errors.append(f"Erreur inattendue : {e}")

            self.rows.append(import_row)
            if import_row.is_valid:
                self.report.nb_lignes_valides += 1
            else:
                self.report.nb_lignes_invalides += 1
                for error in import_row.errors:
                    self.report.errors.append({
                        "row": import_row.row_index,
                        "escale": import_row.escale_key,
                        "champ": "Ligne",
                        "error": error,
                    })

        self._reconstruct_escales()
        return self.rows

    def _reconstruct_escales(self):
        grouped: Dict[str, List[EscaleImportRow]] = defaultdict(list)
        for row in self.rows:
            if row.is_valid and row.escale_key:
                grouped[row.escale_key].append(row)

        for escale, rows in grouped.items():
            rows_sorted = sorted(rows, key=lambda r: r.original_order)
            main_rows = [r for r in rows_sorted if r.row_type == "main"]

            if len(main_rows) > 1:
                # Le fichier officiel ANP peut légitimement contenir plusieurs
                # lignes N°=1 pour une même escale : elles représentent alors
                # des opérations distinctes (import + export, second opérateur,
                # chargement complémentaire, ...).
                # Le simple fait d'avoir plusieurs N°=1 n'est PAS une erreur :
                # il faut comparer la structure réelle des lignes.
                #  - Signatures différentes  → opérations distinctes à importer
                #    (les lignes N°=1 supplémentaires deviennent des 2nd ops).
                #  - Même signature          → vraie doublure (incohérence).
                first_signature = _main_operation_signature(main_rows[0].raw_data)
                real_duplicates: List[EscaleImportRow] = []
                for candidate in main_rows[1:]:
                    if _main_operation_signature(candidate.raw_data) == first_signature:
                        real_duplicates.append(candidate)
                    else:
                        candidate.row_type = "second_operation"

                if real_duplicates:
                    lignes = ", ".join(str(r.row_index) for r in real_duplicates)
                    self.report.errors.append({
                        "row": main_rows[0].row_index,
                        "escale": escale,
                        "champ": "Opération principale",
                        "error": f'Deux opérations principales (N°=1) identiques détectées (lignes {lignes})'
                    })
                    continue

            escale_obj = ReconstructedEscale(escale=escale)
            escale_obj.source_rows = [r.row_index for r in rows_sorted]

            for row in rows_sorted:
                raw = row.raw_data

                if raw.get("navire") and not escale_obj.navire:
                    escale_obj.navire = str(raw["navire"]).strip()
                if raw.get("pavillon") and not escale_obj.pavillon:
                    escale_obj.pavillon = str(raw["pavillon"]).strip()
                if raw.get("type_navire") and not escale_obj.type_navire:
                    escale_obj.type_navire = str(raw["type_navire"]).strip()
                if raw.get("consignataire") and not escale_obj.consignataire:
                    escale_obj.consignataire = str(raw["consignataire"]).strip()
                if raw.get("operateur") and not escale_obj.operateur:
                    escale_obj.operateur = str(raw["operateur"]).strip()
                if raw.get("type_operation") and not escale_obj.type_operation_raw:
                    escale_obj.type_operation_raw = raw["type_operation"]
                if raw.get("mode_conditionnement") and not escale_obj.mode_conditionnement_raw:
                    escale_obj.mode_conditionnement_raw = raw["mode_conditionnement"]

                if raw.get("rade") and escale_obj.date_rade_raw is None:
                    escale_obj.date_rade_raw = raw["rade"]
                if raw.get("app_port"):
                    escale_obj.date_app_port_raw = raw["app_port"]

                if raw.get("type_m") or raw.get("marchandise"):
                    escale_obj.add_marchandise(
                        sanitize_text(raw.get("type_m", "")).upper(),
                        sanitize_text(raw.get("marchandise", "")).upper(),
                        raw.get("quantite") or 0.0,
                    )

                entry = _build_movement_entry(raw, row.row_index)

                if row.row_type == "main":
                    escale_obj.main_operation = entry
                elif row.row_type == "change":
                    escale_obj.poste_changes.append(entry)
                elif row.row_type == "second_operation":
                    escale_obj.second_operations.append(entry)

            if escale_obj.main_operation and escale_obj.main_operation.get("poste_raw"):
                escale_obj.poste_principal_raw = str(escale_obj.main_operation["poste_raw"]).strip()

            self._reconstructed_escales[escale] = escale_obj

        self.report.nb_escales = len(self._reconstructed_escales)
        self.report.nb_marchandises = sum(len(e.marchandises) for e in self._reconstructed_escales.values())
        self.report.nb_changements_poste = sum(len(e.poste_changes) for e in self._reconstructed_escales.values())
        self.report.nb_second_operations = sum(len(e.second_operations) for e in self._reconstructed_escales.values())

        # === TYPE E HORS RÉFÉRENTIEL (ANP / RADE) ===
        # Les valeurs « ANP » / « anp » / « RADE » du fichier officiel ne font
        # PAS partie du référentiel Type E de l'application (IMP/EXP/CAB/CAB EXP).
        # Elles ne sont ni converties en IMP/EXP/CAB ni créées comme nouveau type :
        # les escales concernées sont simplement exclues de l'import et listées
        # ici pour contrôle (aucune insertion dans operations).
        for escale, obj in self._reconstructed_escales.items():
            type_e = (obj.type_operation_raw or "").strip().upper()
            if type_e in ("ANP", "RADE"):
                tonnage = sum(float(m.get("quantite") or 0) for m in obj.marchandises)
                self.report.hors_referentiel_type_e.append({
                    "escale": escale,
                    "navire": obj.navire,
                    "type_e": obj.type_operation_raw,
                    "poste": obj.poste_principal_raw,
                    "tonnage": tonnage,
                })
                self._hors_referentiel_escales.add(escale)

    def build_operation_from_escale(self, escale_obj: ReconstructedEscale) -> Tuple[Optional[OperationRow], List[str]]:
        first_row = escale_obj.source_rows[0] if escale_obj.source_rows else "?"

        data = {
            "navire": escale_obj.navire,
            "poste": escale_obj.poste_principal_raw,
            "operateur": escale_obj.operateur,
            "consignataire": escale_obj.consignataire,
            "type_operation": escale_obj.type_operation_raw,
            "type_navire": escale_obj.type_navire,
            "pavillon": escale_obj.pavillon,
            "mode_conditionnement": escale_obj.mode_conditionnement_raw,
            "marchandises": escale_obj.marchandises,
        }

        main_op = escale_obj.main_operation or {}
        first_change = escale_obj.poste_changes[0] if escale_obj.poste_changes else {}

        # Les horaires Excel sont convertis via _parse_strict_import_datetime,
        # qui accepte JJ/MM/AA HH:MM, les formats ISO/datetime et pandas.Timestamp
        # en conservant l'heure (PARTIE DATETIME COMPLÈTE, jamais tronquée en date).
        # Chaque valeur est ensuite scindée en (date, heure) pour la validation.
        _HORAIRE_COLUMNS = {
            "date_rade": "RADE",
            "date_mouillage": "MOUILLAGE",
            "date_sortie_mouillage": "S MOUILLAGE",
            "date_accostage": "ACCOSTAGE",
            "date_app_quai": "APP QUAI",
            "date_app_port": "APP PORT",
        }
        _horaires_raw = {
            "date_rade": escale_obj.date_rade_raw,
            "date_mouillage": main_op.get("mouillage_raw") or first_change.get("mouillage_raw"),
            "date_sortie_mouillage": main_op.get("sortie_mouillage_raw") or first_change.get("sortie_mouillage_raw"),
            "date_accostage": main_op.get("accostage_raw") or first_change.get("accostage_raw"),
            "date_app_quai": main_op.get("app_quai_raw") or first_change.get("app_quai_raw"),
            "date_app_port": escale_obj.date_app_port_raw,
        }
        horaires = {}
        try:
            for key, raw_value in _horaires_raw.items():
                dt = _parse_strict_import_datetime(raw_value)
                if dt is None:
                    horaires[key] = None
                    horaires["heure_" + key[len("date_"):]] = None
                else:
                    # L'heure/minute du datetime Excel est CONSERVÉE :
                    # la date part dans date_* , l'heure dans heure_* .
                    horaires[key] = dt.date()
                    horaires["heure_" + key[len("date_"):]] = dt.time()
        except ValidationError as e:
            return None, [f"Ligne {first_row}\nESCALE {escale_obj.escale}\n{_HORAIRE_COLUMNS[key]}\n{e.message}"]

        try:
            cleaned = validate_complete_operation(data, horaires)
        except MultiValidationError as e:
            return None, [f"Ligne {first_row}\nESCALE {escale_obj.escale}\n{champ}\n{msg}" for champ, msg in e.errors]
        except ValidationError as e:
            return None, [f"Ligne {first_row}\nESCALE {escale_obj.escale}\n{e.field or 'Validation'}\n{e.message}"]
        except Exception as e:
            logger.exception(f"Erreur validation escale {escale_obj.escale}")
            return None, [f"Ligne {first_row}\nESCALE {escale_obj.escale}\nValidation\n{e}"]

        date_principale = (
            cleaned["date_rade"] or cleaned["date_mouillage"] or cleaned["date_accostage"]
            or cleaned["date_app_quai"] or cleaned["date_app_port"]
        )

        # === FILTRAGE DES CHANGEMENTS DE POSTE POUR LA BASE ===
        # La table poste_changes impose date_accostage / heure_accostage /
        # date_app_quai / heure_app_quai NOT NULL (contrat identique à la saisie
        # manuelle). Seuls les changements dont les quatre composantes sont
        # présentes et lisibles dans l'Excel sont insérables ; les autres sont
        # signalés dans le rapport sans qu'aucune valeur ne soit inventée.
        db_poste_changes = []
        for ch in escale_obj.poste_changes:
            required_keys = ("date_accostage", "heure_accostage", "date_app_quai", "heure_app_quai")
            if all(ch.get(k) is not None for k in required_keys):
                db_poste_changes.append(ch)
                continue

            has_raw_dates = bool(ch.get("accostage_raw") or ch.get("app_quai_raw"))
            if has_raw_dates:
                motif = "dates présentes mais illisibles dans le fichier"
                self.report.errors.append({
                    "row": ch.get("row_index"),
                    "escale": escale_obj.escale,
                    "champ": "Changement de poste",
                    "error": (
                        f"ESCALE {escale_obj.escale} : changement de poste "
                        f"(ligne {ch.get('row_index', '?')}) avec {motif} : "
                        f"non enregistré dans l'historique des changements."
                    ),
                })
            else:
                motif = "sans accostage / appareillage à quai exploitables (mouillage ou départ port seul)"
                self.report.warnings.append({
                    "row": ch.get("row_index"),
                    "escale": escale_obj.escale,
                    "warning": (
                        f"ESCALE {escale_obj.escale} : changement de poste "
                        f"(ligne {ch.get('row_index', '?')}) {motif} : "
                        f"non enregistré dans l'historique des changements."
                    ),
                })

        def _heure_ou_vide(h):
            return str(h) if h else ""

        try:
            row = OperationRow(
                date=str(date_principale) if date_principale else "",
                navire=cleaned["navire"],
                id_navire=escale_obj.escale,
                pavillon=cleaned["pavillon"],
                type_navire=cleaned["type_navire"],
                poste=cleaned["poste"],
                type_operation=cleaned["type_operation"],
                unite=cleaned["unite"],
                quantite=cleaned["quantite"],
                operateur=cleaned["operateur"],
                type_marchandise=cleaned["type_marchandise"],
                mode_conditionnement=cleaned["mode_conditionnement"],
                heure_rade=_heure_ou_vide(cleaned["heure_rade"]),
                heure_mouillage=_heure_ou_vide(cleaned["heure_mouillage"]),
                heure_sortie_mouillage=_heure_ou_vide(cleaned["heure_sortie_mouillage"]),
                heure_accostage=_heure_ou_vide(cleaned["heure_accostage"]),
                heure_app_quai=_heure_ou_vide(cleaned["heure_app_quai"]),
                heure_app_port=_heure_ou_vide(cleaned["heure_app_port"]),
                date_rade=str(cleaned["date_rade"]) if cleaned["date_rade"] else "",
                date_mouillage=str(cleaned["date_mouillage"]) if cleaned["date_mouillage"] else "",
                date_sortie_mouillage=str(cleaned["date_sortie_mouillage"]) if cleaned["date_sortie_mouillage"] else "",
                date_accostage=str(cleaned["date_accostage"]) if cleaned["date_accostage"] else "",
                date_app_quai=str(cleaned["date_app_quai"]) if cleaned["date_app_quai"] else "",
                date_app_port=str(cleaned["date_app_port"]) if cleaned["date_app_port"] else "",
                observations=f"Importé Excel. {len(escale_obj.marchandises)} marchandises, {len(db_poste_changes)} changements",
                consignataire=cleaned["consignataire"],
                incidents=[],
                poste_changes=db_poste_changes,
                type_m_list=cleaned["type_m_list"],
                marchandise_list=cleaned["marchandise_list"],
            )
            return row, []
        except Exception as e:
            logger.exception(f"Erreur construction OperationRow")
            return None, [f"Ligne {first_row}\nESCALE {escale_obj.escale}\nConstruction\n{e}"]

    def import_escales(self, skip_duplicates: bool = True) -> Tuple[int, int, List[str]]:
        imported_escales = 0
        imported_operations = 0
        all_errors = []

        for escale, escale_obj in self._reconstructed_escales.items():
            if skip_duplicates and _normalize_escale(escale) in self._existing_escales:
                self.report.nb_doublons += 1
                continue

            # Escales Type E hors référentiel (ANP/RADE) : exclues de l'import
            if escale in self._hors_referentiel_escales:
                continue

            op_row, errors = self.build_operation_from_escale(escale_obj)
            if op_row is None:
                all_errors.extend(errors)
                continue

            temps_attente = 0.0
            temps_sejour = 0.0
            try:
                from utils import calculer_temps_attente, calculer_temps_sejour
                if op_row.date_rade and op_row.date_mouillage:
                    temps_attente = calculer_temps_attente(
                        op_row.heure_rade, op_row.heure_mouillage,
                        date_rade=op_row.date_rade, date_mouillage=op_row.date_mouillage
                    ) or 0.0
                if op_row.date_accostage and op_row.date_app_quai:
                    temps_sejour = calculer_temps_sejour(
                        op_row.heure_accostage, op_row.heure_app_quai,
                        date_accostage=op_row.date_accostage, date_appareillage=op_row.date_app_quai
                    ) or 0.0
            except Exception:
                pass

            try:
                if self.db.insert_operation(op_row, temps_attente, temps_sejour):
                    imported_escales += 1
                    imported_operations += 1
                    self.report.nb_operations_importees += 1
                else:
                    all_errors.append(f"Escale {escale}: Échec insertion")
            except Exception as e:
                all_errors.append(f"Escale {escale}: {e}")

        return imported_escales, imported_operations, all_errors

    def run(self, df: pd.DataFrame, skip_duplicates: bool = True):
        start = time_module.perf_counter()
        try:
            self.process_dataframe(df)
            self.import_escales(skip_duplicates=skip_duplicates)
        except Exception as e:
            logger.exception("Erreur inattendue")
            self.report.errors.append({"row": None, "escale": "", "champ": "Import", "error": str(e)})
        finally:
            self.report.end_time = datetime.now()
            self.report.duration_seconds = time_module.perf_counter() - start
        return self.report

    def get_preview_data(self) -> pd.DataFrame:
        data = []
        for escale, obj in self._reconstructed_escales.items():
            data.append({
                "Escale": escale,
                "Navire": obj.navire,
                "Poste principal": obj.poste_principal_raw,
                "Opérateur": obj.operateur,
                "Nb changements": len(obj.poste_changes),
                "Nb 2ND OP": len(obj.second_operations),
                "Nb marchandises": len(obj.marchandises),
                "Lignes": ", ".join(str(r) for r in obj.source_rows),
            })
        return pd.DataFrame(data)

    def get_grouped_preview(self) -> pd.DataFrame:
        return self.get_preview_data()

    def get_reconstructed_count(self) -> int:
        return len(self._reconstructed_escales)


# ============================================================
# PARTIE 2 - IMPORTATION DES CONSIGNATIONS
# ============================================================

# Mapping officiel Excel -> Consignations
CONSIGNATION_COLUMN_MAP = {
    "poste": "Postes",
    "consignation": "Consignation",
    "deconsignation": "Déconsignation",
    "motif": "Cause",
    "observations": "Mouvement",
}


@dataclass
class ConsignationImportRow:
    row_index: int
    raw_data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_valid: bool = False
    is_duplicate: bool = False
    cleaned_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsignationImportReport:
    nb_lignes: int = 0
    nb_lignes_valides: int = 0
    nb_lignes_invalides: int = 0
    nb_importees: int = 0
    nb_doublons: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class ConsignationImporter:
    """Importateur de consignations - Utilise validators.validate_complete_consignation()"""

    def __init__(self):
        self.db = DBManager()
        self.report = ConsignationImportReport()
        self.rows: List[ConsignationImportRow] = []
        self._existing_consignations: set = set()

    def read_file(self, file) -> Tuple[Optional[pd.ExcelFile], List[str]]:
        try:
            excel_data = pd.ExcelFile(file)
            return excel_data, excel_data.sheet_names
        except Exception as e:
            logger.exception("Erreur lecture fichier")
            return None, [f"Impossible de lire le fichier : {e}"]

    def read_sheet(self, excel_data: pd.ExcelFile, sheet_name: str) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_excel(excel_data, sheet_name=sheet_name, header=0)
            return df
        except Exception as e:
            logger.exception(f"Erreur lecture feuille '{sheet_name}'")
            return None

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.strip()
            return value if value != "" else None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    @staticmethod
    def _parse_datetime(value: Any, field_name: str = "Date") -> Tuple[Optional[Any], Optional[Any]]:
        if value is None or value == "":
            return None, None
        try:
            dt = _parse_strict_import_datetime(value)
            if dt is None:
                return None, None
            return dt.date(), dt.time()
        except ValidationError as e:
            raise ValidationError(f"{e.message}", field=field_name)
        except Exception:
            raise ValidationError(f"format non reconnu : \"{value}\"", field=field_name)

    def get_existing_consignations(self) -> set:
        try:
            conn = self.db._connect()
            if conn is None:
                return set()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT CONCAT_WS('|', poste, DATE(date_debut), TIME(heure_debut))
                FROM consignations
            """)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return {str(r[0]) for r in results}
        except Exception:
            logger.exception("Erreur récupération consignations existantes")
            return set()

    def _extract_raw_data(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {key: self._clean_value(record.get(col)) for key, col in CONSIGNATION_COLUMN_MAP.items()}

    def process_dataframe(self, df: pd.DataFrame) -> List[ConsignationImportRow]:
        self.rows = []
        self.report = ConsignationImportReport()
        self.report.start_time = datetime.now()
        self.report.nb_lignes = len(df)
        self._existing_consignations = self.get_existing_consignations()

        try:
            records = df.to_dict(orient="records")
        except Exception as e:
            logger.exception("Erreur conversion DataFrame")
            self.report.errors.append({"row": None, "champ": "Fichier", "error": str(e)})
            return self.rows

        for idx, record in enumerate(records):
            excel_row_number = idx + 2
            try:
                raw_data = self._extract_raw_data(record)
                parse_errors: List[str] = []
                try:
                    consignation_date, consignation_time = self._parse_datetime(
                        raw_data.get("consignation"), field_name="Consignation")
                except ValidationError as e:
                    consignation_date, consignation_time = None, None
                    parse_errors.append(f"{e.field}: {e.message}")
                try:
                    deconsignation_date, deconsignation_time = self._parse_datetime(
                        raw_data.get("deconsignation"), field_name="Déconsignation")
                except ValidationError as e:
                    deconsignation_date, deconsignation_time = None, None
                    parse_errors.append(f"{e.field}: {e.message}")

                data_for_validation = {
                    "poste": raw_data.get("poste"),
                    "date_debut": consignation_date,
                    "date_fin": deconsignation_date,
                    "heure_debut": consignation_time,
                    "heure_fin": deconsignation_time,
                    "motif": raw_data.get("motif"),
                    "observations": raw_data.get("observations"),
                }

                try:
                    cleaned = validate_complete_consignation(data_for_validation)
                    is_valid = True
                    errors = []
                    warnings = []
                except MultiValidationError as e:
                    cleaned = {}
                    is_valid = False
                    errors = [f"{champ}: {msg}" for champ, msg in e.errors]
                    warnings = []
                except ValidationError as e:
                    cleaned = {}
                    is_valid = False
                    errors = [f"{e.field}: {e.message}"]
                    warnings = []

                if parse_errors:
                    redundant = ("Date début", "Date fin", "Heure début", "Heure fin")
                    errors = parse_errors + [
                        err for err in errors
                        if not (err.split(":", 1)[0] in redundant and "obligatoire" in err)
                    ]
                    is_valid = False

                is_duplicate = False
                if is_valid and cleaned.get("poste") and cleaned.get("date_debut"):
                    key = f"{cleaned['poste']}|{cleaned['date_debut']}|{cleaned.get('heure_debut', '00:00')}"
                    if key in self._existing_consignations:
                        is_duplicate = True
                        warnings.append(f"Consignation déjà existante pour le poste {cleaned['poste']}")

                import_row = ConsignationImportRow(
                    row_index=excel_row_number,
                    raw_data=raw_data,
                    errors=errors,
                    warnings=warnings,
                    is_valid=is_valid,
                    is_duplicate=is_duplicate,
                    cleaned_data=cleaned,
                )

            except Exception as e:
                logger.exception(f"Erreur ligne {excel_row_number}")
                import_row = ConsignationImportRow(
                    row_index=excel_row_number,
                    raw_data=record,
                    errors=[f"Erreur inattendue : {e}"],
                    is_valid=False,
                )

            self.rows.append(import_row)
            if import_row.is_valid:
                self.report.nb_lignes_valides += 1
            else:
                self.report.nb_lignes_invalides += 1
                for error in import_row.errors:
                    self.report.errors.append({
                        "row": import_row.row_index,
                        "poste": import_row.raw_data.get("poste", ""),
                        "champ": error.split(":")[0] if ": " in error else "Validation",
                        "error": error,
                    })

            if import_row.is_duplicate:
                self.report.nb_doublons += 1
            for warning in import_row.warnings:
                self.report.warnings.append({
                    "row": import_row.row_index,
                    "poste": import_row.raw_data.get("poste", ""),
                    "warning": warning,
                })

        return self.rows

    def import_consignations(self, skip_duplicates: bool = True) -> Tuple[int, List[str]]:
        imported = 0
        all_errors = []
        rows_to_import = [r for r in self.rows if r.is_valid and not (skip_duplicates and r.is_duplicate)]

        for row in rows_to_import:
            try:
                data = row.cleaned_data
                heure_debut_str = data["heure_debut"].strftime("%H:%M") if data.get("heure_debut") else "00:00"
                heure_fin_str = data["heure_fin"].strftime("%H:%M") if data.get("heure_fin") else "00:00"

                success = self.db.insert_consignation_poste(
                    date_debut=data["date_debut"],
                    date_fin=data["date_fin"],
                    heure_debut=heure_debut_str,
                    heure_fin=heure_fin_str,
                    poste=data["poste"],
                    motif=data.get("motif", "Mauvais temps"),
                    nombre_heures=data.get("nombre_heures", 1),
                    observations=data.get("observations", "")
                )

                if success:
                    imported += 1
                    self.report.nb_importees += 1
                else:
                    all_errors.append(f"Ligne {row.row_index}: Échec insertion")
            except Exception as e:
                all_errors.append(f"Ligne {row.row_index}: {e}")

        return imported, all_errors

    def run(self, df: pd.DataFrame, skip_duplicates: bool = True):
        start = time_module.perf_counter()
        try:
            self.process_dataframe(df)
            self.import_consignations(skip_duplicates=skip_duplicates)
        except Exception as e:
            logger.exception("Erreur inattendue")
            self.report.errors.append({"row": None, "poste": "", "champ": "Import", "error": str(e)})
        finally:
            self.report.end_time = datetime.now()
            self.report.duration_seconds = time_module.perf_counter() - start
        return self.report

    def get_preview_data(self, rows: Optional[List[ConsignationImportRow]] = None) -> pd.DataFrame:
        if rows is None:
            rows = self.rows

        data = []
        for row in rows:
            status = "✅ Valide" if row.is_valid else "❌ Erreur"
            if row.is_duplicate:
                status = "⚠️ Doublon"

            data.append({
                "Ligne": row.row_index,
                "Poste": row.raw_data.get("poste", ""),
                "Consignation": row.raw_data.get("consignation", ""),
                "Déconsignation": row.raw_data.get("deconsignation", ""),
                "Motif": row.raw_data.get("motif", ""),
                "Statut": status,
                "Erreurs": ", ".join(row.errors) if row.errors else "-",
                "Avertissements": ", ".join(row.warnings) if row.warnings else "-",
            })

        return pd.DataFrame(data)

    def get_reconstructed_count(self) -> int:
        return len([r for r in self.rows if r.is_valid])
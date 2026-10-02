"""
Gestionnaire de base de données MySQL pour l'application ANP
Version avancée avec support pour :
- Numéro Navire
- Date/Heure Accostage
- Changements de poste (poste_changes)
- Incidents (indépendants)
- Type M et Marchandises multiples (type_m_details)
- Consignations
"""
import os
import logging
import warnings

# pandas émet un UserWarning pour toute connexion DBAPI2 brute (pymysql) ;
# c'est attendu ici et sans impact : on le supprime globalement.
warnings.filterwarnings(
    "ignore", message="pandas only supports SQLAlchemy", category=UserWarning)
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any

import pandas as pd
import pymysql
from pymysql import Error
import streamlit as st
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3307")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "anp_port_new_db"),
    "charset": "utf8mb4",
    "autocommit": False,
}


@dataclass
class OperationRow:
    """
    Structure de données pour une opération portuaire
    Version avancée avec Type M et Marchandises multiples
    """
    # Informations navire
    date: str
    navire: str
    id_navire: str = ""  # Numéro Navire
    pavillon: str = ""
    type_navire: str = ""
    poste: str = ""
    
    # Opération
    type_operation: str = ""
    unite: str = ""
    quantite: float = 0.0
    
    # Horaires
    heure_rade: str = ""
    heure_mouillage: str = ""
    heure_sortie_mouillage: str = ""
    heure_accostage: str = ""
    heure_app_quai: str = ""
    heure_app_port: str = ""
    date_rade: str = ""
    date_mouillage: str = ""
    date_sortie_mouillage: str = ""
    date_accostage: str = ""
    date_app_quai: str = ""
    date_app_port: str = ""
    
    # Autres
    consignataire: str = ""
    operateur: str = ""
    type_marchandise: str = ""
    mode_conditionnement: str = ""
    observations: str = ""
    incidents: List[Dict[str, str]] = field(default_factory=list)
    
    # NOUVEAUX CHAMPS
    poste_changes: List[Dict] = field(default_factory=list)
    type_m_list: List[str] = field(default_factory=list)
    marchandise_list: List[str] = field(default_factory=list)


class DBManager:
    """
    Gestionnaire de la base de données MySQL
    Version avancée avec toutes les nouvelles tables
    """

    def __init__(self) -> None:
        pass

    def _connect(self):
        """Établit une connexion à la base de données"""
        try:
            return pymysql.connect(**MYSQL_CONFIG)
        except Error as e:
            st.error(f"❌ Erreur de connexion MySQL: {e}")
            logger.error(f"Erreur connexion MySQL: {e}")
            return None

    def _table_columns(self, conn, table_name: str) -> set:
        """Récupère les colonnes d'une table"""
        try:
            cursor = conn.cursor()
            cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
            cols = {row[0] for row in cursor.fetchall()}
            cursor.close()
            return cols
        except Exception as e:
            logger.warning(f"Impossible de lire les colonnes de {table_name}: {e}")
            return set()

    @staticmethod
    def _opt(value):
        """'' / None / espace → None (évite les dates zéro 0000-00-00 en base)."""
        if value is None:
            return None
        s = str(value).strip()
        return None if s == "" else value

    @staticmethod
    def _combine(date_value, heure_value):
        """Combine Date + Heure en chaîne DATETIME, ou None si un élément manque."""
        d = DBManager._opt(date_value)
        h = DBManager._opt(heure_value)
        if d is None or h is None:
            return None
        return f"{d} {h}"

    def check_connection(self) -> dict:
        """Vérifie la connexion à la base de données"""
        try:
            conn = self._connect()
            if conn is None:
                return {
                    "status": "error",
                    "message": "Impossible de se connecter à MySQL. Vérifiez que MySQL est démarré.",
                }

            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            cursor.close()
            conn.close()

            return {
                "status": "ok",
                "message": f"Connexion MySQL établie. {len(tables)} tables trouvées.",
                "tables_count": len(tables),
            }

        except pymysql.err.OperationalError as e:
            error_code = e.args[0]
            error_message = e.args[1]

            if error_code == 2003:
                msg = "MySQL n'est pas démarré. Lancez XAMPP et démarrez MySQL."
            elif error_code == 1045:
                msg = "Identifiants MySQL incorrects. Vérifiez le fichier .env"
            elif error_code == 1049:
                msg = f'Base de données "{MYSQL_CONFIG["database"]}" inexistante. Créez-la dans phpMyAdmin.'
            else:
                msg = f"Erreur MySQL: {error_message}"

            return {"status": "error", "message": msg, "code": error_code}

        except Exception as e:
            return {"status": "error", "message": f"Erreur inattendue: {str(e)}"}

    def initialize_database(self) -> bool:
        """
        Initialise la base de données avec toutes les tables nécessaires
        Version complète avec toutes les nouvelles tables
        """
        conn = self._connect()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()

            # ========================================
            # 1. TABLE users (authentification)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) DEFAULT 'user',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 2. TABLE navires (avec numero_navire)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS navires (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(100) NOT NULL,
                    numero_navire VARCHAR(50),
                    pavillon VARCHAR(50),
                    type_navire VARCHAR(50),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_navire_nom (nom)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 3. TABLE postes (nouvelle liste)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS postes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom_poste VARCHAR(20) NOT NULL UNIQUE,
                    operateur VARCHAR(100),
                    type_marchandise VARCHAR(100),
                    actif BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_poste_nom (nom_poste)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 4. TABLE operations (avec toutes les colonnes)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL,
                    navire VARCHAR(100) NOT NULL,
                    numero_navire VARCHAR(50),
                    poste VARCHAR(20) NOT NULL,
                    consignataire VARCHAR(100) NOT NULL,
                    temps_attente FLOAT DEFAULT 0,
                    temps_sejour FLOAT DEFAULT 0,
                    escale_id INT NULL,
                    type_operation VARCHAR(50),
                    unite VARCHAR(20),
                    quantite FLOAT DEFAULT 0,
                    observations TEXT,
                    pavillon VARCHAR(50),
                    type_navire VARCHAR(50),
                    operateur VARCHAR(100),
                    type_marchandise VARCHAR(100),
                    mode_conditionnement VARCHAR(50),
                    -- Horaires avec Accostage
                    date_rade DATE,
                    heure_rade TIME,
                    date_mouillage DATE,
                    heure_mouillage TIME,
                    date_sortie_mouillage DATE,
                    heure_sortie_mouillage TIME,
                    date_accostage DATE,
                    heure_accostage TIME,
                    date_app_quai DATE,
                    heure_app_quai TIME,
                    date_app_port DATE,
                    heure_app_port TIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_operation_date (date),
                    INDEX idx_operation_navire (navire),
                    INDEX idx_operation_poste (poste)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 5. TABLE poste_changes (changements de poste)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS poste_changes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    operation_id INT NOT NULL,
                    poste_numero INT NOT NULL,
                    poste VARCHAR(20) NOT NULL,
                    date_accostage DATE NOT NULL,
                    heure_accostage TIME NOT NULL,
                    date_app_quai DATE NOT NULL,
                    heure_app_quai TIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_poste_change_operation (operation_id),
                    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 6. TABLE incidents (indépendante)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nature VARCHAR(200) NOT NULL,
                    date_incident DATE NOT NULL,
                    lieu VARCHAR(100) NOT NULL,
                    consistance VARCHAR(100) NOT NULL,
                    operation_id INT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_incident_date (date_incident),
                    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 7. TABLE type_m_details (Type M et Marchandises multiples)
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS type_m_details (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    operation_id INT NOT NULL,
                    ligne_numero INT NOT NULL,
                    type_m VARCHAR(20) NOT NULL,
                    marchandise VARCHAR(200) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_type_m_operation (operation_id),
                    FOREIGN KEY (operation_id) REFERENCES operations(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 8. TABLE escales
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS escales (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    navire_id INT NOT NULL,
                    consignataire VARCHAR(100),
                    date_rade DATETIME,
                    date_mouillage DATETIME,
                    date_sortie_mouillage DATETIME,
                    date_accostage DATETIME,
                    date_app_quai DATETIME,
                    date_app_port DATETIME,
                    poste_id INT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_escale_navire (navire_id),
                    INDEX idx_escale_dates (date_rade),
                    FOREIGN KEY (navire_id) REFERENCES navires(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 9. TABLE consignations
            # ========================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS consignations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date_debut DATE NOT NULL,
                    date_fin DATE NOT NULL,
                    heure_debut TIME NOT NULL,
                    heure_fin TIME NOT NULL,
                    poste VARCHAR(50) NOT NULL,
                    motif VARCHAR(100) NOT NULL,
                    nombre_heures INT NOT NULL,
                    observations TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_consignation_dates (date_debut, date_fin),
                    INDEX idx_consignation_poste (poste)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # ========================================
            # 10. DONNÉES PAR DÉFAUT
            # ========================================

            # Insérer un utilisateur admin par défaut
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                import hashlib
                admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute("""
                    INSERT INTO users (username, password, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                """, ("admin", admin_hash, admin_hash, "admin"))

            # Insérer des postes par défaut (nouvelle liste)
            cursor.execute("SELECT COUNT(*) FROM postes")
            if cursor.fetchone()[0] == 0:
                postes_default = [
                    # OCP
                    ("1N", "OCP", "PHOSPHATES ET DERIVES"),
                    ("1S", "OCP", "PHOSPHATES ET DERIVES"),
                    ("1Bis", "OCP", "PHOSPHATES ET DERIVES"),
                    ("1Ter", "OCP", "PHOSPHATES ET DERIVES"),
                    ("2N", "OCP", "PHOSPHATES ET DERIVES"),
                    ("2Bis", "OCP", "PHOSPHATES ET DERIVES"),
                    ("2Ter", "OCP", "PHOSPHATES ET DERIVES"),
                    ("4", "OCP", "PHOSPHATES ET DERIVES"),
                    ("4Bis", "OCP", "PHOSPHATES ET DERIVES"),
                    ("5", "OCP", "PHOSPHATES ET DERIVES"),
                    ("6", "OCP", "PHOSPHATES ET DERIVES"),
                    ("7", "OCP", "PHOSPHATES ET DERIVES"),
                    # JLEC
                    ("3", "JLEC", "CHARBON ET COKE"),
                    ("3Bis", "JLEC", "CHARBON ET COKE"),
                    # HYDROCARB JORF
                    ("9", "HYDROCARB JORF", "HYDROCARBURES"),
                    # MASS CEREALES
                    ("14S", "MASS CEREALES", "CEREALES & AB"),
                    # MARSA MAROC
                    ("8", "MARSA MAROC", "AUTRES"),
                    ("14N", "MARSA MAROC", "AUTRES"),
                    ("16N", "MARSA MAROC", "AUTRES"),
                    ("16S", "MARSA MAROC", "AUTRES"),
                    ("11_12", "MARSA MAROC", "AUTRES"),
                    ("13", "MARSA MAROC", "AUTRES"),
                    # SONASID
                    ("10", "SONASID", "SIDERURGIE & METAL"),
                ]
                for nom, operateur, type_mar in postes_default:
                    cursor.execute("""
                        INSERT INTO postes (nom_poste, operateur, type_marchandise)
                        VALUES (%s, %s, %s)
                    """, (nom, operateur, type_mar))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Erreur initialisation base: {e}")
            conn.rollback()
            return False

        finally:
            conn.close()

    def insert_operation(self, row: OperationRow, temps_attente: float = 0, temps_sejour: float = 0) -> bool:
        """
        Insère une opération complète dans la base de données
        Version avancée avec Type M et Marchandises multiples
        """
        conn = self._connect()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()

            # ========================================
            # 1. Gestion du navire avec numero_navire
            # ========================================
            cursor.execute("SELECT id FROM navires WHERE nom = %s", (row.navire,))
            existing_navire = cursor.fetchone()

            if existing_navire:
                navire_id = existing_navire[0]
                # Mise à jour du numéro si présent
                if row.id_navire:
                    cursor.execute("""
                        UPDATE navires SET numero_navire = %s WHERE id = %s
                    """, (row.id_navire, navire_id))
                # Mise à jour du pavillon si présent
                if row.pavillon:
                    cursor.execute("""
                        UPDATE navires SET pavillon = %s WHERE id = %s
                    """, (row.pavillon, navire_id))
                # Mise à jour du type si présent
                if row.type_navire:
                    cursor.execute("""
                        UPDATE navires SET type_navire = %s WHERE id = %s
                    """, (row.type_navire, navire_id))
            else:
                cursor.execute("""
                    INSERT INTO navires (nom, numero_navire, pavillon, type_navire)
                    VALUES (%s, %s, %s, %s)
                """, (row.navire, row.id_navire, row.pavillon, row.type_navire))
                navire_id = cursor.lastrowid

            # ========================================
            # 2. Gestion du poste
            # ========================================
            poste_id = None
            if row.poste:
                cursor.execute("SELECT id FROM postes WHERE nom_poste = %s", (row.poste,))
                existing_poste = cursor.fetchone()

                if existing_poste:
                    poste_id = existing_poste[0]
                else:
                    cursor.execute("""
                        INSERT INTO postes (nom_poste, operateur, type_marchandise)
                        VALUES (%s, %s, %s)
                    """, (row.poste, row.operateur, row.type_marchandise))
                    poste_id = cursor.lastrowid

            # ========================================
            # 3. Insertion dans escales avec accostage
            # ========================================
            cursor.execute("""
                INSERT INTO escales (
                    navire_id,
                    consignataire,
                    date_rade,
                    date_mouillage,
                    date_sortie_mouillage,
                    date_accostage,
                    date_app_quai,
                    date_app_port,
                    poste_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                navire_id,
                row.consignataire,
                self._combine(row.date_rade, row.heure_rade),
                self._combine(row.date_mouillage, row.heure_mouillage),
                self._combine(row.date_sortie_mouillage, row.heure_sortie_mouillage),
                self._combine(row.date_accostage, row.heure_accostage),
                self._combine(row.date_app_quai, row.heure_app_quai),
                self._combine(row.date_app_port, row.heure_app_port),
                poste_id,
            ))
            escale_id = cursor.lastrowid

            # ========================================
            # 4. Insertion dans operations avec toutes les colonnes
            # ========================================
            cursor.execute("""
                INSERT INTO operations (
                    date,
                    navire,
                    numero_navire,
                    poste,
                    consignataire,
                    temps_attente,
                    temps_sejour,
                    escale_id,
                    type_operation,
                    unite,
                    quantite,
                    observations,
                    pavillon,
                    type_navire,
                    operateur,
                    type_marchandise,
                    mode_conditionnement,
                    date_rade,
                    heure_rade,
                    date_mouillage,
                    heure_mouillage,
                    date_sortie_mouillage,
                    heure_sortie_mouillage,
                    date_accostage,
                    heure_accostage,
                    date_app_quai,
                    heure_app_quai,
                    date_app_port,
                    heure_app_port,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row.date_rade,
                row.navire,
                row.id_navire,
                row.poste,
                row.consignataire,
                temps_attente,
                temps_sejour,
                escale_id,
                row.type_operation,
                row.unite,
                row.quantite,
                row.observations,
                row.pavillon,
                row.type_navire,
                row.operateur,
                row.type_marchandise,
                row.mode_conditionnement,
                self._opt(row.date_rade),
                self._opt(row.heure_rade),
                self._opt(row.date_mouillage),
                self._opt(row.heure_mouillage),
                self._opt(row.date_sortie_mouillage),
                self._opt(row.heure_sortie_mouillage),
                self._opt(row.date_accostage),
                self._opt(row.heure_accostage),
                self._opt(row.date_app_quai),
                self._opt(row.heure_app_quai),
                self._opt(row.date_app_port),
                self._opt(row.heure_app_port),
                datetime.now(),
            ))
            operation_id = cursor.lastrowid

            # ========================================
            # 5. Insertion des changements de poste
            # ========================================
            if row.poste_changes:
                for idx, change in enumerate(row.poste_changes, 1):
                    cursor.execute("""
                        INSERT INTO poste_changes (
                            operation_id,
                            poste_numero,
                            poste,
                            date_accostage,
                            heure_accostage,
                            date_app_quai,
                            heure_app_quai
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        operation_id,
                        idx,
                        change.get("poste", ""),
                        change.get("date_accostage"),
                        change.get("heure_accostage"),
                        change.get("date_app_quai"),
                        change.get("heure_app_quai"),
                    ))

            # ========================================
            # 6. Insertion des incidents
            # ========================================
            for incident in row.incidents:
                consistance = str(incident.get("consistance", "Moyenne")).strip()
                # La consistance est maintenant un texte libre
                cursor.execute("""
                    INSERT INTO incidents (
                        nature,
                        date_incident,
                        lieu,
                        consistance,
                        operation_id
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (
                    incident.get("nature", ""),
                    incident.get("date", datetime.now().date()),
                    incident.get("lieu", "Non spécifié"),
                    consistance,
                    operation_id,
                ))

            # ========================================
            # 7. Insertion des Type M et Marchandises multiples
            # ========================================
            if row.type_m_list and row.marchandise_list:
                for idx, (tm, mar) in enumerate(zip(row.type_m_list, row.marchandise_list), 1):
                    if tm and mar:
                        cursor.execute("""
                            INSERT INTO type_m_details (
                                operation_id,
                                ligne_numero,
                                type_m,
                                marchandise
                            ) VALUES (%s, %s, %s, %s)
                        """, (
                            operation_id,
                            idx,
                            tm,
                            mar,
                        ))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Erreur insert_operation: {e}")
            conn.rollback()
            st.error(f"❌ Erreur lors de l'enregistrement: {str(e)}")
            return False

        finally:
            conn.close()

    def insert_consignation_poste(
        self,
        date_debut,
        date_fin,
        heure_debut,
        heure_fin,
        poste,
        motif,
        nombre_heures,
        observations=""
    ) -> bool:
        """Insère une consignation de poste"""
        if date_fin < date_debut:
            st.error("❌ La date de fin doit être supérieure ou égale à la date de début.")
            return False

        if date_debut == date_fin and heure_fin <= heure_debut:
            st.error("❌ L'heure de fin doit être postérieure à l'heure de début.")
            return False

        conn = self._connect()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO consignations (
                    date_debut,
                    date_fin,
                    heure_debut,
                    heure_fin,
                    poste,
                    motif,
                    nombre_heures,
                    observations
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                date_debut,
                date_fin,
                heure_debut,
                heure_fin,
                poste,
                motif,
                nombre_heures,
                observations
            ))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            logger.error(f"Erreur consignation poste: {e}")
            conn.rollback()
            return False

        finally:
            conn.close()

    # ========================================
    # MÉTHODES DE LECTURE
    # ========================================

    def get_operations(self, limit: int = None, offset: int = 0, search: str = None) -> pd.DataFrame:
        """Récupère les opérations depuis la base"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            columns = self._table_columns(conn, "operations")

            time_cols = [
                "heure_rade", "heure_mouillage", "heure_sortie_mouillage",
                "heure_accostage", "heure_app_quai", "heure_app_port"
            ]

            select_parts = []
            for col in columns:
                if col in time_cols:
                    select_parts.append(f"TIME_FORMAT(`{col}`, '%%H:%%i:%%s') AS `{col}`")
                else:
                    select_parts.append(f"`{col}`")

            query = "SELECT " + ", ".join(select_parts) + " FROM operations"
            params = []

            if search:
                searchable = [
                    c for c in ["navire", "numero_navire", "type_marchandise", "consignataire", "operateur", "poste"]
                    if c in columns
                ]
                if searchable:
                    conditions = [f"`{c}` LIKE %s" for c in searchable]
                    query += " WHERE " + " OR ".join(conditions)
                    params = [f"%{search}%"] * len(searchable)

            query += " ORDER BY id DESC"

            if limit:
                query += " LIMIT %s OFFSET %s"
                params.extend([int(limit), int(offset)])

            return pd.read_sql_query(query, conn, params=params)

        except Exception as e:
            logger.error(f"Erreur get_operations: {e}")
            return pd.DataFrame()

        finally:
            conn.close()

    def get_incidents(self, limit: int = None, operation_id: int = None) -> pd.DataFrame:
        """Récupère les incidents (tous ou pour une opération)"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            if operation_id:
                query = "SELECT * FROM incidents WHERE operation_id = %s ORDER BY created_at DESC"
                return pd.read_sql_query(query, conn, params=(operation_id,))
            else:
                query = "SELECT * FROM incidents ORDER BY created_at DESC"
                if limit:
                    query += f" LIMIT {int(limit)}"
                return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Erreur get_incidents: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_poste_changes(self, operation_id: int) -> pd.DataFrame:
        """Récupère les changements de poste pour une opération"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = """
                SELECT poste_numero, poste, date_accostage, heure_accostage,
                       date_app_quai, heure_app_quai
                FROM poste_changes
                WHERE operation_id = %s
                ORDER BY poste_numero ASC
            """
            return pd.read_sql_query(query, conn, params=(operation_id,))
        except Exception as e:
            logger.error(f"Erreur get_poste_changes: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_type_m_details(self, operation_id: int) -> pd.DataFrame:
        """Récupère les Type M et Marchandises pour une opération"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = """
                SELECT ligne_numero, type_m, marchandise
                FROM type_m_details
                WHERE operation_id = %s
                ORDER BY ligne_numero ASC
            """
            return pd.read_sql_query(query, conn, params=(operation_id,))
        except Exception as e:
            logger.error(f"Erreur get_type_m_details: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_consignations(self, limit: int = 100) -> pd.DataFrame:
        """Récupère la liste des consignations"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = """
                SELECT 
                    id,
                    date_debut,
                    date_fin,
                    heure_debut,
                    heure_fin,
                    poste,
                    motif,
                    nombre_heures,
                    observations,
                    created_at
                FROM consignations 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            return pd.read_sql_query(query, conn, params=(limit,))
        except Exception as e:
            logger.error(f"Erreur get_consignations: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_navires(self, search: str = None) -> pd.DataFrame:
        """Récupère la liste des navires"""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            query = "SELECT id, nom, numero_navire, pavillon, type_navire FROM navires"
            if search:
                query += " WHERE nom LIKE %s OR numero_navire LIKE %s"
                params = (f"%{search}%", f"%{search}%")
                return pd.read_sql_query(query, conn, params=params)
            return pd.read_sql_query(query, conn)
        except Exception as e:
            logger.error(f"Erreur get_navires: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_postes(self) -> pd.DataFrame:
        """Retourne les postes configurés pour le jumeau numérique."""
        conn = self._connect()
        if conn is None:
            return pd.DataFrame()

        try:
            return pd.read_sql_query(
                """SELECT id, nom_poste, operateur, type_marchandise, actif
                   FROM postes WHERE actif = TRUE ORDER BY nom_poste""",
                conn,
            )
        except Exception as e:
            logger.error(f"Erreur get_postes: {e}")
            return pd.DataFrame()
        finally:
            conn.close()


# Instance globale
db_manager = DBManager()

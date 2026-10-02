-- Runs automatically the first time the MySQL container starts (empty volume).
USE anp_port_new_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS navires (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    numero_navire VARCHAR(50),
    pavillon VARCHAR(50),
    type_navire VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_navire_nom (nom)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS postes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_poste VARCHAR(20) NOT NULL UNIQUE,
    operateur VARCHAR(100),
    type_marchandise VARCHAR(100),
    actif BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_poste_nom (nom_poste)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

-- SHA-256: admin123 / agent123
INSERT IGNORE INTO users (username, password, password_hash, role) VALUES
('admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'admin'),
('agent', 'f44d1ac9bf0c69b083380b86dbdf3b73797150e3cca4820ac399f7917e607647', 'f44d1ac9bf0c69b083380b86dbdf3b73797150e3cca4820ac399f7917e607647', 'agent');

INSERT IGNORE INTO postes (nom_poste, operateur, type_marchandise) VALUES
('1N', 'OCP', 'PHOSPHATES ET DERIVES'),
('1S', 'OCP', 'PHOSPHATES ET DERIVES'),
('1Bis', 'OCP', 'PHOSPHATES ET DERIVES'),
('1Ter', 'OCP', 'PHOSPHATES ET DERIVES'),
('2N', 'OCP', 'PHOSPHATES ET DERIVES'),
('2Bis', 'OCP', 'PHOSPHATES ET DERIVES'),
('2Ter', 'OCP', 'PHOSPHATES ET DERIVES'),
('4', 'OCP', 'PHOSPHATES ET DERIVES'),
('4Bis', 'OCP', 'PHOSPHATES ET DERIVES'),
('5', 'OCP', 'PHOSPHATES ET DERIVES'),
('6', 'OCP', 'PHOSPHATES ET DERIVES'),
('7', 'OCP', 'PHOSPHATES ET DERIVES'),
('3', 'JLEC', 'CHARBON ET COKE'),
('3Bis', 'JLEC', 'CHARBON ET COKE'),
('9', 'HYDROCARB JORF', 'HYDROCARBURES'),
('14S', 'MASS CEREALES', 'CEREALES & AB'),
('8', 'MARSA MAROC', 'AUTRES'),
('14N', 'MARSA MAROC', 'AUTRES'),
('16N', 'MARSA MAROC', 'AUTRES'),
('16S', 'MARSA MAROC', 'AUTRES'),
('11_12', 'MARSA MAROC', 'AUTRES'),
('13', 'MARSA MAROC', 'AUTRES'),
('10', 'SONASID', 'SIDERURGIE & METAL');

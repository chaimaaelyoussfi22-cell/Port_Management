# -*- coding: utf-8 -*-
"""
IMPORT ONE-OFF DES INCIDENTS
============================
Lit incidents_raw.tsv (NATURE | DATE | LIEU | CONSISTANCE) et insère
les incidents dans la table `incidents` de la base ANP.

- Les lignes sans date exploitable (dd/mm/yyyy) ou sans nature sont ignorées
  et listées dans le rapport final (→ saisie manuelle).
- operation_id = NULL (incidents indépendants).
- Le fichier .env du projet fournit les paramètres MySQL.
"""
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
TSV_PATH = os.path.join(os.environ.get("INCIDENTS_TSV", ""), "incidents_raw.tsv")
if not os.path.exists(TSV_PATH):
    TSV_PATH = r"C:\Users\DELL\AppData\Local\Temp\opencode\incidents_raw.tsv"


def load_env(path: str):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def parse_tsv(path: str):
    rows = []
    skipped = []
    lines = open(path, encoding="utf-8").read().splitlines()
    for idx, line in enumerate(lines, 1):
        if idx == 1:
            continue
        if not line.strip():
            continue
        parts = line.split("\t")
        nature = parts[0].strip() if parts else ""
        date_raw = parts[1].strip() if len(parts) > 1 else ""
        lieu = parts[2].strip() if len(parts) > 2 else ""
        consistance = "\t".join(p for p in parts[3:] if p.strip()).strip() if len(parts) > 3 else ""
        if len(consistance) > 100:
            consistance = consistance[:100]

        date_incident = None
        if date_raw:
            try:
                date_incident = datetime.strptime(date_raw, "%d/%m/%Y").date()
            except ValueError:
                date_incident = None

        problems = []
        if not nature:
            problems.append("nature vide")
        if date_incident is None:
            problems.append(f"date illisible ({date_raw!r})")
        if not lieu:
            problems.append("lieu vide")
        if not consistance:
            problems.append("consistance vide")

        if problems:
            skipped.append({"ligne": idx, "raison": "; ".join(problems), "contenu": line[:120]})
            continue

        rows.append({
            "ligne": idx,
            "nature": nature[:200],
            "date_incident": date_incident,
            "lieu": lieu[:100],
            "consistance": consistance,
        })
    return rows, skipped


def main():
    cfg = load_env(os.path.join(PROJECT_DIR, ".env"))
    host = cfg.get("MYSQL_HOST", "localhost")
    port = int(cfg.get("MYSQL_PORT", "3307"))
    user = cfg.get("MYSQL_USER", "root")
    password = cfg.get("MYSQL_PASSWORD", "")
    database = cfg.get("MYSQL_DATABASE", "anp_port_new_db")

    rows, skipped = parse_tsv(TSV_PATH)
    print(f"Fichier : {TSV_PATH}")
    print(f"Lignes valides à insérer : {len(rows)}")
    print(f"Lignes ignorées          : {len(skipped)}")

    try:
        import pymysql
    except ImportError:
        print("pymysql absent. Installez les dépendances (requirements.txt).")
        sys.exit(1)

    conn = pymysql.connect(host=host, port=port, user=user, password=password,
                           database=database, charset="utf8mb4", autocommit=False)
    try:
        cursor = conn.cursor()
        inserted = 0
        for row in rows:
            cursor.execute(
                """INSERT INTO incidents (nature, date_incident, lieu, consistance, operation_id)
                   VALUES (%s, %s, %s, %s, NULL)""",
                (row["nature"], row["date_incident"], row["lieu"], row["consistance"]),
            )
            inserted += 1
        conn.commit()
        cursor.close()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), MIN(date_incident), MAX(date_incident) FROM incidents")
        total, dmin, dmax = cursor.fetchone()
        cursor.close()
    finally:
        conn.close()

    print(f"\nRésultat : {inserted} incidents insérés.")
    print(f"Total en table `incidents` : {total} | {dmin} → {dmax}")
    print(f"\nLignes ignorées (à saisir manuellement) : {len(skipped)}")
    for s in skipped:
        print(f"  ligne {s['ligne']}: {s['raison']}")
        print(f"    {s['contenu']}")


if __name__ == "__main__":
    main()
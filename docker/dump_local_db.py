"""Dump local MySQL into docker/mysql/init.sql for Docker first boot."""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv()

OUT = Path(__file__).resolve().parent / "mysql" / "init.sql"


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return "NULL"
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    if isinstance(value, time):
        return "'" + value.strftime("%H:%M:%S") + "'"
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        sign = "-" if total < 0 else ""
        total = abs(total)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        return "'%s%02d:%02d:%02d'" % (sign, hours, minutes, seconds)
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + text + "'"


def main() -> None:
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3307")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "anp_port_new_db"),
        charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [row[0] for row in cur.fetchall()]
    preferred = [
        "users",
        "navires",
        "postes",
        "operations",
        "escales",
        "consignations",
        "poste_changes",
        "incidents",
        "type_m_details",
    ]
    ordered = [name for name in preferred if name in tables]
    ordered.extend(name for name in tables if name not in ordered)

    lines: list[str] = [
        "-- Full dump of anp_port_new_db for Docker first boot",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
        "SET UNIQUE_CHECKS=0;",
        "SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';",
        "USE anp_port_new_db;",
        "",
    ]

    for name in reversed(ordered):
        lines.append(f"DROP TABLE IF EXISTS `{name}`;")
    lines.append("")

    for name in ordered:
        cur.execute(f"SHOW CREATE TABLE `{name}`")
        create_sql = cur.fetchone()[1]
        lines.append(create_sql + ";")
        lines.append("")

        cur.execute(f"SELECT * FROM `{name}`")
        columns = [desc[0] for desc in cur.description]
        col_sql = ", ".join(f"`{col}`" for col in columns)
        batch: list[str] = []
        count = 0

        def flush() -> None:
            nonlocal batch, count
            if not batch:
                return
            lines.append(f"INSERT INTO `{name}` ({col_sql}) VALUES")
            lines.append(",\n".join(batch) + ";")
            count += len(batch)
            batch = []

        while True:
            rows = cur.fetchmany(200)
            if not rows:
                break
            for row in rows:
                batch.append("(" + ", ".join(sql_literal(value) for value in row) + ")")
                if len(batch) >= 100:
                    flush()
        flush()
        lines.append(f"-- rows in {name}: {count}")
        lines.append("")
        print(f"{name}: {count} rows")

    lines.append("SET UNIQUE_CHECKS=1;")
    lines.append("SET FOREIGN_KEY_CHECKS=1;")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    conn.close()


if __name__ == "__main__":
    main()

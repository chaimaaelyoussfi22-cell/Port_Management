"""Wait for MySQL, create tables/users if needed, then start Streamlit."""
import os
import time

import pymysql
from pymysql import Error


def wait_for_mysql(attempts: int = 60, delay: float = 2.0) -> None:
    config = {
        "host": os.getenv("MYSQL_HOST", "mysql"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "anp_port_new_db"),
        "connect_timeout": 5,
    }
    last_error = None
    for i in range(1, attempts + 1):
        try:
            conn = pymysql.connect(**config)
            conn.close()
            print(f"MySQL is ready after {i} attempt(s).", flush=True)
            return
        except Error as exc:
            last_error = exc
            print(f"Waiting for MySQL ({i}/{attempts}): {exc}", flush=True)
            time.sleep(delay)
    raise SystemExit(f"MySQL did not become ready: {last_error}")


if __name__ == "__main__":
    wait_for_mysql()
    from database import DBManager

    if not DBManager().initialize_database():
        raise SystemExit("Database initialization failed.")
    print("Database schema and default accounts are ready.", flush=True)
    os.execvp(
        "streamlit",
        [
            "streamlit",
            "run",
            "app.py",
            "--server.address=0.0.0.0",
            "--server.port=8501",
            "--browser.gatherUsageStats=false",
        ],
    )

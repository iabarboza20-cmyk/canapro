"""
Migra el proyecto de SQLite (canaprosucre.db) a Supabase/Postgres.

Crea las tablas (asociados, beneficiarios, usuarios) en Postgres si no
existen, y copia todos los datos que tengas actualmente en el archivo
canaprosucre.db local.

Requiere la variable de entorno DATABASE_URL apuntando a tu proyecto de
Supabase (Settings > Database > Connection string > URI). Recomendado usar
la cadena del "Connection pooling" en modo Transaction (puerto 6543), ya
que esta app abre y cierra una conexión por cada solicitud.

Uso:
    export DATABASE_URL="postgresql://postgres.xxxx:TU_PASSWORD@aws-0-xxxx.pooler.supabase.com:6543/postgres"
    python3 migrate_to_supabase.py
"""
import os
import sqlite3
import sys

import psycopg2

SQLITE_PATH = "canaprosucre.db"

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS asociados (
    cedula                TEXT PRIMARY KEY,
    nombre                TEXT NOT NULL,
    telefono              TEXT,
    email                 TEXT,
    municipio             TEXT,
    estado                TEXT,
    municipio_trabajo     TEXT,
    institucion           TEXT,
    cargo                 TEXT,
    edad                  TEXT,
    sexo                  TEXT,
    municipio_residencia  TEXT,
    direccion             TEXT
);

CREATE TABLE IF NOT EXISTS beneficiarios (
    id              SERIAL PRIMARY KEY,
    cedula_asociado TEXT NOT NULL REFERENCES asociados(cedula) ON DELETE CASCADE,
    parentesco      TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    documento       TEXT
);
CREATE INDEX IF NOT EXISTS idx_beneficiarios_cedula ON beneficiarios(cedula_asociado);

CREATE TABLE IF NOT EXISTS usuarios (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL CHECK (rol IN ('viewer', 'admin'))
);
"""


def migrate():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: define la variable de entorno DATABASE_URL antes de correr esto.")
        sys.exit(1)

    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: no encuentro {SQLITE_PATH} en esta carpeta.")
        sys.exit(1)

    sq = sqlite3.connect(SQLITE_PATH)
    sq.row_factory = sqlite3.Row

    pg = psycopg2.connect(database_url)
    cur = pg.cursor()

    print("Creando tablas en Postgres (si no existen)...")
    cur.execute(PG_SCHEMA)
    pg.commit()

    # --- asociados ---
    rows = sq.execute("SELECT * FROM asociados").fetchall()
    print(f"Migrando {len(rows)} asociados...")
    for r in rows:
        d = dict(r)
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "cedula")
        cur.execute(
            f"INSERT INTO asociados ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT (cedula) DO UPDATE SET {update_clause}",
            list(d.values()),
        )
    pg.commit()

    # --- beneficiarios ---
    rows = sq.execute("SELECT * FROM beneficiarios").fetchall()
    print(f"Migrando {len(rows)} beneficiarios...")
    cur.execute("DELETE FROM beneficiarios")  # evita duplicar si se corre 2 veces
    for r in rows:
        d = dict(r)
        cur.execute(
            "INSERT INTO beneficiarios (cedula_asociado, parentesco, nombre, documento) "
            "VALUES (%s, %s, %s, %s)",
            (d["cedula_asociado"], d["parentesco"], d["nombre"], d["documento"]),
        )
    pg.commit()

    # --- usuarios ---
    try:
        rows = sq.execute("SELECT * FROM usuarios").fetchall()
    except sqlite3.OperationalError:
        rows = []
    print(f"Migrando {len(rows)} usuarios...")
    for r in rows:
        d = dict(r)
        cur.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (%s, %s, %s) "
            "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, "
            "rol = EXCLUDED.rol",
            (d["username"], d["password_hash"], d["rol"]),
        )
    pg.commit()

    cur.close()
    pg.close()
    sq.close()
    print("¡Listo! Todo migrado a Supabase.")


if __name__ == "__main__":
    migrate()

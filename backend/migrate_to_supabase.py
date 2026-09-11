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
    direccion             TEXT,
    foto_url              TEXT
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

CREATE TABLE IF NOT EXISTS estados (
    id     SERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS categorias (
    id     SERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    orden  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS equipos (
    id           SERIAL PRIMARY KEY,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    nombre       TEXT NOT NULL,
    escudo_url   TEXT
);

CREATE TABLE IF NOT EXISTS jugadores (
    id              SERIAL PRIMARY KEY,
    equipo_id       INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre          TEXT NOT NULL,
    cedula_asociado TEXT REFERENCES asociados(cedula) ON DELETE SET NULL,
    numero          TEXT
);

CREATE TABLE IF NOT EXISTS partidos (
    id                   SERIAL PRIMARY KEY,
    categoria_id         INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    equipo_local_id      INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    equipo_visitante_id  INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    jornada              TEXT,
    fecha                TEXT,
    goles_local          INTEGER,
    goles_visitante      INTEGER
);

CREATE TABLE IF NOT EXISTS goles (
    id         SERIAL PRIMARY KEY,
    partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
    jugador_id INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    cantidad   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tarjetas (
    id         SERIAL PRIMARY KEY,
    partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
    jugador_id INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    tipo       TEXT NOT NULL CHECK (tipo IN ('AMARILLA', 'ROJA')),
    cantidad   INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_equipos_categoria ON equipos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_jugadores_equipo ON jugadores(equipo_id);
CREATE INDEX IF NOT EXISTS idx_partidos_categoria ON partidos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_goles_partido ON goles(partido_id);
CREATE INDEX IF NOT EXISTS idx_tarjetas_partido ON tarjetas(partido_id);
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

    # --- estados ---
    try:
        rows = sq.execute("SELECT * FROM estados").fetchall()
    except sqlite3.OperationalError:
        rows = []
    print(f"Migrando {len(rows)} estados...")
    for r in rows:
        d = dict(r)
        cur.execute(
            "INSERT INTO estados (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING",
            (d["nombre"],),
        )
    pg.commit()

    # --- torneo: categorias, equipos, jugadores, partidos, goles, tarjetas ---
    torneo_tablas = [
        ("categorias", ["nombre", "orden"], "nombre"),
        ("equipos", ["categoria_id", "nombre", "escudo_url"], None),
        ("jugadores", ["equipo_id", "nombre", "cedula_asociado", "numero"], None),
        ("partidos", ["categoria_id", "equipo_local_id", "equipo_visitante_id",
                       "jornada", "fecha", "goles_local", "goles_visitante"], None),
        ("goles", ["partido_id", "jugador_id", "cantidad"], None),
        ("tarjetas", ["partido_id", "jugador_id", "tipo", "cantidad"], None),
    ]
    # Mapa de id viejo (SQLite) -> id nuevo (Postgres) para cada tabla con
    # PRIMARY KEY autogenerado, así las referencias (categoria_id, equipo_id...)
    # se remapean correctamente aunque los ids no coincidan entre ambas bases.
    id_map = {}
    for tabla, cols, conflict_col in torneo_tablas:
        try:
            rows = sq.execute(f"SELECT * FROM {tabla}").fetchall()
        except sqlite3.OperationalError:
            rows = []
        print(f"Migrando {len(rows)} {tabla}...")
        id_map[tabla] = {}
        for r in rows:
            d = dict(r)
            old_id = d.pop("id", None)
            # Remapea claves foráneas a los ids ya insertados en Postgres
            for fk_tabla, fk_col in (
                ("categorias", "categoria_id"), ("equipos", "equipo_id"),
                ("equipos", "equipo_local_id"), ("equipos", "equipo_visitante_id"),
                ("jugadores", "jugador_id"), ("partidos", "partido_id"),
            ):
                if fk_col in d and d[fk_col] is not None:
                    d[fk_col] = id_map.get(fk_tabla, {}).get(d[fk_col], d[fk_col])

            col_names = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            values = [d.get(c) for c in cols]
            if conflict_col:
                update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != conflict_col)
                cur.execute(
                    f"INSERT INTO {tabla} ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_clause} "
                    f"RETURNING id",
                    values,
                )
            else:
                cur.execute(
                    f"INSERT INTO {tabla} ({col_names}) VALUES ({placeholders}) RETURNING id",
                    values,
                )
            new_id = cur.fetchone()[0]
            if old_id is not None:
                id_map[tabla][old_id] = new_id
        pg.commit()

    cur.close()
    pg.close()
    sq.close()
    print("¡Listo! Todo migrado a Supabase.")


if __name__ == "__main__":
    migrate()

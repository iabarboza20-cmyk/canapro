"""
Crea las tablas del módulo de Torneo interno (categorías, equipos,
jugadores, partidos, goles, tarjetas) si no existen, y siembra una
categoría de ejemplo para que la sección no se vea vacía la primera vez.

Es independiente de build_db.py / importar_asociados_activos.py — nunca se
borra al recargar el Excel de asociados.

Uso:
    python3 init_torneo.py

Se puede correr varias veces sin riesgo: si las tablas ya existen, no hace
nada (no borra equipos, partidos ni resultados ya cargados).
"""
import sqlite3

DB_PATH = "canaprosucre.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS categorias (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL,
    orden  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS equipos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    nombre       TEXT NOT NULL,
    escudo_url   TEXT
);

CREATE TABLE IF NOT EXISTS jugadores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo_id       INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre          TEXT NOT NULL,
    cedula_asociado TEXT REFERENCES asociados(cedula) ON DELETE SET NULL,
    numero          TEXT,
    posicion        TEXT,
    foto_url        TEXT
);

CREATE TABLE IF NOT EXISTS partidos (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id         INTEGER NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    equipo_local_id      INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    equipo_visitante_id  INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    jornada              TEXT,
    fecha                TEXT,
    goles_local          INTEGER,
    goles_visitante      INTEGER
);

CREATE TABLE IF NOT EXISTS goles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
    jugador_id INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    cantidad   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tarjetas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
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

DEFAULT_CATEGORIA = "TORNEO CANAPROSUCRE 2026"


def migrar_columnas_jugadores(cur):
    """Agrega posicion/foto_url a instalaciones que ya tenían la tabla
    jugadores creada antes de que existieran estas columnas. SQLite no
    soporta "ADD COLUMN IF NOT EXISTS", así que se intenta y se ignora el
    error si la columna ya existe."""
    for columna, tipo in (("posicion", "TEXT"), ("foto_url", "TEXT")):
        try:
            cur.execute(f"ALTER TABLE jugadores ADD COLUMN {columna} {tipo}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise


def init():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.cursor()
    migrar_columnas_jugadores(cur)

    existente = cur.execute(
        "SELECT COUNT(*) FROM categorias"
    ).fetchone()[0]
    if existente == 0:
        cur.execute(
            "INSERT INTO categorias (nombre, orden) VALUES (?, 0)",
            (DEFAULT_CATEGORIA,),
        )
        print(f"Categoría de ejemplo creada: '{DEFAULT_CATEGORIA}'.")
    else:
        print(f"Ya hay {existente} categoría(s) creada(s). No se agregó ninguna nueva.")

    conn.commit()
    conn.close()
    print("Listo. Tablas del torneo creadas/verificadas: categorias, equipos, "
          "jugadores, partidos, goles, tarjetas.")
    print("Agrega equipos y jugadores desde el panel admin (/admin/torneo).")


if __name__ == "__main__":
    init()

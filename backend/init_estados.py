"""
Crea la tabla 'estados' (si no existe) y siembra los valores que ya existen
en tus datos más algunos comunes (Inactivo, Moroso, Retirado).

Esta tabla es independiente de build_db.py / importar_asociados_activos.py
— nunca se borra al recargar el Excel, así que los estados que agregues
desde el panel admin se mantienen.

Uso:
    python3 init_estados.py
"""
import sqlite3

DB_PATH = "canaprosucre.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS estados (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL
);
"""

DEFAULTS = ["ACTIVO", "INACTIVO", "MOROSO", "RETIRADO", "SIN DATO"]


def init():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    existentes = cur.execute("SELECT COUNT(*) FROM estados").fetchone()[0]
    if existentes > 0:
        print(f"La tabla 'estados' ya tiene {existentes} valor(es). No se creó nada nuevo.")
        conn.close()
        return

    for nombre in DEFAULTS:
        cur.execute("INSERT INTO estados (nombre) VALUES (?)", (nombre,))

    conn.commit()
    conn.close()
    print("Estados creados:", ", ".join(DEFAULTS))
    print("Puedes agregar más desde el panel admin (pestaña Estados).")


if __name__ == "__main__":
    init()

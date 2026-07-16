"""
Crea la tabla 'usuarios' (si no existe) y siembra las 2 cuentas fijas:
  - viewer: solo puede consultar
  - admin:  puede consultar, agregar, editar y eliminar

Uso:
    python3 init_users.py

Se puede correr varias veces sin riesgo: si las cuentas ya existen, no las
vuelve a crear (no borra contraseñas que ya hayas cambiado).
"""
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "canaprosucre.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL CHECK (rol IN ('viewer', 'admin'))
);
"""

# Contraseñas iniciales -- CAMBIALAS después de la primera entrada
# con change_password.py
DEFAULT_USERS = [
    ("viewer", "Canaprosucre2026", "viewer"),
    ("admin", "Canaprosucre2026Admin", "admin"),
]


def init():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.cursor()

    for username, password, rol in DEFAULT_USERS:
        existing = cur.execute(
            "SELECT id FROM usuarios WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            print(f"Usuario '{username}' ya existe, no se modifica.")
            continue
        cur.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), rol),
        )
        print(f"Usuario '{username}' creado con rol '{rol}'.")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init()
    print("\nListo. Contraseñas iniciales (cámbialas con change_password.py):")
    for username, password, rol in DEFAULT_USERS:
        print(f"  {rol:8} -> usuario: {username}   contraseña: {password}")

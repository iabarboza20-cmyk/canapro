"""
Cambia la contraseña de un usuario existente (viewer o admin).

Uso:
    python3 change_password.py viewer nueva_contrasena
    python3 change_password.py admin otra_contrasena
"""
import sys
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "canaprosucre.db"


def change(username, new_password):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM usuarios WHERE username = ?", (username,)).fetchone()
    if not row:
        print(f"No existe el usuario '{username}'.")
        conn.close()
        return
    cur.execute(
        "UPDATE usuarios SET password_hash = ? WHERE username = ?",
        (generate_password_hash(new_password), username),
    )
    conn.commit()
    conn.close()
    print(f"Contraseña de '{username}' actualizada correctamente.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 change_password.py <usuario> <nueva_contrasena>")
        sys.exit(1)
    change(sys.argv[1], sys.argv[2])

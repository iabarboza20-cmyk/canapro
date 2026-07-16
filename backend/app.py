import os
import sqlite3
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from flask_cors import CORS
from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "canaprosucre.db")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, supports_credentials=True)

# IMPORTANTE: en producción define esta variable de entorno con un valor
# largo y aleatorio (por ejemplo con: python3 -c "import secrets; print(secrets.token_hex(32))")
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "No has iniciado sesión"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "No has iniciado sesión"}), 401
            return redirect("/login")
        if session.get("rol") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "No tienes permisos de administrador"}), 403
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM usuarios WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    session["username"] = user["username"]
    session["rol"] = user["rol"]
    return jsonify({"username": user["username"], "rol": user["rol"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    if "username" not in session:
        return jsonify({"logged_in": False}), 401
    return jsonify({"logged_in": True, "username": session["username"], "rol": session["rol"]})


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.route("/login")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/")
@login_required
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/admin")
@admin_required
def admin_page():
    return send_from_directory(FRONTEND_DIR, "admin.html")


# ---------------------------------------------------------------------------
# API de consulta (viewer y admin)
# ---------------------------------------------------------------------------

@app.route("/api/asociado/<cedula>")
@login_required
def get_asociado(cedula):
    cedula = cedula.strip()
    conn = get_conn()
    asociado = conn.execute(
        "SELECT * FROM asociados WHERE cedula = ?", (cedula,)
    ).fetchone()

    if not asociado:
        conn.close()
        return jsonify({"encontrado": False}), 404

    beneficiarios = conn.execute(
        "SELECT id, parentesco, nombre, documento FROM beneficiarios "
        "WHERE cedula_asociado = ? ORDER BY id",
        (cedula,),
    ).fetchall()
    conn.close()

    asociado_dict = dict(asociado)
    for key, val in asociado_dict.items():
        if val is None or val == "":
            asociado_dict[key] = None

    return jsonify({
        "encontrado": True,
        "asociado": asociado_dict,
        "beneficiarios": [dict(b) for b in beneficiarios],
    })


@app.route("/api/estadisticas")
@login_required
def estadisticas():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM asociados").fetchone()["c"]
    activos = conn.execute(
        "SELECT COUNT(*) c FROM asociados WHERE estado = 'ACTIVO'"
    ).fetchone()["c"]
    conn.close()
    return jsonify({"total_asociados": total, "activos": activos})


# ---------------------------------------------------------------------------
# API de administración (solo admin) — CRUD asociados y beneficiarios
# ---------------------------------------------------------------------------

ASOCIADO_FIELDS = [
    "cedula", "nombre", "telefono", "email", "municipio", "estado",
    "municipio_trabajo", "institucion", "cargo", "edad", "sexo",
    "municipio_residencia", "direccion",
]


@app.route("/api/admin/asociados", methods=["GET"])
@admin_required
def admin_listar_asociados():
    q = request.args.get("q", "").strip()
    conn = get_conn()
    if q:
        rows = conn.execute(
            "SELECT cedula, nombre, municipio, estado FROM asociados "
            "WHERE cedula LIKE ? OR nombre LIKE ? ORDER BY nombre LIMIT 100",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cedula, nombre, municipio, estado FROM asociados ORDER BY nombre LIMIT 100"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/asociados", methods=["POST"])
@admin_required
def admin_crear_asociado():
    data = request.get_json(silent=True) or {}
    cedula = (data.get("cedula") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    if not cedula or not nombre:
        return jsonify({"error": "Cédula y nombre son obligatorios"}), 400

    conn = get_conn()
    existing = conn.execute("SELECT cedula FROM asociados WHERE cedula = ?", (cedula,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Ya existe un asociado con esa cédula"}), 409

    values = [data.get(f) or None for f in ASOCIADO_FIELDS]
    placeholders = ", ".join("?" for _ in ASOCIADO_FIELDS)
    conn.execute(
        f"INSERT INTO asociados ({', '.join(ASOCIADO_FIELDS)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/asociados/<cedula>", methods=["PUT"])
@admin_required
def admin_editar_asociado(cedula):
    data = request.get_json(silent=True) or {}
    conn = get_conn()
    existing = conn.execute("SELECT cedula FROM asociados WHERE cedula = ?", (cedula,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    set_clause = ", ".join(f"{f} = ?" for f in ASOCIADO_FIELDS if f != "cedula")
    values = [data.get(f) or None for f in ASOCIADO_FIELDS if f != "cedula"]
    values.append(cedula)
    conn.execute(f"UPDATE asociados SET {set_clause} WHERE cedula = ?", values)
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/asociados/<cedula>", methods=["DELETE"])
@admin_required
def admin_eliminar_asociado(cedula):
    conn = get_conn()
    conn.execute("DELETE FROM beneficiarios WHERE cedula_asociado = ?", (cedula,))
    conn.execute("DELETE FROM asociados WHERE cedula = ?", (cedula,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/asociados/<cedula>/beneficiarios", methods=["POST"])
@admin_required
def admin_crear_beneficiario(cedula):
    data = request.get_json(silent=True) or {}
    parentesco = (data.get("parentesco") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    documento = (data.get("documento") or "").strip() or None
    if not parentesco or not nombre:
        return jsonify({"error": "Parentesco y nombre son obligatorios"}), 400

    conn = get_conn()
    asociado = conn.execute("SELECT cedula FROM asociados WHERE cedula = ?", (cedula,)).fetchone()
    if not asociado:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    conn.execute(
        "INSERT INTO beneficiarios (cedula_asociado, parentesco, nombre, documento) VALUES (?, ?, ?, ?)",
        (cedula, parentesco, nombre, documento),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/beneficiarios/<int:ben_id>", methods=["PUT"])
@admin_required
def admin_editar_beneficiario(ben_id):
    data = request.get_json(silent=True) or {}
    parentesco = (data.get("parentesco") or "").strip()
    nombre = (data.get("nombre") or "").strip()
    documento = (data.get("documento") or "").strip() or None
    if not parentesco or not nombre:
        return jsonify({"error": "Parentesco y nombre son obligatorios"}), 400

    conn = get_conn()
    conn.execute(
        "UPDATE beneficiarios SET parentesco = ?, nombre = ?, documento = ? WHERE id = ?",
        (parentesco, nombre, documento, ben_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/beneficiarios/<int:ben_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_beneficiario(ben_id):
    conn = get_conn()
    conn.execute("DELETE FROM beneficiarios WHERE id = ?", (ben_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

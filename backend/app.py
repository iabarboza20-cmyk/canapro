import os
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads", "fotos")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, supports_credentials=True)

# IMPORTANTE: en producción define esta variable de entorno con un valor
# largo y aleatorio (por ejemplo con: python3 -c "import secrets; print(secrets.token_hex(32))")
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")


def get_conn():
    return db.get_conn()


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
        "SELECT * FROM usuarios WHERE username = %s", (username,)
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
        "SELECT * FROM asociados WHERE cedula = %s", (cedula,)
    ).fetchone()

    if not asociado:
        conn.close()
        return jsonify({"encontrado": False}), 404

    beneficiarios = conn.execute(
        "SELECT id, parentesco, nombre, documento FROM beneficiarios "
        "WHERE cedula_asociado = %s ORDER BY id",
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
            "WHERE cedula LIKE %s OR nombre LIKE %s ORDER BY nombre LIMIT 100",
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
    existing = conn.execute("SELECT cedula FROM asociados WHERE cedula = %s", (cedula,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Ya existe un asociado con esa cédula"}), 409

    values = [data.get(f) or None for f in ASOCIADO_FIELDS]
    placeholders = ", ".join("%s" for _ in ASOCIADO_FIELDS)
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
    existing = conn.execute("SELECT cedula FROM asociados WHERE cedula = %s", (cedula,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    set_clause = ", ".join(f"{f} = %s" for f in ASOCIADO_FIELDS if f != "cedula")
    values = [data.get(f) or None for f in ASOCIADO_FIELDS if f != "cedula"]
    values.append(cedula)
    conn.execute(f"UPDATE asociados SET {set_clause} WHERE cedula = %s", values)
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/asociados/<cedula>", methods=["DELETE"])
@admin_required
def admin_eliminar_asociado(cedula):
    conn = get_conn()
    conn.execute("DELETE FROM beneficiarios WHERE cedula_asociado = %s", (cedula,))
    conn.execute("DELETE FROM asociados WHERE cedula = %s", (cedula,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/asociados/<cedula>/foto", methods=["POST"])
@admin_required
def admin_subir_foto(cedula):
    conn = get_conn()
    asociado = conn.execute("SELECT foto_url FROM asociados WHERE cedula = %s", (cedula,)).fetchone()
    if not asociado:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    if "foto" not in request.files:
        conn.close()
        return jsonify({"error": "No se envió ningún archivo"}), 400

    archivo = request.files["foto"]
    if archivo.filename == "":
        conn.close()
        return jsonify({"error": "No se seleccionó ningún archivo"}), 400

    ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else ""
    if ext not in ("jpg", "jpeg", "png", "webp"):
        conn.close()
        return jsonify({"error": "Solo se permiten imágenes JPG, PNG o WEBP"}), 400

    archivo.seek(0, os.SEEK_END)
    tamano_mb = archivo.tell() / (1024 * 1024)
    archivo.seek(0)
    if tamano_mb > 5:
        conn.close()
        return jsonify({"error": "La imagen no puede pesar más de 5 MB"}), 400

    nombre_archivo = f"{cedula}.{ext}"
    ruta_destino = os.path.join(UPLOADS_DIR, nombre_archivo)

    # Si ya tenía una foto con otra extensión, la borra para no dejar basura
    foto_anterior = asociado["foto_url"]
    if foto_anterior:
        ruta_anterior = os.path.join(UPLOADS_DIR, os.path.basename(foto_anterior))
        if os.path.exists(ruta_anterior) and ruta_anterior != ruta_destino:
            os.remove(ruta_anterior)

    archivo.save(ruta_destino)

    foto_url = f"/uploads/fotos/{nombre_archivo}"
    conn.execute("UPDATE asociados SET foto_url = %s WHERE cedula = %s", (foto_url, cedula))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "foto_url": foto_url})


@app.route("/api/admin/asociados/<cedula>/foto", methods=["DELETE"])
@admin_required
def admin_eliminar_foto(cedula):
    conn = get_conn()
    asociado = conn.execute("SELECT foto_url FROM asociados WHERE cedula = %s", (cedula,)).fetchone()
    if not asociado:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    foto_url = asociado["foto_url"]
    if foto_url:
        ruta = os.path.join(UPLOADS_DIR, os.path.basename(foto_url))
        if os.path.exists(ruta):
            os.remove(ruta)

    conn.execute("UPDATE asociados SET foto_url = NULL WHERE cedula = %s", (cedula,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/uploads/fotos/<path:filename>")
def servir_foto(filename):
    return send_from_directory(UPLOADS_DIR, filename)


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
    asociado = conn.execute("SELECT cedula FROM asociados WHERE cedula = %s", (cedula,)).fetchone()
    if not asociado:
        conn.close()
        return jsonify({"error": "No existe ese asociado"}), 404

    conn.execute(
        "INSERT INTO beneficiarios (cedula_asociado, parentesco, nombre, documento) VALUES (%s, %s, %s, %s)",
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
        "UPDATE beneficiarios SET parentesco = %s, nombre = %s, documento = %s WHERE id = %s",
        (parentesco, nombre, documento, ben_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/beneficiarios/<int:ben_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_beneficiario(ben_id):
    conn = get_conn()
    conn.execute("DELETE FROM beneficiarios WHERE id = %s", (ben_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API de administración (solo admin) — gestión de usuarios
# ---------------------------------------------------------------------------

@app.route("/api/admin/usuarios", methods=["GET"])
@admin_required
def admin_listar_usuarios():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, rol FROM usuarios ORDER BY username"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/usuarios", methods=["POST"])
@admin_required
def admin_crear_usuario():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    rol = data.get("rol") or ""

    if not username or not password or rol not in ("viewer", "admin"):
        return jsonify({"error": "Usuario, contraseña y rol (viewer/admin) son obligatorios"}), 400
    if len(password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400

    conn = get_conn()
    existing = conn.execute("SELECT id FROM usuarios WHERE username = %s", (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Ya existe un usuario con ese nombre"}), 409

    conn.execute(
        "INSERT INTO usuarios (username, password_hash, rol) VALUES (%s, %s, %s)",
        (username, generate_password_hash(password), rol),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/usuarios/<int:user_id>", methods=["PUT"])
@admin_required
def admin_editar_usuario(user_id):
    data = request.get_json(silent=True) or {}
    rol = data.get("rol")
    password = data.get("password")  # opcional: solo si se quiere cambiar

    conn = get_conn()
    user = conn.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "No existe ese usuario"}), 404

    # Evita que el único admin se quite a sí mismo el rol y se quede sin acceso
    if rol and rol != user["rol"]:
        if user["rol"] == "admin":
            total_admins = conn.execute(
                "SELECT COUNT(*) c FROM usuarios WHERE rol = 'admin'"
            ).fetchone()["c"]
            if total_admins <= 1:
                conn.close()
                return jsonify({"error": "Debe quedar al menos un usuario admin"}), 400
        if rol not in ("viewer", "admin"):
            conn.close()
            return jsonify({"error": "Rol inválido"}), 400
        conn.execute("UPDATE usuarios SET rol = %s WHERE id = %s", (rol, user_id))
        # Si el admin se cambia el rol a sí mismo, su sesión actual pierde privilegios
        if user["username"] == session.get("username"):
            session["rol"] = rol

    if password:
        if len(password) < 6:
            conn.close()
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
        conn.execute(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s",
            (generate_password_hash(password), user_id),
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/usuarios/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_usuario(user_id):
    conn = get_conn()
    user = conn.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "No existe ese usuario"}), 404

    if user["username"] == session.get("username"):
        conn.close()
        return jsonify({"error": "No puedes eliminar tu propia cuenta mientras tienes sesión iniciada"}), 400

    if user["rol"] == "admin":
        total_admins = conn.execute(
            "SELECT COUNT(*) c FROM usuarios WHERE rol = 'admin'"
        ).fetchone()["c"]
        if total_admins <= 1:
            conn.close()
            return jsonify({"error": "Debe quedar al menos un usuario admin"}), 400

    conn.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

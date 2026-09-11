import os
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

import db
import storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

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
            return redirect("/consulta")
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
def index():
    # Landing pública institucional: no requiere sesión. Muestra tarjetas de
    # acceso a los distintos servicios (consulta de asociados, torneo,
    # simulador de créditos); cada una exige login si corresponde.
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/consulta")
@login_required
def consulta_page():
    # Buscador de asociados (antes servido en "/"). Requiere sesión iniciada.
    return send_from_directory(FRONTEND_DIR, "consulta.html")


@app.route("/simulador-creditos")
def simulador_creditos_page():
    # Calculadora de cuotas de ejemplo, pública (no expone datos de
    # asociados ni políticas reales de crédito de la cooperativa).
    return send_from_directory(FRONTEND_DIR, "simulador_creditos.html")


@app.route("/admin")
@admin_required
def admin_page():
    return send_from_directory(FRONTEND_DIR, "admin.html")


@app.route("/torneo")
@login_required
def torneo_page():
    return send_from_directory(FRONTEND_DIR, "torneo.html")


@app.route("/admin/torneo")
@admin_required
def admin_torneo_page():
    return send_from_directory(FRONTEND_DIR, "admin_torneo.html")


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
            "WHERE UPPER(cedula) LIKE UPPER(%s) OR UPPER(nombre) LIKE UPPER(%s) "
            "ORDER BY nombre LIMIT 100",
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

    file_bytes = archivo.read()
    tamano_mb = len(file_bytes) / (1024 * 1024)
    if tamano_mb > 5:
        conn.close()
        return jsonify({"error": "La imagen no puede pesar más de 5 MB"}), 400

    # Borra la foto anterior (si había) antes de subir la nueva
    foto_anterior = asociado["foto_url"]
    if foto_anterior:
        try:
            storage.eliminar_foto(foto_anterior)
        except Exception:
            pass  # no bloquea la subida si falla el borrado de la vieja

    try:
        foto_url = storage.guardar_foto(cedula, ext, file_bytes)
    except Exception as e:
        conn.close()
        return jsonify({"error": f"No se pudo guardar la foto: {e}"}), 502

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

    if asociado["foto_url"]:
        try:
            storage.eliminar_foto(asociado["foto_url"])
        except Exception:
            pass

    conn.execute("UPDATE asociados SET foto_url = NULL WHERE cedula = %s", (cedula,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/uploads/fotos/<path:filename>")
def servir_foto(filename):
    # Solo se usa en modo local (disco). En modo Supabase Storage las fotos
    # se sirven directo desde la URL pública de Supabase.
    return send_from_directory(storage.UPLOADS_DIR, filename)


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

@app.route("/api/estados", methods=["GET"])
@login_required
def listar_estados():
    conn = get_conn()
    rows = conn.execute("SELECT id, nombre FROM estados ORDER BY nombre").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/estados", methods=["POST"])
@admin_required
def admin_crear_estado():
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip().upper()
    if not nombre:
        return jsonify({"error": "El nombre del estado es obligatorio"}), 400

    conn = get_conn()
    existente = conn.execute("SELECT id FROM estados WHERE nombre = %s", (nombre,)).fetchone()
    if existente:
        conn.close()
        return jsonify({"error": "Ya existe un estado con ese nombre"}), 409

    conn.execute("INSERT INTO estados (nombre) VALUES (%s)", (nombre,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/estados/<int:estado_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_estado(estado_id):
    conn = get_conn()
    estado = conn.execute("SELECT * FROM estados WHERE id = %s", (estado_id,)).fetchone()
    if not estado:
        conn.close()
        return jsonify({"error": "No existe ese estado"}), 404

    en_uso = conn.execute(
        "SELECT COUNT(*) c FROM asociados WHERE estado = %s", (estado["nombre"],)
    ).fetchone()["c"]
    if en_uso > 0:
        conn.close()
        return jsonify({
            "error": f"No se puede eliminar: {en_uso} asociado(s) tienen este estado asignado"
        }), 400

    conn.execute("DELETE FROM estados WHERE id = %s", (estado_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


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


# ---------------------------------------------------------------------------
# Torneo interno — API pública (viewer y admin): tabla de posiciones,
# goleadores y destacados por categoría
# ---------------------------------------------------------------------------

@app.route("/api/torneo/categorias")
@login_required
def torneo_categorias():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, nombre, orden FROM categorias ORDER BY orden, nombre"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


TABLA_SQL = """
    WITH stats AS (
        SELECT equipo_local_id AS equipo_id, goles_local AS gf, goles_visitante AS gc,
               CASE WHEN goles_local > goles_visitante THEN 1 ELSE 0 END AS win,
               CASE WHEN goles_local = goles_visitante THEN 1 ELSE 0 END AS draw,
               CASE WHEN goles_local < goles_visitante THEN 1 ELSE 0 END AS loss
        FROM partidos
        WHERE categoria_id = %s AND goles_local IS NOT NULL AND goles_visitante IS NOT NULL
        UNION ALL
        SELECT equipo_visitante_id, goles_visitante, goles_local,
               CASE WHEN goles_visitante > goles_local THEN 1 ELSE 0 END,
               CASE WHEN goles_visitante = goles_local THEN 1 ELSE 0 END,
               CASE WHEN goles_visitante < goles_local THEN 1 ELSE 0 END
        FROM partidos
        WHERE categoria_id = %s AND goles_local IS NOT NULL AND goles_visitante IS NOT NULL
    )
    SELECT e.id, e.nombre, e.escudo_url,
           COUNT(s.equipo_id) AS pj,
           COALESCE(SUM(s.win), 0) AS pg,
           COALESCE(SUM(s.draw), 0) AS pe,
           COALESCE(SUM(s.loss), 0) AS pp,
           COALESCE(SUM(s.gf), 0) AS gf,
           COALESCE(SUM(s.gc), 0) AS gc,
           COALESCE(SUM(s.gf), 0) - COALESCE(SUM(s.gc), 0) AS dif,
           COALESCE(SUM(s.win), 0) * 3 + COALESCE(SUM(s.draw), 0) AS pts
    FROM equipos e
    LEFT JOIN stats s ON s.equipo_id = e.id
    WHERE e.categoria_id = %s
    GROUP BY e.id, e.nombre, e.escudo_url
    ORDER BY pts DESC, dif DESC, gf DESC, e.nombre ASC
"""


@app.route("/api/torneo/tabla/<int:categoria_id>")
@login_required
def torneo_tabla(categoria_id):
    conn = get_conn()
    rows = conn.execute(TABLA_SQL, (categoria_id, categoria_id, categoria_id)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/torneo/goleadores/<int:categoria_id>")
@login_required
def torneo_goleadores(categoria_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT j.id, j.nombre, e.nombre AS equipo_nombre, e.escudo_url,
               COALESCE(SUM(g.cantidad), 0) AS goles
        FROM jugadores j
        JOIN equipos e ON e.id = j.equipo_id
        LEFT JOIN goles g ON g.jugador_id = j.id
        WHERE e.categoria_id = %s
        GROUP BY j.id, j.nombre, e.nombre, e.escudo_url
        HAVING COALESCE(SUM(g.cantidad), 0) > 0
        ORDER BY goles DESC, j.nombre ASC
        LIMIT 20
    """, (categoria_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/torneo/destacados/<int:categoria_id>")
@login_required
def torneo_destacados(categoria_id):
    conn = get_conn()

    goleador = conn.execute("""
        SELECT j.nombre, e.nombre AS equipo_nombre, SUM(g.cantidad) AS goles
        FROM goles g
        JOIN jugadores j ON j.id = g.jugador_id
        JOIN equipos e ON e.id = j.equipo_id
        WHERE e.categoria_id = %s
        GROUP BY j.id, j.nombre, e.nombre
        ORDER BY goles DESC, j.nombre ASC
        LIMIT 1
    """, (categoria_id,)).fetchone()

    tabla = conn.execute("""
        WITH stats AS (
            SELECT equipo_local_id AS equipo_id, goles_local AS gf, goles_visitante AS gc
            FROM partidos
            WHERE categoria_id = %s AND goles_local IS NOT NULL AND goles_visitante IS NOT NULL
            UNION ALL
            SELECT equipo_visitante_id, goles_visitante, goles_local
            FROM partidos
            WHERE categoria_id = %s AND goles_local IS NOT NULL AND goles_visitante IS NOT NULL
        )
        SELECT e.id, e.nombre,
               COUNT(s.equipo_id) AS pj,
               COALESCE(SUM(s.gf), 0) AS gf,
               COALESCE(SUM(s.gc), 0) AS gc
        FROM equipos e
        LEFT JOIN stats s ON s.equipo_id = e.id
        WHERE e.categoria_id = %s
        GROUP BY e.id, e.nombre
    """, (categoria_id, categoria_id, categoria_id)).fetchall()

    tarjetas_por_equipo = conn.execute("""
        SELECT e.id, e.nombre, COALESCE(SUM(t.cantidad), 0) AS total
        FROM equipos e
        LEFT JOIN jugadores j ON j.equipo_id = e.id
        LEFT JOIN tarjetas t ON t.jugador_id = j.id
        WHERE e.categoria_id = %s
        GROUP BY e.id, e.nombre
    """, (categoria_id,)).fetchall()
    conn.close()

    jugados = [dict(r) for r in tabla if r["pj"] > 0]
    ofensiva = max(jugados, key=lambda r: r["gf"]) if jugados else None
    defensiva = min(jugados, key=lambda r: r["gc"]) if jugados else None
    tarjetas_list = [dict(r) for r in tarjetas_por_equipo]
    fair_play = min(tarjetas_list, key=lambda r: r["total"]) if tarjetas_list else None

    return jsonify({
        "goleador": dict(goleador) if goleador else None,
        "ofensiva": {"nombre": ofensiva["nombre"], "goles_favor": ofensiva["gf"]} if ofensiva else None,
        "defensiva": {"nombre": defensiva["nombre"], "goles_contra": defensiva["gc"]} if defensiva else None,
        "fair_play": {"nombre": fair_play["nombre"], "tarjetas": fair_play["total"]} if fair_play else None,
    })


@app.route("/api/torneo/partidos/<int:categoria_id>")
@login_required
def torneo_partidos(categoria_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.id, p.jornada, p.fecha, p.goles_local, p.goles_visitante,
               el.nombre AS local_nombre, el.escudo_url AS local_escudo,
               ev.nombre AS visitante_nombre, ev.escudo_url AS visitante_escudo
        FROM partidos p
        JOIN equipos el ON el.id = p.equipo_local_id
        JOIN equipos ev ON ev.id = p.equipo_visitante_id
        WHERE p.categoria_id = %s
        ORDER BY p.id DESC
    """, (categoria_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Torneo interno — API de administración (solo admin): CRUD de categorías,
# equipos, jugadores, partidos, goles y tarjetas
# ---------------------------------------------------------------------------

@app.route("/api/admin/torneo/categorias", methods=["POST"])
@admin_required
def admin_crear_categoria():
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    orden = data.get("orden") or 0
    if not nombre:
        return jsonify({"error": "El nombre de la categoría es obligatorio"}), 400
    conn = get_conn()
    existente = conn.execute("SELECT id FROM categorias WHERE nombre = %s", (nombre,)).fetchone()
    if existente:
        conn.close()
        return jsonify({"error": "Ya existe una categoría con ese nombre"}), 409
    conn.execute("INSERT INTO categorias (nombre, orden) VALUES (%s, %s)", (nombre, orden))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/categorias/<int:categoria_id>", methods=["PUT"])
@admin_required
def admin_editar_categoria(categoria_id):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    orden = data.get("orden") or 0
    if not nombre:
        return jsonify({"error": "El nombre de la categoría es obligatorio"}), 400
    conn = get_conn()
    conn.execute(
        "UPDATE categorias SET nombre = %s, orden = %s WHERE id = %s", (nombre, orden, categoria_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/categorias/<int:categoria_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_categoria(categoria_id):
    conn = get_conn()
    conn.execute("DELETE FROM categorias WHERE id = %s", (categoria_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/equipos", methods=["GET"])
@admin_required
def admin_listar_equipos():
    categoria_id = request.args.get("categoria_id")
    conn = get_conn()
    if categoria_id:
        rows = conn.execute(
            "SELECT id, categoria_id, nombre, escudo_url FROM equipos "
            "WHERE categoria_id = %s ORDER BY nombre", (categoria_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, categoria_id, nombre, escudo_url FROM equipos ORDER BY nombre"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/torneo/equipos", methods=["POST"])
@admin_required
def admin_crear_equipo():
    data = request.get_json(silent=True) or {}
    categoria_id = data.get("categoria_id")
    nombre = (data.get("nombre") or "").strip()
    if not categoria_id or not nombre:
        return jsonify({"error": "Categoría y nombre del equipo son obligatorios"}), 400
    conn = get_conn()
    conn.execute("INSERT INTO equipos (categoria_id, nombre) VALUES (%s, %s)", (categoria_id, nombre))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/equipos/<int:equipo_id>", methods=["PUT"])
@admin_required
def admin_editar_equipo(equipo_id):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    categoria_id = data.get("categoria_id")
    if not nombre or not categoria_id:
        return jsonify({"error": "Categoría y nombre del equipo son obligatorios"}), 400
    conn = get_conn()
    conn.execute(
        "UPDATE equipos SET nombre = %s, categoria_id = %s WHERE id = %s",
        (nombre, categoria_id, equipo_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/equipos/<int:equipo_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_equipo(equipo_id):
    conn = get_conn()
    equipo = conn.execute("SELECT escudo_url FROM equipos WHERE id = %s", (equipo_id,)).fetchone()
    conn.execute("DELETE FROM equipos WHERE id = %s", (equipo_id,))
    conn.commit()
    conn.close()
    if equipo and equipo["escudo_url"]:
        try:
            storage.eliminar_foto(equipo["escudo_url"])
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/equipos/<int:equipo_id>/escudo", methods=["POST"])
@admin_required
def admin_subir_escudo(equipo_id):
    conn = get_conn()
    equipo = conn.execute("SELECT escudo_url FROM equipos WHERE id = %s", (equipo_id,)).fetchone()
    if not equipo:
        conn.close()
        return jsonify({"error": "No existe ese equipo"}), 404

    if "escudo" not in request.files:
        conn.close()
        return jsonify({"error": "No se envió ningún archivo"}), 400
    archivo = request.files["escudo"]
    if archivo.filename == "":
        conn.close()
        return jsonify({"error": "No se seleccionó ningún archivo"}), 400
    ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else ""
    if ext not in ("jpg", "jpeg", "png", "webp"):
        conn.close()
        return jsonify({"error": "Solo se permiten imágenes JPG, PNG o WEBP"}), 400
    file_bytes = archivo.read()
    tamano_mb = len(file_bytes) / (1024 * 1024)
    if tamano_mb > 5:
        conn.close()
        return jsonify({"error": "La imagen no puede pesar más de 5 MB"}), 400

    foto_anterior = equipo["escudo_url"]
    if foto_anterior:
        try:
            storage.eliminar_foto(foto_anterior)
        except Exception:
            pass

    try:
        escudo_url = storage.guardar_foto(f"equipo_{equipo_id}", ext, file_bytes)
    except Exception as e:
        conn.close()
        return jsonify({"error": f"No se pudo guardar el escudo: {e}"}), 502

    conn.execute("UPDATE equipos SET escudo_url = %s WHERE id = %s", (escudo_url, equipo_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "escudo_url": escudo_url})


@app.route("/api/admin/torneo/jugadores", methods=["GET"])
@admin_required
def admin_listar_jugadores():
    equipo_id = request.args.get("equipo_id")
    conn = get_conn()
    if equipo_id:
        rows = conn.execute(
            "SELECT id, equipo_id, nombre, cedula_asociado, numero FROM jugadores "
            "WHERE equipo_id = %s ORDER BY nombre", (equipo_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, equipo_id, nombre, cedula_asociado, numero FROM jugadores ORDER BY nombre"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/torneo/jugadores", methods=["POST"])
@admin_required
def admin_crear_jugador():
    data = request.get_json(silent=True) or {}
    equipo_id = data.get("equipo_id")
    nombre = (data.get("nombre") or "").strip()
    cedula_asociado = (data.get("cedula_asociado") or "").strip() or None
    numero = (data.get("numero") or "").strip() or None
    if not equipo_id or not nombre:
        return jsonify({"error": "Equipo y nombre del jugador son obligatorios"}), 400
    conn = get_conn()
    conn.execute(
        "INSERT INTO jugadores (equipo_id, nombre, cedula_asociado, numero) VALUES (%s, %s, %s, %s)",
        (equipo_id, nombre, cedula_asociado, numero),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/jugadores/<int:jugador_id>", methods=["PUT"])
@admin_required
def admin_editar_jugador(jugador_id):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    cedula_asociado = (data.get("cedula_asociado") or "").strip() or None
    numero = (data.get("numero") or "").strip() or None
    if not nombre:
        return jsonify({"error": "El nombre del jugador es obligatorio"}), 400
    conn = get_conn()
    conn.execute(
        "UPDATE jugadores SET nombre = %s, cedula_asociado = %s, numero = %s WHERE id = %s",
        (nombre, cedula_asociado, numero, jugador_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/jugadores/<int:jugador_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_jugador(jugador_id):
    conn = get_conn()
    conn.execute("DELETE FROM jugadores WHERE id = %s", (jugador_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/partidos", methods=["GET"])
@admin_required
def admin_listar_partidos():
    categoria_id = request.args.get("categoria_id")
    conn = get_conn()
    base_sql = """
        SELECT p.id, p.categoria_id, p.jornada, p.fecha, p.goles_local, p.goles_visitante,
               p.equipo_local_id, p.equipo_visitante_id,
               el.nombre AS local_nombre, ev.nombre AS visitante_nombre
        FROM partidos p
        JOIN equipos el ON el.id = p.equipo_local_id
        JOIN equipos ev ON ev.id = p.equipo_visitante_id
    """
    if categoria_id:
        rows = conn.execute(base_sql + " WHERE p.categoria_id = %s ORDER BY p.id DESC", (categoria_id,)).fetchall()
    else:
        rows = conn.execute(base_sql + " ORDER BY p.id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/torneo/partidos", methods=["POST"])
@admin_required
def admin_crear_partido():
    data = request.get_json(silent=True) or {}
    categoria_id = data.get("categoria_id")
    equipo_local_id = data.get("equipo_local_id")
    equipo_visitante_id = data.get("equipo_visitante_id")
    jornada = (data.get("jornada") or "").strip() or None
    fecha = (data.get("fecha") or "").strip() or None
    goles_local = data.get("goles_local")
    goles_visitante = data.get("goles_visitante")

    if not categoria_id or not equipo_local_id or not equipo_visitante_id:
        return jsonify({"error": "Categoría, equipo local y equipo visitante son obligatorios"}), 400
    if str(equipo_local_id) == str(equipo_visitante_id):
        return jsonify({"error": "El equipo local y el visitante no pueden ser el mismo"}), 400

    conn = get_conn()
    conn.execute(
        "INSERT INTO partidos (categoria_id, equipo_local_id, equipo_visitante_id, jornada, fecha, "
        "goles_local, goles_visitante) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (categoria_id, equipo_local_id, equipo_visitante_id, jornada, fecha,
         goles_local if goles_local not in ("", None) else None,
         goles_visitante if goles_visitante not in ("", None) else None),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/partidos/<int:partido_id>", methods=["PUT"])
@admin_required
def admin_editar_partido(partido_id):
    data = request.get_json(silent=True) or {}
    equipo_local_id = data.get("equipo_local_id")
    equipo_visitante_id = data.get("equipo_visitante_id")
    jornada = (data.get("jornada") or "").strip() or None
    fecha = (data.get("fecha") or "").strip() or None
    goles_local = data.get("goles_local")
    goles_visitante = data.get("goles_visitante")

    if not equipo_local_id or not equipo_visitante_id:
        return jsonify({"error": "Equipo local y equipo visitante son obligatorios"}), 400
    if str(equipo_local_id) == str(equipo_visitante_id):
        return jsonify({"error": "El equipo local y el visitante no pueden ser el mismo"}), 400

    conn = get_conn()
    conn.execute(
        "UPDATE partidos SET equipo_local_id = %s, equipo_visitante_id = %s, jornada = %s, "
        "fecha = %s, goles_local = %s, goles_visitante = %s WHERE id = %s",
        (equipo_local_id, equipo_visitante_id, jornada, fecha,
         goles_local if goles_local not in ("", None) else None,
         goles_visitante if goles_visitante not in ("", None) else None,
         partido_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/partidos/<int:partido_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_partido(partido_id):
    conn = get_conn()
    conn.execute("DELETE FROM partidos WHERE id = %s", (partido_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/partidos/<int:partido_id>/goles", methods=["GET"])
@admin_required
def admin_listar_goles_partido(partido_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT g.id, g.jugador_id, g.cantidad, j.nombre AS jugador_nombre, j.equipo_id
        FROM goles g JOIN jugadores j ON j.id = g.jugador_id
        WHERE g.partido_id = %s ORDER BY g.id
    """, (partido_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/torneo/partidos/<int:partido_id>/goles", methods=["POST"])
@admin_required
def admin_agregar_gol(partido_id):
    data = request.get_json(silent=True) or {}
    jugador_id = data.get("jugador_id")
    cantidad = data.get("cantidad") or 1
    if not jugador_id:
        return jsonify({"error": "El jugador es obligatorio"}), 400
    conn = get_conn()
    conn.execute(
        "INSERT INTO goles (partido_id, jugador_id, cantidad) VALUES (%s, %s, %s)",
        (partido_id, jugador_id, cantidad),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/goles/<int:gol_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_gol(gol_id):
    conn = get_conn()
    conn.execute("DELETE FROM goles WHERE id = %s", (gol_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/torneo/partidos/<int:partido_id>/tarjetas", methods=["GET"])
@admin_required
def admin_listar_tarjetas_partido(partido_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.id, t.jugador_id, t.tipo, t.cantidad, j.nombre AS jugador_nombre, j.equipo_id
        FROM tarjetas t JOIN jugadores j ON j.id = t.jugador_id
        WHERE t.partido_id = %s ORDER BY t.id
    """, (partido_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/torneo/partidos/<int:partido_id>/tarjetas", methods=["POST"])
@admin_required
def admin_agregar_tarjeta(partido_id):
    data = request.get_json(silent=True) or {}
    jugador_id = data.get("jugador_id")
    tipo = (data.get("tipo") or "").strip().upper()
    cantidad = data.get("cantidad") or 1
    if not jugador_id or tipo not in ("AMARILLA", "ROJA"):
        return jsonify({"error": "Jugador y tipo (AMARILLA/ROJA) son obligatorios"}), 400
    conn = get_conn()
    conn.execute(
        "INSERT INTO tarjetas (partido_id, jugador_id, tipo, cantidad) VALUES (%s, %s, %s, %s)",
        (partido_id, jugador_id, tipo, cantidad),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/admin/torneo/tarjetas/<int:tarjeta_id>", methods=["DELETE"])
@admin_required
def admin_eliminar_tarjeta(tarjeta_id):
    conn = get_conn()
    conn.execute("DELETE FROM tarjetas WHERE id = %s", (tarjeta_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

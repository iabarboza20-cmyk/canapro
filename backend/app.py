import os
import sqlite3
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "canaprosucre.db")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/asociado/<cedula>")
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
        "SELECT parentesco, nombre, documento FROM beneficiarios "
        "WHERE cedula_asociado = ? ORDER BY id",
        (cedula,),
    ).fetchall()
    conn.close()

    asociado_dict = dict(asociado)
    for key, val in asociado_dict.items():
        if val is None or val == "":
            asociado_dict[key] = None  # el frontend decide como mostrar "Sin datos"

    return jsonify({
        "encontrado": True,
        "asociado": asociado_dict,
        "beneficiarios": [dict(b) for b in beneficiarios],
    })


@app.route("/api/estadisticas")
def estadisticas():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM asociados").fetchone()["c"]
    activos = conn.execute(
        "SELECT COUNT(*) c FROM asociados WHERE estado = 'ACTIVO'"
    ).fetchone()["c"]
    conn.close()
    return jsonify({"total_asociados": total, "activos": activos})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

"""
Almacenamiento de fotos de asociados.

- Si defines las variables de entorno SUPABASE_URL y SUPABASE_SERVICE_KEY,
  las fotos se suben al bucket de Supabase Storage (persisten para siempre,
  sobreviven a reinicios y redeploys).
- Si NO las defines, las fotos se guardan en el disco local
  (backend/uploads/fotos/) — esto funciona bien en tu computador, pero
  OJO: en Render (plan gratis) el disco es efímero y las fotos se pierden
  en cada reinicio/redeploy.

Variables de entorno relevantes:
    SUPABASE_URL           ej: https://xxxxx.supabase.co
    SUPABASE_SERVICE_KEY    la "service_role" / "Secret key" del proyecto
                            (Settings > API). NUNCA la compartas en un
                            chat ni la subas a git — solo va en variables
                            de entorno (Render: Environment).
    SUPABASE_BUCKET         nombre del bucket (por defecto: fotos-asociados)

Antes de usar el modo Supabase, crea el bucket manualmente en el panel de
Supabase (Storage > New bucket), marcado como "Public" para que las fotos
se puedan mostrar directo en el navegador sin autenticación.
"""
import os

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads", "fotos")
os.makedirs(UPLOADS_DIR, exist_ok=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "fotos-asociados")

MIME_POR_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def modo():
    return "supabase" if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else "local"


def _headers(content_type=None):
    h = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "x-upsert": "true",
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def guardar_foto(cedula, ext, file_bytes):
    """Guarda la foto y devuelve la URL pública para almacenar en foto_url."""
    nombre_archivo = f"{cedula}.{ext}"

    if modo() == "supabase":
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{nombre_archivo}"
        resp = requests.post(
            url,
            headers=_headers(MIME_POR_EXT.get(ext, "application/octet-stream")),
            data=file_bytes,
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Error subiendo a Supabase Storage: {resp.status_code} {resp.text}")
        return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{nombre_archivo}"

    # --- modo local ---
    ruta_destino = os.path.join(UPLOADS_DIR, nombre_archivo)
    with open(ruta_destino, "wb") as f:
        f.write(file_bytes)
    return f"/uploads/fotos/{nombre_archivo}"


def eliminar_foto(foto_url):
    """Borra la foto anterior de donde esté guardada (Supabase o disco local)."""
    if not foto_url:
        return

    if modo() == "supabase" and SUPABASE_URL in foto_url:
        nombre_archivo = foto_url.rsplit("/", 1)[-1]
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}"
        try:
            requests.delete(
                url,
                headers=_headers("application/json"),
                json={"prefixes": [nombre_archivo]},
                timeout=15,
            )
        except requests.RequestException:
            pass  # no bloquea el flujo si falla el borrado de la foto vieja
        return

    # --- modo local ---
    nombre_archivo = os.path.basename(foto_url)
    ruta = os.path.join(UPLOADS_DIR, nombre_archivo)
    if os.path.exists(ruta):
        os.remove(ruta)

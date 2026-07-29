# Consulta de Asociados CANAPROSUCRE — App Web

Reemplaza la consulta de Excel (BUSCARV) por una aplicación web con base de
datos SQL real.

## Estructura del proyecto

```
canaprosucre/
├── backend/
│   ├── app.py                        # API Flask (rutas, login, CRUD)
│   ├── db.py                         # Conexión: Postgres si hay DATABASE_URL, si no SQLite
│   ├── storage.py                    # Fotos: Supabase Storage si está configurado, si no disco local
│   ├── build_db.py                   # Carga inicial completa desde el Excel (BORRA todo)
│   ├── importar_asociados_activos.py # Carga incremental (agrega/actualiza, no borra)
│   ├── migrate_to_supabase.py        # Migra de SQLite a Postgres/Supabase
│   ├── init_users.py                 # Crea las cuentas viewer/admin (una vez)
│   ├── init_estados.py               # Crea los estados por defecto (una vez)
│   ├── change_password.py            # Cambia la contraseña de un usuario
│   ├── canaprosucre.db               # Base de datos SQLite (modo local)
│   ├── uploads/fotos/                # Fotos guardadas en modo local
│   ├── requirements.txt
│   └── Procfile                      # Para desplegar en Render/Railway
└── frontend/
    ├── login.html                    # Pantalla de inicio de sesión
    ├── index.html                    # Buscador (requiere login)
    ├── admin.html                    # Panel de gestión (asociados, usuarios, estados)
    └── assets/logo.png
```

## Cómo quedó organizada la base de datos

Antes (Excel) tenías todo en una sola fila por asociado, con columnas
BEN 2, BEN 3... hasta BEN 7. Eso obliga a un número fijo de beneficiarios.

Ahora hay dos tablas relacionadas:

**asociados**: cedula (clave), nombre, telefono, email, municipio, estado

**beneficiarios**: id, cedula_asociado (referencia a asociados), parentesco
(CONYUGE, BENEFICIARIO 2, 3...), nombre, documento

Con esto un asociado puede tener 0, 1 o 20 beneficiarios sin columnas vacías,
y puedes agregar más campos (fecha de nacimiento, parentesco real, etc.) sin
romper nada.

## Probarlo en tu computador

```bash
cd backend
pip install -r requirements.txt
python3 app.py
```

Abre `http://localhost:5000` en el navegador y busca por cédula (prueba con
`3734125`).

## Actualizar los datos

Hay dos formas distintas, según el caso:

**⚠️ `build_db.py` borra TODO y reconstruye desde cero** (asociados y
beneficiarios, aunque nunca toca `usuarios`). Solo se usa para la carga
inicial o si realmente quieres reemplazar toda la base:

```bash
cd backend
python3 build_db.py "ruta/al/excel_completo.xlsx"
```

**`importar_asociados_activos.py` no borra nada** — agrega asociados nuevos
y actualiza los que ya existen sin perder datos que no vengan en ese Excel
(fotos, beneficiarios ya cargados, etc.). Úsalo para cargas incrementales:

```bash
cd backend
python3 importar_asociados_activos.py "ruta/al/excel_nuevo.xlsx"
```

Este script espera la hoja "Asociados Activos" con columnas: DOCUMENTO,
ASOCIADO, EDAD, DIRECCION RESIDENCIA, CORREO ELECTRONICO, TELEFONO CELULAR,
MUNICIPIO DE TRABAJO, INST EDUC, CARGO, CONYUGE + beneficiarios, ESTADO,
SEXO. Si cambia el formato del Excel, hay que ajustar los nombres de
columna dentro del script.

## Fotos de perfil

Desde el panel admin (`/admin`), al editar un asociado puedes subir su foto
(JPG/PNG/WEBP, máximo 5MB). La URL queda en el campo `foto_url` de la tabla
`asociados`. El buscador (`/`) la muestra en un círculo arriba de los
datos; si no hay foto, se ve un ícono genérico de silueta.

**Dónde se guardan (automático, sin que tengas que elegir):**

- Si defines `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`, las fotos se suben a
  **Supabase Storage** (persisten para siempre, sin importar reinicios).
- Si NO las defines, se guardan en `backend/uploads/fotos/` (disco local).

**⚠️ Importante en Render (plan gratis) si usas el modo local:** el disco
de Render es *efímero* — cada reinicio o redeploy borra lo que no esté en
git, incluidas las fotos. Por eso, para producción, **usa el modo
Supabase Storage** (ver sección de migración más abajo).

### Configurar Supabase Storage

1. En tu proyecto de Supabase: **Storage → New bucket**.
   - Nombre: `fotos-asociados` (o el que quieras, luego lo defines en
     `SUPABASE_BUCKET`).
   - Márcalo como **Public** (para que las fotos se vean directo en el
     navegador sin autenticación).
2. Define estas variables de entorno (en tu terminal para probar local, o
   en Render → Environment para producción):
   ```
   SUPABASE_URL=https://tu-proyecto.supabase.co
   SUPABASE_SERVICE_KEY=tu_service_role_key
   SUPABASE_BUCKET=fotos-asociados
   ```
   La `SUPABASE_SERVICE_KEY` es la clave "service_role" / "Secret key" de
   Settings → API. **Nunca la pegues en un chat ni la subas a git** —
   solo va en variables de entorno.
3. Reinicia la app. Las próximas fotos que subas van a Supabase Storage
   automáticamente; las que ya tenías en disco local no se migran solas
   (tendrías que volver a subirlas, o pedirme un script que las migre).

## Migrar la base de datos a Supabase (Postgres)

Esto hace que **todos** los cambios que hagas desde el panel admin en
producción (agregar/editar asociados, usuarios, estados, fotos) persistan
para siempre, sin importar reinicios ni redeploys de Render.

`db.py` ya funciona en ambos modos automáticamente:
- Si defines `DATABASE_URL`, usa Postgres/Supabase.
- Si no la defines, sigue usando `canaprosucre.db` con SQLite (como ahora).

**⚠️ Esto lo tienes que correr TÚ, desde tu computador** — este asistente
no tiene acceso de red a Supabase para hacerlo por ti. Y por seguridad,
nunca pegues tu `SUPABASE_SERVICE_KEY` ni tu contraseña de base de datos
en un chat — solo en tu terminal o en el panel de Render.

### Pasos

1. **Consigue tu cadena de conexión:** en Supabase → Settings → Database →
   Connection string → pestaña **URI**. Usa la de **Connection pooling,
   modo Transaction (puerto 6543)** — esta app abre/cierra una conexión
   por solicitud, y el pooler maneja eso mejor que la conexión directa.

2. **Corre la migración desde tu computador** (necesitas tener
   `canaprosucre.db` con tus datos actuales en la misma carpeta):
   ```bash
   cd backend
   pip install -r requirements.txt
   export DATABASE_URL="postgresql://postgres.xxxx:TU_PASSWORD@aws-0-xxxx.pooler.supabase.com:6543/postgres"
   python3 migrate_to_supabase.py
   ```
   Esto crea las tablas en Postgres (si no existen) y copia todos tus
   asociados, beneficiarios, usuarios y estados actuales.

3. **Define `DATABASE_URL` también en Render** (Environment → Add
   Environment Variable) con la misma cadena de conexión, y redeploy.
   Desde ese momento, la app en producción usa Supabase en vez del
   `canaprosucre.db` local.

4. **Verifica:** entra a tu app desplegada, haz un cambio de prueba
   (por ejemplo agrega un estado nuevo), reinicia el servicio manualmente
   en Render, y confirma que el cambio sigue ahí.

**Si algo falla en el paso 2** (error de conexión, de permisos, etc.),
compárteme el mensaje de error completo (sin la contraseña) y lo
resolvemos juntos.

## Publicarla en internet (gratis)

La forma más simple es **Render.com**:

1. Crea una cuenta en https://render.com (puedes usar tu cuenta de GitHub).
2. Sube esta carpeta `canaprosucre` a un repositorio de GitHub.
3. En Render: **New > Web Service**, conecta el repositorio.
4. Configura:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Deploy. Render te da una URL pública tipo
   `https://canaprosucre.onrender.com` que ya sirve tanto la API como el
   formulario (`index.html` se sirve desde la misma app Flask).

Alternativas equivalentes: **Railway.app** (mismo proceso) o
**PythonAnywhere** (bueno si prefieres algo más manual y en español en su
documentación).

### Nota sobre la base de datos en producción

SQLite funciona bien para esta escala (547 asociados) y es la opción más
simple. Si en el futuro necesitas que varias personas editen datos al mismo
tiempo desde un panel de administración, conviene migrar a PostgreSQL
(Render ofrece una base Postgres gratuita que se conecta con el mismo código
cambiando solo la cadena de conexión).

## Sistema de login (viewer / admin)

La app ahora tiene 2 cuentas fijas con distintos permisos:

| Usuario | Contraseña inicial      | Rol    | Puede...                                  |
|---------|--------------------------|--------|--------------------------------------------|
| viewer  | `Canaprosucre2026`       | viewer | Solo consultar (buscador)                  |
| admin   | `Canaprosucre2026Admin`  | admin  | Consultar + agregar/editar/eliminar en `/admin` |

**Primera vez que corres el proyecto** (o si borras `canaprosucre.db` y lo
regeneras con `build_db.py`), crea estas cuentas con:

```bash
cd backend
python3 init_users.py
```

Esto solo crea las cuentas si no existen — correrlo de nuevo no borra
contraseñas que ya hayas cambiado.

### Cambiar las contraseñas (¡hazlo antes de publicar la app!)

```bash
cd backend
python3 change_password.py viewer tu_nueva_contrasena
python3 change_password.py admin otra_contrasena_mas_larga
```

### Cómo funciona

- `/login` — página de inicio de sesión (pública)
- `/` — buscador, requiere sesión iniciada (cualquier rol)
- `/admin` — panel de gestión (agregar/editar/eliminar), solo rol `admin`
- Las sesiones se manejan con cookies de Flask; la clave para firmarlas se
  toma de la variable de entorno `SECRET_KEY`. En Render, defínela en
  **Environment** con un valor aleatorio (genera uno con
  `python3 -c "import secrets; print(secrets.token_hex(32))"`). Si no la
  defines, usa una clave por defecto que **no es segura para producción**.

### Nota importante sobre `build_db.py`

`build_db.py` solo recrea las tablas `asociados` y `beneficiarios` (borra y
reconstruye desde el Excel). Las tablas `usuarios` y `estados` nunca se
tocan ahí, así que puedes actualizar los datos de asociados cuantas veces
quieras sin perder las cuentas, contraseñas o estados personalizados que
hayas creado.

## Estados personalizables

Antes el campo Estado solo aceptaba ACTIVO/INACTIVO fijos en el código.
Ahora es una lista editable: en el panel admin (`/admin` → pestaña
**Estados**) puedes agregar los que necesites (MOROSO, RETIRADO,
FALLECIDO, etc.) y el desplegable de Estado en el formulario de asociado
los toma de ahí automáticamente.

Vienen creados por defecto: `ACTIVO`, `INACTIVO`, `MOROSO`, `RETIRADO`,
`SIN DATO`. Si por alguna razón no existen (por ejemplo, en una
instalación nueva desde cero), créalos con:

```bash
cd backend
python3 init_estados.py
```

No puedes eliminar un estado que esté siendo usado por algún asociado (la
app te avisa cuántos lo tienen asignado) — primero tendrías que
cambiarles el estado a esos asociados.

## Próximos pasos posibles

- Exportar resultados a PDF con el mismo diseño de la ficha.
- Agregar más campos personalizables además de Estado (por ejemplo,
  categorías de municipio o de institución).
- Historial de cambios (quién editó qué y cuándo).

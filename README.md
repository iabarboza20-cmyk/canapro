# Consulta de Asociados CANAPROSUCRE — App Web

Reemplaza la consulta de Excel (BUSCARV) por una aplicación web con base de
datos SQL real.

## Estructura del proyecto

```
canaprosucre/
├── backend/
│   ├── app.py              # API Flask (búsqueda por cédula)
│   ├── build_db.py         # Convierte el Excel en base de datos SQLite
│   ├── canaprosucre.db     # Base de datos ya generada (547 asociados)
│   ├── requirements.txt
│   └── Procfile             # Para desplegar en Render/Railway
└── frontend/
    └── index.html           # Formulario de consulta (mismo diseño verde original)
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

Cuando tengas una versión nueva del Excel:

```bash
cd backend
python3 build_db.py "ruta/al/nuevo_excel.xlsx"
```

Esto regenera `canaprosucre.db` desde cero con los datos más recientes de la
hoja "DATOS".

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
reconstruye desde el Excel). La tabla `usuarios` nunca se toca ahí, así que
puedes actualizar los datos de asociados cuantas veces quieras sin perder
las cuentas ni las contraseñas que hayas cambiado.

## Próximos pasos posibles

- Agregar autenticación para restringir quién puede consultar.
- Formulario de edición/alta de asociados y beneficiarios (CRUD completo).
- Exportar resultados a PDF con el mismo diseño de la ficha.
- Agregar los campos que faltan (institución, cargo, edad, foto) si me
  compartes de dónde salen esos datos.

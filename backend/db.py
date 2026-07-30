"""
Conexión a la base de datos.

- Si existe la variable de entorno DATABASE_URL, se conecta a Postgres
  (Supabase) usando psycopg2.
- Si NO existe, usa el archivo local canaprosucre.db con sqlite3 (esto es
  lo que se usa mientras no se complete la migración a Supabase).

En ambos casos expone el mismo get_conn() con la interfaz que ya usa el
resto del proyecto (conn.execute(sql, params).fetchone()/.fetchall(),
conn.executescript(sql), conn.commit(), conn.close()), usando siempre
placeholders estilo "%s" en las consultas — para SQLite se traducen
automáticamente a "?".
"""
import os
import re
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "canaprosucre.db")


class _PGConnWrapper:
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=None):
        import psycopg2.extras
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or None)
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


class _SQLiteConnWrapper:
    """Traduce placeholders %s -> ? para poder usar las mismas consultas
    escritas para Postgres contra un archivo SQLite local."""

    def __init__(self, sq_conn):
        self._conn = sq_conn

    def execute(self, sql, params=None):
        sql_sqlite = re.sub(r"%s", "?", sql)
        # ON CONFLICT ... DO UPDATE SET x = EXCLUDED.x funciona igual en
        # SQLite moderno (3.24+), así que no hace falta traducir eso.
        cur = self._conn.execute(sql_sqlite, params or [])
        return cur

    def executescript(self, sql):
        return self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    if DATABASE_URL:
        import psycopg2
        pg_conn = psycopg2.connect(DATABASE_URL)
        return _PGConnWrapper(pg_conn)

    sq_conn = sqlite3.connect(SQLITE_PATH)
    sq_conn.row_factory = sqlite3.Row
    return _SQLiteConnWrapper(sq_conn)


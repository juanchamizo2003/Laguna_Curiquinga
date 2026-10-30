import os
import sqlite3
from contextlib import closing
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "base_datos")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "registros.db")

# Columnas añadidas después de la primera versión: (nombre, tipo). Se crean si faltan.
COLUMNAS_NUEVAS = [
    ("confianza", "REAL"),      # confianza de SAM (0-1)
    ("observacion", "TEXT"),    # motivo por el que la captura no es apta (niebla sobre el agua…)
    ("calidad", "REAL"),        # puntaje orientativo de calidad de imagen (0-1)
    ("revision", "TEXT"),       # revisión humana: NULL, 'aprobada' o 'rechazada'
]

def _conectar():
    """Conexión que se cierra al salir del with (en Windows una abierta bloquea el archivo)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)  # el vigilante y el panel escriben a la vez
    conn.row_factory = sqlite3.Row
    return closing(conn)

def inicializar_bd():
    with _conectar() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_foto TEXT NOT NULL UNIQUE,
                fecha_subida TEXT NOT NULL,
                fecha_captura TEXT NOT NULL,
                area INTEGER NOT NULL,
                perimetro INTEGER DEFAULT 0,
                color_hex TEXT NOT NULL,
                estado TEXT NOT NULL,
                ruta_original TEXT NOT NULL,
                ruta_procesada TEXT NOT NULL,
                confianza REAL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                nivel TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                registro_id INTEGER,
                leida INTEGER NOT NULL DEFAULT 0,
                envio TEXT
            )
        ''')
        # Migración: bases creadas antes de cada columna nueva
        columnas = [fila[1] for fila in c.execute("PRAGMA table_info(registros)")]
        for nombre, tipo in COLUMNAS_NUEVAS:
            if nombre not in columnas:
                c.execute(f"ALTER TABLE registros ADD COLUMN {nombre} {tipo}")
        # Migración: el vigilante guardaba "Procesado" y el filtro "Automático" del panel no lo encontraba
        c.execute("UPDATE registros SET estado = 'Procesado (Automático)' WHERE estado = 'Procesado'")
        conn.commit()

def guardar_registro(nombre_foto, fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original,
                     ruta_procesada, confianza=None, observacion=None, calidad=None):
    """Inserta o, si la foto ya existe, sobrescribe su resultado y borra la revisión humana anterior."""
    with _conectar() as conn:
        c = conn.cursor()
        valores = (fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original, ruta_procesada,
                   confianza, observacion, calidad)
        existente = c.execute("SELECT id FROM registros WHERE nombre_foto = ?", (nombre_foto,)).fetchone()
        if existente:
            rec_id = existente["id"]
            c.execute('''
                UPDATE registros
                SET fecha_subida=?, fecha_captura=?, area=?, perimetro=?, color_hex=?, estado=?, ruta_original=?,
                    ruta_procesada=?, confianza=?, observacion=?, calidad=?, revision=NULL
                WHERE id=?
            ''', valores + (rec_id,))
        else:
            c.execute('''
                INSERT INTO registros (fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original,
                                       ruta_procesada, confianza, observacion, calidad, nombre_foto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', valores + (nombre_foto,))
            rec_id = c.lastrowid
        conn.commit()
        return rec_id

def obtener_registros():
    inicializar_bd()
    with _conectar() as conn:
        rows = conn.execute("SELECT * FROM registros ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

def obtener_registro(reg_id):
    with _conectar() as conn:
        fila = conn.execute("SELECT * FROM registros WHERE id = ?", (reg_id,)).fetchone()
        return dict(fila) if fila else None

def marcar_revision(reg_id, revision):
    """revision: 'aprobada', 'rechazada' o None para volver al estado automático."""
    with _conectar() as conn:
        conn.execute("UPDATE registros SET revision = ? WHERE id = ?", (revision, reg_id))
        conn.commit()

def marcar_observacion(reg_id, observacion, conservar_revision=False):
    sql = ("UPDATE registros SET observacion = ? WHERE id = ?" if conservar_revision
           else "UPDATE registros SET observacion = ?, revision = NULL WHERE id = ?")
    with _conectar() as conn:
        conn.execute(sql, (observacion, reg_id))
        conn.commit()

def eliminar_registro(reg_id):
    """Borra el registro y sus alertas: un aviso sobre una captura que ya no existe solo confunde."""
    with _conectar() as conn:
        conn.execute("DELETE FROM registros WHERE id = ?", (reg_id,))
        conn.execute("DELETE FROM alertas WHERE registro_id = ?", (reg_id,))
        conn.commit()

# ---------------------------------------------------------------- alertas

def guardar_alerta(tipo, nivel, mensaje, registro_id=None):
    with _conectar() as conn:
        c = conn.execute(
            "INSERT INTO alertas (fecha, tipo, nivel, mensaje, registro_id) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipo, nivel, mensaje, registro_id),
        )
        conn.commit()
        return c.lastrowid

def obtener_alertas(limite=200, solo_no_leidas=False):
    inicializar_bd()
    filtro = "WHERE leida = 0" if solo_no_leidas else ""
    with _conectar() as conn:
        rows = conn.execute(f"SELECT * FROM alertas {filtro} ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]

def ultima_alerta(tipo):
    with _conectar() as conn:
        fila = conn.execute("SELECT * FROM alertas WHERE tipo = ? ORDER BY id DESC LIMIT 1", (tipo,)).fetchone()
        return dict(fila) if fila else None

def existe_alerta(tipo, registro_id):
    with _conectar() as conn:
        return conn.execute("SELECT 1 FROM alertas WHERE tipo = ? AND registro_id = ?", (tipo, registro_id)).fetchone() is not None

def registros_con_alerta(tipo, registro_ids):
    """Subconjunto de registro_ids que ya tiene una alerta de ese tipo."""
    ids = list(registro_ids)
    if not ids:
        return set()
    with _conectar() as conn:
        filas = conn.execute(f"SELECT registro_id FROM alertas WHERE tipo = ? AND registro_id IN ({','.join('?' * len(ids))})",
                             (tipo, *ids)).fetchall()
        return {f[0] for f in filas}

def alertas_por_registro():
    """{registro_id: [mensajes]} de las alertas ligadas a una captura (la gráfica las marca)."""
    inicializar_bd()
    with _conectar() as conn:
        filas = conn.execute("SELECT registro_id, mensaje FROM alertas WHERE registro_id IS NOT NULL ORDER BY id").fetchall()
    resultado = {}
    for registro_id, mensaje in filas:
        resultado.setdefault(registro_id, []).append(mensaje)
    return resultado

def contar_alertas_no_leidas():
    inicializar_bd()
    with _conectar() as conn:
        return conn.execute("SELECT COUNT(*) FROM alertas WHERE leida = 0").fetchone()[0]

def marcar_alertas_leidas(ids=None):
    with _conectar() as conn:
        if ids is None:
            conn.execute("UPDATE alertas SET leida = 1 WHERE leida = 0")
        else:
            conn.executemany("UPDATE alertas SET leida = 1 WHERE id = ?", [(i,) for i in ids])
        conn.commit()

def registrar_envio(alerta_id, resultado):
    with _conectar() as conn:
        conn.execute("UPDATE alertas SET envio = ? WHERE id = ?", (resultado, alerta_id))
        conn.commit()

def eliminar_alertas():
    with _conectar() as conn:
        conn.execute("DELETE FROM alertas")
        conn.commit()

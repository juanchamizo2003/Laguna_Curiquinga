import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "base_datos")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "registros.db")

def inicializar_bd():
    with sqlite3.connect(DB_PATH) as conn:
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
                ruta_procesada TEXT NOT NULL
            )
        ''')
        conn.commit()

def guardar_registro(nombre_foto, fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original, ruta_procesada):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        existente = c.execute("SELECT id FROM registros WHERE nombre_foto = ?", (nombre_foto,)).fetchone()
        if existente:
            rec_id = existente["id"]
            c.execute('''
                UPDATE registros 
                SET fecha_subida=?, fecha_captura=?, area=?, perimetro=?, color_hex=?, estado=?, ruta_original=?, ruta_procesada=?
                WHERE id=?
            ''', (fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original, ruta_procesada, rec_id))
        else:
            c.execute('''
                INSERT INTO registros (nombre_foto, fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original, ruta_procesada)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (nombre_foto, fecha_subida, fecha_captura, area, perimetro, color_hex, estado, ruta_original, ruta_procesada))
            rec_id = c.lastrowid
        conn.commit()
        return rec_id

def obtener_registros():
    inicializar_bd()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        rows = c.execute("SELECT * FROM registros ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

def obtener_registros_por_fechas(lista_fechas):
    inicializar_bd()
    if not lista_fechas:
        return obtener_registros()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        placeholders = ','.join(['?'] * len(lista_fechas))
        query = f"""
            SELECT * FROM registros 
            WHERE substr(fecha_captura, 1, 10) IN ({placeholders})
               OR substr(fecha_subida, 1, 10) IN ({placeholders})
            ORDER BY id ASC
        """
        rows = c.execute(query, lista_fechas + lista_fechas).fetchall()
        return [dict(r) for r in rows]

def eliminar_registro(reg_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM registros WHERE id = ?", (reg_id,))
        conn.commit()
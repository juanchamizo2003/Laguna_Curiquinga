"""Copias de seguridad de registros.db con la API de backup de SQLite (segura con la base en uso)."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime

from backend import data_base
from backend import config as cfg

DIR_RESPALDOS = os.path.join(data_base.DB_DIR, "respaldos")

def listar_respaldos():
    """[(nombre, ruta, bytes, fecha)] del más reciente al más antiguo."""
    if not os.path.isdir(DIR_RESPALDOS):
        return []
    archivos = []
    for nombre in os.listdir(DIR_RESPALDOS):
        if nombre.startswith("registros_") and nombre.endswith(".db"):
            ruta = os.path.join(DIR_RESPALDOS, nombre)
            archivos.append((nombre, ruta, os.path.getsize(ruta), datetime.fromtimestamp(os.path.getmtime(ruta))))
    return sorted(archivos, key=lambda a: a[3], reverse=True)

def crear_respaldo(conservar=None):
    os.makedirs(DIR_RESPALDOS, exist_ok=True)
    destino = os.path.join(DIR_RESPALDOS, f"registros_{datetime.now():%Y%m%d_%H%M%S}.db")
    with closing(sqlite3.connect(data_base.DB_PATH)) as origen, closing(sqlite3.connect(destino)) as copia:
        origen.backup(copia)
    conservar = conservar if conservar is not None else cfg.cargar()["respaldos"]["conservar"]
    for _, ruta, _, _ in listar_respaldos()[conservar:]:
        os.remove(ruta)
    return destino

def respaldo_vencido(ahora=None):
    horas = cfg.cargar()["respaldos"]["cada_horas"]
    respaldos = listar_respaldos()
    if not respaldos:
        return True
    return ((ahora or datetime.now()) - respaldos[0][3]).total_seconds() >= horas * 3600

"""Estado compartido entre vigilante.py y el panel: latido, bitácora y orden de detención.

El vigilante corre en otro proceso, así que se comunica con Streamlit mediante archivos
en base_datos/servicio/: un JSON con su último latido, un log de texto y una bandera
que, si existe, le pide detenerse.
"""
import os
import re
import sys
import json
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICIO_DIR = os.path.join(BASE_DIR, "base_datos", "servicio")
os.makedirs(SERVICIO_DIR, exist_ok=True)

RUTA_LATIDO = os.path.join(SERVICIO_DIR, "latido.json")
RUTA_LOG = os.path.join(SERVICIO_DIR, "vigilante.log")
RUTA_DETENER = os.path.join(SERVICIO_DIR, "detener")

INTERVALO_LATIDO = 5          # segundos entre latidos del vigilante
TOLERANCIA_LATIDO = 3 * INTERVALO_LATIDO
MAX_BYTES_LOG = 512 * 1024    # al superarlo, el log se recorta a su mitad más reciente

EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

def extraer_fecha_hora_de_nombre(filename):
    """Extrae Fecha (AAAA-MM-DD) y Hora (HH:MM:SS 24h) del nombre del archivo."""
    match = re.search(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', str(filename))
    if match:
        a, m, d, h, mn, s = match.groups()
        return f"{a}-{m}-{d}", f"{h}:{mn}:{s}"
    now = datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")

# ---------------------------------------------------------------- latido

def escribir_latido(datos):
    datos = {**datos, "latido": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    temporal = RUTA_LATIDO + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(temporal, RUTA_LATIDO)  # atómico: el panel nunca lee un JSON a medias

def leer_estado():
    """Último latido del vigilante más 'en_linea' y 'segundos' desde que se escribió."""
    try:
        with open(RUTA_LATIDO, encoding="utf-8") as f:
            datos = json.load(f)
        ultimo = datetime.strptime(datos["latido"], "%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, KeyError):
        return {"en_linea": False, "segundos": None}
    segundos = (datetime.now() - ultimo).total_seconds()
    datos["segundos"] = segundos
    datos["en_linea"] = segundos <= TOLERANCIA_LATIDO and not datos.get("detenido", False)
    return datos

# ---------------------------------------------------------------- bitácora

def registrar(nivel, mensaje):
    """Añade una línea al log del vigilante. Niveles: INFO, OK, AVISO, ERROR."""
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {nivel} | {mensaje}"
    if sys.stdout:  # con pythonw (tarea programada) no hay consola
        print(linea, flush=True)
    try:
        if os.path.exists(RUTA_LOG) and os.path.getsize(RUTA_LOG) > MAX_BYTES_LOG:
            with open(RUTA_LOG, encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
            with open(RUTA_LOG, "w", encoding="utf-8") as f:
                f.writelines(lineas[len(lineas) // 2:])
        with open(RUTA_LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass

def leer_log(n=200):
    """Últimas n líneas del log como tuplas (fecha_hora, nivel, mensaje), la más reciente al final."""
    try:
        with open(RUTA_LOG, encoding="utf-8", errors="replace") as f:
            lineas = f.readlines()[-n:]
    except OSError:
        return []
    entradas = []
    for linea in lineas:
        partes = linea.rstrip("\n").split(" | ", 2)
        if len(partes) == 3:
            entradas.append(tuple(partes))
    return entradas

# ---------------------------------------------------------------- control

def detencion_solicitada():
    return os.path.exists(RUTA_DETENER)

def limpiar_detencion():
    if os.path.exists(RUTA_DETENER):
        os.remove(RUTA_DETENER)

def iniciar_vigilante():
    """Lanza vigilante.py en segundo plano. Devuelve False si ya hay uno en línea."""
    if leer_estado()["en_linea"]:
        return False
    limpiar_detencion()
    comando = [sys.executable, os.path.join(BASE_DIR, "vigilante.py")]
    opciones = dict(cwd=BASE_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform != "win32":
        subprocess.Popen(comando, start_new_session=True, **opciones)
        return True
    # Desacoplado del panel: si Streamlit se reinicia o se cierra, el vigilante sigue trabajando
    banderas = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(comando, creationflags=banderas | subprocess.CREATE_BREAKAWAY_FROM_JOB, **opciones)
    except OSError:
        # El job del proceso padre no permite salir de él: se lanza igual, sin esa garantía
        subprocess.Popen(comando, creationflags=banderas, **opciones)
    return True

def detener_vigilante():
    """Pide al vigilante que se detenga; lo hace en su siguiente vuelta (≈1 s)."""
    with open(RUTA_DETENER, "w") as f:
        f.write(datetime.now().isoformat())

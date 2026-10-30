import os
import sys
import json
import time
import queue
import shutil
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend import config as cfg
from backend.data_base import inicializar_bd, obtener_registros
from backend.motor import DEVICE
from backend.procesamiento import procesar_imagen
from backend.alertas import verificar_inactividad
from backend.respaldo import crear_respaldo, respaldo_vencido
from backend.servicio import (
    INTERVALO_LATIDO, EXTENSIONES_IMAGEN, escribir_latido, leer_estado, registrar,
    detencion_solicitada, limpiar_detencion, SERVICIO_DIR,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLUJO_DIR = os.path.join(BASE_DIR, "flujo_imagenes")

DIR_INGESTA = os.path.join(FLUJO_DIR, "ingesta_camara")
DIR_PROCESADAS = os.path.join(FLUJO_DIR, "fotos_procesadas")
DIR_DESCARTES = os.path.join(FLUJO_DIR, "descartes_historicos")
RUTA_MOTIVOS = os.path.join(DIR_DESCARTES, "_motivos.jsonl")
RUTA_IMPORTADAS = os.path.join(SERVICIO_DIR, "importadas.txt")  # fotos ya traídas de la carpeta de origen

INTERVALO_TAREAS = 60  # s entre comprobaciones de inactividad y respaldo

os.makedirs(DIR_INGESTA, exist_ok=True)
os.makedirs(DIR_PROCESADAS, exist_ok=True)
os.makedirs(DIR_DESCARTES, exist_ok=True)

# Una sola cola: watchdog solo encola y el hilo principal procesa de una en una,
# así SAM nunca corre dos veces en paralelo y el arranque puede encolar pendientes.
cola = queue.Queue()
en_proceso = set()  # nombres ya encolados en esta sesión, para no analizarlos dos veces
estado = {
    "pid": os.getpid(),
    "inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "dispositivo": DEVICE,
    "carpeta": os.path.relpath(DIR_INGESTA, BASE_DIR).replace(os.sep, "/"),
    "origen": "",
    "procesadas": 0,
    "descartes": 0,
    "errores": 0,
    "procesando": None,
    "ultima_imagen": None,
    "ultima_llegada": None,  # última foto recibida, aunque se descartara
}

def encolar(ruta):
    nombre = os.path.basename(ruta)
    if nombre in en_proceso:
        return
    en_proceso.add(nombre)
    cola.put(ruta)

class ImageHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(EXTENSIONES_IMAGEN):
            return
        registrar("INFO", f"Nueva imagen detectada: {os.path.basename(event.src_path)}")
        encolar(event.src_path)

def descartar(ruta, motivo):
    """La foto descartada se borra (solo se guardan las útiles); queda una línea con el motivo, que usan
    la página del servidor y la sincronización para no volver a traerla de la cámara."""
    nombre = os.path.basename(ruta)
    if os.path.exists(ruta):
        os.remove(ruta)
    with open(RUTA_MOTIVOS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"archivo": f"descarte_{nombre}", "fecha": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
                            "motivo": motivo}, ensure_ascii=False) + "\n")

def procesar(ruta):
    filename = os.path.basename(ruta)
    estado["procesando"] = filename
    estado["ultima_llegada"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time.sleep(1.5)  # deja terminar la copia del archivo antes de leerlo
    inicio = time.time()

    try:
        r = procesar_imagen(ruta, "Automático")
        if r["resultado"] == "registrada":
            estado["procesadas"] += 1
            estado["ultima_imagen"] = filename
            area = f"{r['registro']['area']:,}".replace(",", ".")
            registrar("OK", f"{filename}: {area} m² guardado en BD ({time.time() - inicio:.1f} s)")
            for _ in r["alertas"]:
                registrar("AVISO", f"{filename}: se generó una alerta (ver página Alertas)")
        elif r["resultado"] == "descartada":
            descartar(ruta, r["mensaje"])
            estado["descartes"] += 1
            registrar("AVISO", f"{filename}: {r['mensaje']}. Descartada y borrada.")
        else:
            estado["errores"] += 1
            registrar("ERROR", f"{filename}: {r['mensaje']}")
    except Exception as e:
        estado["errores"] += 1
        registrar("ERROR", f"{filename}: {e}")
    finally:
        estado["procesando"] = None

def _importadas():
    try:
        with open(RUTA_IMPORTADAS, encoding="utf-8") as f:
            return {linea.strip() for linea in f if linea.strip()}
    except OSError:
        return set()

def _ya_conocidas():
    # Lo ya importado no se vuelve a copiar aunque luego se borre su registro desde el panel
    nombres = _importadas()
    nombres.update(r["nombre_foto"] for r in obtener_registros())
    nombres.update(os.listdir(DIR_INGESTA))
    nombres.update(f.removeprefix("descarte_") for f in os.listdir(DIR_DESCARTES))  # descartes de versiones anteriores
    nombres.update(_descartadas())
    return nombres

def _descartadas():
    """Nombres de las fotos descartadas (ya borradas), leídos del registro de motivos."""
    try:
        with open(RUTA_MOTIVOS, encoding="utf-8") as f:
            return {json.loads(l)["archivo"].removeprefix("descarte_") for l in f if l.strip()}
    except (OSError, ValueError, KeyError):
        return set()

def encolar_pendientes():
    """Fotos que llegaron a ingesta_camara mientras el vigilante estaba apagado."""
    ya_registradas = {r["nombre_foto"] for r in obtener_registros()}
    pendientes = sorted(
        f for f in os.listdir(DIR_INGESTA)
        if f.lower().endswith(EXTENSIONES_IMAGEN) and f not in ya_registradas
    )
    for f in pendientes:
        encolar(os.path.join(DIR_INGESTA, f))
    if pendientes:
        registrar("INFO", f"{len(pendientes)} imagen(es) pendiente(s) de antes del arranque encoladas")

def sincronizar_origen(carpeta):
    """Copia a ingesta_camara las fotos nuevas de la carpeta donde las deja la cámara."""
    if not carpeta:
        return
    if not os.path.isdir(carpeta):
        registrar("ERROR", f"Carpeta de origen no accesible: {carpeta}")
        return
    conocidas = _ya_conocidas()
    copiadas = 0
    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        if (nombre in conocidas or not nombre.lower().endswith(EXTENSIONES_IMAGEN)
                or not os.path.isfile(ruta) or time.time() - os.path.getmtime(ruta) < 5):  # aún se está escribiendo
            continue
        shutil.copy2(ruta, os.path.join(DIR_INGESTA, nombre))  # watchdog la detecta y la encola
        with open(RUTA_IMPORTADAS, "a", encoding="utf-8") as f:
            f.write(nombre + "\n")
        copiadas += 1
    if copiadas:
        registrar("INFO", f"{copiadas} foto(s) nuevas copiadas desde {carpeta}")

def tareas_periodicas(ultimo):
    """Sincroniza el origen, revisa la inactividad y hace el respaldo cuando toca. Devuelve los nuevos tiempos."""
    ahora = time.time()
    config = cfg.cargar()
    estado["origen"] = config["origen"]["carpeta"]
    if ahora - ultimo["origen"] >= config["origen"]["intervalo_s"]:
        ultimo["origen"] = ahora
        try:
            sincronizar_origen(config["origen"]["carpeta"])
        except Exception as e:
            registrar("ERROR", f"Sincronizando origen: {e}")
    if ahora - ultimo["tareas"] >= INTERVALO_TAREAS:
        ultimo["tareas"] = ahora
        try:
            llegada = estado["ultima_llegada"]
            if verificar_inactividad(config, inicio_servicio=datetime.strptime(estado["inicio"], "%Y-%m-%d %H:%M:%S"),
                                     ultima_llegada=datetime.strptime(llegada, "%Y-%m-%d %H:%M:%S") if llegada else None):
                registrar("AVISO", "Alerta: no llegan capturas nuevas de la cámara")
            if respaldo_vencido():
                registrar("INFO", f"Respaldo creado: {os.path.basename(crear_respaldo())}")
        except Exception as e:
            registrar("ERROR", f"Tareas periódicas: {e}")
    return ultimo

def latir(detener):
    while not detener.is_set():
        escribir_latido({**estado, "en_cola": cola.qsize()})
        detener.wait(INTERVALO_LATIDO)

if __name__ == "__main__":
    previo = leer_estado()
    if previo["en_linea"] and previo.get("pid") != os.getpid():
        print(f"Ya hay un vigilante en línea (PID {previo.get('pid')}). No se inicia otro.")
        sys.exit(0)

    limpiar_detencion()
    inicializar_bd()
    observer = Observer()
    observer.schedule(ImageHandler(), path=DIR_INGESTA, recursive=False)
    observer.start()

    fin_latido = threading.Event()
    threading.Thread(target=latir, args=(fin_latido,), daemon=True).start()
    registrar("INFO", f"Servicio iniciado (PID {os.getpid()}, {DEVICE.upper()}). Escuchando {estado['carpeta']}")
    encolar_pendientes()
    ultimo = {"origen": 0, "tareas": time.time() - INTERVALO_TAREAS + 10}  # primeras tareas a los 10 s

    try:
        while not detencion_solicitada():
            ultimo = tareas_periodicas(ultimo)
            try:
                procesar(cola.get(timeout=1))
            except queue.Empty:
                pass
        registrar("INFO", "Detención solicitada desde el panel")
    except KeyboardInterrupt:
        registrar("INFO", "Detenido con Ctrl+C")
    finally:
        fin_latido.set()
        observer.stop()
        observer.join()
        escribir_latido({**estado, "en_cola": cola.qsize(), "detenido": True})
        limpiar_detencion()
        registrar("INFO", "Servicio detenido")

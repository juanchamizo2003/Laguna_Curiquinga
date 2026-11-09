"""
=============================================================================
SERVICIO DE VIGILANCIA EN SEGUNDO PLANO (DAEMON)
=============================================================================
Este script se ejecuta de forma independiente al panel web. 
Utiliza un patrón "Productor-Consumidor":
- Productor (Watchdog): Detecta nuevas fotos y las empuja a una cola instantáneamente.
- Consumidor (Bucle Principal): Saca las fotos de la cola una por una para procesarlas,
  evitando cuellos de botella y saturación de la memoria/GPU.
"""

import os
import sys
import time
import json
import shutil
import threading
import queue
from datetime import datetime
import cv2

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend import config as cfg
from backend.data_base import inicializar_bd, obtener_registros, marcar_observacion
from backend.procesamiento import procesar_imagen
from backend.respaldo import respaldo_vencido, crear_respaldo
from backend.servicio import ( leer_estado, escribir_latido, limpiar_detencion, detencion_solicitada, registrar)
from backend.calidad import revisar_imagen, revisar_agua

# ==========================================
# CONSTANTES Y VARIABLES GLOBALES
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLUJO_DIR = os.path.join(BASE_DIR, "flujo_imagenes")
DIR_INGESTA = os.path.join(FLUJO_DIR, "ingesta_camara")
DIR_DESCARTES = os.path.join(FLUJO_DIR, "descartes_historicos")

RUTA_MOTIVOS = os.path.join(BASE_DIR, "base_datos", "motivos_descarte.jsonl")
RUTA_IMPORTADAS = os.path.join(BASE_DIR, "base_datos", "fotos_importadas.txt")

EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg")
INTERVALO_TAREAS = 60  # Segundos entre revisiones de inactividad o respaldos
INTERVALO_LATIDO = 5   # Segundos entre cada latido (heartbeat) para el panel web

DEVICE = "cuda"

# Estructuras de datos en memoria
cola = queue.Queue()
en_proceso = set()
estado = {
    "procesando": None,
    "procesadas": 0,
    "descartes": 0,
    "errores": 0,
    "ultima_llegada": None,
    "ultima_imagen": None,
    "inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "origen": "",
    "carpeta": DIR_INGESTA,
    "en_linea": True
}

# ==========================================
# 1. SISTEMA DE COLAS Y WATCHDOG (PRODUCTOR)
# ==========================================
def encolar(ruta):
    """Añade una foto a la cola de procesamiento si no está ya en trámite."""
    nombre = os.path.basename(ruta)
    if nombre in en_proceso:
        return
    en_proceso.add(nombre)
    cola.put(ruta)

class ImageHandler(FileSystemEventHandler):
    """Detecta archivos creados en tiempo real mediante el sistema operativo."""
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(EXTENSIONES_IMAGEN):
            return
        registrar("INFO", f"Nueva imagen detectada: {os.path.basename(event.src_path)}")
        encolar(event.src_path)

# ==========================================
# 2. GESTIÓN DE MEMORIA Y ESTADOS HISTÓRICOS
# ==========================================
def _importadas():
    """Lee el registro de fotos que ya se copiaron desde la cámara."""
    try:
        with open(RUTA_IMPORTADAS, encoding="utf-8") as f:
            return {linea.strip() for linea in f if linea.strip()}
    except OSError:
        return set()

def _descartadas():
    """Lee el JSONL de motivos para saber qué fotos se descartaron."""
    try:
        with open(RUTA_MOTIVOS, encoding="utf-8") as f:
            return {json.loads(l)["archivo"].removeprefix("descarte_") for l in f if l.strip()}
    except (OSError, ValueError, KeyError):
        return set()

def _ya_conocidas():
    """Consolida todas las fotos que el sistema ya conoce."""
    nombres = _importadas()
    nombres.update(r["nombre_foto"] for r in obtener_registros())
    nombres.update(os.listdir(DIR_INGESTA))
    nombres.update(f.removeprefix("descarte_") for f in os.listdir(DIR_DESCARTES))
    nombres.update(_descartadas())
    return nombres

def descartar(ruta, motivo):
    """Mueve la foto descartada al historial, registrando el motivo en JSONL."""
    nombre = os.path.basename(ruta)
    if os.path.exists(ruta):
        # Mueve la imagen en lugar de borrarla
        ruta_descarte = os.path.join(DIR_DESCARTES, f"descarte_{nombre}")
        shutil.move(ruta, ruta_descarte)
        
    with open(RUTA_MOTIVOS, "a", encoding="utf-8") as f:
        registro = {
            "archivo": f"descarte_{nombre}", 
            "fecha": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            "motivo": motivo
        }
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

# ==========================================
# 3. PROCESAMIENTO CENTRAL (CONSUMIDOR)
# ==========================================
def procesar(ruta):
    """El Vigilante inspecciona la imagen, decide si es apta y ejecuta la acción en disco."""
    filename = os.path.basename(ruta)
    estado["procesando"] = filename
    estado["ultima_llegada"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    time.sleep(1.5) 
    inicio = time.time()
    config = cfg.cargar()

    try:
        # --- FILTRO 1: Calidad previa (Foco / Brillo / Oscuridad) ---
        img = cv2.imread(ruta)
        if img is None:
            descartar(ruta, "No se pudo leer la imagen")
            estado["errores"] += 1
            return

        apta, motivo, _ = revisar_imagen(img, config["calidad"])
        del img
        if not apta:
            descartar(ruta, motivo)
            estado["descartes"] += 1
            registrar("AVISO", f"{filename}: {motivo}. Descartada por calidad.")
            return

        # --- PROCESAMIENTO GENERAL ---
        r = procesar_imagen(ruta, "Automático")
        
        if r["resultado"] == "registrada":
            # --- FILTRO 2: Inspección de Niebla sobre la laguna ---
            observacion = revisar_agua(r["registro"]["color_hex"], config["calidad"])
            if observacion:
                marcar_observacion(r["registro"]["id"], observacion)
                descartar(ruta, observacion)
                estado["descartes"] += 1
                registrar("AVISO", f"{filename}: {observacion}. Descartada por el vigilante.")
                return

            # Aprobación final
            estado["procesadas"] += 1
            estado["ultima_imagen"] = filename
            area = f"{r['registro']['area']:,}".replace(",", ".")
            registrar("OK", f"{filename}: {area} m² guardado en BD ({time.time() - inicio:.1f} s)")
            
            for _ in r.get("alertas", []):
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
        en_proceso.discard(filename)

def encolar_pendientes():
    """Encola las fotos que quedaron atascadas en ingesta al reiniciar el servicio."""
    ya_registradas = {r["nombre_foto"] for r in obtener_registros()}
    pendientes = sorted(
        f for f in os.listdir(DIR_INGESTA)
        if f.lower().endswith(EXTENSIONES_IMAGEN) and f not in ya_registradas
    )
    for f in pendientes:
        encolar(os.path.join(DIR_INGESTA, f))
    if pendientes:
        registrar("INFO", f"{len(pendientes)} imagen(es) pendiente(s) de antes del arranque encoladas")

# ==========================================
# 4. TAREAS EN SEGUNDO PLANO Y SINCRONIZACIÓN
# ==========================================
def sincronizar_origen(carpeta):
    """Verifica la carpeta de origen y copia archivos nuevos a ingesta_camara."""
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
                or not os.path.isfile(ruta) or time.time() - os.path.getmtime(ruta) < 5):
            continue
            
        shutil.copy2(ruta, os.path.join(DIR_INGESTA, nombre)) 
        
        with open(RUTA_IMPORTADAS, "a", encoding="utf-8") as f:
            f.write(nombre + "\n")
        copiadas += 1
        
    if copiadas:
        registrar("INFO", f"{copiadas} foto(s) nuevas copiadas desde {carpeta}")

def tareas_periodicas(ultimo):
    """Ejecuta sincronización, verificación de inactividad y respaldos."""
    ahora = time.time()
    config = cfg.cargar()
    estado["origen"] = config["origen"]["carpeta"]
    
    # 1. Sincronización con la cámara
    if ahora - ultimo["origen"] >= config["origen"]["intervalo_s"]:
        ultimo["origen"] = ahora
        try:
            sincronizar_origen(config["origen"]["carpeta"])
        except Exception as e:
            registrar("ERROR", f"Sincronizando origen: {e}")
            
    # 2. Revisión de inactividad y respaldos
    if ahora - ultimo["tareas"] >= INTERVALO_TAREAS:
        ultimo["tareas"] = ahora
        try:
            llegada = estado["ultima_llegada"]
            dt_inicio = datetime.strptime(estado["inicio"], "%Y-%m-%d %H:%M:%S")
            dt_llegada = datetime.strptime(llegada, "%Y-%m-%d %H:%M:%S") if llegada else None
            
            #if verificar_inactividad(config, inicio_servicio=dt_inicio, ultima_llegada=dt_llegada):
              #  registrar("AVISO", "Alerta: no llegan capturas nuevas de la cámara")
                
            if respaldo_vencido():
                ruta_respaldo = crear_respaldo()
                registrar("INFO", f"Respaldo creado: {os.path.basename(ruta_respaldo)}")
        except Exception as e:
            registrar("ERROR", f"Tareas periódicas: {e}")
            
    return ultimo

def latir(detener):
    """Actualiza el archivo de latido para informar el estado al dashboard."""
    while not detener.is_set():
        escribir_latido({**estado, "en_cola": cola.qsize()})
        detener.wait(INTERVALO_LATIDO)

# ==========================================
# 5. BUCLE PRINCIPAL (PUNTO DE ENTRADA)
# ==========================================
if __name__ == "__main__":
    previo = leer_estado()
    if previo.get("en_linea") and previo.get("pid") != os.getpid():
        print(f"Ya hay un vigilante en línea (PID {previo.get('pid')}). No se inicia otro.")
        sys.exit(0)

    limpiar_detencion()
    inicializar_bd()
    os.makedirs(DIR_INGESTA, exist_ok=True)
    os.makedirs(DIR_DESCARTES, exist_ok=True)
    
    observer = Observer()
    observer.schedule(ImageHandler(), path=DIR_INGESTA, recursive=False)
    observer.start()

    fin_latido = threading.Event()
    threading.Thread(target=latir, args=(fin_latido,), daemon=True).start()
    
    registrar("INFO", f"Servicio iniciado (PID {os.getpid()}, {DEVICE.upper()}). Escuchando {estado['carpeta']}")
    
    encolar_pendientes()
    ultimo = {"origen": 0, "tareas": time.time() - INTERVALO_TAREAS + 10}

    try:
        while not detencion_solicitada():
            ultimo = tareas_periodicas(ultimo)
            try:
                ruta_a_procesar = cola.get(timeout=1)
                procesar(ruta_a_procesar)
            except queue.Empty:
                pass 
                
        registrar("INFO", "Detención solicitada desde el panel")
        
    except KeyboardInterrupt:
        registrar("INFO", "Detenido con Ctrl+C")
        
    finally:
        fin_latido.set()
        observer.stop()
        observer.join()
        
        escribir_latido({**estado, "en_cola": cola.qsize(), "detenido": True, "en_linea": False})
        limpiar_detencion()
        registrar("INFO", "Servicio detenido correctamente")
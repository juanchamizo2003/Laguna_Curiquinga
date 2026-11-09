"""
=============================================================================
PIPELINE DE PROCESAMIENTO Y PERSISTENCIA DE DATOS
=============================================================================
Orquesta el cálculo de la IA (motor.py), la generación de trazos y miniaturas,
y el registro oficial en la base de datos y alertas.
No realiza descartes de imágenes (esa política la administra el vigilante.py).
"""
import os
from datetime import datetime, timedelta
import cv2

from backend import config as cfg
from backend.calidad import puntaje
from backend.data_base import guardar_registro, obtener_registro, marcar_observacion
from backend.miniaturas import ruta_miniatura
from backend.servicio import extraer_fecha_hora_de_nombre

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROCESADAS = os.path.join(BASE_DIR, "flujo_imagenes", "fotos_procesadas")
HORAS_NOTIFICAR = 24  # Una foto más antigua guarda su alerta, pero no avisa por Telegram/correo

def es_reciente(fecha_captura, ahora=None):
    """False para capturas antiguas: su alerta no se notifica como nueva."""
    try:
        fecha = datetime.fromisoformat(str(fecha_captura))
    except ValueError:
        return True
    return (ahora or datetime.now()) - fecha <= timedelta(hours=HORAS_NOTIFICAR)

def procesar_imagen(ruta_abs, origen, evaluar_alertas=True, analizar=None, fecha_subida=None):
    """Procesa una foto, genera trazado visual, registra en BD y gestiona alertas."""
    nombre = os.path.basename(ruta_abs)
    config = cfg.cargar()

    img = cv2.imread(ruta_abs)
    if img is None:
        return {"resultado": "error", "mensaje": "No se pudo leer la imagen"}
        
    # Calculamos las métricas de la imagen SOLO para guardarlas en la BD (estadística).
    # Ignoramos si la función dice que es "apta" o no, porque aquí no descartamos.
    from backend.calidad import revisar_imagen
    _, _, metricas = revisar_imagen(img, config["calidad"])
    del img

    # 1. Invocación del Motor de IA (SAM + Homografía + Color)
    if analizar is None:
        from backend.motor import analizar_laguna as analizar
        
    exito, msg, datos = analizar(ruta_abs, config["calibracion"])
    if not exito:
        return {"resultado": "error", "mensaje": msg}
        
    if not datos or not datos.get("area"):
        return {"resultado": "error", "mensaje": "SAM no encontró agua en la imagen"}

    # 2. Generación de Imagen de Salida con Trazo Visual
    os.makedirs(DIR_PROCESADAS, exist_ok=True)
    ruta_trazo = os.path.join(DIR_PROCESADAS, f"trazo_{nombre}")
    cv2.imwrite(ruta_trazo, cv2.cvtColor(datos["img_visual"], cv2.COLOR_RGB2BGR))

    # 3. Guardado Oficial en la Base de Datos
    fecha, hora = extraer_fecha_hora_de_nombre(nombre)
    reg_id = guardar_registro(
        nombre_foto=nombre,
        fecha_subida=fecha_subida or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fecha_captura=f"{fecha} {hora}",
        area=datos["area"],
        perimetro=datos["perimetro"],
        color_hex=datos["color_hex"],
        estado=f"Procesado ({origen})",
        ruta_original=os.path.relpath(ruta_abs, BASE_DIR),
        ruta_procesada=os.path.relpath(ruta_trazo, BASE_DIR),
        confianza=datos.get("confianza"),
        # Ahora sí le pasamos las métricas reales a la función puntaje
        calidad=puntaje(metricas, datos["color_hex"]),
    )
    registro = obtener_registro(reg_id)
    ruta_miniatura(registro)

    # 4. Evaluación de Alertas de Sistema
    alertas = []
    notificada = es_reciente(registro["fecha_captura"])
    if evaluar_alertas:
        from backend.alertas import evaluar_registro
        alertas = evaluar_registro(registro, config, notificar=notificada)

    return {
        "resultado": "registrada", 
        "mensaje": msg, 
        "registro": registro, 
        "alertas": alertas,
        "notificada": notificada
    }
def reprocesar_registro(registro, analizar=None):
    """Vuelve a analizar la foto original de un registro existente."""
    ruta = os.path.join(BASE_DIR, registro["ruta_original"])
    if not os.path.exists(ruta):
        return {"resultado": "error", "mensaje": "No se encuentra la foto original"}
    origen = "Manual" if "Manual" in str(registro["estado"]) else "Automático"
    resultado = procesar_imagen(
        ruta, origen, evaluar_alertas=False, analizar=analizar,
        fecha_subida=registro["fecha_subida"]
    )
    if resultado["resultado"] == "descartada":
        marcar_observacion(registro["id"], resultado["mensaje"])
    return resultado
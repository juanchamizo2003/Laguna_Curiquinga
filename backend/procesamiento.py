"""Flujo común de una captura: calidad → SAM → trazo y miniatura → registro → alertas.

Lo usan el vigilante (origen Automático), la carga manual (Manual) y el reprocesado desde el panel,
así los tres aplican exactamente las mismas reglas.
"""
import os
from datetime import datetime
import cv2

from backend import config as cfg
from backend.calidad import revisar_imagen, revisar_agua, puntaje
from backend.data_base import guardar_registro, obtener_registro, marcar_observacion
from backend.miniaturas import ruta_miniatura
from backend.servicio import extraer_fecha_hora_de_nombre

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_PROCESADAS = os.path.join(BASE_DIR, "flujo_imagenes", "fotos_procesadas")

def procesar_imagen(ruta_abs, origen, evaluar_alertas=True, analizar=None, fecha_subida=None):
    """Procesa una foto ya guardada en su carpeta de origen.

    Devuelve un dict con 'resultado' ∈ {'registrada', 'descartada', 'error'}, 'mensaje',
    y para las registradas 'registro' y 'alertas'. Las descartadas no se guardan: solo quedan las útiles.
    """
    nombre = os.path.basename(ruta_abs)
    config = cfg.cargar()

    img = cv2.imread(ruta_abs)
    if img is None:
        return {"resultado": "error", "mensaje": "No se pudo leer la imagen"}

    apta, motivo, metricas = revisar_imagen(img, config["calidad"])
    del img
    if not apta:
        return {"resultado": "descartada", "mensaje": motivo}

    if analizar is None:
        from backend.motor import analizar_laguna as analizar  # carga torch solo cuando hace falta
    exito, msg, datos = analizar(ruta_abs, config["calibracion"])
    if not exito:
        return {"resultado": "error", "mensaje": msg}
    if not datos["area"]:
        return {"resultado": "descartada", "mensaje": "SAM no encontró agua en la imagen"}
    # Agua sin color (niebla sobre la laguna): el área no es fiable, así que la foto no se guarda
    observacion = revisar_agua(datos["color_hex"], config["calidad"])
    if observacion:
        return {"resultado": "descartada", "mensaje": observacion}

    os.makedirs(DIR_PROCESADAS, exist_ok=True)
    ruta_trazo = os.path.join(DIR_PROCESADAS, f"trazo_{nombre}")
    cv2.imwrite(ruta_trazo, cv2.cvtColor(datos["img_visual"], cv2.COLOR_RGB2BGR))

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
        calidad=puntaje(metricas, datos["color_hex"]),
    )
    registro = obtener_registro(reg_id)
    ruta_miniatura(registro)

    alertas = []
    if evaluar_alertas:
        from backend.alertas import evaluar_registro
        alertas = evaluar_registro(registro, config)

    return {"resultado": "registrada", "mensaje": msg, "registro": registro, "alertas": alertas}

def reprocesar_registro(registro, analizar=None):
    """Vuelve a analizar la foto original de un registro con la calibración y los umbrales actuales."""
    ruta = os.path.join(BASE_DIR, registro["ruta_original"])
    if not os.path.exists(ruta):
        return {"resultado": "error", "mensaje": "No se encuentra la foto original"}
    origen = "Manual" if "Manual" in str(registro["estado"]) else "Automático"
    # Se conserva la fecha de subida: reprocesar no es una captura nueva (cuenta para la alerta de inactividad)
    resultado = procesar_imagen(ruta, origen, evaluar_alertas=False, analizar=analizar,
                                fecha_subida=registro["fecha_subida"])
    if resultado["resultado"] == "descartada":
        # La foto ya no pasa el control: se conserva el registro pero queda fuera de la gráfica
        marcar_observacion(registro["id"], resultado["mensaje"])
    return resultado

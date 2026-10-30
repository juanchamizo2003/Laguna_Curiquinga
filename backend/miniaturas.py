"""Miniaturas de las fotos procesadas para la galería y el carrusel (cargar 1920×1080 por cada una es lento)."""
import os
import cv2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_MINIATURAS = os.path.join(BASE_DIR, "flujo_imagenes", "miniaturas")
ANCHO = 480

def crear_miniatura(ruta_origen, ruta_destino, ancho=ANCHO):
    img = cv2.imread(ruta_origen)
    if img is None:
        return False
    h, w = img.shape[:2]
    if w > ancho:
        img = cv2.resize(img, (ancho, int(h * ancho / w)), interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(ruta_destino), exist_ok=True)
    return cv2.imwrite(ruta_destino, img, [cv2.IMWRITE_JPEG_QUALITY, 82])

def ruta_miniatura(registro, clave="ruta_procesada"):
    """Ruta absoluta de la miniatura; la genera si falta. Si no se puede, devuelve la imagen completa."""
    original = os.path.join(BASE_DIR, str(registro.get(clave) or ""))
    nombre = os.path.splitext(os.path.basename(original))[0] + ".jpg"
    prefijo = "orig_" if clave == "ruta_original" else ""
    destino = os.path.join(DIR_MINIATURAS, prefijo + nombre)
    if os.path.exists(destino) and (not os.path.exists(original) or os.path.getmtime(destino) >= os.path.getmtime(original)):
        return destino
    if os.path.exists(original) and crear_miniatura(original, destino):
        return destino
    return original

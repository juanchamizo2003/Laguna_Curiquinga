import os
import gc
import threading
import cv2
import numpy as np
import torch

# Asume que tienes un archivo config.py en tu backend para guardar la calibración
# Si aún no lo tienes implementado al 100%, las funciones usan valores por defecto seguros.
from backend import config as cfg

# ==========================================
# CONSTANTES Y CONFIGURACIÓN DE RUTAS
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELOS_DIR = os.path.join(BASE_DIR, "modelos")
RUTA_MODELO_SAM = os.path.join(MODELOS_DIR, "sam_vit_b_01ec64.pth")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Variables globales para el manejo de estado en memoria
_predictor = None
_cancelar = threading.Event()

# ==========================================
# 1. CONTROL DE FLUJO Y HILOS (ASINCRONISMO)
# ==========================================
class AnalisisCancelado(Exception):
    """Excepción personalizada para detener el análisis en seco."""
    pass

def cancelar_analisis():
    """Interrumpe el análisis en curso. Ideal si el usuario cambia de pestaña."""
    _cancelar.set()

def permitir_analisis():
    """Restablece la bandera para permitir nuevos análisis."""
    _cancelar.clear()

def _revisar_cancelacion(_modulo, _entrada):
    """Hook que se inyecta en las capas de la IA para revisar si debe detenerse."""
    if _cancelar.is_set():
        raise AnalisisCancelado("Análisis cancelado por el usuario o el sistema")

# ==========================================
# 2. GESTIÓN DEL MODELO IA Y MEMORIA (VRAM/RAM)
# ==========================================
def get_predictor():
    """
    Carga el modelo SAM en memoria de forma 'perezosa' (solo cuando se necesita).
    Además, inyecta los hooks de cancelación entre las capas del modelo.
    """
    global _predictor
    if _predictor is None:
        if not os.path.exists(RUTA_MODELO_SAM):
            raise FileNotFoundError(f"No se encontró el archivo de pesos SAM en: {RUTA_MODELO_SAM}")
        
        from segment_anything import sam_model_registry, SamPredictor
        sam = sam_model_registry["vit_b"](checkpoint=RUTA_MODELO_SAM).to(device=DEVICE)
        
        # Inyectar revisión de cancelación en el encoder (la parte más pesada)
        for bloque in sam.image_encoder.blocks:
            bloque.register_forward_pre_hook(_revisar_cancelacion)
            
        _predictor = SamPredictor(sam)
    return _predictor

def liberar_modelo():
    """Descarga el modelo de la memoria RAM/VRAM para no asfixiar el servidor."""
    global _predictor
    _predictor = None
    _cancelar.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# ==========================================
# 3. PROCESAMIENTO PREVIO (VISIÓN ARTIFICIAL)
# ==========================================
def redimensionar_para_ia(img, max_dim=1024):
    """
    Escala imágenes de alta resolución (ej. 4K de drones) a un tamaño manejable 
    para que la inferencia de la IA tome milisegundos en lugar de segundos.
    """
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        escala = max_dim / float(max(h, w))
        nuevo_w = int(round(w * escala))
        nuevo_h = int(round(h * escala))
        img_res = cv2.resize(img, (nuevo_w, nuevo_h), interpolation=cv2.INTER_AREA)
        return img_res, escala
    return img, 1.0

# ==========================================
# 4. NÚCLEO DE ANÁLISIS (MOTOR PRINCIPAL)
# ==========================================
def analizar_laguna(ruta_img, calibracion=None):
    """
    Toma una imagen, extrae el espejo de agua usando SAM, corrige la perspectiva 
    (homografía) para el cálculo de área, extrae el color con normalización 
    y devuelve las métricas completas.
    """
    # Cargar datos de calibración dinámicos (o usar el diccionario pasado)
    calibracion = calibracion or cfg.cargar()["calibracion"]
    
    if not os.path.exists(ruta_img):
        return False, f"No se encontró el archivo: {ruta_img}", None

    img = cv2.imread(ruta_img)
    if img is None:
        return False, "Error al leer el archivo de imagen", None

    try:
        # 1. Preparación de la imagen
        img_opt, escala = redimensionar_para_ia(img, max_dim=1024)
        h, w = img_opt.shape[:2]
        img_rgb = cv2.cvtColor(img_opt, cv2.COLOR_BGR2RGB)

        predictor = get_predictor()

        # 2. Inferencia con IA (Bloque optimizado para rendimiento)
        with torch.inference_mode():
            predictor.set_image(img_rgb)
            
            # Escalar los puntos configurados a la nueva resolución de la imagen
            puntos = np.array(calibracion["puntos_sam"], dtype=np.float32)
            puntos_referencia = (puntos[:, :2] * escala).astype(np.int32)
            etiquetas = puntos[:, 2].astype(np.int32)

            masks, puntajes, _ = predictor.predict(
                point_coords=puntos_referencia,
                point_labels=etiquetas,
                multimask_output=False
            )

        mascara_agua = masks[0].astype(np.uint8)
        confianza = round(float(puntajes[0]), 4) # Calidad predicha por SAM

        # 3. Cálculo de Área (Corrección de Perspectiva vía Homografía)
        pts_origen_orig = np.float32(calibracion["homografia"])
        pts_origen = pts_origen_orig * escala
        pts_destino = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        
        matriz_homografia = cv2.getPerspectiveTransform(pts_origen, pts_destino)
        mascara_plana = cv2.warpPerspective(mascara_agua, matriz_homografia, (w, h))
        
        area_px = np.sum(mascara_plana)
        area_m2 = int(round((area_px / (escala ** 2)) * calibracion["m2_por_px"]))

        # 4. Cálculo de Color (Normalización por Área de Referencia)
        punto_roca_orig = np.array(calibracion.get("punto_roca", [533, 1031]))
        punto_roca_esc = (punto_roca_orig * escala).astype(int)
        x_r, y_r = punto_roca_esc[0], punto_roca_esc[1]
        
        # Parche de muestra (cuadro dinámico resistente a resoluciones)
        radio = max(2, int(10 * escala)) 
        y1, y2 = max(0, y_r - radio), min(h, y_r + radio)
        x1, x2 = max(0, x_r - radio), min(w, x_r + radio)
        parche_roca = img_rgb[y1:y2, x1:x2]

        if parche_roca.size > 0:
            # Mediana para evitar variaciones por reflejos o sombras
            color_roca_medido = np.median(parche_roca, axis=(0, 1)).astype(float)
            color_roca_patron = np.array(calibracion.get("color_patron", [120.0, 120.0, 120.0]))
            factor_correccion = color_roca_patron / (color_roca_medido + 1e-5)
        else:
            factor_correccion = np.array([1.0, 1.0, 1.0])

        pixeles_agua_crudos = img_rgb[mascara_agua == 1].astype(float)
        if len(pixeles_agua_crudos) > 0:
            # Aplicar filtro de iluminación solo al agua y extraer hexadecimal
            pixeles_agua_corregidos = np.clip(pixeles_agua_crudos * factor_correccion, 0, 255)
            color_promedio = np.mean(pixeles_agua_corregidos, axis=0).astype(int)
            color_hex = f"#{color_promedio[0]:02x}{color_promedio[1]:02x}{color_promedio[2]:02x}".upper()
        else:
            color_hex = "#000000"

        # 5. Representación Visual y Perímetro
        img_resultado_visual = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        perimetro_m = 0

        contornos, _ = cv2.findContours(mascara_agua, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contornos:
            contorno_principal = max(contornos, key=cv2.contourArea)
            
            # Devolver el contorno a la escala de la imagen original para dibujarlo
            if escala != 1.0:
                contorno_principal = (contorno_principal / escala).astype(np.int32)
                
            perimetro_px = cv2.arcLength(contorno_principal, True)
            perimetro_m = int(round(perimetro_px * calibracion.get("m_por_px", 0.05)))
            
            cv2.drawContours(img_resultado_visual, [contorno_principal], -1, (255, 0, 0), 2)

        # 6. Limpieza Quirúrgica de Memoria
        del img, img_opt, img_rgb, masks, mascara_agua
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()

        # 7. Formateo de Resultados
        resultado = {
            "area": area_m2,
            "perimetro": perimetro_m,
            "color_hex": color_hex,
            "confianza": confianza,
            "img_visual": img_resultado_visual
        }

        return True, "Análisis exitoso", resultado

    except AnalisisCancelado as e:
        # Limpieza rápida si se cancela en medio del proceso
        gc.collect()
        if DEVICE == "cuda": torch.cuda.empty_cache()
        return False, str(e), None

    except Exception as e:
        # Limpieza ante errores fatales
        gc.collect()
        if DEVICE == "cuda": torch.cuda.empty_cache()
        return False, f"Error en procesamiento: {str(e)}", None
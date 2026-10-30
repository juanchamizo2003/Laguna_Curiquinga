import os
import gc
import cv2
import numpy as np
import torch

from backend import config as cfg

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELOS_DIR = os.path.join(BASE_DIR, "modelos")
RUTA_MODELO_SAM = os.path.join(MODELOS_DIR, "sam_vit_b_01ec64.pth")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_predictor = None

def get_predictor():
    global _predictor
    if _predictor is None:
        if not os.path.exists(RUTA_MODELO_SAM):
            raise FileNotFoundError(f"No se encontró el archivo de pesos SAM en: {RUTA_MODELO_SAM}")
        from segment_anything import sam_model_registry, SamPredictor
        sam = sam_model_registry["vit_b"](checkpoint=RUTA_MODELO_SAM).to(device=DEVICE)
        _predictor = SamPredictor(sam)
    return _predictor

def redimensionar_para_ia(img, max_dim=1024):
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        escala = max_dim / float(max(h, w))
        nuevo_w = int(round(w * escala))
        nuevo_h = int(round(h * escala))
        img_res = cv2.resize(img, (nuevo_w, nuevo_h), interpolation=cv2.INTER_AREA)
        return img_res, escala
    return img, 1.0

def analizar_laguna(ruta_img, calibracion=None):
    """Segmenta la laguna. calibracion permite probar valores sin guardarlos (pantalla de Configuración)."""
    calibracion = calibracion or cfg.cargar()["calibracion"]
    if not os.path.exists(ruta_img):
        return False, f"No se encontró el archivo: {ruta_img}", None

    img = cv2.imread(ruta_img)
    if img is None:
        return False, "Error al leer el archivo de imagen", None

    try:
        img_opt, escala = redimensionar_para_ia(img, max_dim=1024)
        h, w = img_opt.shape[:2]
        img_rgb = cv2.cvtColor(img_opt, cv2.COLOR_BGR2RGB)

        predictor = get_predictor()

        with torch.inference_mode():
            predictor.set_image(img_rgb)
            puntos = np.array(calibracion["puntos_sam"], dtype=np.float32)
            puntos_referencia = (puntos[:, :2] * escala).astype(np.int32)
            etiquetas = puntos[:, 2].astype(np.int32)

            masks, puntajes, _ = predictor.predict(
                point_coords=puntos_referencia,
                point_labels=etiquetas,
                multimask_output=False
            )

        mascara_agua = masks[0].astype(np.uint8)
        # Calidad de la máscara estimada por SAM (IoU predicho, 0-1)
        confianza = round(float(puntajes[0]), 4)

        pts_origen_orig = np.float32(calibracion["homografia"])
        pts_origen = pts_origen_orig * escala
        pts_destino = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        matriz_homografia = cv2.getPerspectiveTransform(pts_origen, pts_destino)

        mascara_plana = cv2.warpPerspective(mascara_agua, matriz_homografia, (w, h))
        area_px = np.sum(mascara_plana)
        area_m2 = int(round((area_px / (escala ** 2)) * calibracion["m2_por_px"]))

        pixeles_agua = img_rgb[mascara_agua == 1]
        if len(pixeles_agua) > 0:
            color_promedio = np.mean(pixeles_agua, axis=0).astype(int)
            color_hex = f"#{color_promedio[0]:02x}{color_promedio[1]:02x}{color_promedio[2]:02x}".upper()
        else:
            color_hex = "#000000"

        img_resultado_visual = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        perimetro_m = 0

        contornos, _ = cv2.findContours(mascara_agua, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contornos:
            contorno_principal = max(contornos, key=cv2.contourArea)
            if escala != 1.0:
                contorno_principal = (contorno_principal / escala).astype(np.int32)
            perimetro_px = cv2.arcLength(contorno_principal, True)
            perimetro_m = int(round(perimetro_px * calibracion["m_por_px"]))
            cv2.drawContours(img_resultado_visual, [contorno_principal], -1, (255, 0, 0), 2)

        del img, img_opt, img_rgb, masks, mascara_agua
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()

        resultado = {
            "area": area_m2,
            "perimetro": perimetro_m,
            "color_hex": color_hex,
            "confianza": confianza,
            "img_visual": img_resultado_visual
        }

        return True, "Análisis exitoso", resultado

    except Exception as e:
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
        return False, str(e), None
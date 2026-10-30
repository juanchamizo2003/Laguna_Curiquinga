"""Control de calidad de las capturas y estado de validación de cada registro.

Dos filtros:
- revisar_imagen(): antes de SAM. Descarta noches, imágenes quemadas, sin contraste o desenfocadas.
- revisar_agua(): después de SAM. Si el agua segmentada sale casi gris, hay niebla sobre la laguna
  y el área medida no es fiable (caso real: 2 mar 2025, 24.305 m² frente a ~50.000 de las vecinas).
Y uno sobre el conjunto:
- marcar_atipicas(): un área que se aleja de la mediana de las capturas cercanas es un error de
  segmentación (sombra de nube, reflejo) aunque la foto pasara los dos filtros anteriores.
"""
import colorsys
import cv2
import numpy as np
import pandas as pd

from backend import config as cfg

# Recorte que deja fuera el marco negro del ojo de pez y el rótulo de fecha de la cámara
def _recorte(img):
    h, w = img.shape[:2]
    return img[int(h * 0.18):, int(w * 0.10):int(w * 0.90)]

def medir_imagen(img_bgr):
    zona = _recorte(img_bgr)
    gris = cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY)
    return {
        "brillo": float(gris.mean()),
        "contraste": float(gris.std()),
        "nitidez": float(cv2.Laplacian(gris, cv2.CV_64F).var()),
    }

def revisar_imagen(img_bgr, umbrales=None):
    """(apta, motivo, métricas). motivo es None si la imagen es apta."""
    u = umbrales or cfg.cargar()["calidad"]
    m = medir_imagen(img_bgr)
    if m["brillo"] < u["brillo_min"]:
        return False, f"Imagen demasiado oscura (brillo {m['brillo']:.0f})", m
    if m["brillo"] > u["brillo_max"]:
        return False, f"Imagen sobreexpuesta (brillo {m['brillo']:.0f})", m
    if m["contraste"] < u["contraste_min"]:
        return False, f"Sin contraste: niebla densa o lente cubierto ({m['contraste']:.0f})", m
    if m["nitidez"] < u["nitidez_min"]:
        return False, f"Imagen desenfocada o lente empañado (nitidez {m['nitidez']:.0f})", m
    return True, None, m

def saturacion_hex(color_hex):
    try:
        r, g, b = (int(color_hex[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (TypeError, ValueError):
        return None
    return colorsys.rgb_to_hsv(r, g, b)[1]

def revisar_agua(color_hex, umbrales=None):
    """Observación si el color del agua indica niebla sobre la laguna; None si está bien."""
    u = umbrales or cfg.cargar()["calidad"]
    sat = saturacion_hex(color_hex)
    if sat is not None and sat < u["saturacion_agua_min"]:
        return f"Agua sin color ({sat:.2f}): posible niebla sobre la laguna"
    return None

def puntaje(metricas, color_hex):
    """0-1 orientativo para mostrar en el panel: media de cada métrica frente a un valor 'bueno'."""
    partes = [
        min(metricas["contraste"] / 40, 1),
        min(metricas["nitidez"] / 800, 1),
        1 - min(abs(metricas["brillo"] - 125) / 125, 1),
    ]
    sat = saturacion_hex(color_hex)
    if sat is not None:
        partes.append(min(sat / 0.2, 1))
    return round(float(np.mean(partes)), 3)

# ---------------------------------------------------------------- estado de validación

COLORES_ESTADO = {
    "Aprobada": "#2fd27a",
    "Validada": "#2fd27a",
    "Revisar": "#f5a742",
    "No apta": "#f0616d",
    "Rechazada": "#f0616d",
    "Atípica": "#b48cf2",
    "Pendiente": "#8b95a3",
}

# Estados que quedan fuera de la gráfica, los indicadores, las alertas y el reporte
EXCLUIDOS = ("Rechazada", "No apta", "Atípica")

def _valor(registro, clave):
    v = registro.get(clave)
    return None if v is None or (isinstance(v, float) and v != v) else v  # NaN de pandas -> None

def estado_validacion(registro, confianza_min=None):
    """Estado de un registro: la revisión humana manda sobre la calidad y la confianza de SAM."""
    revision = _valor(registro, "revision")
    if revision == "rechazada":
        return "Rechazada"
    if revision == "aprobada":
        return "Aprobada"
    if _valor(registro, "observacion"):
        return "No apta"
    if registro.get("atipica"):
        return "Atípica"
    confianza = _valor(registro, "confianza")
    if confianza is None:
        return "Pendiente"
    umbral = confianza_min if confianza_min is not None else cfg.cargar()["calidad"]["confianza_min"]
    return "Validada" if confianza >= umbral else "Revisar"

def es_confiable(registro, confianza_min=None):
    """Entra en la gráfica, los KPI y las alertas: todo menos lo rechazado, no apto o atípico."""
    return estado_validacion(registro, confianza_min) not in EXCLUIDOS

def marcar_atipicas(registros, umbrales=None):
    """Añade 'atipica' a cada registro y devuelve la misma lista.

    Es atípica la captura cuya área se aleja más de 'atipico_pct' de la mediana de las capturas tomadas
    'atipico_ventana_h' horas antes y después: una laguna no cambia tanto en tan poco tiempo. Con menos de
    'atipico_vecinas' cercanas no se juzga. Una captura recién llegada solo tiene vecinas anteriores, así que
    para ella la regla mira hacia atrás; cuando llegan las siguientes se vuelve a juzgar con ambos lados.
    La aprobación humana manda: una captura aprobada nunca es atípica, pero sí sirve de vecina.
    """
    q = umbrales or cfg.cargar()["calidad"]
    for r in registros:
        r["atipica"] = False
    candidatas = sorted((r for r in registros if _valor(r, "revision") != "rechazada" and not _valor(r, "observacion")),
                        key=lambda r: r["fecha_captura"])
    if len(candidatas) <= q["atipico_vecinas"]:
        return registros
    serie = pd.Series([float(r["area"]) for r in candidatas],
                      index=pd.to_datetime([r["fecha_captura"] for r in candidatas]))
    ventana = serie.rolling(pd.Timedelta(hours=2 * q["atipico_ventana_h"]), center=True, closed="both")
    mediana = ventana.median().to_numpy()
    vecinas = ventana.count().to_numpy() - 1  # la propia captura no cuenta como vecina
    desvio = np.abs(serie.to_numpy() - mediana) / mediana * 100
    for r, d, n in zip(candidatas, desvio, vecinas):
        r["atipica"] = bool(n >= q["atipico_vecinas"] and d > q["atipico_pct"] and _valor(r, "revision") != "aprobada")
    return registros

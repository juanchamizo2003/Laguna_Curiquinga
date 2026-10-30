"""Configuración editable desde el panel, guardada en base_datos/config.json.

Los valores por defecto viven aquí; el JSON solo guarda lo que el usuario cambió, así que
añadir una opción nueva no rompe instalaciones existentes.
"""
import os
import json
import copy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CONFIG = os.path.join(BASE_DIR, "base_datos", "config.json")

POR_DEFECTO = {
    "calidad": {
        "brillo_min": 40,             # media de gris por debajo: noche o cámara tapada
        "brillo_max": 225,            # por encima: imagen quemada
        "contraste_min": 15,          # desviación de gris: niebla muy densa o lente cubierto
        "nitidez_min": 60,            # varianza del laplaciano: desenfocada o lente empañado
        "saturacion_agua_min": 0.08,  # agua casi gris: niebla sobre la laguna, el área no es fiable
        "confianza_min": 0.85,        # confianza de SAM para validar sin revisión humana
        "atipico_pct": 10,            # desviación máxima respecto a la mediana de las capturas cercanas
        "atipico_ventana_h": 2,       # horas antes y después que cuentan como cercanas
        "atipico_vecinas": 3,         # con menos capturas cercanas no se juzga (cargas manuales espaciadas)
    },
    "alertas": {
        "activas": True,
        "cambio_pct": 15,             # variación de la mediana de la última ventana respecto a la anterior
        "mediana_h": 1,               # horas de capturas que se resumen en una mediana antes de comparar
        "area_min": 30000,            # m² por debajo de los cuales se avisa
        "horas_sin_fotos": 6,         # el vigilante en línea pero sin capturas nuevas
    },
    "notificaciones": {
        "telegram": {"activo": False, "token": "", "chat_id": ""},
        "correo": {"activo": False, "servidor": "smtp.gmail.com", "puerto": 587,
                   "usuario": "", "clave": "", "destinatarios": ""},
    },
    "calibracion": {
        # Coordenadas en la imagen original (1920×1080). tipo 1 = agua, 0 = no agua
        "puntos_sam": [[723, 1040, 1], [380, 1000, 0], [490, 1030, 0], [600, 1050, 0]],
        # Esquinas sup-izq, sup-der, inf-izq, inf-der del plano de referencia para la homografía
        "homografia": [[277, 689], [1273, 689], [277, 1077], [1273, 1077]],
        "m2_por_px": 0.192385,
        "m_por_px": 0.4318,
    },
    "origen": {
        "nombre_camara": "CAM-01 Borde norte",
        "carpeta": "",                # carpeta (local o de red) donde la cámara deja las fotos
        "intervalo_s": 30,
    },
    "respaldos": {
        "cada_horas": 24,
        "conservar": 14,
    },
    "acceso": {
        "clave_hash": "",             # vacío = panel sin contraseña
    },
    "pie": {                          # créditos del pie de página (ejemplos hasta que se editen en Configuración)
        "autores": "Ana Pérez, Luis Gómez",
        "correo": "contacto@ejemplo.com",
        "institucion": "Universidad de ejemplo",
    },
    "grafica": {                      # preferencias de la gráfica del inicio
        "tipo": "Puntos",
        "color_auto": "#3cc9b4",
        "color_manual": "#f5a742",
        "tendencia": False,
        "orden": [],                  # orden de las tarjetas en "Otros tipos de gráfico" (vacío = el de siempre)
    },
}

def _fusionar(base, cambios):
    resultado = copy.deepcopy(base)
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _fusionar(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado

def cargar():
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            return _fusionar(POR_DEFECTO, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(POR_DEFECTO)

def guardar(config):
    os.makedirs(os.path.dirname(RUTA_CONFIG), exist_ok=True)
    temporal = RUTA_CONFIG + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.replace(temporal, RUTA_CONFIG)

def actualizar(seccion, valores):
    """Sustituye una sección (p. ej. 'alertas') y guarda. Devuelve la configuración completa."""
    config = cargar()
    config[seccion] = _fusionar(config.get(seccion, {}), valores)
    guardar(config)
    return config

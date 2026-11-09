"""
=============================================================================
GESTOR DE CONFIGURACIÓN DEL SISTEMA
=============================================================================
Este módulo maneja las preferencias del panel de control (dashboard). 
Guarda los cambios del usuario en 'base_datos/config.json'.

Ventaja de esta arquitectura: El JSON solo guarda lo que el usuario modificó.
Si en el futuro agregamos nuevas variables a 'POR_DEFECTO', el sistema no 
romperá las instalaciones existentes porque fusionará las variables nuevas 
con el archivo viejo automáticamente.
"""

import os
import json
import copy

# ==========================================
# RUTAS DE ARCHIVOS
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CONFIG = os.path.join(BASE_DIR, "base_datos", "config.json")

# ==========================================
# DICCIONARIO BASE (VALORES DE FÁBRICA)
# ==========================================
POR_DEFECTO = {
    "calidad": {
        "brillo_min": 40,             # Media de gris por debajo: noche o cámara tapada
        "brillo_max": 225,            # Por encima: imagen quemada por el sol
        "contraste_min": 15,          # Desviación de gris: niebla muy densa o lente cubierto
        "nitidez_min": 60,            # Varianza del laplaciano: desenfocada o lente empañado
        "saturacion_agua_min": 0.08,  # Agua casi gris: niebla sobre la laguna
        "confianza_min": 0.85,        # Confianza de SAM para validar sin revisión humana
        "atipico_pct": 10,            # Desviación máxima respecto a la mediana de capturas cercanas
        "atipico_ventana_h": 2,       # Horas antes y después que cuentan como cercanas
        "atipico_vecinas": 3,         # Mínimo de capturas cercanas para juzgar anomalías
    },
    "alertas": {
        "activas": True,
        "cambio_pct": 15,             # Variación de la mediana de la última ventana respecto a la anterior
        "mediana_h": 1,               # Horas de capturas que se resumen en una mediana antes de comparar
        "area_min": 30000,            # Metros cuadrados por debajo de los cuales se dispara alerta
        "horas_sin_fotos": 6,         # El vigilante está en línea pero no llegan capturas nuevas
    },
    "notificaciones": {
        "telegram": {"activo": False, "token": "", "chat_id": ""},
        "correo": {"activo": False, "servidor": "smtp.gmail.com", "puerto": 587,
                   "usuario": "", "clave": "", "destinatarios": ""},
    },
    "calibracion": {
        # Coordenadas SAM (1920x1080). Etiqueta 1 = agua, 0 = exclusión (roca/muro)
        "puntos_sam": [[723, 1040, 1], [380, 1000, 0], [490, 1030, 0], [600, 1050, 0]],
        
        # Puntos de la imagen origen para enderezar la perspectiva (Homografía)
        "homografia": [[277, 689], [1273, 689], [277, 1077], [1273, 1077]],
        "m2_por_px": 0.192385,
        "m_por_px": 0.4318,
        
        # --- Variables del Motor de Color Avanzado ---
        "punto_roca": [533, 1031],              # Punto central (x,y) de la roca estática
        "color_patron": [120.0, 120.0, 120.0],  # Color RGB ideal de la roca en día despejado
    },
    "origen": {
        "nombre_camara": "CAM-01 Borde norte",
        "carpeta": "",                # Ruta local o de red donde la cámara deposita las fotos
        "intervalo_s": 30,
    },
    "respaldos": {
        "cada_horas": 24,
        "conservar": 14,              # Días de antigüedad antes de borrar respaldos
    },
    "acceso": {
        "clave_hash": "",             # Vacío = panel Streamlit sin contraseña
    },
    "pie": {                          
        "autores": "Ana Pérez, Luis Gómez",
        "correo": "contacto@ejemplo.com",
        "institucion": "Universidad de ejemplo",
    },
    "grafica": {                      
        "tipo": "Puntos",
        "color_auto": "#3cc9b4",
        "color_manual": "#f5a742",
        "tendencia": False,
        "alertas": False,             
        "color_tendencia": "#8b95a3",
        "color_alertas": "#f0616d",
        "orden": [],                  
    },
}

# ==========================================
# LÓGICA DE MANEJO DE DATOS
# ==========================================

def _fusionar(base, cambios):
    """
    Realiza una fusión profunda (deep merge) de dos diccionarios.
    Evita que al actualizar una sola clave (ej. 'brillo_min') se borre el resto 
    del bloque 'calidad'. Es el corazón de la tolerancia a fallos del config.
    """
    resultado = copy.deepcopy(base)
    for clave, valor in cambios.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            # Si ambas son carpetas (diccionarios), entra y fusiona su interior
            resultado[clave] = _fusionar(resultado[clave], valor)
        else:
            # Si es un valor final (número, texto, lista), lo sobrescribe
            resultado[clave] = valor
    return resultado

def cargar():
    """
    Lee el archivo JSON y lo fusiona con los valores POR_DEFECTO.
    Si el archivo no existe (primera vez) o está corrupto, devuelve los 
    valores de fábrica sin detener el programa.
    """
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            datos_guardados = json.load(f)
            return _fusionar(POR_DEFECTO, datos_guardados)
    except (OSError, ValueError):
        # ValueError atrapa errores de JSON mal formado
        return copy.deepcopy(POR_DEFECTO)

def guardar(config):
    """
    Escritura atómica de seguridad. 
    Primero guarda en un archivo temporal (.tmp). Si la escritura termina 
    con éxito, reemplaza el archivo original. Esto previene que el config.json 
    quede corrupto o en blanco si hay un corte de energía a mitad del guardado.
    """
    os.makedirs(os.path.dirname(RUTA_CONFIG), exist_ok=True)
    temporal = RUTA_CONFIG + ".tmp"
    
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    # Reemplazo seguro a nivel de sistema operativo
    os.replace(temporal, RUTA_CONFIG)

def actualizar(seccion, valores):
    """
    Función puente para la interfaz gráfica (Streamlit).
    Permite enviar actualizaciones de una sola sección (ej. modificar solo 
    las alertas) cargando el estado actual, aplicando el cambio y guardando.
    Devuelve la configuración completa actualizada.
    """
    config = cargar()
    # Fusiona solo la sección específica solicitada
    config[seccion] = _fusionar(config.get(seccion, {}), valores)
    guardar(config)
    
    return config
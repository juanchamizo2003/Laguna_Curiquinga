"""Reglas de alerta y su envío por Telegram o correo.

Se evalúan después de guardar cada registro (cambio brusco y área baja, sobre la mediana de la
última ventana) y periódicamente desde el vigilante (sin fotos nuevas). Cada alerta se guarda en la
tabla 'alertas' y, si hay canales configurados, se envía; el resultado del envío queda en la columna 'envio'.
"""
import json
import smtplib
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage

from backend import config as cfg
from backend.calidad import es_confiable, marcar_atipicas
from backend.data_base import obtener_registros, guardar_alerta, ultima_alerta, registrar_envio, registros_con_alerta

NIVELES = {"critica": "Crítica", "aviso": "Aviso", "info": "Info"}

def _fmt_m2(valor):
    return f"{int(valor):,} m²".replace(",", ".")

FORMATO = "%Y-%m-%d %H:%M:%S"  # ordena igual como texto que como fecha: se compara sin convertir cada registro

def _menos(fecha_texto, delta):
    return (datetime.strptime(fecha_texto, FORMATO) - delta).strftime(FORMATO)

def _mediana(bloque):
    return float(statistics.median(r["area"] for r in bloque))

def _origen(bloque, ultimo):
    """Texto que acompaña a un área: la fecha si es una captura suelta, o de cuántas sale la mediana."""
    if len(bloque) == 1:
        return ultimo["fecha_captura"][:10]
    return f"mediana de {len(bloque)} capturas hasta {ultimo['fecha_captura'][:16]}"

def evaluar_registro(registro, config=None, registros=None, notificar=True):
    """Aplica las reglas de área a un registro recién guardado. Devuelve la lista de alertas creadas.

    No se compara una foto suelta: se toma la mediana de las capturas confiables de las últimas
    'mediana_h' horas (hasta este registro) y se compara con la mediana de la ventana anterior.
    Con capturas espaciadas cada ventana tiene una sola foto y equivale a comparar con la anterior.
    """
    config = config or cfg.cargar()
    reglas = config["alertas"]
    confianza_min = config["calidad"]["confianza_min"]
    if not reglas["activas"]:
        return []

    registros = registros if registros is not None else obtener_registros()
    marcar_atipicas(registros, config["calidad"])
    registro = next((r for r in registros if r["id"] == registro["id"]), registro)
    if not es_confiable(registro, confianza_min):
        return []

    fin = registro["fecha_captura"]
    ventana = timedelta(hours=reglas["mediana_h"])
    inicio = _menos(fin, ventana)
    confiables = sorted([r for r in registros if r["id"] != registro["id"] and r["fecha_captura"] <= fin
                         and es_confiable(r, confianza_min)] + [registro], key=lambda r: r["fecha_captura"])
    actual = [r for r in confiables if r["fecha_captura"] > inicio]
    area = _mediana(actual)
    creadas = []

    if area < reglas["area_min"]:
        detalle = registro["nombre_foto"] if len(actual) == 1 else _origen(actual, registro)
        creadas.append(("area_baja", "critica",
                        f"Área de {_fmt_m2(area)} por debajo del mínimo de {_fmt_m2(reglas['area_min'])} ({detalle})"))

    previas = [r for r in confiables if r["fecha_captura"] <= inicio]
    if previas:
        ultima_previa = previas[-1]
        inicio_ref = _menos(ultima_previa["fecha_captura"], ventana)
        referencia = [r for r in previas if r["fecha_captura"] > inicio_ref]
        area_ref = _mediana(referencia)
        cambio = (area - area_ref) / area_ref * 100
        if abs(cambio) >= reglas["cambio_pct"]:
            sentido = "subió" if cambio > 0 else "bajó"
            creadas.append(("cambio_brusco", "aviso",
                            f"El área {sentido} {abs(cambio):.1f}%: de {_fmt_m2(area_ref)} "
                            f"({_origen(referencia, ultima_previa)}) a {_fmt_m2(area)} ({_origen(actual, registro)})"))

    # Una regla avisa una sola vez por ventana: si ya saltó con alguna captura de la ventana actual
    # (este mismo registro reprocesado, "Revisar historial" o la foto de hace 30 s) no se repite
    ids_ventana = [r["id"] for r in actual]
    creadas = [c for c in creadas if not registros_con_alerta(c[0], ids_ventana)]
    ids = [guardar_alerta(tipo, nivel, mensaje, registro["id"]) for tipo, nivel, mensaje in creadas]
    if notificar:
        for alerta_id, (_, nivel, mensaje) in zip(ids, creadas):
            notificar_alerta(alerta_id, nivel, mensaje, config)
    return ids

def verificar_inactividad(config=None, ahora=None, registros=None, inicio_servicio=None, ultima_llegada=None):
    """Alerta si no entra ninguna captura automática en 'horas_sin_fotos'. Una sola vez por periodo.

    inicio_servicio evita avisar nada más arrancar: el plazo cuenta desde la última captura
    o desde que arrancó el vigilante, lo que sea más reciente.
    ultima_llegada es la última foto recibida aunque se descartara (p. ej. de noche): la cámara
    sigue enviando, así que no hay que avisar.
    """
    config = config or cfg.cargar()
    reglas = config["alertas"]
    if not reglas["activas"]:
        return None
    ahora = ahora or datetime.now()
    limite = timedelta(hours=reglas["horas_sin_fotos"])

    registros = registros if registros is not None else obtener_registros()
    automaticos = [r for r in registros if "Automático" in str(r["estado"])]
    referencia = max((r["fecha_subida"] for r in automaticos), default=None)
    ultima = datetime.strptime(referencia, "%Y-%m-%d %H:%M:%S") if referencia else None
    desde_ref = max(d for d in (ultima, inicio_servicio, ultima_llegada, datetime.min) if d)
    if ahora - desde_ref < limite:
        return None

    previa = ultima_alerta("sin_fotos")
    if previa and ahora - datetime.strptime(previa["fecha"], "%Y-%m-%d %H:%M:%S") < limite:
        return None  # ya se avisó en este periodo

    desde = f"desde el {ultima:%d/%m/%Y %H:%M}" if ultima else "desde que se inició el servicio"
    mensaje = f"No llegan capturas de la cámara {desde} (umbral: {reglas['horas_sin_fotos']} h)"
    alerta_id = guardar_alerta("sin_fotos", "aviso", mensaje)
    notificar_alerta(alerta_id, "aviso", mensaje, config)
    return alerta_id

# ---------------------------------------------------------------- envío

def _texto(nivel, mensaje):
    return f"[Laguna Curiquinga · {NIVELES.get(nivel, nivel)}] {mensaje}"

def enviar_telegram(conf, texto):
    url = f"https://api.telegram.org/bot{conf['token']}/sendMessage"
    datos = urllib.parse.urlencode({"chat_id": conf["chat_id"], "text": texto}).encode()
    with urllib.request.urlopen(url, data=datos, timeout=15) as resp:
        respuesta = json.loads(resp.read().decode())
    if not respuesta.get("ok"):
        raise RuntimeError(respuesta.get("description", "respuesta no válida de Telegram"))

def enviar_correo(conf, nivel, texto):
    destinatarios = [d.strip() for d in conf["destinatarios"].replace(";", ",").split(",") if d.strip()]
    if not destinatarios:
        raise ValueError("no hay destinatarios")
    msg = EmailMessage()
    msg["Subject"] = f"Laguna Curiquinga · alerta {NIVELES.get(nivel, nivel).lower()}"
    msg["From"] = conf["usuario"]
    msg["To"] = ", ".join(destinatarios)
    msg.set_content(texto)
    with smtplib.SMTP(conf["servidor"], int(conf["puerto"]), timeout=20) as smtp:
        smtp.starttls()
        smtp.login(conf["usuario"], conf["clave"])
        smtp.send_message(msg)

def enviar(nivel, mensaje, config=None):
    """Envía por los canales activos. Devuelve un resumen legible: 'Telegram: ok · Correo: error (…)'."""
    canales = (config or cfg.cargar())["notificaciones"]
    texto = _texto(nivel, mensaje)
    resultados = []
    if canales["telegram"]["activo"]:
        try:
            enviar_telegram(canales["telegram"], texto)
            resultados.append("Telegram: ok")
        except Exception as e:
            resultados.append(f"Telegram: error ({e})")
    if canales["correo"]["activo"]:
        try:
            enviar_correo(canales["correo"], nivel, texto)
            resultados.append("Correo: ok")
        except Exception as e:
            resultados.append(f"Correo: error ({e})")
    return " · ".join(resultados) if resultados else "Sin canales activos"

def notificar_alerta(alerta_id, nivel, mensaje, config=None):
    resultado = enviar(nivel, mensaje, config)
    registrar_envio(alerta_id, resultado)
    return resultado

"""Análisis de las fotos subidas a mano en segundo plano.

El lote corre en un hilo del servidor, aparte de la página: se puede navegar por otros módulos (o cerrar el
navegador) y sigue trabajando. Su estado vive en este módulo, compartido por todo el servidor: hay un solo
lote a la vez y un solo registro, también si se abren varias pestañas. La página de carga lo consulta cada
segundo mientras corre.

Lo que falta por analizar se guarda en un archivo: si el servidor se reinicia a mitad, el lote se retoma solo.
"""
import os
import sys
import json
import html
import time
import threading
from datetime import datetime

import streamlit as st

from backend.data_base import obtener_registros
from backend.servicio import SERVICIO_DIR, motivo_nombre, fecha_captura_de_nombre
from frontend.components.datos import registros
from frontend.components.formato import formatear_m2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Carpeta separada de ingesta_camara: esa la vigila vigilante.py y procesaría la foto otra vez
DIR_CARGA = os.path.join(BASE_DIR, "flujo_imagenes", "carga_manual")
RUTA_PENDIENTES = os.path.join(SERVICIO_DIR, "lote_pendiente.json")
DURACION_ESTIMADA = 15.0  # s por imagen (SAM en CPU) hasta medir las primeras fotos del lote
MAX_LINEAS = 300          # mensajes visibles: el registro se redibuja cada segundo y un lote puede tener miles

_cerrojo = threading.Lock()
_reanudacion_revisada = False
_estado = {
    "activo": False, "total": 0, "hecho": 0, "actual": "", "inicio_foto": 0.0, "duraciones": [],
    "logs": [], "resumen": {}, "ids": [], "ya": 0, "ya_ids": [], "fin": None, "cancelar": False, "cancelado": False,
    "visto": True,
}

def estado():
    """Copia del estado del lote (se lee desde cualquier sesión sin bloquear el hilo)."""
    with _cerrojo:
        return {**_estado, "logs": list(_estado["logs"]), "resumen": dict(_estado["resumen"]),
                "ids": list(_estado["ids"]), "ya_ids": list(_estado["ya_ids"]),
                "duraciones": list(_estado["duraciones"])}

def _log(nivel, mensaje):
    with _cerrojo:
        _estado["logs"].append((datetime.now().strftime("%H:%M:%S"), nivel, mensaje))

def clasificar(nombre, guardados, vistas=()):
    """Qué pasa con una foto: (motivo por el que se descarta, registro si ya está almacenada).
    guardados: {fecha de captura: registro}. Se compara la captura y no el nombre: con o sin la letra final, o
    con otra extensión en mayúsculas, sigue siendo la misma foto."""
    motivo = motivo_nombre(nombre)
    if motivo:
        return motivo, None
    captura = fecha_captura_de_nombre(nombre)
    if captura in vistas:
        return "está repetida en este lote (misma fecha y hora)", None
    return "", guardados.get(captura)

def _guardar_pendientes(rutas):
    """Fotos que faltan por analizar, para retomarlas si el servidor se reinicia a mitad."""
    if rutas:
        temporal = RUTA_PENDIENTES + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(rutas, f)
        os.replace(temporal, RUTA_PENDIENTES)
    elif os.path.exists(RUTA_PENDIENTES):
        os.remove(RUTA_PENDIENTES)

def _borrar(ruta):
    if ruta and os.path.isfile(ruta):
        os.remove(ruta)

def _limpiar_huerfanas():
    """Quita de la carpeta de carga las fotos que no pertenecen a ningún registro (p. ej. registros eliminados)."""
    if not os.path.isdir(DIR_CARGA):
        return
    usadas = {os.path.basename(str(r.get("ruta_original") or "")) for r in obtener_registros()}
    for nombre in os.listdir(DIR_CARGA):
        if nombre not in usadas:
            _borrar(os.path.join(DIR_CARGA, nombre))

def _lanzar(tareas, mensaje):
    with _cerrojo:
        _estado.update(activo=True, total=len(tareas), hecho=0, actual="", inicio_foto=time.time(), duraciones=[],
                       logs=[], resumen={"registrada": 0, "descartada": 0, "error": 0}, ids=[], ya=0, ya_ids=[],
                       fin=None, cancelar=False, cancelado=False, visto=False)
    _log("INFO", mensaje)
    threading.Thread(target=_trabajar, args=(tareas,), daemon=True, name="lote-manual").start()

def iniciar(archivos, guardados):
    """Lanza el hilo con todas las fotos subidas, en su orden; guardados: {fecha de captura: registro}.
    Las ya almacenadas no se analizan: el registro lo indica y sigue con la siguiente. Los bytes subidos solo
    existen durante esta ejecución del script: las nuevas se escriben aquí en disco y el hilo usa sus rutas."""
    with _cerrojo:
        if _estado["activo"]:
            return
    _limpiar_huerfanas()
    os.makedirs(DIR_CARGA, exist_ok=True)
    tareas, vistas = [], set()
    for archivo in archivos:
        motivo, guardado = clasificar(archivo.name, guardados, vistas)
        ruta = None
        if not motivo:
            vistas.add(fecha_captura_de_nombre(archivo.name))
            if guardado is None:
                ruta = os.path.join(DIR_CARGA, archivo.name)
                with open(ruta, "wb") as f:
                    f.write(archivo.getbuffer())
        tareas.append({"nombre": archivo.name, "ruta": ruta, "guardado": guardado, "motivo": motivo})
    _lanzar(tareas, f"Iniciando el análisis de {len(tareas)} imagen(es)…")

def reanudar():
    """Una vez por arranque del servidor: si quedó un lote a medias, lo retoma con las fotos que faltaban."""
    global _reanudacion_revisada
    with _cerrojo:
        if _reanudacion_revisada or _estado["activo"]:
            return
        _reanudacion_revisada = True
    if not os.path.isfile(RUTA_PENDIENTES):
        return
    try:
        with open(RUTA_PENDIENTES, encoding="utf-8") as f:
            rutas = [r for r in json.load(f) if os.path.isfile(r)]
    except (OSError, ValueError):
        rutas = []
    # La foto que se estaba analizando pudo llegar a guardarse: esa ya no se repite
    guardados = {r["fecha_captura"] for r in obtener_registros()}
    rutas = [r for r in rutas if fecha_captura_de_nombre(os.path.basename(r)) not in guardados]
    if not rutas:
        _guardar_pendientes([])
        return
    tareas = [{"nombre": os.path.basename(r), "ruta": r, "guardado": None, "motivo": ""} for r in rutas]
    _lanzar(tareas, f"Retomando {len(tareas)} imagen(es) que quedaron pendientes al reiniciarse el servidor…")

def cancelar():
    """Detiene el lote ya: interrumpe la foto en curso (no se guarda) y no empieza las que faltan."""
    with _cerrojo:
        _estado["cancelar"] = True
    motor = sys.modules.get("backend.motor")  # solo si ya se cargó: importarlo aquí tardaría varios segundos
    if motor is not None:
        motor.cancelar_analisis()
    _log("AVISO", "Cancelando el análisis…")

def marcar_visto():
    with _cerrojo:
        _estado["visto"] = True

def limpiar():
    """Vacía el registro del último lote (no hace nada si hay uno en curso)."""
    with _cerrojo:
        if _estado["activo"]:
            return
        _estado.update(total=0, hecho=0, actual="", duraciones=[], logs=[], resumen={}, ids=[], ya=0, ya_ids=[],
                       fin=None, cancelado=False, visto=True)

def limpiar_al_abrir():
    """Al recargar la pestaña (sesión nueva) el registro empieza vacío; salvo si hay un lote en curso o uno
    terminado cuyo resultado aún no se vio (se conserva para que no se pierda)."""
    if st.session_state.get("_registro_sesion"):
        return
    st.session_state["_registro_sesion"] = True
    e = estado()
    if not e["activo"] and e["visto"]:
        limpiar()

def _cargar_modelo():
    """Carga SAM antes de la primera foto: así su espera no se confunde con el % de esa foto."""
    _log("INFO", "Cargando el modelo SAM…")
    from backend.procesamiento import procesar_imagen  # importa torch: solo si hay algo que analizar
    try:
        from backend.motor import get_predictor, permitir_analisis
        permitir_analisis()
        get_predictor()
    except Exception as e:  # p. ej. faltan los pesos: cada foto lo dirá como error
        _log("ERROR", f"No se pudo cargar el modelo SAM: {html.escape(str(e))}")
    return procesar_imagen

def _trabajar(tareas):
    procesar_imagen = None
    pendientes = [t["ruta"] for t in tareas if t["ruta"]]
    try:
        _guardar_pendientes(pendientes)
        for i, tarea in enumerate(tareas):
            nombre, ruta, guardado = tarea["nombre"], tarea["ruta"], tarea["guardado"]
            with _cerrojo:
                if _estado["cancelar"]:
                    break
                _estado.update(hecho=i)
            prefijo = f"[{i + 1}/{len(tareas)}] {html.escape(nombre)}"
            if tarea["motivo"]:
                with _cerrojo:
                    _estado["resumen"]["descartada"] += 1
                _log("AVISO", f"{prefijo} descartada: {html.escape(tarea['motivo'])}.")
                continue
            if guardado is not None:
                # Ya analizada antes: se informa y se sigue con la siguiente, sin pasar por SAM
                with _cerrojo:
                    _estado["ya"] += 1
                    _estado["ya_ids"].append(guardado["id"])
                    _estado["ids"].append(guardado["id"])
                _log("INFO", f"{prefijo} ya está almacenada en la base de datos ({formatear_m2(guardado['area'])}): "
                             "no se vuelve a analizar.")
                continue
            if procesar_imagen is None:
                procesar_imagen = _cargar_modelo()
                with _cerrojo:
                    if _estado["cancelar"]:  # cancelado mientras se cargaba el modelo
                        break
            inicio = time.time()
            with _cerrojo:
                _estado.update(actual=nombre, inicio_foto=inicio)
            try:
                r = procesar_imagen(ruta, "Manual")
            except Exception as e:  # una foto rota no debe parar el resto del lote
                r = {"resultado": "error", "mensaje": str(e)}
            pendientes.remove(ruta)
            _guardar_pendientes(pendientes)
            with _cerrojo:
                interrumpida = _estado["cancelar"] and r["resultado"] == "error"
                _estado["actual"] = ""
            if interrumpida:
                _borrar(ruta)
                _log("AVISO", f"{prefijo} · análisis interrumpido: no se guardó.")
                break
            with _cerrojo:
                _estado["resumen"][r["resultado"]] += 1
                _estado["actual"] = ""
                if r["resultado"] == "registrada":
                    _estado["ids"].append(r["registro"]["id"])
                    _estado["duraciones"].append(time.time() - inicio)
            if r["resultado"] == "registrada":
                _log("OK", f"{prefijo} · 100 % → {formatear_m2(r['registro']['area'])}")
                if r.get("alertas"):
                    aviso = "" if r.get("notificada", True) else " Es una foto antigua: se guardó sin notificar."
                    _log("AVISO", f"{prefijo}: generó {len(r['alertas'])} alerta(s). Revisa la página Alertas.{aviso}")
            elif r["resultado"] == "descartada":
                _borrar(ruta)
                _log("AVISO", f"{prefijo} · 100 % → descartada y no guardada: {html.escape(r['mensaje'])}")
            else:
                _borrar(ruta)  # sin registro la foto no sirve de nada en la carpeta: se puede volver a subir
                _log("ERROR", f"{prefijo} · error: {html.escape(str(r['mensaje']))}")
    except Exception as e:
        _log("ERROR", f"El análisis se detuvo: {html.escape(str(e))}")
    finally:
        # Lo que no llegó a analizarse (cancelado o fallo) no se queda suelto en la carpeta
        for ruta in pendientes:
            _borrar(ruta)
        _guardar_pendientes([])
        if procesar_imagen is not None:
            try:
                from backend.motor import liberar_modelo
                liberar_modelo()  # el modelo ocupa mucha memoria y el vigilante puede tener el suyo cargado
            except Exception:
                pass
        with _cerrojo:
            cancelado = _estado["cancelar"]
            e = {**_estado, "resumen": dict(_estado["resumen"])}
        # Los últimos mensajes van antes de marcarlo terminado: al verlo terminado la página deja de refrescarse
        if cancelado:
            _log("AVISO", "Análisis cancelado: las imágenes ya analizadas se conservaron.")
        _log("OK", f"Lote finalizado: {texto_resumen(e)}.")
        with _cerrojo:
            _estado.update(activo=False, hecho=sum(e["resumen"].values()) + e["ya"], actual="", fin=datetime.now(),
                           cancelado=cancelado)

# ---------------------------------------------------------------- vistas

def texto_resumen(e):
    r = e["resumen"]
    partes = [f"{r.get('registrada', 0)} registrada(s)", f"{r.get('descartada', 0)} descartada(s)"]
    if r.get("error"):
        partes.append(f"{r['error']} con error")
    if e["ya"]:
        partes.append(f"{e['ya']} ya almacenada(s)")
    return " · ".join(partes)

def _duracion(e):
    """Segundos por foto: la media de las últimas del lote; hasta tener alguna, la estimación."""
    ultimas = e["duraciones"][-5:]
    return sum(ultimas) / len(ultimas) if ultimas else DURACION_ESTIMADA

def _avance(e):
    """Fracción hecha, animando la foto en curso con el tiempo por imagen."""
    if not e["total"]:
        return 1.0
    en_curso = min(0.95, (time.time() - e["inicio_foto"]) / _duracion(e)) if e["activo"] and e["actual"] else 0
    return min(1.0, (e["hecho"] + en_curso) / e["total"])

def lote_resultados(ids):
    """Registros guardados del lote, releídos de la base, en el orden en que se cargaron."""
    actuales = {r["id"]: r for r in registros()}
    return [actuales[i] for i in ids if i in actuales]

def _pct_foto(e):
    """% estimado de la foto en curso según lo que tardan las del lote; llega al 100 % al terminarla."""
    return min(99, int((time.time() - e["inicio_foto"]) / _duracion(e) * 100))

def _linea(contenido, clase=""):
    return f"<div class='{clase}'><span class='t-signo'>&gt;</span>{contenido}</div>"

def _terminal(e):
    """Ventana de comandos: cada informe es una línea que empieza con ">"; mientras analiza, la foto en curso
    con su %, y al final el cursor parpadeando. Vacía, solo "> █"."""
    lineas = [_linea(f"<span class='t-hora'>{hora}</span><span class='t-nivel t-{nivel}'>{nivel}</span>{mensaje}")
              for hora, nivel, mensaje in e["logs"][-MAX_LINEAS:]]
    if len(e["logs"]) > MAX_LINEAS:
        lineas.insert(0, _linea(f"<span class='t-hora'>… {len(e['logs']) - MAX_LINEAS} mensajes anteriores ocultos</span>"))
    if e["activo"] and e["actual"] and not e["cancelar"]:
        lineas.append(_linea(f"<span class='t-hora'>{datetime.now():%H:%M:%S}</span>"
                             f"<span class='t-nivel t-INFO'>INFO</span>[{min(e['hecho'] + 1, e['total'])}/{e['total']}] "
                             f"{html.escape(e['actual'])} · analizando {_pct_foto(e)} %", "t-vivo"))
    lineas.append(_linea("<i class='t-cursor'></i>", "t-prompt"))
    # .terminal usa column-reverse: la línea más reciente va primero en el HTML
    return f"<div class='terminal cmd'>{''.join(reversed(lineas))}</div>"

def _linea_estado(e):
    """Barra de avance mientras corre; si no, nada (el final del lote ya se lee en la ventana de comandos)."""
    if e["activo"]:
        if e["cancelar"]:
            detalle = "Cancelando…"
        elif e["actual"]:
            detalle = f"Imagen {min(e['hecho'] + 1, e['total'])} de {e['total']} · {html.escape(e['actual'])}"
        else:
            detalle = "Preparando…"
        texto = f"{detalle}<b>{_avance(e) * 100:.0f} % del lote</b>"
        return (f"<div class='lote-avance'><span>{texto}</span>"
                f"<div class='lote-barra'><i style='width:{_avance(e) * 100:.1f}%'></i></div></div>")
    # Sin lote en curso no se muestra nada: el resultado ya queda escrito en la ventana de comandos
    return "<div class='lote-msg vacio'></div>"

def panel_registro(abrir_resultados):
    """Cuadro "Registro del análisis" de la página de carga: avance y mensajes en vivo mientras corre.
    Siempre dibuja los mismos elementos en el mismo orden (cabecera, línea de estado, mensajes): así nada
    queda descolocado cuando se refresca cada segundo."""
    corriendo = estado()["activo"]

    def cuerpo():
        e = estado()
        if corriendo and not e["activo"]:
            st.rerun()  # acaba de terminar: recarga la página para dejar de consultar cada segundo
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="lote_cabecera"):
            st.markdown("<div class='card-title'>Registro del análisis</div>", unsafe_allow_html=True)
            st.space("stretch")
            if e["activo"]:
                st.button("Cancelando…" if e["cancelar"] else "Cancelar", icon=":material/stop_circle:",
                          key="lote_cancelar", on_click=cancelar, disabled=e["cancelar"],
                          help="Detiene el análisis: la foto en curso no se guarda; lo ya analizado se conserva")
            else:
                # Siempre a la vista; se activa cuando hay un análisis con fotos que mostrar.
                # El registro es un fragmento: su botón solo lo refrescaría a él. Se recarga la página entera
                # para que la ventana de resultados (se abre en avisos_lote, al final de app.py) salga en el acto
                hay_resultados = bool(e["fin"] and e["ids"])
                if st.button("Mostrar resultados", icon=":material/photo_library:", key="lote_ver", type="primary",
                             disabled=not hay_resultados,
                             help=None if hay_resultados else "Disponible cuando termine un análisis"):
                    abrir_resultados(e["ids"])
                    st.rerun(scope="app")
            st.button("Limpiar", icon=":material/delete_sweep:", key="lote_limpiar", on_click=limpiar,
                      disabled=e["activo"] or not e["logs"],
                      help="Espera a que termine el análisis" if e["activo"]
                      else "Vaciar el registro (las fotos analizadas siguen guardadas)")
        st.markdown(_linea_estado(e), unsafe_allow_html=True)
        st.markdown(_terminal(e), unsafe_allow_html=True)

    with st.container(key="carga_registro_card"):
        st.fragment(cuerpo, run_every=1 if corriendo else None)()

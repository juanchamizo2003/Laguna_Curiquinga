import os
import html
import time
import json
import shutil
import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data_base import DB_PATH, contar_alertas_no_leidas
from backend.respaldo import crear_respaldo, listar_respaldos
from frontend.components.datos import registros
from backend.servicio import (
    leer_estado, leer_log, iniciar_vigilante, detener_vigilante, RUTA_LOG, EXTENSIONES_IMAGEN,
)
from frontend.components.tarjetas import tarjeta_kpi, punto, ICONO_SERVIDOR, ICONO_CHIP, ICONO_COLA, ICONO_CHECK
from frontend.components.formato import fecha_legible

RUTA_MODELO = os.path.join(BASE_DIR, "modelos", "sam_vit_b_01ec64.pth")
CARPETAS = {
    "ingesta_camara": "Ingesta de la cámara",
    "fotos_procesadas": "Fotos procesadas",
    "descartes_historicos": "Descartes",
    "carga_manual": "Carga manual",
}
ESPERA_TRANSICION = 60  # s que se muestra "Iniciando…"/"Deteniendo…" mientras el vigilante responde

def _tamano(bytes_):
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024 or unidad == "TB":
            return f"{bytes_:.0f} {unidad}" if unidad == "B" else f"{bytes_:.1f} {unidad}"
        bytes_ /= 1024

def _hace(segundos):
    if segundos is None:
        return "nunca"
    if segundos < 60:
        return f"hace {int(segundos)} s"
    if segundos < 3600:
        return f"hace {int(segundos // 60)} min"
    if segundos < 86400:
        return f"hace {int(segundos // 3600)} h"
    return f"hace {int(segundos // 86400)} d"

def _imagenes(carpeta):
    ruta = os.path.join(BASE_DIR, "flujo_imagenes", carpeta)
    if not os.path.isdir(ruta):
        return []
    return [f for f in os.listdir(ruta) if f.lower().endswith(EXTENSIONES_IMAGEN)]

def _transicion(en_linea):
    """'iniciando', 'deteniendo' o None según la última orden dada desde este panel."""
    orden = st.session_state.get("vig_orden")
    if not orden:
        return None
    accion, momento = orden
    vencida = time.time() - momento > ESPERA_TRANSICION
    cumplida = (accion == "iniciando" and en_linea) or (accion == "deteniendo" and not en_linea)
    if vencida or cumplida:
        del st.session_state["vig_orden"]
        if cumplida:
            st.rerun()  # rerun completo para que la tarjeta de estado de la barra lateral también cambie
        return None
    return accion

def _render_log(filtro):
    entradas = leer_log(300)
    if filtro == "Avisos y errores":
        entradas = [e for e in entradas if e[1] in ("AVISO", "ERROR")]
    if not entradas:
        cuerpo = "<div class='t-vacio'>Sin actividad registrada todavía.</div>"
    else:
        # .terminal usa column-reverse para quedar anclada abajo: la entrada más reciente va primero en el HTML
        cuerpo = "".join(
            f"<div><span class='t-hora'>{fecha[5:]}</span>"
            f"<span class='t-nivel t-{nivel}'>{nivel}</span>{html.escape(mensaje)}</div>"
            for fecha, nivel, mensaje in reversed(entradas)
        )
    st.markdown(f"<div class='terminal' style='height:calc(100vh - 372px); min-height:240px'>{cuerpo}</div>",
                unsafe_allow_html=True)

@st.fragment(run_every=5)
def _panel_estado():
    servicio = leer_estado()
    en_linea = servicio["en_linea"]
    transicion = _transicion(en_linea)

    # Si el vigilante registró capturas o generó alertas, se recarga toda la página para que
    # la barra lateral (estado y contador de alertas) también se actualice
    huella = (servicio.get("procesadas"), servicio.get("descartes"), contar_alertas_no_leidas())
    if st.session_state.get("srv_huella") not in (None, huella):
        st.session_state["srv_huella"] = huella
        st.rerun()
    st.session_state["srv_huella"] = huella
    registradas = {r["nombre_foto"] for r in registros()}
    en_ingesta = _imagenes("ingesta_camara")
    pendientes = servicio.get("en_cola", 0) if en_linea else len([f for f in en_ingesta if f not in registradas])
    modelo_ok = os.path.exists(RUTA_MODELO)

    # ---- Encabezado y botonera (dentro del fragmento para que refleje el estado al instante)
    col_tit, col_acc = st.columns([1.6, 1], vertical_alignment="center")
    with col_tit:
        st.markdown("""
            <div class='header-title'>Control de servidor</div>
            <div class='header-sub' style='margin-bottom:0 !important'>Servicio vigilante, su actividad y el almacenamiento del proyecto</div>
        """, unsafe_allow_html=True)
    with col_acc, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
        if transicion:
            st.button("Iniciando…" if transicion == "iniciando" else "Deteniendo…", disabled=True, icon=":material/hourglass_top:")
        elif en_linea:
            if st.button("Detener vigilante", icon=":material/stop_circle:", key="btn_srv_detener"):
                detener_vigilante()
                st.session_state["vig_orden"] = ("deteniendo", time.time())
                st.rerun()
        else:
            if st.button("Iniciar vigilante", type="primary", icon=":material/play_arrow:", key="btn_srv_iniciar",
                         disabled=not modelo_ok, help=None if modelo_ok else "Faltan los pesos de SAM en modelos/"):
                if iniciar_vigilante():
                    st.session_state["vig_orden"] = ("iniciando", time.time())
                st.rerun()

    # ---- Tarjetas de estado
    if transicion == "iniciando":
        valor, tono = "Iniciando…", "warn"
    elif transicion == "deteniendo":
        valor, tono = "Deteniendo…", "warn"
    elif en_linea and servicio.get("procesando"):
        valor, tono = "Procesando", ""
    elif en_linea:
        valor, tono = "En línea", "ok"
    else:
        valor, tono = "Detenido", "danger"

    if not modelo_ok:
        modelo, tono_modelo = "Sin pesos", "danger"
    elif en_linea:
        modelo = "GPU · CUDA" if servicio.get("dispositivo") == "cuda" else "CPU"
        tono_modelo = "ok" if servicio.get("dispositivo") == "cuda" else "warn"
    else:
        modelo, tono_modelo = "No cargado", ""

    procesadas = servicio.get("procesadas", 0)
    descartes = servicio.get("descartes", 0) + servicio.get("errores", 0)
    extra_desc = f"<span class='kpi-delta down'>{descartes} descartadas</span>" if descartes else ""

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        tarjeta_kpi(ICONO_SERVIDOR, "Vigilante", valor, tono=tono)
    with k2:
        tarjeta_kpi(ICONO_CHIP, "Modelo SAM", modelo, tono=tono_modelo)
    with k3:
        tarjeta_kpi(ICONO_COLA, "En cola" if en_linea else "Pendientes en ingesta", str(pendientes),
                    tono="warn" if pendientes and not en_linea else "")
    with k4:
        tarjeta_kpi(ICONO_CHECK, "Procesadas en la sesión", str(procesadas) if en_linea else "—", extra_desc)

    col_log, col_info = st.columns([2.05, 1], gap="medium")

    # ---- Consola de actividad
    with col_log, st.container(key="srv_log_card"):
        c_tit, c_fil = st.columns([1, 1.3], vertical_alignment="center")
        with c_tit:
            st.markdown("""
                <div class='card-title'>Actividad del vigilante</div>
                <div class='card-sub'>Se actualiza cada 5 segundos</div>
            """, unsafe_allow_html=True)
        with c_fil, st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            filtro = st.segmented_control("Filtro del registro", ["Todo", "Avisos y errores"], default="Todo",
                                          key="srv_filtro_log", label_visibility="collapsed") or "Todo"
            if os.path.exists(RUTA_LOG):
                with open(RUTA_LOG, "rb") as f:
                    st.download_button("Log", f.read(), file_name="vigilante.log", mime="text/plain",
                                       icon=":material/download:", help="Descargar el registro completo")
        _render_log(filtro)

    # ---- Servicio y almacenamiento
    with col_info:
        with st.container(key="srv_servicio_card"):
            if en_linea:
                procesando = html.escape(servicio["procesando"]) if servicio.get("procesando") else "Nada"
                filas = [
                    ("Estado", f"{punto('#2fd27a')}En línea"),
                    ("PID", servicio.get("pid", "—")),
                    ("En marcha desde", fecha_legible(servicio.get("inicio", ""))),
                    ("Último latido", _hace(servicio.get("segundos"))),
                    ("Carpeta vigilada", f"<code>{html.escape(servicio.get('carpeta', ''))}</code>"),
                    ("Origen de la cámara", f"<code>{html.escape(servicio['origen'])}</code>" if servicio.get("origen") else "Sin configurar"),
                    ("Procesando ahora", procesando),
                ]
            else:
                filas = [
                    ("Estado", f"{punto('#f0616d')}Detenido"),
                    ("Último latido", _hace(servicio.get("segundos"))),
                    ("Última imagen", html.escape(servicio.get("ultima_imagen") or "—")),
                ]
            st.markdown(
                "<div class='card-title'>Servicio</div><div class='lista-datos'>"
                + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in filas) + "</div>",
                unsafe_allow_html=True,
            )

        with st.container(key="srv_almacen_card"):
            filas = [(nombre, f"{len(_imagenes(carpeta))} imágenes") for carpeta, nombre in CARPETAS.items()]
            if os.path.exists(DB_PATH):
                filas.append(("Base de datos", f"{len(registradas)} registros · {_tamano(os.path.getsize(DB_PATH))}"))
            filas.append(("Pesos SAM", _tamano(os.path.getsize(RUTA_MODELO)) if modelo_ok else "No encontrados"))
            respaldos = listar_respaldos()
            filas.append(("Último respaldo", f"{respaldos[0][3]:%d/%m %H:%M} · {len(respaldos)} guardados" if respaldos else "Ninguno"))
            disco = shutil.disk_usage(BASE_DIR)
            libre_pct = disco.free / disco.total
            color_disco = "#f0616d" if libre_pct < 0.1 else "#f5a742" if libre_pct < 0.2 else "#2fd27a"
            filas.append(("Disco libre", f"{punto(color_disco)}{_tamano(disco.free)} ({libre_pct:.0%})"))
            st.markdown(
                "<div class='card-title'>Almacenamiento</div><div class='lista-datos'>"
                + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in filas) + "</div>",
                unsafe_allow_html=True,
            )
            if st.button("Respaldar base de datos", icon=":material/backup:", width="stretch", key="srv_respaldar"):
                st.toast(f"Respaldo creado: {os.path.basename(crear_respaldo())}", icon=":material/check_circle:")

        descartes = _ultimos_descartes()
        if descartes:
            with st.container(key="srv_descartes_card"):
                st.markdown(
                    "<div class='card-title'>Últimos descartes</div><div class='card-sub'>Fotos que no pasaron el control de calidad</div>"
                    "<div class='lista-datos'>" + "".join(
                        f"<div title='{html.escape(d['archivo'])}'><span>{d['fecha'][5:16]}</span><b>{html.escape(d['motivo'])}</b></div>"
                        for d in descartes) + "</div>",
                    unsafe_allow_html=True,
                )

def _ultimos_descartes(n=5):
    ruta = os.path.join(BASE_DIR, "flujo_imagenes", "descartes_historicos", "_motivos.jsonl")
    try:
        with open(ruta, encoding="utf-8") as f:
            lineas = f.readlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in reversed(lineas) if l.strip()]

def render_servidor():
    _panel_estado()

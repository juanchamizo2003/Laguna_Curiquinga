import os
import html
import time
import threading
from datetime import datetime
import streamlit as st

from backend.servicio import extraer_fecha_hora_de_nombre, EXTENSIONES_IMAGEN
from backend.calidad import estado_validacion
from frontend.components.datos import registros, color_estado
from frontend.components.formato import formatear_m2, fecha_legible
from frontend.components.tarjetas import punto
from frontend.components.visor_laguna import render_revision

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DURACION_ESTIMADA = 14.0  # s por imagen; solo sirve para animar la barra mientras SAM trabaja

def render_metricas_captura(item):
    """Franja de métricas de una captura: fecha, hora, área y color medio del agua."""
    fecha_captura = str(item.get("fecha_captura", ""))
    if " " in fecha_captura:
        fecha_val, hora_val = fecha_captura.split(" ", 1)
    else:
        fecha_val, hora_val = extraer_fecha_hora_de_nombre(item.get("nombre_foto", ""))
    color = item.get("color_hex") or "#8b95a3"
    estado = estado_validacion(item)
    observacion = item.get("observacion") if isinstance(item.get("observacion"), str) else ""
    st.markdown(f"""
        <div class="visor-metricas" style="grid-template-columns: repeat(5, minmax(0, 1fr))">
            <div><span>Fecha</span><b>{fecha_legible(fecha_val, con_hora=False)}</b></div>
            <div><span>Hora</span><b>{hora_val[:5]}</b></div>
            <div><span>Área</span><b>{formatear_m2(item.get('area', 0))}</b></div>
            <div><span>Color del agua</span><b>{punto(color)}{html.escape(color.upper())}</b></div>
            <div title="{html.escape(observacion)}"><span>Estado</span><b>{punto(color_estado(estado))}{estado}</b></div>
        </div>
    """, unsafe_allow_html=True)

def render_par_imagenes(item):
    """Original y procesada lado a lado."""
    c1, c2 = st.columns(2, gap="medium")
    for col, clave, titulo in ((c1, "ruta_original", "Original"), (c2, "ruta_procesada", "Segmentación SAM")):
        with col:
            st.markdown(f"<div class='img-titulo'>{titulo}</div>", unsafe_allow_html=True)
            ruta = os.path.join(BASE_DIR, item.get(clave, ""))
            if item.get(clave) and os.path.exists(ruta):
                st.image(ruta, width="stretch")
            else:
                st.info("Imagen no disponible.")

@st.dialog("Resultado del análisis", width="large")
def ver_imagenes_ampliadas(lote):
    if not lote:
        st.warning("No hay imágenes disponibles para mostrar.")
        return

    idx = max(0, min(st.session_state.get("indice_modal", 0), len(lote) - 1))
    st.session_state.indice_modal = idx
    item = lote[idx]

    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="modal_vlaguna_nav"):
        st.markdown(f"<div class='card-sub card-sub-ellipsis'>{html.escape(item['nombre_foto'])}</div>", unsafe_allow_html=True)
        if len(lote) > 1:
            if st.button("", icon=":material/chevron_left:", key="modal_prev_btn", disabled=idx == 0):
                st.session_state.indice_modal -= 1
                st.rerun(scope="fragment")
            st.markdown(f"<div class='visor-contador'>{idx + 1}/{len(lote)}</div>", unsafe_allow_html=True)
            if st.button("", icon=":material/chevron_right:", key="modal_next_btn", disabled=idx == len(lote) - 1):
                st.session_state.indice_modal += 1
                st.rerun(scope="fragment")

    render_metricas_captura(item)
    render_revision(item, "modal_lote")
    render_par_imagenes(item)

def _terminal(lineas):
    # .terminal usa column-reverse: la línea más reciente va primero en el HTML
    return f"<div class='terminal' style='max-height:180px'>{''.join(reversed(lineas))}</div>"

def _linea(nivel, mensaje):
    return (f"<div><span class='t-hora'>{datetime.now():%H:%M:%S}</span>"
            f"<span class='t-nivel t-{nivel}'>{nivel}</span>{mensaje}</div>")

def _procesar_lote(imagenes_validas):
    from backend.procesamiento import procesar_imagen  # importa torch: solo al procesar

    total_imgs = len(imagenes_validas)
    # Solo existe mientras corre el lote: pulsarlo relanza el script y eso corta el bucle
    st.button("Cancelar procesamiento", icon=":material/stop_circle:", key="btn_cancelar_lote",
              on_click=lambda: st.session_state.update(lote_cancelado=True))
    progreso_bar = st.progress(0, text="Iniciando procesamiento…")
    cmd_placeholder = st.empty()
    logs = [_linea("INFO", f"Iniciando procesamiento de {total_imgs} imagen(es)…")]

    # Carpeta separada de ingesta_camara: esa la vigila vigilante.py y procesaría la foto otra vez
    dir_ingesta = os.path.join(BASE_DIR, "flujo_imagenes", "carga_manual")
    os.makedirs(dir_ingesta, exist_ok=True)

    st.session_state.lote_actual = []
    resumen = {"registrada": 0, "descartada": 0, "error": 0}

    for i, f_file in enumerate(imagenes_validas):
        nombre = html.escape(f_file.name)
        r_orig = os.path.join(dir_ingesta, f_file.name)
        with open(r_orig, "wb") as f:
            f.write(f_file.getbuffer())

        resultado = {}

        def worker():
            resultado['res'] = procesar_imagen(r_orig, "Manual")

        t = threading.Thread(target=worker)
        t.start()
        start_t = time.time()

        while t.is_alive():
            pct_img = min(0.98, (time.time() - start_t) / DURACION_ESTIMADA)
            progreso_bar.progress((i + pct_img) / total_imgs, text=f"Imagen {i + 1} de {total_imgs} · {f_file.name}")
            cmd_placeholder.markdown(
                _terminal(logs + [_linea("INFO", f"Segmentando [{i + 1}/{total_imgs}] {nombre} · {pct_img:.0%}")]),
                unsafe_allow_html=True,
            )
            time.sleep(0.3)

        t.join()
        r = resultado.get('res', {"resultado": "error", "mensaje": "Error en el procesamiento"})
        resumen[r["resultado"]] += 1
        prefijo = f"[{i + 1}/{total_imgs}] {nombre}"

        if r["resultado"] == "registrada":
            st.session_state.lote_actual.append(r["registro"])
            area = formatear_m2(r["registro"]["area"])
            logs.append(_linea("OK", f"{prefijo} → {area}"))
            if r["alertas"]:
                logs.append(_linea("AVISO", f"{prefijo}: generó {len(r['alertas'])} alerta(s). Revisa la página Alertas."))
        elif r["resultado"] == "descartada":
            os.remove(r_orig)
            logs.append(_linea("AVISO", f"{prefijo} descartada y no guardada: {html.escape(r['mensaje'])}"))
        else:
            logs.append(_linea("ERROR", f"{prefijo}: {html.escape(str(r['mensaje']))}"))

    progreso_bar.progress(1.0, text="Lote completado")
    logs.append(_linea("OK", f"Lote finalizado: {resumen['registrada']} registrada(s), "
                             f"{resumen['descartada']} descartada(s), {resumen['error']} con error."))
    cmd_placeholder.markdown(_terminal(logs), unsafe_allow_html=True)

def render_formulario_carga():
    if "lote_actual" not in st.session_state:
        st.session_state.lote_actual = []
    if "indice_modal" not in st.session_state:
        st.session_state.indice_modal = 0

    with st.container(key="carga_subida_card"):
        st.markdown("""
            <div class='card-title'>Subir fotografías</div>
            <div class='card-sub'>Cada imagen se segmenta con SAM y se guarda como registro manual</div>
        """, unsafe_allow_html=True)

        col_drop, col_acc = st.columns([3.2, 1], gap="medium", vertical_alignment="center")
        with col_drop:
            archivos = st.file_uploader(
                "Fotografías",
                type=[e.lstrip(".") for e in EXTENSIONES_IMAGEN],
                accept_multiple_files=True,
                label_visibility="collapsed",
            ) or []
        with col_acc:
            n = len(archivos)
            btn_procesar = st.button(
                f"Procesar {n} imagen{'es' if n != 1 else ''}" if n else "Procesar imágenes",
                type="primary", icon=":material/auto_awesome:", width="stretch", disabled=not n,
                key="btn_procesar_lote",
            )
        st.markdown("""
            <div class='ayuda-carga'>
                Carpeta completa: ábrela, pulsa <kbd>Ctrl</kbd> + <kbd>A</kbd> y arrastra todo<i>·</i>
                La fecha y hora se leen del nombre <code>Curiquinga_AAAAMMDD_HHMMSS.jpg</code>
            </div>
        """, unsafe_allow_html=True)

        if st.session_state.pop("lote_cancelado", False):
            st.toast("Procesamiento cancelado. Las imágenes ya segmentadas se conservaron.", icon=":material/stop_circle:")

        if btn_procesar:
            imagenes_validas = [f for f in archivos if os.path.splitext(f.name)[1].lower() in EXTENSIONES_IMAGEN]
            ignorados = len(archivos) - len(imagenes_validas)
            if ignorados:
                st.warning(f"Se ignoraron {ignorados} archivo(s) que no son imágenes válidas.")
            if imagenes_validas:
                _procesar_lote(imagenes_validas)

    # ---- Resultado: el lote recién procesado o, si no hay, el último registro guardado
    # Se releen de la base para reflejar aprobaciones/rechazos hechos después de procesar
    actuales = {r["id"]: r for r in registros()}
    lote = [actuales[r["id"]] for r in st.session_state.lote_actual if r["id"] in actuales]
    es_lote = bool(lote)
    if not lote:
        registros_bd = registros()
        lote = [registros_bd[-1]] if registros_bd else []
    if not lote:
        return

    ultimo = lote[-1]
    with st.container(key="carga_resultado_card"):
        c_tit, c_btn = st.columns([4, 1], vertical_alignment="center")
        with c_tit:
            origen = f"Lote actual · {len(lote)} imagen{'es' if len(lote) != 1 else ''}" if es_lote else "Último registro guardado"
            st.markdown(f"""
                <div class='card-title'>Resultado del análisis</div>
                <div class='card-sub card-sub-ellipsis'>{origen} · {html.escape(ultimo['nombre_foto'])}</div>
            """, unsafe_allow_html=True)
        with c_btn, st.container(horizontal=True, horizontal_alignment="right"):
            if st.button("Ampliar", icon=":material/open_in_full:", help="Ver el lote a tamaño completo"):
                st.session_state.indice_modal = len(lote) - 1
                ver_imagenes_ampliadas(lote)

        render_metricas_captura(ultimo)
        render_revision(ultimo, "carga_resultado")
        render_par_imagenes(ultimo)

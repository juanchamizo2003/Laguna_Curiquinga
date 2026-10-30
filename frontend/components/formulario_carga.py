import streamlit as st

from backend.servicio import fecha_captura_de_nombre
from frontend.components.datos import registros
from frontend.components import lote_fondo
from frontend.components.visor_laguna import foto_ampliada

MIN_FOTOS_SALTO = 10  # desde aquí, los resultados ofrecen una lista para saltar a cualquier foto

def _al_cerrar_resultados():
    st.session_state.pop("lote_abrir", None)
    st.session_state.galeria_sel = None

def _ir_a_foto():
    st.session_state.galeria_sel = st.session_state["lote_ir_a"]

@st.dialog("Resultados del análisis", width="large", on_dismiss=_al_cerrar_resultados)
def _dialogo_resultados(ids):
    """Las fotos del lote con la misma vista que una foto abierta en el Inicio: fija, sin desplazarse."""
    lote = lote_fondo.lote_resultados(ids)
    if not lote:
        st.info("No hay imágenes disponibles para mostrar.")
        return
    ss = st.session_state
    sel = max(0, min(ss.get("galeria_sel") or 0, len(lote) - 1))
    ss.galeria_sel = sel
    # El aviso solo tiene sentido al ver el resultado de una carga, no al abrir una foto de la galería
    ya_almacenadas = set(lote_fondo.estado()["ya_ids"]) if ss.get("lote_de_carga", True) else set()

    def extra():
        if lote[sel].get("id") in ya_almacenadas:
            st.markdown("<span class='chip-almacenada' title='Ya estaba en la base de datos: no se volvió a "
                        "analizar'>Ya almacenada</span>", unsafe_allow_html=True, width="content")
        if len(lote) > MIN_FOTOS_SALTO:
            # Con muchas fotos las flechas no bastan: se puede ir a cualquiera (al escribir, la lista se filtra)
            ss["lote_ir_a"] = sel
            st.selectbox("Ir a la foto", range(len(lote)), key="lote_ir_a", label_visibility="collapsed", width=220,
                         format_func=lambda i: f"{i + 1}. {lote[i]['nombre_foto']}", on_change=_ir_a_foto)

    foto_ampliada(lote, sel, extra)

def pedir_resultados(ids, sel=0, de_carga=True):
    """Botón "Mostrar resultados" o una foto de la galería: la ventana se abre en la siguiente pasada (un callback
    no puede abrir un diálogo) y se mantiene hasta cerrarla, aunque la página se recargue entera."""
    st.session_state.lote_abrir = list(ids)
    st.session_state.lote_de_carga = de_carga
    st.session_state.galeria_sel = sel

def avisos_lote():
    """Se llama al final de app.py, en cualquier módulo: retoma un lote interrumpido y abre la ventana de
    resultados cuando se pide con "Mostrar resultados"."""
    lote_fondo.reanudar()
    lote_fondo.limpiar_al_abrir()
    pedido = st.session_state.get("lote_abrir")
    if pedido is not None:
        _dialogo_resultados(pedido)

def _menu_fotos(validas):
    """Qué pasará con las fotos elegidas antes de procesarlas (cada una se quita con su ✕ en la zona de subida)."""
    guardados = {r["fecha_captura"]: r for r in registros()}
    nuevas, almacenadas, problemas, vistas = 0, 0, [], set()
    for foto in validas:
        motivo, guardado = lote_fondo.clasificar(foto.name, guardados, vistas)
        if motivo:
            problemas.append(f"**{foto.name}**: {motivo}")
            continue
        vistas.add(fecha_captura_de_nombre(foto.name))
        almacenadas, nuevas = (almacenadas + 1, nuevas) if guardado else (almacenadas, nuevas + 1)
    with st.popover(f"Ver {len(validas)} foto(s)", icon=":material/list:"):
        st.markdown(f"**{nuevas}** por analizar · **{almacenadas}** ya almacenada(s) · "
                    f"**{len(problemas)}** se descartará(n)")
        for problema in problemas[:20]:
            st.caption(problema)
        if len(problemas) > 20:
            st.caption(f"… y {len(problemas) - 20} más")

def _vaciar_selector():
    st.session_state.carga_version = st.session_state.get("carga_version", 0) + 1

def render_formulario_carga():
    lote_fondo.reanudar()          # servidor reiniciado a mitad de un lote: sigue con lo que faltaba
    lote_fondo.limpiar_al_abrir()  # pestaña recargada: el registro empieza vacío
    e = lote_fondo.estado()
    if e["fin"] and not e["activo"] and not e["visto"]:
        lote_fondo.marcar_visto()
    with st.container(key="carga_subida_card"):
        st.markdown("""
            <div class='card-title'>Subir fotografías</div>
            <div class='card-sub'>Cada imagen se segmenta con SAM y se guarda como registro manual. El análisis sigue
            aunque cambies de módulo o de pestaña.</div>
        """, unsafe_allow_html=True)

        col_drop, col_acc = st.columns([3.2, 1], gap="medium", vertical_alignment="center")
        with col_drop:
            # Solo .jpg: las fotos de la cámara siempre lo son. Las que no tengan su nombre se descartan al
            # procesar (lo dice el registro del análisis)
            # La clave cambia al quitar las fotos o al empezar el análisis: así el selector se vacía
            archivos = st.file_uploader(
                "Fotografías", type=["jpg"], accept_multiple_files=True, label_visibility="collapsed",
                key=f"carga_fotos_{st.session_state.get('carga_version', 0)}",
            ) or []
        validas = archivos
        with col_acc:
            n = len(validas)
            if e["activo"]:
                etiqueta = "Analizando…"
            else:
                etiqueta = f"Procesar {n} {'imagen' if n == 1 else 'imágenes'}" if n else "Procesar imágenes"
            btn_procesar = st.button(etiqueta, type="primary", icon=":material/auto_awesome:", width="stretch",
                                     disabled=not validas or e["activo"], key="btn_procesar_lote",
                                     help="Espera a que termine el análisis en curso" if e["activo"] else None)
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="carga_ayuda"):
            st.markdown("""
                <div class='ayuda-carga'>
                    Carpeta completa: ábrela, pulsa <kbd>Ctrl</kbd> + <kbd>A</kbd> y arrastra todo<i>·</i>
                    Solo fotos <code>.jpg</code> con el nombre de la cámara <code>Curiquinga_AAAAMMDD_HHMMSS.jpg</code>
                    (de ahí salen la fecha y la hora); las demás se descartan
                </div>
            """, unsafe_allow_html=True)
            if archivos:
                _menu_fotos(validas)
                st.button("Quitar todas", icon=":material/close:", key="carga_quitar", type="tertiary",
                          on_click=_vaciar_selector)

        if btn_procesar and validas and not e["activo"]:
            # Las que ya están en la base (mismo nombre de archivo) no se vuelven a analizar: el registro del
            # análisis lo indica y sigue con la siguiente. Ya quedaron en disco: el selector se vacía
            lote_fondo.iniciar(validas, {r["fecha_captura"]: r for r in registros()})
            _vaciar_selector()
            st.rerun()

    # Mensajes del análisis: siempre a la vista, vacío hasta que se procese algo
    lote_fondo.panel_registro(pedir_resultados)

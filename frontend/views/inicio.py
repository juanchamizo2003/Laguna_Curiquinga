import html
import streamlit as st

from frontend.components.datos import df_registros, solo_confiables
from frontend.components.filtro_temporal import (render_filtro_compacto, aplicar_filtro_temporal, en_vivo,
                                                 restablecer_filtro, SEGUNDOS_EN_VIVO)
from frontend.components.visor_laguna import render_visor_laguna, boton_tema, N_CARRUSEL
from backend import config as cfg
from frontend.components.graficos_dashboard import fig_area, TIPOS_GRAFICO
from frontend.components.tooltip_grafica import activar_tooltip
from frontend.components.ordenar_graficas import nuevo_orden, asa
from frontend.components.formato import formatear_m2, fecha_legible
from frontend.components.tarjetas import (html_kpi, ICONO_AREA, ICONO_PROMEDIO, ICONO_MAXIMO, ICONO_MUESTRAS,
                                          ICONO_FECHA, ICONO_COLOR)

MODOS = {"Ambos": "ambos", "Automático": "auto", "Manual": "manual"}
SIN_DATO = "<span class='kpi-unidad'>—</span>"
VENTANA_AMPLIADA = 30   # capturas visibles al abrir la gráfica ampliada; el resto se recorre arrastrando
# Clave del widget -> clave en la sección "grafica" de config.json (las preferencias sobreviven a la recarga)
PREFERENCIAS = {"graf_tipo": "tipo", "graf_color_auto": "color_auto", "graf_color_manual": "color_manual",
                "graf_tendencia": "tendencia"}

def _html_area(df_kpi):
    """Área de la captura anterior y de la actual; la actual en verde si subió y en rojo si bajó."""
    actual = df_kpi.iloc[-1]["area"] if len(df_kpi) else None
    anterior = df_kpi.iloc[-2]["area"] if len(df_kpi) > 1 else None
    tono = "" if anterior is None or actual == anterior else ("up" if actual > anterior else "down")
    flecha = {"up": "↗", "down": "↘"}.get(tono, "→")

    def valor(v):
        return formatear_m2(v) if v is not None else "—"
    return f"""<div class="kpi-par">
        <div><b>{valor(anterior)}</b><small>Anterior</small></div>
        <span class="kpi-flecha {tono}">{flecha}</span>
        <div class="{tono}"><b>{valor(actual)}</b><small>Actual</small></div>
    </div>"""

def _extremos(df):
    """(fila del mínimo, fila del máximo) del área."""
    return df.loc[df["area"].idxmin()], df.loc[df["area"].idxmax()]

def _html_rango(df):
    """Mínimo ↔ máximo del área en el periodo, con el mismo formato que la tarjeta de Área."""
    minimo, maximo = _extremos(df)
    return f"""<div class="kpi-par kpi-rango">
        <div><b>{formatear_m2(minimo["area"])}</b><small>Mínimo</small></div>
        <span class="kpi-flecha">↔</span>
        <div><b>{formatear_m2(maximo["area"])}</b><small>Máximo</small></div>
    </div>"""

def _ayuda_rango(df, del_periodo):
    minimo, maximo = _extremos(df)
    return (f"Área más pequeña y más grande {del_periodo}. "
            f"Mínimo: {formatear_m2(minimo['area'])} el {fecha_legible(minimo['fecha_captura'])} · "
            f"Máximo: {formatear_m2(maximo['area'])} el {fecha_legible(maximo['fecha_captura'])}")

def _render_kpis(df_kpi, df_periodo, df_grafica, periodo):
    """Fila de arriba: estado actual (última captura), no depende del filtro.
    Fila de abajo: estadísticas de lo que muestra la gráfica, con el periodo escrito debajo."""
    ultima = df_kpi.iloc[-1] if len(df_kpi) else None
    if ultima is not None:
        color = html.escape(str(ultima["color_hex"] or "#8b95a3").upper())
        fecha, _, hora = fecha_legible(ultima["fecha_captura"]).partition(" · ")
        color_html = f"<i class='kpi-sw' style='background:{color}'></i>{color}"
    else:
        fecha = color_html = SIN_DATO
        hora = ""

    ahora = "<span class='kpi-ahora'><i></i>ahora</span>"
    # En las tarjetas estrechas "ahora" va bajo el valor (en el título partía la línea); en Fecha, junto a la hora
    pie_ahora = f"<div class='kpi-periodo'>{ahora}</div>"
    pie_hora = f"<div class='kpi-periodo'><span class='kpi-hora-pie'>{hora}</span>{ahora}</div>"
    vivo = en_vivo()
    texto_periodo = periodo.removeprefix("En vivo · ")
    pie = f"<div class='kpi-periodo {'vivo' if vivo else 'filtro'}'>{html.escape(texto_periodo)}</div>"
    hay = not df_grafica.empty
    excluidas = len(df_periodo) - len(df_grafica)
    extra = (f"<span class='kpi-delta down' title='Rechazadas, no aptas o atípicas: no cuentan'>{excluidas} excluidas</span>"
             if excluidas else "")
    del_periodo = "en el periodo que muestra la gráfica (cambia con el filtro)"
    tarjetas = [
        html_kpi(ICONO_AREA, f"Área {ahora}", _html_area(df_kpi),
                 ayuda="Área de la última captura y de la anterior. No depende del filtro."),
        html_kpi(ICONO_FECHA, "Fecha y hora", fecha, pie=pie_hora, ayuda="Cuándo se tomó la última captura."),
        html_kpi(ICONO_COLOR, "Color del agua", color_html, pie=pie_ahora,
                 ayuda="Color medio del agua en la última captura."),
        html_kpi(ICONO_PROMEDIO, "Promedio", formatear_m2(df_grafica["area"].mean()) if hay else SIN_DATO,
                 pie=pie, ayuda=f"Promedio del área {del_periodo}."),
        html_kpi(ICONO_MAXIMO, "Rango del área", _html_rango(df_grafica) if hay else SIN_DATO,
                 pie=pie, ayuda=_ayuda_rango(df_grafica, del_periodo) if hay else ""),
        html_kpi(ICONO_MUESTRAS, "Muestras", str(len(df_grafica)), extra,
                 pie=pie, ayuda=f"Capturas confiables {del_periodo}."),
    ]
    # En una sola línea: con la sangría Markdown tomaría las tarjetas por un bloque de código
    contenido = "".join(linea.strip() for t in tarjetas for linea in t.splitlines())
    st.markdown(f"<div class='kpi-grid'>{contenido}</div>", unsafe_allow_html=True)

def _preferencias():
    """Preferencias guardadas de la gráfica. Se leen siempre de config.json: los widgets toman de aquí su
    valor inicial (precargarlos en la sesión no funciona dentro del fragmento en vivo)."""
    pref = dict(cfg.cargar()["grafica"])
    if pref["tipo"] not in TIPOS_GRAFICO:
        pref["tipo"] = "Puntos"
    pref["colores"] = {"Automático": pref["color_auto"], "Manual": pref["color_manual"]}
    return pref

def _guardar_preferencia(*claves):
    """Guarda en config.json los ajustes indicados (los demás no se tocan)."""
    cfg.actualizar("grafica", {PREFERENCIAS[c]: st.session_state.get(c) for c in claves})

def _popover_ajustes(pref, con_tipo=True):
    """Ajustes de la gráfica. El tipo y la tendencia se aplican al elegirlos; cada color, al cerrar su selector
    (el botón "Confirmar" que añade el script de app.py solo lo cierra de forma evidente)."""
    with st.popover("", icon=":material/tune:", help="Tipo de gráfico y colores" if con_tipo else "Colores de las gráficas"):
        if con_tipo:
            st.markdown("**Tipo de gráfico**")
            st.pills("Tipo de gráfico", TIPOS_GRAFICO, default=pref["tipo"], key="graf_tipo",
                     label_visibility="collapsed", on_change=_guardar_preferencia, args=("graf_tipo",))
        # El color se aplica al cerrar el selector (con "Confirmar" o pulsando fuera): Streamlit lo envía entonces
        st.markdown("**Colores por origen**")
        c1, c2 = st.columns(2)
        c1.color_picker("Servidor", pref["color_auto"], key="graf_color_auto",
                        on_change=_guardar_preferencia, args=("graf_color_auto",))
        c2.color_picker("Manual", pref["color_manual"], key="graf_color_manual",
                        on_change=_guardar_preferencia, args=("graf_color_manual",))
        st.toggle("Línea de tendencia", pref["tendencia"], key="graf_tendencia",
                  on_change=_guardar_preferencia, args=("graf_tendencia",))
        # "Listo" cierra el menú (lo atiende el script de app.py: Streamlit no puede cerrar un popover desde Python)
        st.html('<button class="pop-listo" type="button">Listo</button>')

def _opciones_grafica(pref):
    """Botones del encabezado de la gráfica: ajustes y ampliar."""
    _popover_ajustes(pref)
    # Ampliar se abre fuera del fragmento en vivo (si no, el refresco cada 30 s cerraría la ventana)
    if st.button("", icon=":material/open_in_full:", key="btn_ampliar_grafica",
                 help="Ampliar la gráfica y ver sus datos con los filtros actuales",
                 on_click=st.session_state.__setitem__, args=("grafica_ampliada", True)):
        st.rerun()

def _boton_otros_tipos():
    # El botón está dentro del fragmento de la gráfica: cambiar de vista exige recargar toda la página
    with st.container(horizontal=True, horizontal_alignment="right", key="graf_otros_tipos"):
        if st.button("Más gráficos", icon=":material/add_chart:",
                     key="btn_vista_graficas", type="tertiary", on_click=_mostrar_vista_graficas, args=(True,)):
            st.rerun()

def _cerrar_ampliada():
    st.session_state["grafica_ampliada"] = False

@st.dialog("Área superficial de la laguna", width="large", on_dismiss=_cerrar_ampliada)
def _grafica_ampliada(modo, tipo=None):
    """Una gráfica en grande y navegable: zoom con la rueda y arrastre para moverse.
    tipo None = la principal (con su tipo guardado); o uno concreto desde "Más gráficos".
    Los datos de cada punto salen al pasar el cursor, así que no hace falta una tabla."""
    df_periodo, subtitulo = aplicar_filtro_temporal(_datos_de_modo(modo))
    df = solo_confiables(df_periodo)
    pref = _preferencias()
    tipo = tipo or pref["tipo"]
    st.markdown(f"<div class='card-sub'><b>{tipo}</b> · <span class='filtro-badge'>{subtitulo}</span> "
                f"{len(df)} captura(s) confiable(s) · origen: {modo} · rueda del ratón: zoom · arrastrar: moverse · "
                f"doble clic: ver todo</div>", unsafe_allow_html=True)
    fig = fig_area(df, tipo, pref["colores"], pref["tendencia"])
    if not df.empty:
        fig.update_layout(dragmode="pan",
                          modebar=dict(bgcolor="rgba(0,0,0,0)", color="#8b95a3", activecolor="#3cc9b4"))
        # Con muchas capturas se abre en las más recientes; arrastrando se va hacia atrás
        if len(df) > VENTANA_AMPLIADA:
            fig.update_xaxes(range=[len(df) - VENTANA_AMPLIADA - 0.6, len(df) - 0.4])
    with st.container(key="amp_grafica"):
        st.plotly_chart(fig, width="stretch", height="stretch", key="grafica_ampliada_fig",
                        config={"scrollZoom": True, "displaylogo": False, "displayModeBar": True,
                                "modeBarButtonsToRemove": ["zoom2d", "select2d", "lasso2d", "autoScale2d", "toImage"]})

def _mostrar_vista_graficas(visible):
    st.session_state["vista_graficas"] = visible

def _orden_graficas():
    """Orden guardado de las tarjetas; los tipos nuevos o perdidos se completan al final."""
    guardado = [t for t in cfg.cargar()["grafica"]["orden"] if t in TIPOS_GRAFICO]
    return guardado + [t for t in TIPOS_GRAFICO if t not in guardado]

def _datos_de_modo(modo):
    """Registros del origen elegido; se leen de nuevo en cada pasada para que el modo en vivo vea capturas nuevas."""
    df = df_registros()
    if modo != "Ambos" and not df.empty:
        df = df[df["estado"].str.contains(modo, na=False)].reset_index(drop=True)
    return df

def _seguir_en_vivo(vivo):
    """Tras cambiar el filtro dentro del fragmento se relanza toda la página: el refresco en vivo se fija al
    crear el fragmento, y el reporte PDF de Exportar debe ver el mismo periodo que la gráfica."""
    ss = st.session_state
    firma = (ss.tipo_seleccion, ss.limite_dias, tuple(ss.fechas_seleccionadas),
             tuple(ss.meses_seleccionados), tuple(ss.anios_seleccionados))
    cambio = ss.get("_firma_filtro") not in (None, firma)
    ss["_firma_filtro"] = firma
    if cambio or en_vivo() != vivo:
        st.rerun()

def _en_fragmento(funcion, *args):
    """Ejecuta la parte cambiante del inicio como fragmento; en vivo se repite sola cada SEGUNDOS_EN_VIVO."""
    vivo = en_vivo()
    st.fragment(funcion, run_every=SEGUNDOS_EN_VIVO if vivo else None)(*args, vivo)

def render_vista_graficas(modo, key_prefix, vivo=False):
    """Subpestaña con la serie de área en todos los tipos de gráfico; las tarjetas se reordenan arrastrando ≡."""
    df_datos = _datos_de_modo(modo)
    pref = _preferencias()
    orden = _orden_graficas()
    movido = nuevo_orden(orden, key=f"{key_prefix}_gm_orden")
    if movido and set(movido) == set(TIPOS_GRAFICO) and movido != orden:
        cfg.actualizar("grafica", {"orden": movido})
        orden = movido

    with st.container(key=f"{key_prefix}_gm_cabecera_card"):
        c_tit, c_vol = st.columns([3, 1.2], vertical_alignment="center")
        titulo = c_tit.empty()
        with c_vol, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                                 gap="small", key=f"{key_prefix}_gm_acciones"):
            _popover_ajustes(pref, con_tipo=False)
            if st.button("Volver al panel", icon=":material/arrow_back:", key="btn_volver_panel",
                         on_click=_mostrar_vista_graficas, args=(False,)):
                st.rerun()
        render_filtro_compacto(df_datos, key_prefix=f"{key_prefix}_gm")
        _seguir_en_vivo(vivo)
        df_periodo, subtitulo = aplicar_filtro_temporal(df_datos)
        df_grafica = solo_confiables(df_periodo)
        titulo.markdown(f"""
            <div class='card-title'>Otros tipos de gráfico</div>
            <div class='card-sub card-sub-ellipsis'>Mismos datos de la gráfica principal · {subtitulo} · {len(df_grafica)} captura(s) · arrastra ≡ para ordenar</div>
        """, unsafe_allow_html=True)

    for i in range(0, len(orden), 2):
        for col, tipo in zip(st.columns(2, gap="small"), orden[i:i + 2]):
            with col, st.container(key=f"{key_prefix}_gm_{tipo}_card"):
                with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"gm_cab_{tipo}"):
                    st.markdown(f"<div class='card-title'>Área superficial · {tipo}</div>", unsafe_allow_html=True)
                    # Pantalla completa de esta gráfica, igual que la principal (se abre fuera del fragmento)
                    if st.button("", icon=":material/open_in_full:", key=f"gm_ampliar_{tipo}",
                                 help=f"Ver «{tipo}» en pantalla completa",
                                 on_click=st.session_state.__setitem__, args=("grafica_ampliada", tipo)):
                        st.rerun()
                    st.markdown(asa(tipo), unsafe_allow_html=True, width="content")
                st.plotly_chart(fig_area(df_grafica, tipo, pref["colores"], pref["tendencia"], compacta=True), width="stretch",
                                height=300, key=f"{key_prefix}_gm_chart_{tipo}", config={"displayModeBar": False})

def _columna_principal(modo, key_prefix, vivo=False):
    """Gráfica arriba y tarjetas de métricas debajo."""
    df_datos = _datos_de_modo(modo)
    df_kpi = solo_confiables(df_datos)
    pref = _preferencias()

    # 1. GRÁFICA: título con opciones, fila de filtros y un punto por captura
    with st.container(key=f"{key_prefix}_card_grafica"):
        # El título se rellena después del filtro para que el subtítulo refleje la selección actual
        c_tit, c_opc = st.columns([4, 1], vertical_alignment="center")
        titulo = c_tit.empty()
        with c_opc, st.container(horizontal=True, horizontal_alignment="right", gap="small",
                                 key=f"{key_prefix}_graf_opciones"):
            _opciones_grafica(pref)
        render_filtro_compacto(df_datos, key_prefix=key_prefix)
        _seguir_en_vivo(vivo)
        df_periodo, subtitulo = aplicar_filtro_temporal(df_datos)
        df_grafica = solo_confiables(df_periodo)
        # Con un filtro de fechas la gráfica no muestra lo último: se avisa con una etiqueta
        aviso = "" if en_vivo() else "<span class='filtro-badge'>Filtro activo</span> "
        titulo.markdown(f"""
            <div class='card-title'>Área superficial de la laguna</div>
            <div class='card-sub card-sub-ellipsis'>{aviso}Mediciones confiables · {subtitulo} · {len(df_grafica)} captura(s)</div>
        """, unsafe_allow_html=True)

        if df_grafica.empty and not en_vivo():
            # El filtro no deja capturas: se dice claramente y se ofrece salir de él con un clic
            with st.container(key="graf_vacio", horizontal_alignment="center", vertical_alignment="center"):
                st.markdown("<div class='graf-vacio'><b>No hay capturas en el periodo elegido</b>"
                            "<span>Prueba con otras fechas o vuelve a ver las últimas capturas.</span></div>",
                            unsafe_allow_html=True)
                st.button("Volver a En vivo", icon=":material/sensors:", key=f"{key_prefix}_volver_vivo",
                          type="primary", on_click=restablecer_filtro)
        else:
            fig = fig_area(df_grafica, pref["tipo"], pref["colores"], pref["tendencia"])
            st.plotly_chart(fig, width="stretch", height="stretch", key=f"{key_prefix}_chart_pano",
                            config={"displayModeBar": False})
            _boton_otros_tipos()

    # 2. TARJETAS: arriba el estado actual (fijo); abajo las estadísticas del periodo de la gráfica
    _render_kpis(df_kpi, df_periodo, df_grafica, subtitulo)

def render_dashboard_layout(modo, registros_visor, todas, key_prefix, periodo=None):
    col_main, col_visor = st.columns([2.05, 1], gap="medium")

    with col_main:
        _en_fragmento(_columna_principal, modo, key_prefix)

    with col_visor:
        # 3. CARRUSEL CON LAS ÚLTIMAS CAPTURAS CONFIABLES (la más reciente primero) y la galería completa
        render_visor_laguna(registros_visor, todas, key_prefix=f"{key_prefix}_vlaguna", periodo=periodo)

@st.fragment
def _exportar(df_datos, nombre):
    with st.popover("Exportar", icon=":material/download:", disabled=df_datos.empty):
        st.download_button(
            "Datos en CSV", data=df_datos.drop(columns=["validacion"], errors="ignore").to_csv(index=False).encode("utf-8"),
            file_name=f"curiquinga_{nombre}.csv", mime="text/csv", icon=":material/table:", width="stretch",
        )
        df_periodo, periodo = aplicar_filtro_temporal(df_datos)
        # Huella del periodo: un reporte generado antes de cambiar el filtro o el origen ya no se ofrece
        huella = (nombre, periodo, len(df_periodo))
        if st.button("Generar reporte PDF", icon=":material/picture_as_pdf:", width="stretch", key="btn_generar_pdf"):
            from backend.reporte import generar_reporte
            with st.spinner("Generando reporte…"):
                st.session_state["reporte_pdf"] = (generar_reporte(df_periodo.to_dict("records"), periodo), huella)
        guardado = st.session_state.get("reporte_pdf")
        if guardado and guardado[1] == huella:
            st.download_button("Descargar PDF", data=guardado[0], file_name=f"reporte_curiquinga_{nombre}.pdf",
                               mime="application/pdf", type="primary", icon=":material/download:", width="stretch")
        st.caption(f"El reporte usa el periodo de la gráfica: {periodo}.")

def render_inicio():
    df_completo = df_registros()

    # ENCABEZADO: título a la izquierda; origen, exportar y tema claro/oscuro a la derecha
    col_tit, col_acc = st.columns([1, 2.8], vertical_alignment="center")
    with col_tit:
        st.markdown("<div class='header-title'>Panel de monitoreo</div>", unsafe_allow_html=True)

    with col_acc, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
        modo = st.segmented_control(
            "Origen de los datos", list(MODOS), default="Ambos",
            key="inicio_modo", label_visibility="collapsed"
        ) or "Ambos"

        if modo != "Ambos" and not df_completo.empty:
            df_datos = df_completo[df_completo['estado'].str.contains(modo, na=False)].reset_index(drop=True)
        else:
            df_datos = df_completo
        df_kpi = solo_confiables(df_datos)
        key_prefix = f"inicio_{MODOS[modo]}"
        registros_visor = df_kpi.iloc[::-1].head(N_CARRUSEL).to_dict('records') if not df_kpi.empty else []

        _exportar(df_datos, MODOS[modo])
        boton_tema()

    if st.session_state.get("vista_graficas"):
        _en_fragmento(render_vista_graficas, modo, key_prefix)
    else:
        # La galería sigue al filtro de la gráfica: en vivo, todo el historial; con filtro, solo ese periodo
        periodo = None
        fotos = df_datos
        if not en_vivo():
            fotos, periodo = aplicar_filtro_temporal(df_datos)
        todas = fotos.iloc[::-1].to_dict("records") if not fotos.empty else []
        render_dashboard_layout(modo, registros_visor, todas, key_prefix, periodo)
    # La gráfica ampliada (principal o de "Más gráficos") se abre aquí, fuera del fragmento en vivo
    ampliada = st.session_state.get("grafica_ampliada")
    if ampliada:
        _grafica_ampliada(modo, ampliada if isinstance(ampliada, str) else None)
    activar_tooltip()

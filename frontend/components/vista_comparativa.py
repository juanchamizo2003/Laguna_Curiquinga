import html
import streamlit as st

from backend.calidad import estado_validacion
from backend.miniaturas import ruta_miniatura
from frontend.components.datos import registros, color_estado
from frontend.components.formato import formatear_m2, fecha_legible
from frontend.components.formulario_carga import render_metricas_captura, render_par_imagenes
from frontend.components.tarjetas import punto
from frontend.components.visor_laguna import render_revision

COLUMNAS_GALERIA = 4
POR_PAGINA = 12

def render_vista_comparativa():
    todos = registros()
    if not todos:
        st.info("Aún no hay capturas procesadas para mostrar.")
        return

    ultimo = max(todos, key=lambda r: r["fecha_captura"])
    with st.container(key="visual_ultimo_card"):
        st.markdown(f"""
            <div class='card-title'>Captura más reciente</div>
            <div class='card-sub card-sub-ellipsis'>{html.escape(ultimo['nombre_foto'])} · perímetro {ultimo['perimetro']} m</div>
        """, unsafe_allow_html=True)
        render_metricas_captura(ultimo)
        render_revision(ultimo, "visual_ultimo")
        render_par_imagenes(ultimo)

    # Galería: la más reciente primero, paginada y con miniaturas para no cargar cientos de fotos completas
    ordenados = sorted(todos, key=lambda r: r["fecha_captura"], reverse=True)
    with st.container(key="visual_galeria_card"):
        paginas = max(1, -(-len(ordenados) // POR_PAGINA))
        c_tit, c_pag = st.columns([3, 1], vertical_alignment="center")
        with c_tit:
            st.markdown(f"""
                <div class='card-title'>Galería de segmentaciones</div>
                <div class='card-sub'>{len(ordenados)} capturas · el punto indica su estado de validación</div>
            """, unsafe_allow_html=True)
        pagina = 1
        if paginas > 1:
            with c_pag:
                pagina = st.number_input("Página", 1, paginas, 1, key="galeria_pagina", label_visibility="collapsed")

        visibles = ordenados[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]
        cols = st.columns(COLUMNAS_GALERIA, gap="small")
        for i, r in enumerate(visibles):
            estado = estado_validacion(r)
            with cols[i % COLUMNAS_GALERIA]:
                st.image(ruta_miniatura(r), width="stretch")
                st.markdown(
                    f"<div class='galeria-pie' title='{estado}'>{punto(color_estado(estado))} <b>{formatear_m2(r['area'])}</b> · "
                    f"{fecha_legible(r['fecha_captura'], con_hora=False)} · #{r['id']}</div>",
                    unsafe_allow_html=True,
                )

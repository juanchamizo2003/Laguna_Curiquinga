import streamlit as st

from frontend.components.datos import registros
from frontend.components.formulario_carga import pedir_resultados
from frontend.components.formato import fecha_legible
from frontend.components.visor_laguna import filtrar_por_dia, foto_cuadricula, selector_dia

COLUMNAS_GALERIA = 4
POR_PAGINA = 8  # 2 filas de 4: caben sin desplazarse

def _ir_pagina(pagina):
    st.session_state.visual_pag = pagina

def _poner_dia(dia):
    st.session_state.visual_dia_v = dia
    st.session_state.visual_pag = 0

def render_vista_comparativa():
    # Galería independiente del Inicio: todas las capturas (automáticas y manuales), la más reciente primero, por
    # páginas que caben en la pantalla y con filtro por día; al pulsar una foto se abre en grande
    todos = sorted(registros(), key=lambda r: r["fecha_captura"], reverse=True)
    with st.container(key="visual_galeria_card"):
        if not todos:
            st.markdown("<div class='graf-vacio'><b>Todavía no hay fotos</b>"
                        "<span>Aquí aparecerán las capturas procesadas.</span></div>", unsafe_allow_html=True)
            return
        ordenados, por_dia, dia = filtrar_por_dia(todos, st.session_state.get("visual_dia_v"))
        paginas = max(1, -(-len(ordenados) // POR_PAGINA))
        pagina = min(st.session_state.get("visual_pag", 0), paginas - 1)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"""
                <div class='card-title'>Galería de segmentaciones</div>
                <div class='card-sub'>{fecha_legible(dia, con_hora=False) + " · " if dia else ""}{len(ordenados)} captura(s) · pulsa una foto para verla en grande</div>
            """, unsafe_allow_html=True, width="content")
            st.space("stretch")
            if len(por_dia) > 1:
                selector_dia(por_dia, dia, len(todos), "visual_dia_mes", _poner_dia)
            if paginas > 1:
                with st.container(horizontal=True, vertical_alignment="center", gap=None, key="galeria_pager",
                                  width="content"):
                    st.button("", icon=":material/chevron_left:", key="visual_pag_ant", disabled=pagina == 0,
                              on_click=_ir_pagina, args=(pagina - 1,), type="tertiary", help="Página anterior")
                    st.markdown(f"<p class='gal-pag'>{pagina + 1} / {paginas}</p>", unsafe_allow_html=True, width="content")
                    st.button("", icon=":material/chevron_right:", key="visual_pag_sig", disabled=pagina == paginas - 1,
                              on_click=_ir_pagina, args=(pagina + 1,), type="tertiary", help="Página siguiente")

        ids = [r["id"] for r in ordenados]
        inicio = pagina * POR_PAGINA
        visibles = ordenados[inicio:inicio + POR_PAGINA]
        for fila in range(0, len(visibles), COLUMNAS_GALERIA):
            filas = enumerate(visibles[fila:fila + COLUMNAS_GALERIA], start=inicio + fila)
            for col, (i, r) in zip(st.columns(COLUMNAS_GALERIA, gap="small"), filas):
                with col:
                    foto_cuadricula(r, i, pedir_resultados, (ids, i, False))

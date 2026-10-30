import streamlit as st
from frontend.components.formulario_carga import render_formulario_carga
from frontend.components.tabla_registros import render_tabla_registros
from frontend.components.vista_comparativa import render_vista_comparativa

def render_cargar():
    st.markdown("""
        <div class='header-title'>Cargar y procesar</div>
        <div class='header-sub'>Carga manual de fotografías, revisión de registros y resultados de la segmentación</div>
    """, unsafe_allow_html=True)

    tab_carga, tab_tabla, tab_visuales = st.tabs([
        ":material/cloud_upload: Carga de datos",
        ":material/table_rows: Registros",
        ":material/photo_library: Resultados visuales",
    ])

    with tab_carga:
        render_formulario_carga()

    with tab_tabla:
        render_tabla_registros()

    with tab_visuales:
        render_vista_comparativa()

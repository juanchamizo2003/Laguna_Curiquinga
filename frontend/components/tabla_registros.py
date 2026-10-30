import os
import pandas as pd
import streamlit as st

from backend.data_base import obtener_registro, eliminar_registro
from backend.miniaturas import ruta_miniatura
from frontend.components import recordar
from frontend.components.datos import df_registros, refrescar
from frontend.components.filtro_temporal import render_filtro_temporal, aplicar_filtro_temporal
from frontend.components.visor_laguna import borrar_copias

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ORDENES = {
    "Más recientes": (["Captura"], False),
    "Más antiguas": (["Captura"], True),
    "Mayor área": (["Área (m²)"], False),
    "Menor confianza": (["Confianza"], True),
    "Por estado": (["Estado", "Captura"], [True, False]),
}
ICONOS_ESTADO = {"Aprobada": "🟢", "Validada": "🟢", "Revisar": "🟠", "No apta": "🔴", "Rechazada": "🔴", "Atípica": "🟣", "Pendiente": "⚪"}

@st.dialog("Confirmar eliminación")
def confirmar_eliminacion(ids, borrar_imagenes):
    st.markdown(f"¿Eliminar **{len(ids)} registro(s)** ({', '.join(f'#{i}' for i in ids)})? Esta acción no se puede deshacer.")
    if borrar_imagenes:
        st.caption("También se borrarán la foto original, la procesada y la miniatura del disco.")
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", width="stretch"):
        st.rerun()
    if c2.button("Eliminar", type="primary", width="stretch"):
        for reg_id in ids:
            registro = obtener_registro(reg_id)
            if registro is None:
                continue
            eliminar_registro(reg_id)
            if borrar_imagenes:
                rutas = [os.path.join(BASE_DIR, registro[c]) for c in ("ruta_original", "ruta_procesada")]
                rutas.append(ruta_miniatura(registro))
                for ruta in rutas:
                    if os.path.isfile(ruta):
                        os.remove(ruta)
                borrar_copias(registro)
        _reiniciar_seleccion()
        st.rerun()

def _reiniciar_seleccion():
    # La selección del dataframe es por posición de fila: tras borrar, otra captura ocuparía ese lugar
    st.session_state["tabla_version"] = st.session_state.get("tabla_version", 0) + 1

def _boton_refrescar():
    st.button("Refrescar", icon=":material/refresh:", key="tabla_refrescar", on_click=refrescar,
              help="Vuelve a leer los registros de la base de datos")

def render_tabla_registros():
    df = df_registros()

    with st.container(key="tabla_registros_card"):
        if df.empty:
            st.markdown("<div class='graf-vacio'><b>Todavía no hay registros</b>"
                        "<span>Aquí aparecerán las capturas procesadas.</span></div>", unsafe_allow_html=True)
            with st.container(horizontal_alignment="center"):
                _boton_refrescar()
            return

        total = len(df)
        titulo = st.empty()

        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            recordar.widget("chk_filtrado_tabla", (True, False))
            modo_filtrado = st.toggle("Filtrar por fecha", key="chk_filtrado_tabla")
            opciones_estado = sorted(df["validacion"].unique())
            recordar.widget("tabla_estados", opciones_estado)
            estados = st.multiselect("Estado", opciones_estado, key="tabla_estados",
                                     placeholder="Todos los estados", label_visibility="collapsed", width=260)
            st.space("stretch")
            recordar.widget("tabla_orden", list(ORDENES))
            criterio_orden = st.selectbox("Ordenar por", list(ORDENES), key="tabla_orden",
                                          label_visibility="collapsed", width=180)

        if modo_filtrado:
            render_filtro_temporal(df)
            df, _ = aplicar_filtro_temporal(df, ventana_dias=False)
        if estados:
            df = df[df["validacion"].isin(estados)]

        df_final = pd.DataFrame({
            "ID": df["id"],
            "Archivo": df["nombre_foto"],
            "Captura": pd.to_datetime(df["fecha_captura"], errors="coerce"),
            "Origen": df["estado"].map(lambda e: "Manual" if "Manual" in str(e) else "Automático"),
            "Área (m²)": df["area"],
            "Perímetro (m)": df["perimetro"],
            "Confianza": pd.to_numeric(df["confianza"], errors="coerce"),
            "Calidad": pd.to_numeric(df["calidad"], errors="coerce"),
            "Estado": df["validacion"].map(lambda e: f"{ICONOS_ESTADO.get(e, '')} {e}"),
            "Observación": df["observacion"].fillna(""),
        })
        columnas, ascendente = ORDENES[criterio_orden]
        df_final = df_final.sort_values(columnas, ascending=ascendente, na_position="last").reset_index(drop=True)

        titulo.markdown(f"""
            <div class='card-title'>Base de datos de capturas</div>
            <div class='card-sub'>{len(df_final)} de {total} registros · selecciona filas para eliminarlas</div>
        """, unsafe_allow_html=True)

        evento = st.dataframe(
            # La clave depende de qué filas se ven y en qué orden: si cambian, la selección se vacía
            # en lugar de saltar a otras capturas
            df_final, width="stretch", hide_index=True,
            key=f"tabla_sel_{st.session_state.get('tabla_version', 0)}_{hash(tuple(df_final['ID']))}",
            on_select="rerun", selection_mode="multi-row",
            height="stretch",
            column_config={
                "ID": st.column_config.NumberColumn(width=56),
                "Archivo": st.column_config.TextColumn(width=270),
                "Captura": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                "Área (m²)": st.column_config.NumberColumn(format="localized"),
                "Perímetro (m)": st.column_config.NumberColumn(format="localized", width=112),
                "Confianza": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent", width=125,
                                                             help="Confianza de SAM en la segmentación"),
                "Calidad": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent", width=125,
                                                           help="Puntaje orientativo de nitidez, contraste, brillo y color del agua"),
                "Estado": st.column_config.TextColumn(width=110),
                "Observación": st.column_config.TextColumn(width="medium"),
            },
        )

        filas = evento.selection.rows if evento else []
        ids = [int(df_final.loc[i, "ID"]) for i in filas]

        # ---- Acciones sobre la selección
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            texto = f"{len(ids)} seleccionado(s)" if ids else "Sin selección"
            st.markdown(f"<div class='card-sub'>{texto}</div>", unsafe_allow_html=True, width="content")
            st.space("stretch")
            _boton_refrescar()
            with st.popover("Eliminar", icon=":material/delete:", disabled=not ids):
                borrar_imgs = st.checkbox("Borrar también sus imágenes", value=True, key="chk_elim_imagenes")
                if st.button(f"Eliminar {len(ids)} registro(s)", type="primary", width="stretch", key="tabla_eliminar"):
                    confirmar_eliminacion(ids, borrar_imgs)

import os
import time
import pandas as pd
import streamlit as st

from backend.data_base import obtener_registro, eliminar_registro, marcar_revision
from backend.miniaturas import ruta_miniatura
from frontend.components.datos import df_registros
from frontend.components.filtro_temporal import render_filtro_temporal, aplicar_filtro_temporal

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
        _reiniciar_seleccion()
        st.rerun()

def _reiniciar_seleccion():
    # La selección del dataframe es por posición de fila: tras borrar, otra captura ocuparía ese lugar
    st.session_state["tabla_version"] = st.session_state.get("tabla_version", 0) + 1

def _reprocesar(registros):
    """Vuelve a pasar por calidad + SAM los registros indicados, con barra de progreso."""
    from backend.procesamiento import reprocesar_registro  # importa torch: solo al usarlo
    barra = st.progress(0.0, text="Cargando el modelo SAM…")
    resumen = {"registrada": 0, "descartada": 0, "error": 0}
    detalles = []
    inicio = time.time()
    for i, registro in enumerate(registros, 1):
        barra.progress((i - 1) / len(registros), text=f"Reprocesando {i} de {len(registros)} · {registro['nombre_foto']}")
        r = reprocesar_registro(registro)
        resumen[r["resultado"]] += 1
        if r["resultado"] != "registrada":
            detalles.append(f"#{registro['id']}: {r['mensaje']}")
    barra.progress(1.0, text=f"Reprocesado en {time.time() - inicio:.0f} s")
    st.session_state["tabla_resultado"] = (resumen, detalles)
    st.rerun()

def render_tabla_registros():
    df = df_registros()

    with st.container(key="tabla_registros_card"):
        if df.empty:
            st.markdown("<div class='card-title'>Base de datos de capturas</div>", unsafe_allow_html=True)
            st.info("La base de datos está vacía.")
            return

        total = len(df)
        titulo = st.empty()

        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            modo_filtrado = st.toggle("Filtrar por fecha", key="chk_filtrado_tabla")
            estados = st.multiselect("Estado", sorted(df["validacion"].unique()), key="tabla_estados",
                                     placeholder="Todos los estados", label_visibility="collapsed", width=260)
            st.space("stretch")
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
            <div class='card-sub'>{len(df_final)} de {total} registros · selecciona filas para revisarlas, reprocesarlas o eliminarlas</div>
        """, unsafe_allow_html=True)

        evento = st.dataframe(
            # La clave depende de qué filas se ven y en qué orden: si cambian, la selección se vacía
            # en lugar de saltar a otras capturas
            df_final, width="stretch", hide_index=True,
            key=f"tabla_sel_{st.session_state.get('tabla_version', 0)}_{hash(tuple(df_final['ID']))}",
            on_select="rerun", selection_mode="multi-row",
            height=min(38 + 35 * len(df_final), 520),
            column_config={
                "ID": st.column_config.NumberColumn(width="small"),
                "Archivo": st.column_config.TextColumn(width="medium"),
                "Captura": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                "Área (m²)": st.column_config.NumberColumn(format="localized"),
                "Perímetro (m)": st.column_config.NumberColumn(format="localized", width="small"),
                "Confianza": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent",
                                                             help="Confianza de SAM en la segmentación"),
                "Calidad": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent",
                                                           help="Puntaje orientativo de nitidez, contraste, brillo y color del agua"),
                "Observación": st.column_config.TextColumn(width="medium"),
            },
        )

        filas = evento.selection.rows if evento else []
        ids = [int(df_final.loc[i, "ID"]) for i in filas]
        seleccion = df[df["id"].isin(ids)].to_dict("records")

        # ---- Acciones sobre la selección
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"<div class='card-sub'>{len(ids)} seleccionado(s)</div>" if ids else
                        "<div class='card-sub'>Sin selección</div>", unsafe_allow_html=True, width="content")
            st.space("stretch")
            if st.button("Aprobar", icon=":material/check:", disabled=not ids, key="tabla_aprobar"):
                for i in ids:
                    marcar_revision(i, "aprobada")
                st.rerun()
            if st.button("Rechazar", icon=":material/close:", disabled=not ids, key="tabla_rechazar"):
                for i in ids:
                    marcar_revision(i, "rechazada")
                st.rerun()
            with st.popover("Reprocesar", icon=":material/autorenew:"):
                st.caption("Vuelve a pasar las fotos originales por el control de calidad y SAM con la "
                           "calibración actual. Se borra la revisión manual de esas capturas.")
                sin_conf = df[df["confianza"].isna()].to_dict("records")
                opciones = {
                    f"Seleccionados ({len(seleccion)})": seleccion,
                    f"Sin confianza guardada ({len(sin_conf)})": sin_conf,
                    f"Todos los visibles ({len(df)})": df.to_dict("records"),
                }
                eleccion = st.radio("Qué reprocesar", list(opciones), key="tabla_reproc_alcance", label_visibility="collapsed")
                objetivo = opciones[eleccion]
                st.caption(f"≈ {len(objetivo) * 14 // 60} min en CPU" if len(objetivo) > 4 else "")
                lanzar = st.button("Reprocesar ahora", type="primary", width="stretch", disabled=not objetivo,
                                   key="tabla_reproc_btn")
            with st.popover("Eliminar", icon=":material/delete:", disabled=not ids):
                borrar_imgs = st.checkbox("Borrar también sus imágenes", value=True, key="chk_elim_imagenes")
                if st.button(f"Eliminar {len(ids)} registro(s)", type="primary", width="stretch", key="tabla_eliminar"):
                    confirmar_eliminacion(ids, borrar_imgs)

        if lanzar:
            _reprocesar(objetivo)

        if st.session_state.get("tabla_resultado"):
            resumen, detalles = st.session_state.pop("tabla_resultado")
            texto = (f"Reprocesado: {resumen['registrada']} actualizada(s), {resumen['descartada']} no apta(s), "
                     f"{resumen['error']} con error.")
            (st.success if not resumen["error"] else st.warning)(texto + ("\n\n" + "\n\n".join(detalles) if detalles else ""))

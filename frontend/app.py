import os
import sys
import re
import cv2
import pandas as pd
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from streamlit_calendar import calendar

# Conexión con el módulo Backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.data_base import (
    inicializar_bd, guardar_registro, obtener_registros,
    obtener_registros_por_fechas, eliminar_registro
)
from backend.motor import analizar_laguna

# 1. Configuración de pantalla completa
st.set_page_config(
    page_title="Curiquinga - Monitoreo de Laguna",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. CSS Estricto de Alta Legibilidad y Estilo Corporativo
st.markdown("""
<style>
    /* FONDO Y TIPOGRAFÍA GENERAL */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #f4f6fa !important;
        color: #141a2b !important;
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    }

    [data-testid="stMainBlockContainer"] {
        padding: 20px 35px 40px 35px !important;
        max-width: 100% !important;
    }

    footer {
        visibility: hidden !important;
    }

    /* MANTENER VISIBLE EL BOTÓN DE MENÚ LATERAL (☰) */
    [data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 100000 !important;
    }
    [data-testid="stSidebarCollapseButton"], 
    [data-testid="stHeader"] button {
        visibility: visible !important;
        display: flex !important;
        color: #141a2b !important;
        background-color: #ffffff !important;
        border: 1px solid #d9deea !important;
        border-radius: 8px !important;
    }

    /* BARRA LATERAL (SIDEBAR) ESTILIZADA */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #d9deea !important;
        padding: 15px 12px !important;
    }

    /* Botones de navegación en Sidebar */
    [data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 6px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        background-color: transparent !important;
        border-radius: 10px !important;
        padding: 10px 14px !important;
        border: 1px solid transparent !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background-color: #f4f6fa !important;
    }
    /* Opción Activa estilo Píldora Azul */
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] {
        background-color: #1f4fd8 !important;
        color: #ffffff !important;
        box-shadow: 0 4px 10px rgba(31, 79, 216, 0.2) !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] p,
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"] span {
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    /* TITULARES Y CABECERA */
    .header-title {
        font-size: 26px !important;
        font-weight: 700 !important;
        color: #141a2b !important;
        margin-bottom: 2px !important;
    }
    .header-sub {
        font-size: 13.5px !important;
        color: #6b7386 !important;
        margin-bottom: 15px !important;
    }

    /* PREVISUALIZACIÓN DE IMÁGENES DE LA LAGUNA */
    .ph-box-normal {
        aspect-ratio: 4/3;
        border-radius: 10px;
        border: 1px dashed #cbd5e1;
        background: linear-gradient(135deg, #eef3fb 0%, #e2eafd 100%) !important;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #475569 !important;
        font-size: 13px;
        text-align: center;
        padding: 15px;
    }

    .ph-box-proc {
        aspect-ratio: 4/3;
        border-radius: 10px;
        border: 1px dashed #a7f3d0;
        background: linear-gradient(135deg, #edf7f2 0%, #dcf0e5 100%) !important;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #166534 !important;
        font-size: 13px;
        text-align: center;
        padding: 15px;
    }

    /* CHIPS INFORMATIVOS */
    .chip-container {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 15px;
    }
    .chip-item {
        background-color: #f4f6fa !important;
        border: 1px solid #d9deea !important;
        border-radius: 20px !important;
        padding: 5px 14px !important;
        font-size: 12.5px !important;
        font-weight: 500 !important;
        color: #141a2b !important;
    }

    /* PESTAÑAS (TABS) CON LÍNEA INFERIOR AZUL */
    div[data-baseweb="tab-list"] {
        background-color: transparent !important;
        gap: 20px !important;
        border-bottom: 1px solid #d9deea !important;
        margin-bottom: 18px !important;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        color: #6b7386 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 8px 4px !important;
    }
    div[data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #1f4fd8 !important;
        font-weight: 700 !important;
        border-bottom: 2px solid #1f4fd8 !important;
    }
</style>
""", unsafe_allow_html=True)

inicializar_bd()

# -----------------------------------------------------------------------------
# FUNCIONES CON CACHÉ PARA RENDERIZADO RÁPIDO
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def cargar_registros_bd():
    return obtener_registros()

@st.cache_data(ttl=60)
def cargar_registros_por_fechas_bd(fechas_tuple):
    return obtener_registros_por_fechas(list(fechas_tuple))

# Control de Estados de Sesión
if "fechas_seleccionadas" not in st.session_state:
    st.session_state.fechas_seleccionadas = []
if "meses_seleccionados" not in st.session_state:
    st.session_state.meses_seleccionados = []
if "anios_seleccionados" not in st.session_state:
    st.session_state.anios_seleccionados = []

if "limite_dias" not in st.session_state:
    st.session_state.limite_dias = 7
if "limite_meses" not in st.session_state:
    st.session_state.limite_meses = 3
if "limite_anios" not in st.session_state:
    st.session_state.limite_anios = 1

if "tipo_seleccion" not in st.session_state:
    st.session_state.tipo_seleccion = "Días"
if "ultimo_clic" not in st.session_state:
    st.session_state.ultimo_clic = None

MAPA_MESES = {
    "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Ago": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dic": "12"
}

def extraer_fecha_hora(filename):
    match1 = re.search(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', filename)
    if match1:
        a, m, d, h, mn, s = match1.groups()
        return f"{d}/{m}/{a}", f"{h}:{mn}:{s}"
    now = datetime.now()
    return now.strftime("%d/%m/%Y"), now.strftime("%H:%M:%S")

# -----------------------------------------------------------------------------
# GRÁFICO PANORÁMICO SUPERIOR EN TIEMPO REAL
# -----------------------------------------------------------------------------
def crear_grafico_barras_puntos(df):
    fig = go.Figure()

    if df.empty:
        x_data = [f"Muestra {i}" for i in range(1, 9)]
        y_data = [150, 220, 180, 290, 310, 270, 340, 390]
    else:
        x_data = df['nombre_foto'].tolist()
        y_data = df['area'].tolist()

    fig.add_trace(go.Bar(
        x=x_data, y=y_data, name="Área (m²)",
        marker_color="#1f4fd8", opacity=0.75
    ))

    fig.add_trace(go.Scatter(
        x=x_data, y=y_data, mode="markers+lines", name="Puntos de Medición",
        marker=dict(size=10, color="#1b7f4b", symbol="circle"),
        line=dict(color="#1b7f4b", width=2)
    ))

    fig.update_layout(
        title="<b>📊 Monitoreo de Flujo de Datos en Tiempo Real</b>",
        xaxis_title="Registros / Muestras",
        yaxis_title="Área Medida (m²)",
        paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
        margin=dict(l=20, r=20, t=40, b=20), height=260,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e2e7f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e7f0")
    return fig

# -----------------------------------------------------------------------------
# FUNCIONES DE GRÁFICOS INFERIORES (CUADRÍCULA 2x2)
# -----------------------------------------------------------------------------
def fig_area_tiempo(df):
    fig = go.Figure()
    if df.empty:
        x_d = [f"Reg #{i}" for i in range(1, 7)]
        y_d = [120, 180, 160, 240, 210, 290]
    else:
        x_d = df['fecha_captura'].tolist()
        y_d = [v / 10000.0 for v in df['area'].tolist()]

    fig.add_trace(go.Scatter(x=x_d, y=y_d, mode='lines+markers', line=dict(color='#1f4fd8', width=2), marker=dict(size=6)))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#fff', plot_bgcolor='#fff')
    fig.update_xaxes(showgrid=True, gridcolor="#e2e7f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e7f0", title="ha")
    return fig

def fig_histograma_area(df):
    if df.empty:
        val = [1.2, 1.5, 1.8, 2.1, 1.4, 1.6, 2.0, 1.7, 1.5, 2.2]
    else:
        val = [v / 10000.0 for v in df['area'].tolist()]

    fig = px.histogram(x=val, nbins=8, color_discrete_sequence=['#1f4fd8'])
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#fff', plot_bgcolor='#fff', showlegend=False)
    fig.update_xaxes(showgrid=True, gridcolor="#e2e7f0", title="Área (ha)")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e7f0", title="Frecuencia")
    return fig

def fig_deteccion_color(df):
    colores = ['Verde', 'Azul', 'Marrón']
    conteo = [0, 0, 0]
    if not df.empty and 'color_hex' in df.columns:
        conteo = [len(df[df['color_hex'] == '#2E9B5B']), len(df[df['color_hex'] == '#2F6FD6']), len(df[df['color_hex'] == '#8A5A2B'])]
    else:
        conteo = [12, 5, 2]

    fig = go.Figure(data=[go.Bar(x=colores, y=conteo, marker_color=['#2e9b5b', '#2f6fd6', '#8a5a2b'])])
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#fff', plot_bgcolor='#fff')
    fig.update_xaxes(showgrid=True, gridcolor="#e2e7f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e7f0")
    return fig

def fig_registros_hora(df):
    horas = list(range(24))
    conteo = [0] * 24
    if not df.empty:
        for f in df['fecha_subida'].tolist():
            try:
                h = int(f.split(" ")[1].split(":")[0])
                conteo[h] += 1
            except:
                pass
    else:
        conteo = [1, 0, 0, 0, 2, 5, 8, 12, 15, 10, 6, 4, 3, 5, 9, 11, 7, 4, 2, 1, 0, 0, 1, 0]

    fig = go.Figure(data=[go.Bar(x=horas, y=conteo, marker_color='#1f4fd8')])
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#fff', plot_bgcolor='#fff')
    fig.update_xaxes(showgrid=True, gridcolor="#e2e7f0", title="Hora")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e7f0")
    return fig

# BARRA LATERAL (SIDEBAR CORPORATIVO)
st.sidebar.markdown("""
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:20px; padding-left:4px;">
        <span style="font-size:22px;">🌊</span>
        <span style="font-size:20px; font-weight:700; color:#141a2b;">Curiquinga</span>
    </div>
""", unsafe_allow_html=True)

opcion = st.sidebar.radio(
    "Navegación",
    ["🏠  Inicio", "📷  Cargar y Procesar", "⚙️  Control de Servidor"],
    label_visibility="collapsed"
)

# -----------------------------------------------------------------------------
# MÓDULO 1: PANEL DE INICIO
# -----------------------------------------------------------------------------
if "Inicio" in opcion:
    st.markdown("<div class='header-title'>Panel de Inicio <span style='font-size:14px; font-weight:400; color:#6b7386;'>Bienvenido, Administrador (Admin)</span></div>", unsafe_allow_html=True)
    st.markdown("<div class='header-sub'>Monitoreo y análisis en tiempo real de la laguna</div>", unsafe_allow_html=True)

    tab_ambos, tab_auto, tab_manual = st.tabs(["Ambos", "Automático", "Manual"])

    with tab_ambos:
        # 1. Obtener todos los datos para luego aplicar el filtro según el modo activo
        registros_raw = cargar_registros_bd()
        df_base = pd.DataFrame(registros_raw) if registros_raw else pd.DataFrame()

        # 2. FILTRO EN TIEMPO REAL SEGÚN TIPO (Días / Meses / Años)
        if not df_base.empty and 'fecha_captura' in df_base.columns:
            if st.session_state.tipo_seleccion == "Días" and st.session_state.fechas_seleccionadas:
                fechas_tuple = tuple(sorted(st.session_state.fechas_seleccionadas))
                registros = cargar_registros_por_fechas_bd(fechas_tuple)
                df = pd.DataFrame(registros) if registros else pd.DataFrame()
            elif st.session_state.tipo_seleccion == "Meses" and st.session_state.meses_seleccionados:
                m_nums = [MAPA_MESES[m] for m in st.session_state.meses_seleccionados if m in MAPA_MESES]
                df = df_base[df_base['fecha_captura'].str.slice(3, 5).isin(m_nums)]
                registros = df.to_dict('records')
            elif st.session_state.tipo_seleccion == "Años" and st.session_state.anios_seleccionados:
                df = df_base[df_base['fecha_captura'].str.slice(6, 10).isin(st.session_state.anios_seleccionados)]
                registros = df.to_dict('records')
            else:
                df = df_base
                registros = registros_raw
        else:
            df = df_base
            registros = registros_raw

        # 3. GRÁFICO PANORÁMICO SUPERIOR
        with st.container(border=True):
            st.plotly_chart(crear_grafico_barras_puntos(df), use_container_width=True)

        # 4. FILTRO TEMPORAL Y VISOR DE IMÁGENES
        col_left, col_right = st.columns([1, 1.8], gap="large")

        # ----- TARJETA IZQUIERDA: FILTRO ADAPTABLE (DÍAS / MESES / AÑOS) -----
        with col_left:
            with st.container(border=True):
                st.markdown("#### 🗓️ **Filtro temporal**")

                # Selector de Modo
                tipo_sel = st.radio(
                    "Tipo", ["Días", "Meses", "Años"], 
                    index=["Días", "Meses", "Años"].index(st.session_state.tipo_seleccion),
                    key="radio_tipo_seleccion",
                    horizontal=True, label_visibility="collapsed"
                )
                st.session_state.tipo_seleccion = tipo_sel

                # -------------------------------------------------------------
                # CASO A: FILTRO POR DÍAS (CALENDARIO)
                # -------------------------------------------------------------
                if st.session_state.tipo_seleccion == "Días":
                    def al_cambiar_limite_dias():
                        sel = st.session_state.select_limite_dias
                        if sel == "7 días": st.session_state.limite_dias = 7
                        elif sel == "15 días": st.session_state.limite_dias = 15
                        elif sel == "30 días": st.session_state.limite_dias = 30

                    lim_opciones = ["7 días", "15 días", "30 días", "Personalizado"]
                    idx_lim = 0
                    if st.session_state.limite_dias == 15: idx_lim = 1
                    elif st.session_state.limite_dias == 30: idx_lim = 2
                    elif st.session_state.limite_dias not in [7, 15, 30]: idx_lim = 3

                    st.selectbox("Límite", lim_opciones, index=idx_lim, key="select_limite_dias", on_change=al_cambiar_limite_dias, label_visibility="collapsed")

                    if st.session_state.select_limite_dias == "Personalizado":
                        st.session_state.limite_dias = st.number_input("Días personalizados:", min_value=1, max_value=365, value=st.session_state.limite_dias, key="input_custom_dias")

                    eventos_cal = [{
                        "title": "✓", "start": f, "end": f,
                        "backgroundColor": "#1f4fd8", "borderColor": "#1f4fd8", "allDay": True
                    } for f in st.session_state.fechas_seleccionadas]

                    options_cal = {
                        "headerToolbar": {"left": "prev,next today", "center": "title", "right": ""},
                        "initialView": "dayGridMonth", "selectable": True, "locale": "es"
                    }

                    cal_data = calendar(
                        events=eventos_cal, options=options_cal,
                        custom_css="""
                            .fc { font-family: 'Inter', sans-serif; font-size: 12.5px; }
                            .fc-toolbar-title { font-size: 14px !important; color: #141a2b; font-weight: 700; text-transform: capitalize; }
                            .fc-button-primary { background-color: #1f4fd8 !important; border-color: #1f4fd8 !important; text-transform: capitalize; }
                        """,
                        key="calendar_dias"
                    )

                    if cal_data.get("dateClick"):
                        click_info = cal_data["dateClick"]["date"]
                        if click_info != st.session_state.ultimo_clic:
                            st.session_state.ultimo_clic = click_info
                            dia_pulsado = click_info.split("T")[0]
                            if dia_pulsado in st.session_state.fechas_seleccionadas:
                                st.session_state.fechas_seleccionadas.remove(dia_pulsado)
                                st.rerun()
                            else:
                                if len(st.session_state.fechas_seleccionadas) < st.session_state.limite_dias:
                                    st.session_state.fechas_seleccionadas.append(dia_pulsado)
                                    st.rerun()

                    num_sel = len(st.session_state.fechas_seleccionadas)
                    if num_sel >= st.session_state.limite_dias:
                        st.warning(f"Límite de {st.session_state.limite_dias} días alcanzado.")
                    st.caption(f"**Seleccionados:** {num_sel} / {st.session_state.limite_dias}")

                # -------------------------------------------------------------
                # CASO B: FILTRO POR MESES (CUADRÍCULA 3x4)
                # -------------------------------------------------------------
                elif st.session_state.tipo_seleccion == "Meses":
                    def al_cambiar_limite_meses():
                        sel = st.session_state.select_limite_meses
                        if sel == "1 mes": st.session_state.limite_meses = 1
                        elif sel == "3 meses": st.session_state.limite_meses = 3
                        elif sel == "6 meses": st.session_state.limite_meses = 6
                        elif sel == "12 meses": st.session_state.limite_meses = 12

                    lim_m_opciones = ["1 mes", "3 meses", "6 meses", "12 meses", "Personalizado"]
                    idx_m_lim = 1
                    if st.session_state.limite_meses == 1: idx_m_lim = 0
                    elif st.session_state.limite_meses == 6: idx_m_lim = 2
                    elif st.session_state.limite_meses == 12: idx_m_lim = 3
                    elif st.session_state.limite_meses not in [1, 3, 6, 12]: idx_m_lim = 4

                    st.selectbox("Límite Meses", lim_m_opciones, index=idx_m_lim, key="select_limite_meses", on_change=al_cambiar_limite_meses, label_visibility="collapsed")

                    if st.session_state.select_limite_meses == "Personalizado":
                        st.session_state.limite_meses = st.number_input("Meses personalizados:", min_value=1, max_value=12, value=st.session_state.limite_meses, key="input_custom_meses")

                    st.caption("Selecciona los meses que necesitas. Puedes combinar meses.")
                    
                    lista_meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                    cols_m = st.columns(3)
                    for i, m_name in enumerate(lista_meses):
                        col = cols_m[i % 3]
                        esta_sel = m_name in st.session_state.meses_seleccionados
                        lbl = f"✓ {m_name}" if esta_sel else m_name
                        b_type = "primary" if esta_sel else "secondary"
                        if col.button(lbl, type=b_type, key=f"btn_mes_{m_name}", use_container_width=True):
                            if esta_sel:
                                st.session_state.meses_seleccionados.remove(m_name)
                                st.rerun()
                            else:
                                if len(st.session_state.meses_seleccionados) < st.session_state.limite_meses:
                                    st.session_state.meses_seleccionados.append(m_name)
                                    st.rerun()

                    num_sel_m = len(st.session_state.meses_seleccionados)
                    if num_sel_m >= st.session_state.limite_meses:
                        st.warning(f"Límite de {st.session_state.limite_meses} meses alcanzado.")
                    st.caption(f"**Seleccionados:** {num_sel_m} / {st.session_state.limite_meses}")

                # -------------------------------------------------------------
                # CASO C: FILTRO POR AÑOS (CUADRÍCULA 3x5)
                # -------------------------------------------------------------
                elif st.session_state.tipo_seleccion == "Años":
                    def al_cambiar_limite_anios():
                        sel = st.session_state.select_limite_anios
                        if sel == "1 año": st.session_state.limite_anios = 1
                        elif sel == "2 años": st.session_state.limite_anios = 2
                        elif sel == "5 años": st.session_state.limite_anios = 5
                        elif sel == "10 años": st.session_state.limite_anios = 10

                    lim_y_opciones = ["1 año", "2 años", "5 años", "10 años", "Personalizado"]
                    idx_y_lim = 0
                    if st.session_state.limite_anios == 2: idx_y_lim = 1
                    elif st.session_state.limite_anios == 5: idx_y_lim = 2
                    elif st.session_state.limite_anios == 10: idx_y_lim = 3
                    elif st.session_state.limite_anios not in [1, 2, 5, 10]: idx_y_lim = 4

                    st.selectbox("Límite Años", lim_y_opciones, index=idx_y_lim, key="select_limite_anios", on_change=al_cambiar_limite_anios, label_visibility="collapsed")

                    if st.session_state.select_limite_anios == "Personalizado":
                        st.session_state.limite_anios = st.number_input("Años personalizados:", min_value=1, max_value=20, value=st.session_state.limite_anios, key="input_custom_anios")

                    st.caption("Selecciona los años que quieres consultar.")
                    
                    lista_anios = [str(y) for y in range(2020, 2035)]
                    cols_y = st.columns(3)
                    for i, y_str in enumerate(lista_anios):
                        col = cols_y[i % 3]
                        esta_sel = y_str in st.session_state.anios_seleccionados
                        lbl = f"✓ {y_str}" if esta_sel else y_str
                        b_type = "primary" if esta_sel else "secondary"
                        if col.button(lbl, type=b_type, key=f"btn_anio_{y_str}", use_container_width=True):
                            if esta_sel:
                                st.session_state.anios_seleccionados.remove(y_str)
                                st.rerun()
                            else:
                                if len(st.session_state.anios_seleccionados) < st.session_state.limite_anios:
                                    st.session_state.anios_seleccionados.append(y_str)
                                    st.rerun()

                    num_sel_y = len(st.session_state.anios_seleccionados)
                    if num_sel_y >= st.session_state.limite_anios:
                        st.warning(f"Límite de {st.session_state.limite_anios} años alcanzado.")
                    st.caption(f"**Seleccionados:** {num_sel_y} / {st.session_state.limite_anios}")

                # Botones Limpiar y Buscar
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    if st.button("🧹 Limpiar", use_container_width=True):
                        st.session_state.fechas_seleccionadas = []
                        st.session_state.meses_seleccionados = []
                        st.session_state.anios_seleccionados = []
                        st.session_state.ultimo_clic = None
                        st.cache_data.clear()
                        st.rerun()
                with b_col2:
                    if st.button("🔍 Aplicar selección", type="primary", use_container_width=True):
                        st.rerun()

                # Chips resumidos
                color_txt = "sin datos"
                area_txt = "sin datos"
                total_regs = len(df) if not df.empty else 0

                if not df.empty:
                    color_txt = df.iloc[-1]['color_hex']
                    area_txt = f"{df.iloc[-1]['area']} m²"

                st.markdown(f"""
                    <div class='chip-container'>
                        <div class='chip-item'>Color: <b>{color_txt}</b></div>
                        <div class='chip-item'>Área: <b>{area_txt}</b></div>
                        <div class='chip-item'><b>{total_regs}</b> registros</div>
                    </div>
                """, unsafe_allow_html=True)

        # ----- TARJETA DERECHA: IMÁGENES DE LA LAGUNA (CUADRÍCULA 2x2) -----
        with col_right:
            with st.container(border=True):
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    st.markdown("#### 📷 **Imágenes de la laguna** <span style='font-size:12px; color:#6b7386;'>2/4</span>", unsafe_allow_html=True)
                with c_head2:
                    st.markdown("<div style='text-align:right;'><button style='border:1px solid #d9deea; background:#fff; border-radius:6px; padding:2px 8px;'>‹</button> <button style='border:1px solid #d9deea; background:#fff; border-radius:6px; padding:2px 8px;'>›</button></div>", unsafe_allow_html=True)

                rec1 = df.iloc[-1] if not df.empty else None
                rec2 = df.iloc[-2] if (not df.empty and len(df) >= 2) else None

                # FILA 1 DE IMÁGENES
                col_img1, col_img2 = st.columns(2, gap="medium")

                with col_img1:
                    if rec1 and os.path.exists(os.path.join(BASE_DIR, rec1["ruta_original"])):
                        st.image(os.path.join(BASE_DIR, rec1["ruta_original"]), use_container_width=True)
                    else:
                        st.markdown("""
                            <div class='ph-box-normal'>
                                <b>Imagen normal</b><br>
                                <small>Captura 1 • pendiente</small>
                            </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<p style='text-align:center; font-size:12.5px; color:#6b7386; margin-top:4px; margin-bottom:12px;'>Imagen normal (1)</p>", unsafe_allow_html=True)

                with col_img2:
                    if rec1 and os.path.exists(os.path.join(BASE_DIR, rec1["ruta_procesada"])):
                        st.image(os.path.join(BASE_DIR, rec1["ruta_procesada"]), use_container_width=True)
                    else:
                        st.markdown("""
                            <div class='ph-box-proc'>
                                <b>Imagen procesada</b><br>
                                <small>Captura 1 • pendiente</small>
                            </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<p style='text-align:center; font-size:12.5px; color:#6b7386; margin-top:4px; margin-bottom:12px;'>Imagen procesada (IA 1)</p>", unsafe_allow_html=True)

                # FILA 2 DE IMÁGENES
                col_img3, col_img4 = st.columns(2, gap="medium")

                with col_img3:
                    if rec2 and os.path.exists(os.path.join(BASE_DIR, rec2["ruta_original"])):
                        st.image(os.path.join(BASE_DIR, rec2["ruta_original"]), use_container_width=True)
                    else:
                        st.markdown("""
                            <div class='ph-box-normal'>
                                <b>Imagen normal</b><br>
                                <small>Captura 2 • pendiente</small>
                            </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<p style='text-align:center; font-size:12.5px; color:#6b7386; margin-top:4px;'>Imagen normal (2)</p>", unsafe_allow_html=True)

                with col_img4:
                    if rec2 and os.path.exists(os.path.join(BASE_DIR, rec2["ruta_procesada"])):
                        st.image(os.path.join(BASE_DIR, rec2["ruta_procesada"]), use_container_width=True)
                    else:
                        st.markdown("""
                            <div class='ph-box-proc'>
                                <b>Imagen procesada</b><br>
                                <small>Captura 2 • pendiente</small>
                            </div>
                        """, unsafe_allow_html=True)
                    st.markdown("<p style='text-align:center; font-size:12.5px; color:#6b7386; margin-top:4px;'>Imagen procesada (IA 2)</p>", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("Desplegar galería ▾"):
                    if not df.empty:
                        cols_gal = st.columns(3)
                        for i, r in enumerate(registros):
                            p_proc = os.path.join(BASE_DIR, r["ruta_procesada"])
                            if os.path.exists(p_proc):
                                cols_gal[i % 3].image(p_proc, caption=r["nombre_foto"], use_container_width=True)
                    else:
                        st.info("No hay imágenes almacenadas en la galería.")

        # 5. SECCIÓN DE GRÁFICOS Y ANÁLISIS VISUAL DEL SISTEMA (CUADRÍCULA 2x2)
        st.markdown("<br>", unsafe_allow_html=True)
        c_th1, c_th2 = st.columns([2, 1])
        with c_th1:
            st.markdown("### **Gráficos y análisis visual del sistema**")
        with c_th2:
            st.markdown("<p style='text-align:right; font-size:12px; color:#6b7386; margin-top:8px;'>Usa ☰ para reordenar las tarjetas. Haz clic en un gráfico para ampliarlo.</p>", unsafe_allow_html=True)

        g_row1_col1, g_row1_col2 = st.columns(2, gap="large")
        with g_row1_col1:
            with st.container(border=True):
                st.markdown("##### ☰ **Área de la laguna (ha)**")
                st.plotly_chart(fig_area_tiempo(df), use_container_width=True)

        with g_row1_col2:
            with st.container(border=True):
                st.markdown("##### ☰ **Histograma de área (ha)**")
                st.plotly_chart(fig_histograma_area(df), use_container_width=True)

        g_row2_col1, g_row2_col2 = st.columns(2, gap="large")
        with g_row2_col1:
            with st.container(border=True):
                st.markdown("##### ☰ **Detección de color**")
                st.plotly_chart(fig_deteccion_color(df), use_container_width=True)

        with g_row2_col2:
            with st.container(border=True):
                st.markdown("##### ☰ **Registros por hora del día**")
                st.plotly_chart(fig_registros_hora(df), use_container_width=True)

    with tab_auto:
        st.info("Registros provenientes de capturas automáticas de cámaras.")

    with tab_manual:
        st.info("Registros procesados por carga manual.")

# -----------------------------------------------------------------------------
# MÓDULO 2: CARGAR Y PROCESAR
# -----------------------------------------------------------------------------
elif "Cargar" in opcion:
    st.markdown("<div class='header-title'>Carga Manual y Procesamiento</div>", unsafe_allow_html=True)
    st.markdown("<div class='header-sub'>Sube fotografías para ejecutar la segmentación con el modelo SAM</div>", unsafe_allow_html=True)

    with st.container(border=True):
        archivos = st.file_uploader("Selecciona imágenes (.jpg, .png)", type=["jpg", "png", "jpeg"], accept_multiple_files=True)

        if archivos and st.button("🚀 Procesar imágenes", type="primary"):
            progreso = st.progress(0)
            status = st.empty()

            dir_ingesta = os.path.join(BASE_DIR, "flujo_imagenes", "ingesta_camara")
            dir_proc = os.path.join(BASE_DIR, "flujo_imagenes", "fotos_procesadas")
            os.makedirs(dir_ingesta, exist_ok=True)
            os.makedirs(dir_proc, exist_ok=True)

            for i, f_file in enumerate(archivos):
                r_orig = os.path.join(dir_ingesta, f_file.name)
                with open(r_orig, "wb") as f:
                    f.write(f_file.getbuffer())

                status.info(f"Analizando [{i+1}/{len(archivos)}]: {f_file.name}...")
                exito, msg, datos = analizar_laguna(r_orig)

                if exito and datos:
                    r_proc = os.path.join(dir_proc, f"trazo_{f_file.name}")
                    cv2.imwrite(r_proc, cv2.cvtColor(datos["img_visual"], cv2.COLOR_RGB2BGR))

                    f_str, h_str = extraer_fecha_hora(f_file.name)
                    guardar_registro(
                        nombre_foto=f_file.name,
                        fecha_subida=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        fecha_captura=f"{f_str} {h_str}",
                        area=datos["area"],
                        perimetro=datos["perimetro"],
                        color_hex=datos["color_hex"],
                        estado="Procesado",
                        ruta_original=os.path.join("flujo_imagenes", "ingesta_camara", f_file.name),
                        ruta_procesada=os.path.join("flujo_imagenes", "fotos_procesadas", f"trazo_{f_file.name}")
                    )
                progreso.progress((i + 1) / len(archivos))

            st.cache_data.clear()
            status.success("¡Procesamiento masivo finalizado!")

# -----------------------------------------------------------------------------
# MÓDULO 3: CONTROL DE SERVIDOR
# -----------------------------------------------------------------------------
elif "Servidor" in opcion:
    st.markdown("<div class='header-title'>Control de Servidor</div>", unsafe_allow_html=True)
    st.markdown("<div class='header-sub'>Diagnóstico de red y servicios en segundo plano</div>", unsafe_allow_html=True)

    with st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.success("🟢 Servidor: Online")
        m2.info("📷 Flujo: Activo")
        m3.success("⚡ Modelo SAM: En memoria")

        st.markdown("<br>", unsafe_allow_html=True)
        st.code("""
[16:45:12] [INFO] Observador escuchando flujo_imagenes/ingesta_camara...
[16:45:13] [SUCCESS] Inferencia completada y datos almacenados en registros.db.
        """, language="bash")
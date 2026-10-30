import os
import sys
import html
from datetime import datetime
import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.data_base import inicializar_bd, contar_alertas_no_leidas
from backend.servicio import leer_estado
from backend import acceso
from backend import config as cfg
from frontend.components import recordar
from frontend.components.datos import registros
from frontend.components.visor_laguna import boton_tema

st.set_page_config(
    page_title="Monitoreo Laguna Curiquinga",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos y tema claro/oscuro: Streamlit guarda el tema elegido en localStorage; el botón del encabezado lo cambia
# y recarga para que también los componentes nativos (tablas, campos) lo tomen. data-tema activa las variables CSS.
st.html("""
<style>
    :root {
        --bg: #0b0f14;
        --surface: #12171e;
        --surface-2: #1a2029;
        --border: #232a33;
        --text: #e8edf2;
        --muted: #8b95a3;
        --accent: #3cc9b4;
        --accent-soft: rgba(60, 201, 180, 0.13);
        --accent-ink: #06201c;
        --danger: #f0616d;
        --danger-soft: rgba(240, 97, 109, 0.14);
        --ok: #2fd27a;
        --ok-soft: rgba(47, 210, 122, 0.14);
        --warn: #f5a742;
        --text-2: #c5ccd5;
        --menu-text: #b5bec9;
        --tip-bg: #151b22;
        --tip-border: #2b333d;
        --sw-border: rgba(255, 255, 255, .2);
        --dropzone-border: #2f3844;
    }
    /* Tema claro: lo activa el botón del encabezado (atributo data-tema de la raíz, ver el script al final) */
    :root[data-tema="claro"] {
        --bg: #edf0f4;
        --surface: #ffffff;
        --surface-2: #e9edf2;
        --border: #dce1e7;
        --text: #17212c;
        --muted: #5e6a78;
        --accent: #17a08e;
        --accent-soft: rgba(23, 160, 142, 0.12);
        --accent-ink: #ffffff;
        --danger: #d43f4d;
        --danger-soft: rgba(212, 63, 77, 0.1);
        --ok: #18975a;
        --ok-soft: rgba(24, 151, 90, 0.12);
        --warn: #d4861c;
        --text-2: #3b4756;
        --menu-text: #4a5563;
        --tip-bg: #ffffff;
        --tip-border: #dce1e7;
        --sw-border: rgba(0, 0, 0, .15);
        --dropzone-border: #c6cdd6;
    }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: var(--bg) !important;
        color: var(--text) !important;
    }
    [data-testid="stMainBlockContainer"] {
        padding: 1.4rem 1.6rem 0.4rem 1.6rem !important;
        max-width: 100% !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] { gap: 0.75rem; }
    /* Streamlit aplica margin-bottom:-1rem al markdown; en tarjetas propias se anula */
    [data-testid="stMarkdownContainer"]:has(.kpi-card, .visor-metricas, .card-title, .header-title, .brand, .estado-card, .terminal, .lista-datos, .ayuda-carga, .img-titulo, .alertas-lista) { margin-bottom: 0 !important; }
    footer { visibility: hidden !important; }

    /* Cabecera de Streamlit: transparente y sin bloquear los botones del panel */
    [data-testid="stHeader"] { background: transparent !important; pointer-events: none; z-index: 1000100 !important; }
    [data-testid="stHeader"] button { pointer-events: auto; }
    [data-testid="stToolbar"] { pointer-events: none; }
    /* La barra de herramientas aloja el botón para expandir el menú: solo se ocultan sus otras acciones */
    [data-testid="stToolbarActions"], [data-testid="stMainMenu"] { display: none !important; }

    /* ---------- Barra lateral ---------- */
    [data-testid="stSidebar"] {
        background-color: var(--bg) !important;
        border-right: 1px solid var(--border) !important;
        min-width: 300px !important; max-width: 300px !important;
    }
    [data-testid="stSidebarContent"] { position: relative; width: 300px !important; padding: 0 !important; }
    [data-testid="stSidebarHeader"] { height: 0 !important; min-height: 0 !important; padding: 0 !important; }
    [data-testid="stSidebarUserContent"] { padding: 1.3rem 1rem 0 1rem !important; width: 100% !important; }
    [data-testid="stSidebarUserContent"] [data-testid="stRadio"],
    [data-testid="stSidebarUserContent"] [data-testid="stElementContainer"] { width: 100% !important; }
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 0; }

    .brand { display: flex; align-items: center; gap: 14px; margin: 0 0 30px 4px; }
    .brand-logo {
        flex: none; width: 46px; height: 46px; border-radius: 50%; background: var(--accent); color: var(--accent-ink);
        display: flex; align-items: center; justify-content: center;
    }
    .brand-logo svg { width: 22px; height: 22px; }
    .brand-name { font-size: 18px; font-weight: 700; color: var(--text); line-height: 1.25; }
    .brand-sub { font-size: 13.5px; color: var(--muted); }
    .menu-label { font-size: 12px; font-weight: 600; letter-spacing: .08em; color: var(--muted); margin: 0 0 12px 16px; }

    [data-testid="stSidebar"] [data-testid="stRadioGroup"] { width: 100%; align-items: stretch !important; }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div { width: 100%; gap: 6px; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        position: relative; width: 100% !important; max-width: none !important; align-self: stretch; margin: 0 !important;
        padding: 13px 16px !important; border-radius: 12px;
        transition: background-color .15s;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child { display: none !important; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div { flex: 1; min-width: 0; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p {
        font-size: 16px !important; color: var(--menu-text) !important; display: flex; align-items: center; gap: 14px;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p span { font-size: 22px !important; color: var(--muted); }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background-color: var(--surface); }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background-color: var(--surface-2); }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p { color: var(--text) !important; font-weight: 600; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p span { color: var(--text); }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"]::after {
        content: ""; position: absolute; right: 18px; top: 50%; transform: translateY(-50%);
        width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
    }

    /* Tarjeta de estado y botón "Contraer" anclados al pie de la barra lateral */
    .st-key-sb_estado { position: absolute !important; left: 16px; right: 16px; bottom: 76px; width: auto !important; }
    /* En ventanas bajas la tarjeta fija taparía el menú: pasa a ir debajo de él */
    @media (max-height: 720px) {
        .st-key-sb_estado { position: static !important; margin: 18px 0 70px 0; }
    }
    .estado-card { border: 1px solid var(--border); border-radius: 16px; padding: 14px 16px; background: var(--bg); }
    .estado-card b { display: flex; align-items: center; gap: 10px; font-size: 14.5px; color: var(--text); }
    .estado-card b i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
    .estado-card span { display: block; font-size: 13.5px; color: var(--muted); margin-top: 6px; }
    [data-testid="stSidebarCollapseButton"] {
        position: absolute !important; left: 12px; right: auto; bottom: 16px;
        display: flex !important; justify-content: flex-start; opacity: 1 !important; visibility: visible !important;
    }
    /* Pie de la barra: una línea lo separa del menú; "Contraer" a la izquierda y el tema a la derecha, bien aparte */
    [data-testid="stSidebar"]:not([data-collapsed="true"]) [data-testid="stSidebarContent"]::after {
        content: ""; position: absolute; left: 16px; right: 16px; bottom: 62px; height: 1px; background: var(--border);
    }
    .st-key-sb_tema { position: absolute !important; right: 16px; bottom: 15px; width: auto !important; z-index: 2; }
    .st-key-sb_tema .tema-toggle { min-height: 34px; padding: 2px; border-radius: 10px; }
    .st-key-sb_tema .tema-toggle i { width: 30px; height: 28px; border-radius: 8px; }
    .st-key-sb_tema .tema-toggle i::before { width: 16px; height: 16px; }
    [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.tema-toggle) { width: auto !important; }
    [data-testid="stSidebarCollapseButton"] button { color: var(--muted) !important; gap: 10px; padding: 6px 14px !important; }
    [data-testid="stSidebarCollapseButton"] button::after { content: "Contraer"; font-size: 15.5px; }

    /* Menú contraído: queda un riel angosto solo con los iconos */
    [data-testid="stSidebar"][data-collapsed="true"] {
        transform: none !important; width: 76px !important; min-width: 76px !important; max-width: 76px !important;
    }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stSidebarContent"] {
        width: 76px !important; overflow-x: hidden; scrollbar-gutter: auto !important; scrollbar-width: none;
    }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stSidebarUserContent"] { padding: 1.3rem 0 0 0 !important; width: 76px !important; }
    [data-testid="stSidebar"][data-collapsed="true"] .brand { justify-content: center; margin: 0 0 30px 0; }
    [data-testid="stSidebar"][data-collapsed="true"] .brand > div:last-child,
    [data-testid="stSidebar"][data-collapsed="true"] .menu-label,
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stSidebarResizeHandle"] { display: none !important; }
    /* Opciones: cuadros de 48px centrados en el riel, icono en el centro exacto */
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioGroup"] > div { align-items: center; gap: 8px; }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"] {
        width: 48px !important; height: 48px; padding: 0 !important; margin: 0 auto !important;
        display: flex !important; align-items: center; justify-content: center;
    }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"] > span { display: none !important; }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"] > div { flex: none; width: auto; }
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"] p { font-size: 0 !important; gap: 0; line-height: 1; }
    /* Página activa: barra de acento en el borde del riel en lugar del punto */
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"][data-selected="true"]::after {
        left: -14px; right: auto; top: 12px; bottom: 12px; transform: none;
        width: 3px; height: auto; border-radius: 0 3px 3px 0;
    }
    /* Contador de alertas: insignia en la esquina del cuadro, separada del icono */
    [data-testid="stSidebar"][data-collapsed="true"] [data-testid="stRadioOption"] p::after {
        position: absolute; top: 2px; right: 0; margin: 0 !important; min-width: 18px !important; height: 18px !important;
        font-size: 10.5px !important; padding: 0 5px !important; box-shadow: 0 0 0 2px var(--bg);
    }
    [data-testid="stSidebar"][data-collapsed="true"] .st-key-sb_salir { padding-left: 0; display: flex; justify-content: center; }
    [data-testid="stSidebar"][data-collapsed="true"] .st-key-sb_salir button p { font-size: 0 !important; }
    /* Estado del vigilante: icono de antena con el punto de color como insignia */
    .estado-mini { display: none; }
    [data-testid="stSidebar"][data-collapsed="true"] .st-key-sb_estado { left: 14px; right: 14px; bottom: 112px; }
    [data-testid="stSidebar"][data-collapsed="true"] .st-key-sb_tema { left: 14px; right: 14px; bottom: 60px; display: flex; justify-content: center; }
    [data-testid="stSidebar"][data-collapsed="true"] .tema-toggle { padding: 0; width: 48px; min-height: 42px; justify-content: center; }
    [data-testid="stSidebar"][data-collapsed="true"] .tema-toggle i { background: transparent !important; width: 44px; height: 38px; }
    :root:not([data-tema="claro"]) [data-testid="stSidebar"][data-collapsed="true"] .tema-toggle .t-sol,
    :root[data-tema="claro"] [data-testid="stSidebar"][data-collapsed="true"] .tema-toggle .t-luna { display: none; }
    /* Menú contraído: etiqueta con el nombre de cada icono al pasar el ratón (la crea el script del final) */
    .riel-tip {
        position: fixed; z-index: 1000100; left: 84px; transform: translateY(-50%); pointer-events: none; display: none;
        padding: 6px 10px; border-radius: 8px; font-size: 13px; font-weight: 600; white-space: nowrap;
        color: var(--text); background: var(--tip-bg); border: 1px solid var(--tip-border);
        box-shadow: 0 4px 14px rgba(0, 0, 0, .28);
    }
    .riel-tip.visible { display: block; }
    /* Fuera del riel la etiqueta solo la usa el tema */
    .riel-tip.junto { left: auto; transform: translate(-100%, -130%); }
    [data-testid="stSidebar"][data-collapsed="true"] .estado-card {
        position: relative; width: 48px; height: 48px; margin: 0 auto; padding: 0; border-radius: 12px;
        display: flex; align-items: center; justify-content: center; cursor: help;
    }
    [data-testid="stSidebar"][data-collapsed="true"] .estado-card b,
    [data-testid="stSidebar"][data-collapsed="true"] .estado-card span { display: none; }
    [data-testid="stSidebar"][data-collapsed="true"] .estado-mini { display: block; color: var(--muted); line-height: 0; }
    .estado-mini svg { width: 22px; height: 22px; }
    .estado-mini i {
        position: absolute; top: 7px; right: 7px; width: 10px; height: 10px; border-radius: 50%;
        box-shadow: 0 0 0 2px var(--bg);
    }
    /* Botón para expandir, en el mismo sitio que "Contraer" */
    [data-testid="stExpandSidebarButton"] {
        position: fixed !important; left: 0; bottom: 18px; width: 76px; margin: 0 !important; z-index: 1000060;
        display: flex !important; justify-content: center; color: var(--muted) !important;
    }
    [data-testid="stExpandSidebarButton"]:hover { color: var(--text) !important; }

    /* ---------- Encabezados ---------- */
    .header-title { font-size: 24px !important; font-weight: 700 !important; color: var(--text) !important; letter-spacing: -0.01em; }
    /* Ruta "Panel de monitoreo › Más gráficos": el primer tramo es un enlace de vuelta */
    .st-key-miga { flex-wrap: nowrap !important; }
    .st-key-miga_panel button {
        padding: 0 !important; min-height: 0 !important; color: var(--muted) !important; white-space: nowrap;
    }
    .st-key-miga_panel button p { font-size: 24px !important; font-weight: 700 !important; letter-spacing: -0.01em; }
    .st-key-miga_panel button:hover { color: var(--accent) !important; }
    .st-key-miga_panel button:hover p { text-decoration: underline; text-underline-offset: 5px; }
    .miga-actual { white-space: nowrap; }
    .miga-actual span { color: var(--muted); font-weight: 400; margin: 0 10px; }
    .header-sub { font-size: 13.5px !important; color: var(--muted) !important; margin-bottom: 15px !important; }
    .card-title { font-size: 16px; font-weight: 700; color: var(--text); line-height: 1.3; }
    .card-sub { font-size: 13.5px; color: var(--muted); margin-top: 3px; }
    .card-sub-ellipsis { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* ---------- Tarjetas (contenedores con borde) ---------- */
    div[class*="st-key-"][class*="_card"] {
        background-color: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 18px !important;
        padding: 18px 20px !important;
    }

    /* Tarjeta de la gráfica: ocupa el alto restante de la ventana y la gráfica se estira dentro,
       así el panel de inicio cabe en una sola pantalla sin desplazarse */
    /* Inicio en una sola pantalla: --alto-panel es lo que queda tras márgenes, encabezado y pie de página.
       El carrusel ocupa ese alto; a la izquierda la gráfica toma lo que dejan las tarjetas (2 filas de 82px) */
    :root { --alto-panel: max(560px, calc(100vh - 105px)); }
    [data-testid="stLayoutWrapper"]:has(> div[class*="_card_grafica"]) { height: calc(var(--alto-panel) - 186px); min-height: 0; }
    div[class*="_graf_opciones"] [data-testid="stPopoverButton"] { border-radius: 50% !important; width: 36px; min-height: 36px; padding: 0 !important; }
    div[class*="_graf_opciones"] [data-testid="stPopoverButton"] > div > div:last-child { display: none; }
    div[class*="_gm_acciones"] [data-testid="stPopoverButton"] { border-radius: 50% !important; width: 40px; min-height: 40px; padding: 0 !important; }
    div[class*="_gm_acciones"] [data-testid="stPopoverButton"] > div > div:last-child { display: none; }
    div[class*="_card_grafica"] > [data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]) { flex: 1 1 0; min-height: 0; }
    /* Gráfica ampliada: alto según la ventana para que la gráfica y la tabla quepan sin desplazarse */
    [data-testid="stLayoutWrapper"]:has(> div.st-key-amp_grafica) { height: max(300px, calc(100vh - 236px)); }
    .st-key-amp_grafica { height: 100%; }
    .st-key-amp_grafica > [data-testid="stElementContainer"] { flex: 1 1 0; min-height: 0; }

    /* ---------- Tarjetas KPI ---------- */
    .kpi-card {
        display: flex; align-items: center; gap: 16px;
        background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
        padding: 18px 18px;
    }
    .kpi-icon {
        flex: none; width: 46px; height: 46px; border-radius: 12px;
        background: var(--accent-soft); color: var(--accent);
        display: flex; align-items: center; justify-content: center;
    }
    .kpi-icon svg { width: 22px; height: 22px; }
    .kpi-card > div:last-child { min-width: 0; }
    .kpi-label { font-size: 14px; color: var(--muted); }
    .kpi-value { font-size: 21px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .kpi-delta { font-size: 12.5px; font-weight: 600; padding: 2px 6px; border-radius: 5px; }
    .kpi-delta.down { color: var(--danger); background: var(--danger-soft); }
    .kpi-delta.up { color: var(--ok); background: var(--ok-soft); }
    /* Panel de inicio: 6 tarjetas en 3 columnas */
    .kpi-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
    .kpi-grid .kpi-value { white-space: nowrap; flex-wrap: nowrap; }
    .kpi-grid { grid-auto-rows: 82px; }
    .kpi-grid .kpi-card { padding: 10px 16px; gap: 14px; }
    .kpi-grid .kpi-icon { width: 42px; height: 42px; }
    .kpi-grid .kpi-value { font-size: 19px; }
    .kpi-par { display: flex; align-items: center; gap: 10px; flex-wrap: nowrap; }
    .kpi-par > div { display: flex; flex-direction: column; line-height: 1.15; }
    .kpi-par b { font-size: 17px; white-space: nowrap; }
    .kpi-par small { font-size: 11.5px; font-weight: 500; color: var(--muted); margin-top: 2px; }
    .kpi-par > div:first-child b { color: var(--text-2); }
    .kpi-par .up b, .kpi-flecha.up { color: var(--ok); }
    .kpi-par .down b, .kpi-flecha.down { color: var(--danger); }
    .kpi-flecha { font-size: 15px; color: var(--muted); }
    /* Rango del área (mínimo ↔ máximo): va en la columna estrecha, con algo menos de tamaño */
    .kpi-rango { gap: 7px; }
    .kpi-rango b { font-size: 15.5px; }
    /* Tarjeta estrecha: "46.833 ↔ 106.713" con la unidad en el título, para que el máximo no se corte */
    .kpi-grid .kpi-card { container-type: inline-size; }
    .kpi-card .u-etq { display: none; }
    @container (max-width: 280px) {
        .kpi-rango { gap: 5px; }
        .kpi-rango b { font-size: 14.5px; }
        .kpi-rango .u-num { display: none; }
        .kpi-card .u-etq { display: inline; }
    }
    /* "● ahora" en las tarjetas de estado actual y el periodo bajo las estadísticas */
    .kpi-ahora { display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; font-size: 11.5px; font-weight: 600; color: var(--ok); }
    .kpi-ahora i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    /* Última captura vieja: ámbar pasado el plazo de "sin capturas" de las alertas, rojo mucho después */
    .kpi-ahora.aviso { color: var(--warn); }
    .kpi-ahora.alerta { color: var(--danger); }
    .kpi-delta:not(.up):not(.down) { color: var(--muted); background: var(--surface-2); }
    .kpi-periodo { font-size: 11.5px; font-weight: 500; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi-periodo.vivo { color: var(--ok); }
    .kpi-periodo .kpi-ahora { margin-left: 0; }
    .kpi-hora-pie { font-size: 13px; font-weight: 600; color: var(--text-2); margin-right: 8px; }
    .kpi-periodo.filtro { color: var(--warn); }
    .kpi-hora { font-size: 15px; font-weight: 600; color: var(--muted); padding-left: 8px; margin-left: 2px; border-left: 1px solid var(--border); }
    .kpi-sw { width: 20px; height: 20px; border-radius: 6px; display: inline-block; flex: none; border: 1px solid var(--sw-border); }
    @media (max-width: 1500px) {
        .kpi-grid .kpi-icon { display: none; }
        .kpi-grid .kpi-value { font-size: 17px; }
        .kpi-par b { font-size: 15px; }
    }

    /* ---------- Botones ---------- */
    [data-testid="stBaseButton-secondary"], [data-testid="stDownloadButton"] button:not([data-testid="stBaseButton-primary"]), [data-testid="stPopoverButton"] {
        background-color: transparent !important; border: 1px solid var(--border) !important;
        color: var(--text) !important; border-radius: 12px !important; min-height: 40px;
    }
    [data-testid="stBaseButton-secondary"]:hover, [data-testid="stDownloadButton"] button:not([data-testid="stBaseButton-primary"]):hover, [data-testid="stPopoverButton"]:hover {
        border-color: var(--accent) !important; color: var(--accent) !important;
    }
    [data-testid="stBaseButton-primary"] { color: var(--accent-ink) !important; font-weight: 600 !important; border-radius: 12px !important; }
    [data-testid="stBaseButton-primary"]:disabled {
        background: var(--surface-2) !important; border-color: var(--border) !important; color: var(--muted) !important; opacity: 1 !important;
    }
    [data-testid="stBaseButton-primary"]:disabled p { color: var(--muted) !important; }
    [data-testid="stDownloadButton"] button p { font-size: 15.5px !important; font-weight: 600; }

    /* Selectores segmentados (Ambos/Automático/Manual, Días/Meses/Años, Original/Procesada) */
    [data-testid="stButtonGroup"] [role="radiogroup"] {
        background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 3px; gap: 2px;
        flex-wrap: nowrap !important;
    }
    [data-testid="stButtonGroup"] button {
        border: none !important; background: transparent !important; color: var(--muted) !important;
        border-radius: 9px !important; min-height: 34px; padding: 0 14px !important; box-shadow: none !important;
    }
    [data-testid="stButtonGroup"] button p { font-size: 15px; }
    [data-testid="stButtonGroup"] button[aria-checked="true"] { background: var(--surface-2) !important; color: var(--text) !important; }
    [data-testid="stButtonGroup"] button[aria-checked="true"] p { font-weight: 600; }
    .st-key-inicio_modo button p { font-size: 16px; }
    .st-key-inicio_modo button { min-height: 38px; }

    /* Fila de filtros de la gráfica: chips redondeados */
    div[class*="_filtros"] [data-testid="stBaseButton-secondary"],
    div[class*="_filtros"] [data-testid="stBaseButton-primary"] { border-radius: 999px !important; min-height: 36px; padding: 0 14px !important; }
    div[class*="_filtros"] [data-testid="stPopoverButton"] { border-radius: 50% !important; width: 36px; min-height: 36px; padding: 0 !important; }
    div[class*="_filtros"] [data-testid="stPopoverButton"] > div > div:last-child { display: none; }
    div[class*="_btn_reset"] button { border: none !important; padding: 0 6px !important; }

    /* ---------- Visor de la laguna ---------- */
    .visor-contador { text-align: center; font-size: 14px; font-weight: 700; margin: 0; color: var(--text); }
    div[class*="_vlaguna_nav"] { flex-wrap: nowrap !important; }
    div[class*="_vlaguna_nav"] button { border-radius: 50% !important; width: 36px; min-height: 36px; padding: 0 !important; }
    /* Carrusel del inicio (HTML propio en visor_laguna.py), a toda la altura disponible */
    [data-testid="stLayoutWrapper"]:has(> div[class*="_vlaguna_card"]) { height: var(--alto-panel); }
    div[class*="_vlaguna_card"] { height: 100%; overflow: hidden; }
    div[class*="_vlaguna_card"] > [data-testid="stElementContainer"]:has(.vl) { flex: 1 1 0; min-height: 0; }
    div[class*="_vlaguna_card"] [data-testid="stHtml"]:has(.vl) { height: 100%; }
    .vl { height: 100%; }
    .vl { display: flex; flex-direction: column; gap: 12px; }
    .vl-nav { display: flex; align-items: center; gap: 8px; }
    .vl-cont { font-size: 14px; font-weight: 700; color: var(--text); min-width: 42px; text-align: center; }
    .vl-btn {
        width: 36px; height: 36px; border-radius: 50%; border: 1px solid var(--border); background: transparent;
        color: var(--text); display: inline-flex; align-items: center; justify-content: center; cursor: pointer; padding: 0;
        transition: border-color .15s, color .15s;
    }
    .vl-btn:hover { border-color: var(--accent); color: var(--accent); }
    .vl-btn svg { width: 18px; height: 18px; }
    .vl-btn-exp { margin-left: auto; border-radius: 10px; }
    .vl-seg { display: flex; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 3px; gap: 2px; }
    .vl-seg button {
        flex: 1 1 0; border: none; background: transparent; color: var(--muted); border-radius: 9px; min-height: 34px;
        font: inherit; font-size: 14.5px; cursor: pointer;
    }
    .vl-seg button.on { background: var(--surface-2); color: var(--text); font-weight: 600; }
    .vl-foto { position: relative; border-radius: 12px; overflow: hidden; cursor: zoom-in; background: var(--bg); }
    .vl-foto { flex: 1 1 0; min-height: 120px; }
    .vl-foto img { display: block; width: 100%; height: 100%; object-fit: cover; transition: transform .25s; }
    .vl-foto:hover img { transform: scale(1.02); }
    .vl-barra { position: absolute; left: 0; bottom: 0; height: 3px; width: 0; background: var(--accent); opacity: .85;
                transition: width .25s linear; }
    @keyframes vl-avance { from { width: 0; } to { width: 100%; } }
    /* Área, confianza y color en una fila; fecha y hora a todo el ancho debajo para que se lea completa */
    .vl-met { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .75fr) minmax(0, 1.2fr); border: 1px solid var(--border); border-radius: 12px; }
    .vl-met > div { padding: 9px 10px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .vl-met > div + div { border-left: 1px solid var(--border); }
    .vl-met > div:nth-child(4) { grid-column: 1 / -1; border-left: none; border-top: 1px solid var(--border); }
    .vl-met span { font-size: 12.5px; color: var(--muted); }
    .vl-met b { font-size: 14.5px; color: var(--text); display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .vl-sw { width: 16px; height: 16px; border-radius: 5px; flex: none; border: 1px solid var(--sw-border); }
    .vl-thumbs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .vl-thumbs button { padding: 0; border: none; background: none; cursor: pointer; border-radius: 10px; overflow: hidden; }
    .vl-thumbs img { display: block; width: 100%; height: 58px; object-fit: cover; border-radius: 10px; opacity: .8; transition: opacity .15s; }
    .vl-thumbs button:hover img { opacity: 1; outline: 2px solid var(--accent); outline-offset: -2px; }
    #vl-modal {
        position: fixed; inset: 0; z-index: 1000200; background: rgba(5, 8, 11, .82); backdrop-filter: blur(3px);
        display: none; align-items: center; justify-content: center; padding: 24px;
    }
    #vl-modal.abierto { display: flex; }
    .vl-modal-caja {
        background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 16px;
        width: min(1200px, 100%); display: flex; flex-direction: column; gap: 12px;
    }
    .vl-modal-cab { display: flex; gap: 12px; align-items: center; }
    .vl-modal-nav { display: flex; align-items: center; gap: 6px; }
    .vl-modal-cab .vl-seg { flex: 1; max-width: 420px; }
    .vl-modal-cab .vl-btn { margin-left: auto; }
    .vl-modal-caja > img { width: 100%; max-height: 70vh; object-fit: contain; border-radius: 12px; background: var(--bg); }
    .vl-met-modal { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .vl-met-modal > div:nth-child(n) { grid-column: auto; border-top: none; border-left: 1px solid var(--border); }
    .vl-met-modal > div:first-child { border-left: none; }
    /* Interruptor de tema de la barra lateral: sol y luna, la opción activa resaltada */
    .tema-toggle {
        display: inline-flex; gap: 2px; padding: 3px; cursor: pointer; border-radius: 12px;
        background: var(--surface); border: 1px solid var(--border); min-height: 40px; align-items: center;
    }
    .tema-toggle i {
        width: 38px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; color: var(--muted);
    }
    .tema-toggle i::before {
        content: ""; width: 18px; height: 18px; background: currentColor;
        -webkit-mask: var(--ico) center / contain no-repeat; mask: var(--ico) center / contain no-repeat;
    }
    .tema-toggle .t-sol { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='12' cy='12' r='4'/%3E%3Cpath d='M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41'/%3E%3C/svg%3E"); }
    .tema-toggle .t-luna { --ico: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z'/%3E%3C/svg%3E"); }
    :root:not([data-tema="claro"]) .tema-toggle .t-luna,
    :root[data-tema="claro"] .tema-toggle .t-sol { background: var(--surface-2); color: var(--accent); }
    .tema-toggle:hover { border-color: var(--accent); }
    /* Subpestaña "Otros tipos de gráfico": tarjetas que se reordenan arrastrando el asa */
    .gm-cab { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .gm-asa {
        flex: none; width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
        color: var(--muted); cursor: grab; border: 1px solid transparent; transition: color .15s, border-color .15s;
    }
    .gm-asa:hover { color: var(--accent); border-color: var(--border); }
    .gm-asa:active { cursor: grabbing; }
    .gm-asa svg { width: 18px; height: 18px; pointer-events: none; }
    div[class*="_gm_"][class*="_card"] { transition: opacity .15s, box-shadow .15s; }
    div[class*="_gm_"].gm-arrastrando { opacity: .4; }
    div[class*="_gm_"].gm-sobre { box-shadow: 0 0 0 2px var(--accent); }
    div[class*="_graf_opciones"] [data-testid="stButton"] button { border-radius: 50% !important; width: 36px; min-height: 36px; padding: 0 !important; }
    /* Filtro "En vivo": punto que late */
    .en-vivo { display: inline-flex; align-items: center; gap: 8px; font-size: 13.5px; color: var(--muted); white-space: nowrap; }
    .en-vivo i { width: 9px; height: 9px; border-radius: 50%; background: var(--ok); animation: en-vivo 1.6s ease-out infinite; }
    @keyframes en-vivo { 0% { box-shadow: 0 0 0 0 rgba(47, 210, 122, .55); } 100% { box-shadow: 0 0 0 9px rgba(47, 210, 122, 0); } }
    div[class*="_btn_cal"] button { border-radius: 999px !important; min-height: 36px; padding: 0 12px !important; }
    /* Fila de filtros en una sola línea: En vivo/Días/Meses/Años, ventanas, calendario y restablecer */
    div[class*="_filtros"] { flex-wrap: nowrap !important; }
    div[class*="_filtros"] [data-testid="stButtonGroup"] button { padding: 0 11px !important; }
    div[class*="_filtros"] [data-testid="stBaseButton-secondary"],
    div[class*="_filtros"] [data-testid="stBaseButton-primary"] { padding: 0 12px !important; }

    /* Calendario del filtro (ventana "Elegir periodo") */
    .cal-ayuda { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .cal-ayuda b { color: var(--text); }
    .cal-ayuda { min-height: 26px; padding: 3px 0; line-height: 20px; }
    .cal-aviso { color: var(--warn); background: rgba(245, 167, 66, .12); border-radius: 8px; padding: 3px 10px; }
    /* Ventana del calendario compacta: cabe entera en pantalla sin barra de desplazamiento */
    [data-testid="stDialog"]:has(.cal-ayuda) [data-testid="stVerticalBlock"] { gap: 6px; }
    [data-testid="stDialog"]:has(.cal-ayuda) [data-testid="stButtonGroup"] button { min-height: 32px; }
    [data-testid="stDialog"] div[class*="st-key-cal_d_"] button { min-height: 34px; }
    [data-testid="stMarkdownContainer"]:has(.cal-ayuda, .cal-semana, .cal-titulo) { margin-bottom: 0 !important; }
    .cal-semana { text-align: center; font-size: 12.5px; font-weight: 600; color: var(--muted); }
    .cal-titulo { font-size: 17px; font-weight: 700; color: var(--text); min-width: 120px; text-align: center; }
    .cal-punto, div[class*="st-key-cal_"][class*="_con_"] button::after {
        content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); display: inline-block;
    }
    div[class*="st-key-cal_d_"] button, div[class*="st-key-cal_m_"] button, div[class*="st-key-cal_a_"] button {
        position: relative; min-height: 40px; padding: 0 !important; border-radius: 10px !important;
    }
    div[class*="st-key-cal_"][class*="_con_"] button::after { position: absolute; bottom: 5px; left: 50%; transform: translateX(-50%); }
    div[class*="st-key-cal_d_"][class*="_f_"] button { opacity: .38; }
    .st-key-cal_nav, .st-key-cal_nav_m, .st-key-cal_nav_a { flex-wrap: nowrap !important; }
    .st-key-cal_nav [data-testid="stButton"] button, .st-key-cal_nav_m button, .st-key-cal_nav_a button {
        border-radius: 50% !important; width: 38px; min-height: 38px; padding: 0 !important;
    }
    [data-testid="stDialog"] [data-testid="stHorizontalBlock"] { gap: 6px !important; }

    /* Galería de fotos: 3 columnas a todo el ancho; la foto entera es clicable (botón invisible encima)
       y lleva sus datos encima */
    div[class*="st-key-galeria_gfoto_"] { position: relative; border-radius: 12px; overflow: hidden; }
    /* La cuadrícula se desplaza dentro de su caja */
    .st-key-galeria_grilla {
        max-height: calc(100vh - 250px); overflow-y: auto; overflow-x: hidden; padding-right: 4px;
        scroll-snap-type: y mandatory;
    }
    /* Al desplazarse avanza fila a fila, sin dejar fotos cortadas */
    .st-key-galeria_grilla [data-testid="stHorizontalBlock"] { scroll-snap-align: start; }
    /* Cada foto (16:9) se limita para que quepan 2 filas enteras en el alto de la cuadrícula */
    [data-testid="stLayoutWrapper"] > div.stVerticalBlock[class*="st-key-galeria_gfoto_"] {
        width: min(100%, calc((100vh - 290px) / 2 * 16 / 9)) !important; margin: 0 auto;
    }
    div[class*="st-key-galeria_gfoto_"],
    div[class*="st-key-galeria_gfoto_"] [data-testid="stFullScreenFrame"],
    div[class*="st-key-galeria_gfoto_"] [data-testid="stFullScreenFrame"] > div,
    div[class*="st-key-galeria_gfoto_"] [data-testid="stImage"],
    div[class*="st-key-galeria_gfoto_"] [data-testid="stImageContainer"] { width: 100% !important; }
    div[class*="st-key-galeria_gfoto_"] [data-testid="stImage"] img {
        /* Fotos de la cámara en 16:9: la tarjeta coincide con la foto y los datos quedan sobre ella */
        aspect-ratio: 16 / 9; height: auto !important; width: 100% !important; object-fit: cover;
        display: block; background: var(--bg); border-radius: 12px;
    }
    /* Datos siempre visibles sobre la parte baja de la foto */
    div[class*="st-key-galeria_gfoto_"] [data-testid="stElementContainer"]:has(.gal-datos) {
        position: absolute !important; left: 0; right: 0; bottom: 0; z-index: 1; pointer-events: none; width: 100% !important;
    }
    .gal-datos {
        display: flex; align-items: flex-end; flex-wrap: nowrap; gap: 10px; padding: 28px 14px 10px; white-space: nowrap;
        color: #fff; font-size: 13px; text-shadow: 0 1px 2px rgba(0, 0, 0, .6);
        background: linear-gradient(to top, rgba(5, 8, 11, .88), rgba(5, 8, 11, 0)); border-radius: 0 0 12px 12px;
    }
    .gal-datos b { font-size: 16px; margin-right: auto; }
    /* Captura cuya foto ya no está en el disco: ocupa lo mismo que una foto */
    .gal-sin-foto {
        display: flex; align-items: center; justify-content: center; aspect-ratio: 16 / 9; font-size: 13px;
        color: var(--muted); background: var(--bg); border: 1px dashed var(--border); border-radius: 12px;
    }
    [data-testid="stMarkdownContainer"]:has(.gal-sin-foto) { margin-bottom: 0 !important; }
    .st-key-visual_galeria_card .gal-sin-foto { aspect-ratio: auto; height: var(--alto-foto); }
    /* Foto pequeña (p. ej. con el panel de comparar abierto): solo área y fecha, para que no se corten */
    div[class*="st-key-galeria_gfoto_"] { container-type: inline-size; }
    @container (max-width: 330px) {
        .gal-datos { font-size: 12px; gap: 8px; padding: 22px 10px 8px; }
        .gal-datos b { font-size: 14px; }
        .gal-datos span:not(.gal-orden) ~ span { display: none; }
        .gal-datos span:not(.gal-orden) { min-width: 0; overflow: hidden; text-overflow: ellipsis; display: block; }
    }
    .gal-datos span { display: inline-flex; align-items: center; gap: 6px; }
    div[class*="st-key-galeria_gfoto_"]:hover img { outline: 2px solid var(--accent); outline-offset: -2px; }
    [data-testid="stMarkdownContainer"]:has(.gal-datos) { margin-bottom: 0 !important; }
    div[class*="st-key-galeria_gfoto_"] [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
        position: absolute !important; inset: 0; z-index: 2; opacity: 0; width: 100% !important;
    }
    div[class*="st-key-galeria_gfoto_"] [data-testid="stButton"],
    div[class*="st-key-galeria_gfoto_"] [data-testid="stButton"] > *,
    div[class*="st-key-galeria_gfoto_"] [data-testid="stButton"] button { width: 100% !important; height: 100% !important; min-height: 100%; }
    /* Encabezado de la galería: chip En vivo / Filtro y el número de capturas con sus fechas */
    .gal-titulo { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; font-size: 14px; color: var(--muted); }
    .gal-chip {
        display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px;
        font-size: 12.5px; font-weight: 700;
    }
    .gal-chip.vivo { color: var(--ok); background: var(--ok-soft); }
    .gal-chip.filtro { color: var(--warn); background: rgba(245, 167, 66, .14); }
    .gal-chip i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
    .gal-pag { margin: 0 6px; font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; }
    [data-testid="stMarkdownContainer"]:has(.gal-pag) { margin-bottom: 0 !important; }
    /* La galería usa casi todo el ancho de la ventana */
    [data-testid="stDialog"] div:has(> [role="dialog"] .st-key-galeria_grilla) { width: min(96vw, 1700px) !important; margin: auto !important; }
    /* Foto abierta: mismo tamaño y forma que la ampliación del carrusel (#vl-modal): caja de 1200 px, sin título
       y con la X redonda en la fila de las flechas */
    [data-testid="stDialog"] div:has(> [role="dialog"] .st-key-galeria_barra) {
        width: min(1200px, calc(100vw - 48px)) !important; margin: auto !important;
        background: var(--surface) !important; border: 1px solid var(--border); border-radius: 18px !important;
    }
    [role="dialog"]:has(.st-key-galeria_barra) > h2 { display: none; }
    [role="dialog"]:has(.st-key-galeria_barra) > div { padding: 16px !important; }
    [role="dialog"]:has(.st-key-galeria_barra) > button {
        top: 16px !important; right: 16px !important; width: 40px; height: 40px; border-radius: 50%;
        border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; z-index: 2;
    }
    [role="dialog"]:has(.st-key-galeria_barra) > button:hover { border-color: var(--accent); color: var(--accent); }
    /* ...y queda centrada en vertical entre el borde de arriba y el pie de página, que sigue visible */
    [data-testid="stDialog"]:has(.st-key-galeria_grilla), [data-testid="stDialog"]:has(.st-key-galeria_barra) {
        padding: 12px 0 44px !important;
    }
    /* Paginador de la cuadrícula en una cápsula: ‹ 1 / 3 › */
    .st-key-galeria_pager {
        border: 1px solid var(--border); border-radius: 999px; background: var(--surface); padding: 2px; flex: 0 0 auto;
    }
    .st-key-galeria_pager button {
        width: 32px; height: 32px; min-height: 32px !important; padding: 0 !important; border-radius: 50% !important;
    }
    .st-key-galeria_pager button:not(:disabled):hover { background: var(--accent-soft) !important; color: var(--accent) !important; }
    /* Foto abierta, igual que la ampliación del carrusel: ‹ 6/9 › y Original / Procesada arriba, la foto y sus datos */
    .st-key-galeria_barra { flex-wrap: nowrap !important; padding-right: 52px; }
    .st-key-galeria_extra { flex: 0 0 auto; flex-wrap: nowrap !important; }
    [data-testid="stMarkdownContainer"]:has(.chip-almacenada) p { margin: 0; }
    .st-key-galeria_nav { flex: 0 0 auto; }
    .st-key-galeria_nav button {
        width: 40px; height: 40px; min-height: 40px !important; padding: 0 !important; border-radius: 50% !important;
    }
    .st-key-galeria_barra [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) { max-width: 520px; }
    .st-key-galeria_foto_grande [data-testid="stFullScreenFrame"],
    .st-key-galeria_foto_grande [data-testid="stFullScreenFrame"] > div,
    .st-key-galeria_foto_grande [data-testid="stImage"],
    .st-key-galeria_foto_grande [data-testid="stImageContainer"] { width: 100% !important; }
    .st-key-galeria_foto_grande [data-testid="stImage"] img {
        display: block; width: 100% !important; aspect-ratio: 16 / 9; height: auto !important;
        max-height: min(70vh, calc(100vh - 230px)); object-fit: contain; background: var(--bg); border-radius: 12px;
    }
    /* Comparar: las fotos elegidas llevan borde y su número (1 y 2) */
    .gal-chip.comparar { color: var(--accent); background: var(--accent-soft); }
    div[class*="st-key-galeria_gfoto_"][class*="_elegida"] img { outline: 3px solid var(--accent) !important; outline-offset: -3px; }
    .gal-datos .gal-orden {
        flex: none; width: 24px; height: 24px; border-radius: 50%; justify-content: center; text-shadow: none;
        font-weight: 800; font-size: 13px; background: var(--accent); color: var(--accent-ink);
    }
    /* Antes / después: con "Deslizador" las dos fotos se superponen y la línea muestra una u otra;
       con "Lado a lado", una junto a la otra */
    .cmp { position: relative; display: grid; border-radius: 12px; overflow: hidden; background: var(--bg); --pos: 50%; }
    /* El deslizador mide lo mismo que la foto (16:9 al alto disponible): etiquetas y línea quedan sobre ella */
    .cmp.deslizar { width: min(100%, calc(min(66vh, 100vh - 250px) * 16 / 9)); margin: 0 auto; }
    .cmp img {
        display: block; width: 100%; aspect-ratio: 16 / 9; max-height: min(66vh, calc(100vh - 250px));
        object-fit: contain; -webkit-user-drag: none; user-select: none;
    }
    .cmp-lado { position: relative; min-width: 0; }
    .cmp-et {
        position: absolute; top: 26px; left: 10px; padding: 3px 10px; border-radius: 999px; white-space: nowrap;
        font-size: 12.5px; font-weight: 700; color: #fff; background: rgba(5, 8, 11, .72);
    }
    .cmp.deslizar .cmp-lado { grid-area: 1 / 1; }
    .cmp.deslizar .cmp-b { clip-path: inset(0 0 0 var(--pos)); }
    .cmp.deslizar .cmp-b .cmp-et { left: auto; right: 10px; }
    .cmp-linea {
        position: absolute; top: 0; bottom: 0; left: var(--pos); width: 2px; margin-left: -1px;
        background: #fff; box-shadow: 0 0 6px rgba(0, 0, 0, .5); pointer-events: none;
    }
    .cmp-linea i {
        position: absolute; top: 50%; left: 50%; width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%;
        background: #fff; box-shadow: 0 1px 6px rgba(0, 0, 0, .45);
    }
    .cmp-linea i::before, .cmp-linea i::after {
        content: ""; position: absolute; top: 50%; width: 0; height: 0; margin-top: -5px;
        border: 5px solid transparent;
    }
    .cmp-linea i::before { left: 5px; border-right: 6px solid #12171e; border-left: 0; }
    .cmp-linea i::after { right: 5px; border-left: 6px solid #12171e; border-right: 0; }
    .cmp input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: ew-resize; }
    .cmp.lado { grid-template-columns: 1fr 1fr; gap: 8px; background: transparent; }
    .cmp.lado img { background: var(--bg); border-radius: 12px; }
    .cmp.lado .cmp-linea, .cmp.lado input { display: none; }
    /* Comparar: una sola línea "Antes [día] [captura] → Después [día] [captura] [Comparar]" y atajos en texto */
    .st-key-galeria_cmp_fechas { gap: 2px; padding: 2px 0 4px; }
    .st-key-galeria_cmp_fila { flex-wrap: wrap !important; row-gap: 6px !important; }
    .st-key-galeria_cmp_fila [data-testid="stPopoverButton"] button,
    .st-key-galeria_cmp_fila [data-testid="stPopoverButton"] { min-height: 38px; white-space: nowrap; }
    .cmp-lbl { font-size: 12.5px; font-weight: 700; color: var(--muted); }
    .cmp-flecha { font-size: 16px; color: var(--muted); margin: 0 4px; }
    .cmp-atajos-tit { font-size: 12.5px; color: var(--muted); margin-right: 4px; }
    .st-key-galeria_cmp_atajos { flex-wrap: wrap !important; }
    .st-key-galeria_cmp_atajos button { min-height: 26px !important; padding: 0 8px !important; }
    .st-key-galeria_cmp_atajos button p { font-size: 12.5px !important; color: var(--accent); }
    .cmp-sel-aviso { margin: 0; font-size: 12px; color: var(--warn); }
    /* Carrusel sin fotos: el mismo aviso gris centrado que la gráfica */
    div[class*="_vlaguna_card"]:has(.graf-vacio) { justify-content: center; }
    .st-key-galeria_barra .st-key-galeria_cmp_volver button { white-space: nowrap; }
    [data-testid="stMarkdownContainer"]:has(.cmp-lbl, .cmp-flecha, .cmp-atajos-tit, .cmp-sel-aviso) { margin-bottom: 0 !important; }
    [data-testid="stElementContainer"]:has(.cmp-lbl, .cmp-flecha, .cmp-atajos-tit) { align-self: center; }
    [data-testid="stMarkdownContainer"]:has(.cmp-lbl, .cmp-flecha, .cmp-atajos-tit) p { margin: 0; line-height: 1; }
    [role="dialog"]:has(.st-key-galeria_cmp_fechas) .st-key-galeria_grilla { max-height: calc(100vh - 330px); }
    [role="dialog"]:has(.st-key-galeria_cmp_fechas) [data-testid="stLayoutWrapper"] > div.stVerticalBlock[class*="st-key-galeria_gfoto_"] {
        width: min(100%, calc((100vh - 370px) / 2 * 16 / 9)) !important;
    }
    /* Calendario pequeño dentro del menú del día (galería y comparar): 7 columnas compactas, sin recuadros
       en los días; los que tienen capturas llevan el punto y el elegido va en el color de acento */
    [data-testid="stPopoverBody"]:has(div[class*="st-key-galeria_cmp_calendario_"]) { min-width: 296px; width: 296px; padding: 10px !important; }
    div[class*="st-key-galeria_cmp_calendario_"] { gap: 2px; }
    div[class*="st-key-galeria_cmp_calendario_"] [data-testid="stHorizontalBlock"] { gap: 0 !important; }
    div[class*="st-key-galeria_cmp_calnav_"] { flex-wrap: nowrap !important; margin-bottom: 4px; }
    div[class*="st-key-galeria_cmp_calnav_"] button { width: 28px; height: 28px; min-height: 28px !important; padding: 0 !important; border-radius: 50% !important; }
    div[class*="st-key-galeria_cmp_calendario_"] .cal-titulo { font-size: 14px; min-width: 0; }
    div[class*="st-key-galeria_cmp_calendario_"] .cal-semana { font-size: 11px; }
    div[class*="st-key-galeria_cmp_calendario_"] div[class*="st-key-cal_d_"] button {
        min-height: 34px !important; height: 34px; border-radius: 50% !important; font-size: 13px;
    }
    div[class*="st-key-galeria_cmp_calendario_"] div[class*="st-key-cal_d_"] button p { font-size: 13px; }
    div[class*="st-key-galeria_cmp_calendario_"] div[class*="st-key-cal_"][class*="_con_"] button::after { bottom: 3px; width: 4px; height: 4px; }
    div[class*="st-key-galeria_cmp_calendario_"] div[class*="st-key-cal_d_con"] button:hover { background: var(--accent-soft) !important; }
    /* Días, meses y años sin capturas: apagados y sin poder pulsarse (en el filtro, la galería y al comparar) */
    div[class*="st-key-cal_"][class*="_sin_"] button:disabled { opacity: .3; cursor: not-allowed; }
    .cmp-met b.cmp-up { color: var(--ok); }
    .cmp-met b.cmp-down { color: var(--danger); }

    /* Pie de página */
    /* Pie de página: una sola línea fina y centrada */
    .pie-pagina {
        display: flex; justify-content: center; gap: 14px; padding: 3px 4px 0; line-height: 1.3;
        border-top: 1px solid var(--border); font-size: 11px; color: var(--muted);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .pie-pagina span + span::before { content: "·"; margin-right: 14px; opacity: .6; }
    .pie-pagina b { color: var(--text-2); font-weight: 500; }
    [data-testid="stElementContainer"]:has(.pie-pagina) { margin-top: -6px; }
    .pie-pagina a { color: var(--accent); text-decoration: none; }
    .pie-pagina a:hover { text-decoration: underline; }
    [data-testid="stMarkdownContainer"]:has(.pie-pagina) { margin-bottom: 0 !important; }

    /* Carrusel compacto: Original/Procesada junto a las flechas, fecha sobre la foto, datos en una fila */
    .vl { gap: 10px; }
    .vl-seg-nav { flex: 1; min-width: 0; padding: 2px; }
    .vl-seg-nav button { min-height: 30px; font-size: 13.5px; padding: 0 6px; white-space: nowrap; }
    .vl-btn-exp { margin-left: 0; }
    /* Pie de la foto: fecha y botón de pausa del carrusel */
    .vl-foto-pie { position: absolute; left: 10px; right: 10px; bottom: 12px; display: flex; align-items: center; gap: 8px; }
    .vl-fecha, .vl-pausa {
        padding: 3px 9px; border-radius: 8px; background: rgba(8, 11, 15, .62); color: #fff;
        font-size: 12.5px; font-weight: 600; backdrop-filter: blur(2px);
    }
    .vl-fecha { pointer-events: none; }
    .vl-pausa { margin-left: auto; border: 1px solid rgba(255, 255, 255, .18); cursor: pointer; font-family: inherit; }
    .vl-pausa:hover { background: rgba(8, 11, 15, .82); border-color: var(--accent); }
    .vl-pausa > span { display: inline-flex; align-items: center; gap: 6px; }
    .vl-pausa svg { width: 13px; height: 13px; fill: currentColor; stroke: none; }
    .vl-ico-play, .vl.pausado .vl-ico-pausa { display: none !important; }
    .vl.pausado .vl-ico-play { display: inline-flex !important; }
    .vl.pausado .vl-pausa { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
    .vl.pausado .vl-barra { background: var(--muted); }
    .vl-met-corta { grid-template-columns: minmax(0, 1.15fr) minmax(0, .8fr) minmax(0, 1.2fr); }
    .vl-met-corta > div { padding: 6px 10px; }
    .vl-met-corta > div:nth-child(n) { grid-column: auto; border-top: none; }
    .vl-met-corta > div + div { border-left: 1px solid var(--border); }
    .vl-met-corta span { font-size: 11.5px; }
    .vl-met-corta b { font-size: 14px; }
    .vl-thumbs img { height: 50px !important; }
    div[class*="_vlaguna_card"] [data-testid="stButton"] button { min-height: 34px; }
    div[class*="_vlaguna_card"] [data-testid="stButton"] button p { font-size: 14px; }

    /* Aviso de filtro: etiqueta en el subtítulo y cartel mientras la gráfica se recalcula */
    .filtro-badge {
        display: inline-block; padding: 1px 8px; margin-right: 4px; border-radius: 6px; font-size: 12px; font-weight: 600;
        color: var(--warn); background: rgba(245, 167, 66, .14); border: 1px solid rgba(245, 167, 66, .35);
    }
    .filtro-badge.vivo { color: var(--ok); background: var(--ok-soft); border-color: transparent; }
    div[class*="_card_grafica"] { position: relative; }
    div[class*="_card_grafica"]:has([data-stale="true"] [data-testid="stPlotlyChart"])::after {
        content: "Actualizando datos…"; position: absolute; left: 50%; top: 52%; transform: translate(-50%, -50%);
        padding: 8px 16px; border-radius: 10px; font-size: 13.5px; font-weight: 600; z-index: 5;
        background: var(--surface-2); color: var(--text); border: 1px solid var(--accent);
        box-shadow: 0 6px 20px rgba(0, 0, 0, .25);
    }
    /* "Ver los mismos datos en otros tipos de gráfico": enlace discreto al pie de la gráfica */
    /* Va en la esquina inferior derecha de la tarjeta, a la altura de la leyenda: no ocupa una fila propia
       y la gráfica aprovecha ese alto */
    [data-testid="stLayoutWrapper"]:has(> .st-key-graf_otros_tipos) {
        position: absolute !important; right: 18px; bottom: 17px; width: auto !important; z-index: 3;
    }
    .st-key-graf_otros_tipos button { min-height: 28px !important; padding: 0 6px !important; }
    .st-key-graf_otros_tipos button p { font-size: 13.5px; color: var(--accent) !important; }

    /* ---------- Tema claro: profundidad y contraste ----------
       Las tarjetas blancas sobre un fondo casi igual se perdían: sombra suave, barra lateral blanca
       y selectores con la opción activa en relieve */
    :root[data-tema="claro"] div[class*="st-key-"][class*="_card"],
    :root[data-tema="claro"] .kpi-card {
        box-shadow: 0 1px 2px rgba(16, 24, 40, .05), 0 4px 14px rgba(16, 24, 40, .06);
    }
    :root[data-tema="claro"] [data-testid="stSidebar"] { background-color: var(--surface) !important; }
    :root[data-tema="claro"] [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background-color: var(--accent-soft); }
    :root[data-tema="claro"] [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p,
    :root[data-tema="claro"] [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p span { color: var(--accent) !important; }
    :root[data-tema="claro"] [data-testid="stButtonGroup"] [role="radiogroup"],
    :root[data-tema="claro"] .vl-seg, :root[data-tema="claro"] .tema-toggle { background: var(--surface-2); border-color: transparent; }
    :root[data-tema="claro"] [data-testid="stButtonGroup"] button[aria-checked="true"],
    :root[data-tema="claro"] .vl-seg button.on {
        background: var(--surface) !important; color: var(--text) !important; box-shadow: 0 1px 3px rgba(16, 24, 40, .14) !important;
    }
    :root[data-tema="claro"] .tema-toggle .t-sol { background: var(--surface); box-shadow: 0 1px 3px rgba(16, 24, 40, .14); }
    :root[data-tema="claro"] .visor-metricas, :root[data-tema="claro"] .vl-met { background: var(--surface); }
    :root[data-tema="claro"] .estado-card { background: var(--surface-2); border-color: transparent; }

    /* Gráfica sin capturas en el periodo filtrado: mensaje centrado con salida a En vivo */
    [data-testid="stLayoutWrapper"]:has(> .st-key-graf_vacio) { flex: 1 1 0; min-height: 0; }
    .st-key-graf_vacio { height: 100%; gap: 10px; }
    .graf-vacio { display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center; }
    .graf-vacio b { font-size: 15px; color: var(--text); }
    .graf-vacio span { font-size: 13px; color: var(--muted); }
    [data-testid="stMarkdownContainer"]:has(.graf-vacio) { margin-bottom: 0 !important; }

    /* Botón "Confirmar" dentro del selector de color (lo añade el script del final) */
    .cp-confirmar {
        display: block; width: calc(100% - 24px); margin: 2px 12px 12px; min-height: 36px; border: none; border-radius: 10px;
        background: var(--accent); color: var(--accent-ink); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
    }
    .cp-confirmar:hover { filter: brightness(1.08); }

    /* Botón "Listo" al pie del menú de ajustes de la gráfica */
    .pop-listo {
        width: 100%; min-height: 38px; border-radius: 10px; border: none; cursor: pointer;
        background: var(--accent); color: var(--accent-ink); font: inherit; font-size: 14.5px; font-weight: 600;
    }
    .pop-listo:hover { filter: brightness(1.08); }

    /* Carrusel: etiqueta que deja claro que muestra lo último (no sigue al filtro) */
    .vl-vivo {
        position: absolute; left: 10px; top: 10px; display: inline-flex; align-items: center; gap: 6px; pointer-events: none;
        padding: 3px 9px; border-radius: 8px; background: rgba(8, 11, 15, .62); color: #fff; font-size: 12px; font-weight: 600;
        backdrop-filter: blur(2px);
    }
    .vl-vivo i { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }
    /* Galería con filtro: el botón va en naranja, como la etiqueta "Filtro activo" */
    div[class*="_ver_periodo"] button { border-color: rgba(245, 167, 66, .55) !important; }
    div[class*="_ver_periodo"] button p, div[class*="_ver_periodo"] button span { color: var(--warn) !important; }
    /* "Más gráficos": título, pantalla completa y asa en la cabecera de cada tarjeta */
    div[class*="st-key-gm_cab_"] { flex-wrap: nowrap !important; }
    div[class*="st-key-gm_cab_"] > [data-testid="stElementContainer"]:first-child { flex: 1 1 auto; min-width: 0; }
    div[class*="st-key-gm_ampliar_"] button { border-radius: 10px !important; width: 34px; min-height: 34px; padding: 0 !important; }

    /* Un st.html que solo trae estilos o un script no debe ocupar sitio en la página */
    [data-testid="stElementContainer"]:has(> [data-testid="stHtml"] > script:only-child),
    [data-testid="stElementContainer"]:has(> [data-testid="stHtml"] > style:first-child) { display: none; }
    /* Tooltip de las gráficas (tooltip_grafica.py) */
    .tt-laguna {
        position: fixed; z-index: 1000300; display: none; flex-direction: column; gap: 6px; padding: 10px 12px;
        background: var(--tip-bg); border: 1px solid var(--tip-border); border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.25);
        font-size: 13px; color: var(--text);
    }
    .tt-laguna.visible { display: flex; }
    .tt-laguna > div { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
    .tt-laguna svg { width: 15px; height: 15px; color: var(--muted); flex: none; }
    .tt-laguna b { font-weight: 600; }
    /* Captura que disparó una alerta: el aviso, debajo de sus datos */
    .tt-laguna .tt-alerta {
        margin: 2px 0 0; padding-top: 6px; border-top: 1px solid var(--tip-border); max-width: 260px;
        font-size: 12px; line-height: 1.35; color: var(--danger); white-space: normal;
    }
    .tt-sw { width: 16px; height: 16px; border-radius: 5px; border: 1px solid var(--sw-border); flex: none; }
    .visor-metricas {
        display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
        border: 1px solid var(--border); border-radius: 12px;
    }
    .visor-metricas > div { padding: 10px 14px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .visor-metricas > div + div { border-left: 1px solid var(--border); }
    .visor-metricas span { font-size: 13px; color: var(--muted); }
    .visor-metricas b { font-size: 16.5px; color: var(--text); display: flex; align-items: center; gap: 7px; white-space: nowrap; }
    .visor-metricas i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .visor-metricas span, div[class*="_vlaguna_card"] .card-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    /* Pantallas angostas (portátiles): visor más compacto para que nada se parta */
    @media (max-width: 1500px) {
        .visor-metricas > div { padding: 8px 10px; }
        .visor-metricas b { font-size: 14.5px; }
        .vl-met b { font-size: 14px; }
        .vl-met > div { padding: 8px 10px; }
    }

    .kpi-icon.ok { background: var(--ok-soft); color: var(--ok); }
    .kpi-icon.warn { background: rgba(245, 167, 66, .14); color: var(--warn); }
    .kpi-icon.danger { background: var(--danger-soft); color: var(--danger); }
    .kpi-value .kpi-unidad { font-size: 14px; font-weight: 500; color: var(--muted); }
    i.punto { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }

    /* ---------- Pestañas ---------- */
    [data-testid="stTabs"] [role="tablist"] { gap: 26px; }
    [data-testid="stTabs"] button[role="tab"] { padding: 0 2px 10px 2px; }
    [data-testid="stTabs"] button[role="tab"] p span { color: inherit; }
    [data-testid="stTabs"] button[role="tab"] p { font-size: 15px; color: var(--muted); }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] p { color: var(--text); font-weight: 600; }
    [data-testid="stTabs"] [data-baseweb="tab-panel"] { padding-top: 16px; }

    /* ---------- Zona de subida de archivos ---------- */
    [data-testid="stFileUploaderDropzone"] {
        background: var(--bg) !important; border: 1.5px dashed var(--dropzone-border) !important; border-radius: 14px !important;
        padding: 26px 22px !important; transition: border-color .15s, background-color .15s;
    }
    [data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent) !important; background: var(--accent-soft) !important; }
    [data-testid="stFileUploaderDropzoneInstructions"] span { color: var(--text) !important; }
    [data-testid="stFileUploaderDropzoneInstructions"] small { color: var(--muted) !important; }
    [data-testid="stFileUploaderDropzone"] svg { color: var(--accent) !important; }

    /* ---------- Consola de actividad ---------- */
    .terminal {
        background: #080b0f; border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
        font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 12.5px; line-height: 1.65;
        color: #c5ccd5; overflow-y: auto; display: flex; flex-direction: column-reverse;
    }
    /* Las fotos elegidas (etiquetas con su ✕) no alargan la página: una fila y, si hay más, se desplaza dentro */
    .st-key-carga_subida_card [data-testid="stFileChips"] { max-height: 44px; overflow-y: auto; align-content: flex-start; }
    .st-key-carga_ayuda { flex-wrap: nowrap !important; }
    .st-key-carga_ayuda button { min-height: 26px !important; padding: 0 6px !important; white-space: nowrap; }
    .st-key-carga_ayuda button p { font-size: 12.5px !important; color: var(--accent); }
    /* Registro del análisis: la pestaña entera cabe sin desplazarse. El alto va en la envoltura de la tarjeta
       (como en el Inicio) y la ventana de comandos ocupa todo lo que queda: alto de la tarjeta menos su relleno,
       la cabecera y, si se ve, la línea de avance / aviso final */
    :root { --alto-registro: max(200px, calc(100vh - 455px)); }
    [data-testid="stLayoutWrapper"]:has(> .st-key-carga_registro_card) { height: var(--alto-registro); }
    .st-key-carga_registro_card { height: 100%; overflow: hidden; }
    /* Todo lo que envuelve a la ventana de comandos se estira hasta el fondo de la tarjeta */
    .st-key-carga_registro_card :is([data-testid="stVerticalBlock"], [data-testid="stLayoutWrapper"],
        [data-testid="stElementContainer"], [data-testid="stMarkdown"], [data-testid="stMarkdownContainer"]):has(.terminal) {
        flex: 1 1 0 !important; min-height: 0; display: flex; flex-direction: column; height: auto !important;
    }
    /* Streamlit mete una caja sin nombre entre stMarkdown y su contenido: también tiene que estirarse */
    .st-key-carga_registro_card [data-testid="stMarkdown"]:has(.terminal) > div {
        flex: 1 1 0; min-height: 0; display: flex; flex-direction: column;
    }
    .st-key-carga_registro_card .terminal { flex: 1 1 0; min-height: 90px; box-sizing: border-box; }
    [data-testid="stElementContainer"]:has(.lote-msg.vacio) { display: none; }
    /* Registros y Resultados visuales: la tarjeta llega hasta el pie de página, sin desplazar la página.
       En Registros la tabla se estira y se desplaza por dentro; si el filtro de fechas no deja sitio, la tarjeta */
    :root { --alto-pestana: max(200px, calc(100vh - 235px)); }
    [data-testid="stLayoutWrapper"]:has(> :is(.st-key-tabla_registros_card, .st-key-visual_galeria_card)) { height: var(--alto-pestana); }
    .st-key-tabla_registros_card { height: 100%; overflow-y: auto; }
    .st-key-visual_galeria_card { height: 100%; overflow: hidden; }
    :is(.st-key-tabla_registros_card, .st-key-visual_galeria_card):has(.graf-vacio) { justify-content: center; }
    /* Galería: dos filas de fotos que reparten el alto de la tarjeta (menos relleno, cabecera y separaciones) */
    .st-key-visual_galeria_card { --alto-foto: max(110px, calc((var(--alto-pestana) - 109px) / 2)); }
    .st-key-visual_galeria_card [data-testid="stLayoutWrapper"] > div.stVerticalBlock[class*="st-key-galeria_gfoto_"] { width: 100% !important; }
    .st-key-visual_galeria_card div[class*="st-key-galeria_gfoto_"] [data-testid="stImage"] img {
        aspect-ratio: auto; height: var(--alto-foto) !important;
    }
    /* En un móvil las fotos van en una sola columna: ahí sí se desplaza */
    @media (max-width: 640px) {
        [data-testid="stLayoutWrapper"]:has(> :is(.st-key-tabla_registros_card, .st-key-visual_galeria_card)) { height: auto; }
        .st-key-visual_galeria_card div[class*="st-key-galeria_gfoto_"] [data-testid="stImage"] img { aspect-ratio: 16 / 9; height: auto !important; }
    }
    /* Aspecto de ventana de comandos (CMD): fondo negro, texto gris claro, cada línea con ">" y el cursor
       parpadeando al final. Las líneas empiezan arriba; si no caben, se ve siempre la última */
    .terminal.cmd {
        background: #0c0c0c; color: #cccccc; border-color: #262626; border-radius: 10px;
        font-family: Consolas, "Cascadia Mono", ui-monospace, monospace; font-size: 13px; line-height: 1.6;
    }
    /* El margen automático deja el hueco debajo de la última línea; si no caben, vale 0 y manda column-reverse */
    .terminal.cmd > :first-child { margin-bottom: auto; }
    .terminal.cmd > div { display: flex; white-space: pre-wrap; word-break: break-word; }
    .terminal.cmd .t-signo { color: #8a8a8a; margin-right: 8px; flex: none; }
    .terminal.cmd .t-hora { color: #6d6d6d; }
    .terminal.cmd .t-vivo { color: #e8e8e8; }
    .terminal.cmd .t-cursor {
        display: inline-block; width: 8px; height: 15px; margin-top: 3px; background: #cccccc;
        animation: cursor-cmd 1s steps(1) infinite;
    }
    @keyframes cursor-cmd { 50% { opacity: 0; } }
    /* En el tema claro la ventana de comandos es gris: texto oscuro y niveles en tonos que se leen sobre ella */
    :root[data-tema="claro"] .terminal.cmd { background: #e3e6eb; color: #2b3440; border-color: #cfd4db; }
    :root[data-tema="claro"] .terminal.cmd .t-signo { color: #6b7480; }
    :root[data-tema="claro"] .terminal.cmd .t-hora { color: #6b7480; }
    :root[data-tema="claro"] .terminal.cmd .t-vivo { color: #17212c; }
    :root[data-tema="claro"] .terminal.cmd .t-cursor { background: #2b3440; }
    :root[data-tema="claro"] .terminal.cmd .t-INFO { color: #0f766e; }
    :root[data-tema="claro"] .terminal.cmd .t-OK { color: #15803d; }
    :root[data-tema="claro"] .terminal.cmd .t-AVISO { color: #b45309; }
    :root[data-tema="claro"] .terminal.cmd .t-ERROR { color: #c81e2d; }
    [data-testid="stMarkdownContainer"]:has(.lote-msg, .lote-avance, .chip-almacenada) { margin-bottom: 0 !important; }
    /* Resultados: foto que ya estaba en la base y no se volvió a analizar */
    .chip-almacenada {
        display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
        white-space: nowrap; color: var(--accent); background: var(--accent-soft);
    }
    /* Avance mientras analiza */
    .lote-avance { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
    .lote-avance > span { display: flex; justify-content: space-between; gap: 12px; }
    .lote-avance b { color: var(--text); font-weight: 600; white-space: nowrap; }
    .lote-barra { height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
    .lote-barra i { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
    .terminal .t-hora { color: #5d6774; margin-right: 8px; }
    .terminal .t-nivel { display: inline-block; min-width: 52px; font-weight: 600; margin-right: 8px; }
    .terminal .t-INFO { color: var(--accent); }
    .terminal .t-OK { color: var(--ok); }
    .terminal .t-AVISO { color: var(--warn); }
    .terminal .t-ERROR { color: var(--danger); }
    .terminal .t-vacio { color: var(--muted); font-style: italic; }

    /* ---------- Listas clave/valor dentro de tarjetas ---------- */
    .lista-datos { display: flex; flex-direction: column; margin-top: 6px; }
    .lista-datos > div { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0; border-top: 1px solid var(--border); font-size: 14px; }
    .lista-datos > div:first-child { border-top: none; }
    .lista-datos span { color: var(--muted); white-space: nowrap; }
    .lista-datos b { color: var(--text); font-weight: 600; text-align: right; display: flex; align-items: center; gap: 8px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .st-key-srv_descartes_card .lista-datos b { display: block; white-space: normal; }
    .lista-datos code { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; font-size: 12.5px; color: var(--muted); background: var(--surface-2); padding: 1px 6px; border-radius: 6px; }

    /* ---------- Cargar y procesar ---------- */
    .ayuda-carga { font-size: 12.5px; color: var(--muted); line-height: 1.5; margin-top: -4px; }
    .ayuda-carga kbd { background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px; padding: 0 5px; font-size: 11.5px; color: var(--text); }
    .ayuda-carga code { font-size: 11.5px; white-space: nowrap; }
    .ayuda-carga i { font-style: normal; margin: 0 6px; opacity: .5; }
    /* Zona de carga compacta: icono y texto a la izquierda, botón a la derecha */
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzone"] { padding: 14px 18px !important; gap: 14px; align-items: center; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzone"]::before {
        content: ""; flex: none; width: 40px; height: 40px; border-radius: 11px; background: var(--accent-soft) center / 22px no-repeat
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233cc9b4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2'/%3E%3Cpath d='M12 12v9'/%3E%3Cpath d='m16 16-4-4-4 4'/%3E%3C/svg%3E");
    }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzone"] > span { order: 3; margin-left: auto; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] { order: 2; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] > div { display: flex; flex-direction: column; gap: 1px; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] > div::before {
        content: "Arrastra aquí tus fotografías"; color: var(--text); font-weight: 600; font-size: 14.5px;
    }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] span { color: var(--muted) !important; font-size: 12.5px; }
    /* Textos del selector de archivos en español (Streamlit los trae en inglés y no deja cambiarlos desde Python) */
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 0 !important; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzoneInstructions"] span::after {
        content: "Hasta 200 MB por foto · solo JPG"; font-size: 12.5px;
    }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p { font-size: 0 !important; }
    .st-key-carga_subida_card [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
        content: "Seleccionar fotos"; font-size: 14px;
    }
    /* El botón Procesar toma el alto de la zona de carga */
    .st-key-btn_procesar_lote button { min-height: 70px; }
    .st-key-carga_resultado_card [data-testid="stImage"] img { max-height: 44vh; object-fit: contain; background: var(--bg); }
    .img-titulo { font-size: 13px; color: var(--muted); margin: 0 0 6px 2px; display: flex; align-items: center; gap: 6px; }
    div[class*="_card"] [data-testid="stImage"] img { border-radius: 12px; }

    /* ---------- Alertas ---------- */
    .alertas-lista { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; max-height: calc(100vh - 330px); overflow-y: auto; padding-right: 4px; }
    .alerta-fila { display: flex; gap: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
    .alerta-fila.leida { opacity: .62; }
    .alerta-nivel { flex: none; width: 4px; border-radius: 4px; }
    .alerta-cuerpo { min-width: 0; flex: 1; }
    .alerta-cabecera { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 14px; }
    .alerta-cabecera b { color: var(--text); }
    .alerta-cabecera span { color: var(--muted); font-size: 13px; }
    .alerta-nueva { background: var(--danger-soft); color: var(--danger) !important; font-weight: 600; font-size: 11.5px !important; padding: 1px 7px; border-radius: 6px; }
    .alerta-mensaje { color: var(--text-2); font-size: 14px; margin-top: 4px; line-height: 1.45; }
    .alerta-envio { display: block; color: var(--muted); font-size: 12px; margin-top: 4px; }
    .st-key-sb_salir { margin-top: 10px; padding-left: 8px; }
    .st-key-sb_salir button p { color: var(--muted) !important; font-size: 14.5px; }
    .st-key-acceso_card { margin-top: 18vh; }

    /* ---------- Placeholders y chips heredados ---------- */
    .ph-box-normal, .ph-box-proc {
        aspect-ratio: 4/3; border-radius: 10px; border: 1px dashed var(--border);
        background: var(--surface-2) !important;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        color: var(--muted) !important; font-size: 13px; text-align: center; padding: 15px;
    }
    .ph-box-proc { border-color: var(--accent); color: var(--accent) !important; }
    .chip-container { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 15px; }
    .chip-item {
        background-color: var(--surface-2) !important; border: 1px solid var(--border) !important;
        border-radius: 20px !important; padding: 5px 14px !important;
        font-size: 12.5px !important; font-weight: 500 !important; color: var(--text) !important;
    }
</style>
<script>
(() => {
  const CLAVE = `stActiveTheme-${location.pathname}-v2`;
  let guardado = null;
  try { guardado = JSON.parse(localStorage.getItem(CLAVE)); } catch (e) {}
  const claro = guardado === "Light" || (guardado !== "Dark" && matchMedia("(prefers-color-scheme: light)").matches);
  document.documentElement.dataset.tema = claro ? "claro" : "oscuro";
  if (window.__temaLaguna) return;
  window.__temaLaguna = true;
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".tema-toggle")) return;
    const aClaro = document.documentElement.dataset.tema !== "claro";
    try { localStorage.setItem(CLAVE, JSON.stringify(aClaro ? "Light" : "Dark")); } catch (e) {}
    // Con contraseña: el pase evita volver a pedirla tras la recarga (cookie de un minuto)
    const pase = e.target.closest(".tema-toggle").dataset.pase;
    if (pase) document.cookie = `curiquinga_pase=${pase}; max-age=60; path=/; SameSite=Strict`;
    location.reload();
  });

  // Selector de color de Streamlit: se le añade un botón "Confirmar" que lo cierra. El color se aplica al
  // cerrarlo de cualquier forma (Confirmar o pulsando fuera); el botón es para que se entienda cómo terminar.
  let abierto = null;   // botón (muestra de color) que abrió el selector visible
  document.addEventListener("click", (e) => {
    const muestra = e.target.closest('[data-testid="stColorPicker"] button[aria-haspopup="dialog"]');
    if (muestra) abierto = muestra;
  }, true);
  const agregarConfirmar = () => {
    document.querySelectorAll('[data-testid="stColorPickerPopover"]').forEach((pop) => {
      const caja = pop.querySelector(".chrome-picker") || pop;   // dentro de la tarjeta del selector
      if (caja.querySelector(".cp-confirmar") || !abierto) return;
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "cp-confirmar";
      boton.textContent = "Confirmar";
      const muestra = abierto;
      // El menú de ajustes tomaría este clic como "fuera" y se cerraría: no se le deja llegar
      ["pointerdown", "mousedown", "touchstart"].forEach((t) => boton.addEventListener(t, (e) => e.stopPropagation()));
      boton.addEventListener("click", (e) => {
        e.stopPropagation();
        muestra.click();   // cierra el selector y Streamlit envía el color elegido
      });
      caja.appendChild(boton);
    });
  };
  new MutationObserver(agregarConfirmar).observe(document.body, { childList: true, subtree: true });


  // Subpestaña "Más gráficos": su salida es el enlace "Panel de monitoreo" de la ruta del encabezado.
  // El botón atrás del navegador y pulsar "Inicio" en el menú (ya marcado, Streamlit no haría nada) lo pulsan.
  const miga = () => document.querySelector(".st-key-miga_panel button");
  let enHistorial = false;
  new MutationObserver(() => {
    const hay = !!miga();
    if (hay && !enHistorial) history.pushState({ curiquingaVista: true }, "", location.href);
    enHistorial = hay;
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("popstate", () => { if (miga()) miga().click(); });
  // En fase de captura: el menú de Streamlit no deja que el clic suba hasta document
  document.addEventListener("click", (e) => {
    const opcion = e.target.closest('[data-testid="stSidebar"] [role="radiogroup"] label');
    if (opcion && opcion.querySelector("input:checked") && miga()) miga().click();
    // Otro módulo: abre por arriba, aunque el anterior estuviera desplazado
    if (opcion && !opcion.querySelector("input:checked")) document.querySelector('[data-testid="stMain"]')?.scrollTo(0, 0);
  }, true);

  // Calendarios dentro de un menú emergente (día de la galería y de comparar): al pulsar un día el menú se
  // cierra solo. Streamlit lo deja abierto; un "clic fuera" sobre el título del diálogo lo cierra sin cerrar
  // el diálogo (Esc cerraría los dos).
  document.addEventListener("click", (e) => {
    if (!e.target.closest('[data-testid="stPopoverBody"] :is(div[class*="st-key-cal_d_"], .st-key-tabla_eliminar) button')) return;
    setTimeout(() => {
      const fuera = document.querySelector('[role="dialog"] h2') || document.body;
      ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]
        .forEach((tipo) => fuera.dispatchEvent(new MouseEvent(tipo, { bubbles: true })));
    }, 250);
  }, true);

  // Nombres al pasar el ratón: en el menú contraído, cada icono; con el menú abierto, solo el tema (sus iconos no
  // llevan texto). Una etiqueta propia y no "title": aparece al instante y no la recorta el riel.
  const etiqueta = document.createElement("div");
  etiqueta.className = "riel-tip";
  document.body.appendChild(etiqueta);
  const textoDe = (el) => {
    if (el.matches(".tema-toggle")) {
      return document.documentElement.dataset.tema === "claro" ? "Cambiar a tema oscuro" : "Cambiar a tema claro";
    }
    if (el.matches('[data-testid="stExpandSidebarButton"]')) return "Expandir menú";
    if (el.matches(".estado-card")) return el.dataset.tip;
    if (el.matches(".brand")) return "Curiquinga · Monitoreo lacustre";
    // El nombre del icono también es texto ("home", "dns"…): se salta lo que usa la fuente de iconos
    const partes = [];
    const recorrido = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (recorrido.nextNode()) {
      const nodo = recorrido.currentNode;
      if (!getComputedStyle(nodo.parentElement).fontFamily.includes("Material")) partes.push(nodo.textContent);
    }
    return partes.join(" ").trim();
  };
  document.addEventListener("mouseover", (e) => {
    const destino = e.target.closest?.('[data-testid="stRadioOption"], .estado-card, .tema-toggle, .brand, .st-key-sb_salir button, [data-testid="stExpandSidebarButton"]');
    const contraido = !!document.querySelector('[data-testid="stSidebar"][data-collapsed="true"]');
    const enBarra = destino && (destino.closest('[data-testid="stSidebar"]') || destino.matches('[data-testid="stExpandSidebarButton"]'));
    if (!enBarra || !(contraido || destino.matches(".tema-toggle"))) {
      etiqueta.classList.remove("visible");
      return;
    }
    const caja = destino.getBoundingClientRect();
    etiqueta.textContent = textoDe(destino);
    etiqueta.classList.toggle("junto", !contraido);
    etiqueta.style.top = `${caja.top + caja.height / 2}px`;
    etiqueta.style.left = contraido ? "" : `${caja.right}px`;
    etiqueta.classList.add("visible");
  });

  // Foto abierta en la galería: ← → pasan a la anterior / siguiente, como en la ampliación del carrusel
  document.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key) || e.target.closest?.("input, textarea, [contenteditable]")) return;
    const boton = document.querySelector(`.st-key-galeria_${e.key === "ArrowLeft" ? "ant" : "sig"} button`);
    if (boton && !boton.disabled) { e.preventDefault(); boton.click(); }
  });

  // Tarjetas de Cargar y procesar: su alto es lo que queda de pantalla desde donde empiezan hasta el pie de
  // página, que así queda abajo del todo sin desplazarse. Se mide la posición real (cambia con el ancho: el
  // texto de ayuda puede ocupar una o dos líneas) y se guarda en una variable de CSS.
  const TARJETAS = { carga_registro_card: "--alto-registro", tabla_registros_card: "--alto-pestana", visual_galeria_card: "--alto-pestana" };
  let pendienteAlto = false;
  const ajustarAltoRegistro = () => {
    pendienteAlto = false;
    const pie = document.querySelector(".pie-pagina");
    const zona = document.querySelector('[data-testid="stMain"]');
    for (const [clave, variable] of Object.entries(TARJETAS)) {
      const caja = document.querySelector(`[data-testid="stLayoutWrapper"]:has(> .st-key-${clave})`);
      if (!caja || !pie || !caja.offsetParent) continue;  // sin offsetParent: está en otra pestaña
      const arriba = caja.getBoundingClientRect().top + (zona ? zona.scrollTop : 0);
      const bajoTarjeta = pie.getBoundingClientRect().bottom - caja.getBoundingClientRect().bottom + 16;
      const alto = Math.max(200, Math.floor(window.innerHeight - arriba - bajoTarjeta));
      if (document.documentElement.style.getPropertyValue(variable) !== `${alto}px`) {
        document.documentElement.style.setProperty(variable, `${alto}px`);
      }
    }
  };
  const programarAlto = () => { if (!pendienteAlto) { pendienteAlto = true; requestAnimationFrame(ajustarAltoRegistro); } };
  new MutationObserver(programarAlto).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", programarAlto);
  document.addEventListener("click", (e) => { if (e.target.closest('[role="tab"]')) setTimeout(programarAlto, 80); });

  // Botón "Listo" de los menús emergentes: los cierra como lo haría la tecla Esc
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".pop-listo")) return;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
  });
})();
</script>""", unsafe_allow_javascript=True)

inicializar_bd()

PAGINAS = {
    "inicio": ":material/home: Inicio",
    "cargar": ":material/cloud_upload: Cargar y procesar",
    "alertas": ":material/notifications: Alertas",
    "servidor": ":material/dns: Control de servidor",
    "configuracion": ":material/settings: Configuración",
}

def _pantalla_acceso():
    """Formulario de contraseña; detiene la app hasta que sea correcta."""
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] { display: none !important; }</style>",
                unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro, st.container(key="acceso_card"):
        st.markdown("""
            <div class="brand" style="margin-bottom:18px">
                <div class="brand-logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
                <div><div class="brand-name">Curiquinga</div><div class="brand-sub">Monitoreo lacustre</div></div>
            </div>
        """, unsafe_allow_html=True)
        with st.form("form_acceso", border=False):
            clave = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", type="primary", width="stretch", icon=":material/login:"):
                if acceso.comprobar(clave):
                    st.session_state["autenticado"] = True
                    st.rerun()
                st.error("Contraseña incorrecta.")
    st.stop()

if acceso.protegido() and not st.session_state.get("autenticado"):
    # Recarga por cambio de tema: el pase de la cookie mantiene la sesión iniciada
    if acceso.pase_valido(st.context.cookies.get("curiquinga_pase")):
        st.session_state["autenticado"] = True
    else:
        _pantalla_acceso()

def _hace(delta):
    minutos = int(delta.total_seconds() // 60)
    if minutos < 60:
        return f"{max(minutos, 1)} min"
    if minutos < 60 * 24:
        return f"{minutos // 60} h"
    dias = minutos // (60 * 24)
    return f"{dias} día" if dias == 1 else f"{dias} días"

def _estado_servidor():
    """(título, color del punto, detalle) según el latido del vigilante y los registros guardados."""
    servicio = leer_estado()
    if servicio["en_linea"]:
        if servicio.get("procesando"):
            return "Vigilante procesando", "#3cc9b4", servicio["procesando"]
        return "Vigilante en línea", "#2fd27a", f"Escuchando · {servicio.get('procesadas', 0)} procesadas"
    regs = registros()
    if not regs:
        return "Vigilante detenido", "#f0616d", "Aún no se ha procesado ninguna imagen"
    ultima = max(datetime.strptime(r["fecha_subida"], "%Y-%m-%d %H:%M:%S") for r in regs)
    return "Vigilante detenido", "#f0616d", f"Último registro hace {_hace(datetime.now() - ultima)}"

st.sidebar.markdown("""
    <div class="brand">
        <div class="brand-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z"/>
                <path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97"/>
            </svg>
        </div>
        <div>
            <div class="brand-name">Curiquinga</div>
            <div class="brand-sub">Monitoreo lacustre</div>
        </div>
    </div>
    <div class="menu-label">MENÚ</div>
""", unsafe_allow_html=True)

# El módulo va en la dirección (?pagina=cargar): al recargar se sigue en el mismo y el enlace se puede guardar.
# Se maneja a mano y no con bind="query-params", que pondría en la URL el texto visible con su icono.
recordar.restaurar()
if "pagina" not in st.session_state and st.query_params.get("pagina") in PAGINAS:
    st.session_state["pagina"] = st.query_params["pagina"]
opcion = st.sidebar.radio("Navegación", list(PAGINAS), format_func=PAGINAS.get, label_visibility="collapsed",
                          key="pagina")
if opcion == "inicio":
    st.query_params.pop("pagina", None)
elif st.query_params.get("pagina") != opcion:
    st.query_params["pagina"] = opcion

# Contador de alertas sin leer sobre la opción del menú (CSS: el radio no admite contenido extra)
no_leidas = contar_alertas_no_leidas()
if no_leidas:
    posicion = list(PAGINAS).index("alertas") + 1
    st.sidebar.markdown(f"""<style>
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] div:nth-child({posicion}) > [data-testid="stRadioOption"] p::after {{
            content: "{min(no_leidas, 99)}"; margin-left: auto; margin-right: 18px; min-width: 22px; height: 22px; padding: 0 6px;
            border-radius: 11px; background: var(--danger); color: #fff; font-size: 12px; font-weight: 700;
            display: inline-flex; align-items: center; justify-content: center;
        }}
    </style>""", unsafe_allow_html=True)

if acceso.protegido():
    with st.sidebar.container(key="sb_salir"):
        if st.button("Cerrar sesión", icon=":material/logout:", type="tertiary"):
            st.session_state["autenticado"] = False
            st.rerun()

with st.sidebar.container(key="sb_tema"):
    boton_tema()

titulo_estado, color_estado, detalle_estado = _estado_servidor()
with st.sidebar.container(key="sb_estado"):
    st.markdown(f"""
        <div class="estado-card" data-tip="{titulo_estado} · {detalle_estado}">
            <div class="estado-mini">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19.1"/></svg>
                <i style="background:{color_estado}"></i>
            </div>
            <b><i style="background:{color_estado}"></i>{titulo_estado}</b>
            <span>{detalle_estado}</span>
        </div>
    """, unsafe_allow_html=True)

# Al volver al Inicio desde otro módulo se llega al panel principal (no a "Más gráficos" ni a la gráfica ampliada);
# el filtro de fechas vuelve a En vivo, para no creer que lo que se ve es el estado actual, y el origen se mantiene
if opcion == "inicio" and st.session_state.get("_pagina_previa") not in (None, "inicio"):
    from frontend.components.filtro_temporal import restablecer_filtro
    restablecer_filtro()
    st.session_state["vista_graficas"] = False
    st.session_state["grafica_ampliada"] = False
st.session_state["_pagina_previa"] = opcion
if opcion != "inicio" and "vista" in st.query_params:
    del st.query_params["vista"]

if opcion == "inicio":
    from frontend.views.inicio import render_inicio
    render_inicio()
elif opcion == "cargar":
    from frontend.views.cargar import render_cargar
    render_cargar()
elif opcion == "alertas":
    from frontend.views.alertas import render_alertas
    render_alertas()
elif opcion == "servidor":
    from frontend.views.servidor import render_servidor
    render_servidor()
elif opcion == "configuracion":
    from frontend.views.configuracion import render_configuracion
    render_configuracion()

# Análisis de fotos subidas a mano: corre en segundo plano. Aquí se retoma si quedó a medias y se abre la
# ventana de resultados, en cualquier módulo
from frontend.components.formulario_carga import avisos_lote
avisos_lote()
recordar.sincronizar()

# Pie de página con los créditos de Configuración → Acceso y créditos
_pie = cfg.cargar()["pie"]
_correo = html.escape(_pie["correo"])
st.markdown(f"""<div class="pie-pagina">
    <span>© {datetime.now().year} Monitoreo Laguna Curiquinga{' · ' + html.escape(_pie['institucion']) if _pie['institucion'] else ''}</span>
    <span>Autor(es): <b>{html.escape(_pie['autores']) or 'sin definir'}</b></span>
    <span>Contacto: {f'<a href="mailto:{_correo}">{_correo}</a>' if _correo else '<b>sin definir</b>'}</span>
</div>""", unsafe_allow_html=True)

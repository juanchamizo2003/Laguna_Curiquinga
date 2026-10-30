import streamlit as st

# Iconos de trazo (estilo Lucide) para las tarjetas de métricas
_SVG = "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{}</svg>"
ICONO_AREA = _SVG.format(
    "<path d='M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>"
    "<path d='M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>"
    "<path d='M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>"
)
ICONO_PROMEDIO = _SVG.format("<path d='M22 12h-4l-3 9L9 3l-3 9H2'/>")
ICONO_MAXIMO = _SVG.format(
    "<polyline points='15 3 21 3 21 9'/><polyline points='9 21 3 21 3 15'/>"
    "<line x1='21' x2='14' y1='3' y2='10'/><line x1='3' x2='10' y1='21' y2='14'/>"
)
ICONO_MUESTRAS = _SVG.format("<path d='m12 14 4-4'/><path d='M3.34 19a10 10 0 1 1 17.32 0'/>")
ICONO_SERVIDOR = _SVG.format(
    "<rect width='20' height='8' x='2' y='2' rx='2'/><rect width='20' height='8' x='2' y='14' rx='2'/>"
    "<line x1='6' x2='6.01' y1='6' y2='6'/><line x1='6' x2='6.01' y1='18' y2='18'/>"
)
ICONO_CHIP = _SVG.format(
    "<rect width='16' height='16' x='4' y='4' rx='2'/><rect width='6' height='6' x='9' y='9' rx='1'/>"
    "<path d='M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2'/>"
)
ICONO_COLA = _SVG.format(
    "<path d='M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83'/>"
)
ICONO_CHECK = _SVG.format("<path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'/><polyline points='22 4 12 14.01 9 11.01'/>")
ICONO_FECHA = _SVG.format("<rect x='3' y='4' width='18' height='18' rx='2'/><path d='M16 2v4M8 2v4M3 10h18'/>")
ICONO_COLOR = _SVG.format("<path d='M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z'/>")

def html_kpi(icono, etiqueta, valor, extra="", tono="", pie="", ayuda=""):
    """HTML de una tarjeta de métrica. tono: '' (acento), 'ok', 'warn' o 'danger' para el color del icono.
    pie: línea pequeña bajo el valor (p. ej. el periodo de una estadística); ayuda: texto al pasar el ratón."""
    titulo = f' title="{ayuda}"' if ayuda else ""
    return f"""
        <div class="kpi-card"{titulo}>
            <div class="kpi-icon {tono}">{icono}</div>
            <div>
                <div class="kpi-label">{etiqueta}</div>
                <div class="kpi-value">{valor}{extra}</div>
                {pie}
            </div>
        </div>
    """

def tarjeta_kpi(icono, etiqueta, valor, extra="", tono=""):
    st.markdown(html_kpi(icono, etiqueta, valor, extra, tono), unsafe_allow_html=True)

def punto(color):
    return f"<i class='punto' style='background:{color}'></i>"

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.components.formato import MESES_CORTOS, fecha_legible, formatear_m2

COLOR_AUTO = "#3cc9b4"
COLOR_MANUAL = "#f5a742"
COLOR_TENDENCIA = "#8b95a3"
COLOR_TEXTO_SUAVE = "#8b95a3"
COLOR_ALERTA = "#f0616d"

# (nombre en leyenda, texto a buscar en 'estado', color por defecto)
SERIES_AREA = [
    ("Automático", "Automático", COLOR_AUTO),
    ("Manual", "Manual", COLOR_MANUAL),
]
TIPOS_GRAFICO = ["Puntos", "Línea", "Área", "Barras", "Escalones", "Tallos"]
VENTANA_TENDENCIA = 5   # días con datos que promedia la tendencia
MAX_ETIQUETAS_X = 8

# Las trazas con meta=TOOLTIP las dibuja el tooltip propio de tooltip_grafica.py (con iconos y color)
TOOLTIP = "laguna"

def _etiqueta_dia(fecha, con_anio):
    texto = f"{fecha.day} {MESES_CORTOS[fecha.month - 1]}"
    return f"{texto} {fecha:%y}" if con_anio else texto

def _texto_confianza(valor):
    return f"{valor:.0%}" if pd.notna(valor) else "—"

def _preparar(df):
    """Una fila por captura, en orden, con la posición X (cada captura ocupa el mismo ancho)."""
    df = df.copy()
    df["_fecha"] = pd.to_datetime(df["fecha_captura"], errors="coerce")
    df = df.dropna(subset=["_fecha"]).sort_values("_fecha").reset_index(drop=True)
    df["_x"] = np.arange(len(df))
    return df

def _datos_tooltip(sub, alertas=None):
    """Columnas del tooltip propio; la última es el aviso de la alerta que disparó la captura ("" si ninguna)."""
    confianza = sub["confianza"] if "confianza" in sub else pd.Series(np.nan, index=sub.index)
    alertas = alertas or {}
    ids = sub["id"] if "id" in sub else pd.Series(None, index=sub.index)
    return np.stack([
        [fecha_legible(f) for f in sub["fecha_captura"]],
        [formatear_m2(a) for a in sub["area"]],
        [str(c or "#8b95a3").upper() for c in sub["color_hex"]],
        [_texto_confianza(c) for c in confianza],
        [" · ".join(alertas.get(i, [])) for i in ids],
    ], axis=-1)

def _eje_x_por_dias(fig, df, max_etiquetas=MAX_ETIQUETAS_X):
    """Marca en X el primer registro de cada día, con como mucho max_etiquetas etiquetas."""
    primeros = df.groupby(df["_fecha"].dt.normalize())["_x"].min()
    con_anio = primeros.index[0].year != primeros.index[-1].year
    paso = max(1, int(np.ceil(len(primeros) / max_etiquetas)))
    fig.update_xaxes(tickvals=primeros.values[::paso],
                     ticktext=[_etiqueta_dia(d, con_anio) for d in primeros.index[::paso]],
                     range=[-0.6, len(df) - 0.4])

def _sin_datos(fig):
    fig.add_annotation(text="Sin datos para mostrar", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
                       font=dict(color=COLOR_TEXTO_SUAVE, size=13))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)

# Ejes y rejilla según el tema activo: en claro las líneas deben ser más suaves que en oscuro
PALETAS_EJES = {
    "dark": {"eje": "#4a5563", "rejilla": "rgba(139, 149, 163, 0.16)", "texto": COLOR_TEXTO_SUAVE},
    "light": {"eje": "#9aa5b1", "rejilla": "rgba(23, 33, 44, 0.08)", "texto": "#5e6a78"},
}

def _paleta_ejes():
    try:
        tema = st.context.theme.type
    except Exception:
        tema = None
    return PALETAS_EJES.get(tema or "dark", PALETAS_EJES["dark"])

def estilo_base(fig, leyenda=True, hover="closest", ejes=True):
    """Estilo común: ejes X e Y como en un plano cartesiano y rejilla horizontal suave.

    Las líneas de eje de Plotly se dibujan unos px por fuera del área de la gráfica (el eje X quedaba por
    debajo del 0); por eso los ejes son dos líneas pegadas al borde del área, que se cruzan en el origen.
    """
    p = _paleta_ejes()
    eje = dict(showline=False, ticks="", zeroline=False, gridcolor=p["rejilla"], tickfont=dict(color=p["texto"], size=13))
    if ejes:
        linea = dict(type="line", xref="paper", yref="paper", line=dict(color=p["eje"], width=1.5), layer="above")
        fig.add_shape(linea, x0=0, x1=1, y0=0, y1=0)
        fig.add_shape(linea, x0=0, x1=0, y0=0, y1=1)
    fig.update_layout(
        # Solo rejilla horizontal: las verticales caían donde hay fecha y quedaban a intervalos irregulares
        xaxis=dict(eje, showgrid=False),
        yaxis=dict(eje, showgrid=True, griddash="dash", nticks=6),
        # Leyenda pegada al borde inferior de la figura (no relativa al alto): así queda siempre a la misma
        # altura y el botón "Más gráficos" se alinea con ella. A la izquierda: con varias series no lo pisa
        legend=dict(orientation="h", x=0, xanchor="left", yref="container", y=0, yanchor="bottom",
                    font=dict(color=p["texto"], size=13), itemsizing="constant"),
        hoverlabel=dict(bgcolor="#151b22", bordercolor="#2b333d", font=dict(color="#e8edf2", size=12)),
        separators=",.", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=4, r=12, t=10, b=30 if leyenda else 4), showlegend=leyenda, hovermode=hover,
        font=dict(family="Inter, sans-serif"),
    )
    return fig

def _marcar_alertas(fig, df, umbral, alertas, color=COLOR_ALERTA):
    """Línea discontinua en el área mínima de las alertas y un aro en las capturas que dispararon una
    (rojo por defecto; el color se elige en los ajustes de la gráfica)."""
    if umbral:
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=umbral, y1=umbral, layer="below",
                      line=dict(color=color, width=1.4, dash="dash"))
        fig.add_annotation(xref="paper", x=1, y=umbral, xanchor="right", yanchor="bottom", showarrow=False,
                           text=f"Mínimo de alerta · {formatear_m2(umbral)}",
                           font=dict(color=_paleta_ejes()["texto"], size=11))
    if alertas and "id" in df:
        con = df[df["id"].isin(list(alertas))]
        if not con.empty:
            fig.add_trace(go.Scatter(
                x=con["_x"], y=con["area"], mode="markers", name="Con alerta", hoverinfo="skip",
                marker=dict(size=19, color="rgba(0,0,0,0)", line=dict(color=color, width=2)),
            ))

def fig_area(df, tipo="Puntos", colores=None, tendencia=False, compacta=False, umbral=None, alertas=None):
    """Área de cada captura por origen. colores: {'Automático': hex, 'Manual': hex} y, opcionales,
    'Tendencia' y 'Alerta' para esas dos capas.
    compacta: para las gráficas adicionales, más estrechas (menos fechas y sin leyenda).
    umbral: área mínima de las alertas (línea roja); alertas: {id de captura: [mensajes]} de las que dispararon una."""
    colores = colores or {}
    fig = go.Figure()
    if df.empty:
        _sin_datos(fig)
        return estilo_base(fig, ejes=False)

    df = _preparar(df)
    for nombre, clave, color_def in SERIES_AREA:
        sub = df[df["estado"].str.contains(clave, na=False)]
        if sub.empty:
            continue
        color = colores.get(clave, color_def)
        comunes = dict(x=sub["_x"], y=sub["area"], name=nombre, customdata=_datos_tooltip(sub, alertas),
                       hoverinfo="none", meta=TOOLTIP)
        if tipo in ("Barras", "Tallos"):
            # Tallos: barra fina con un punto en la punta
            ancho = 0.08 if tipo == "Tallos" else None
            fig.add_trace(go.Bar(marker=dict(color=color, cornerradius=4 if ancho is None else 0), width=ancho, **comunes))
            if tipo == "Tallos":
                fig.add_trace(go.Scatter(mode="markers", marker=dict(size=11, color=color), showlegend=False,
                                         **dict(comunes, name=nombre)))
            continue
        modo = {"Puntos": "markers", "Línea": "lines+markers", "Área": "lines+markers", "Escalones": "lines+markers"}[tipo]
        forma = "hv" if tipo == "Escalones" else "spline"
        traza = go.Scatter(mode=modo if len(sub) > 1 else "markers", line=dict(color=color, width=2.5, shape=forma),
                           marker=dict(size=10 if tipo == "Puntos" else 7, color=color, line=dict(width=0)), **comunes)
        if tipo == "Área":
            rgb = ", ".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
            traza.update(fill="tozeroy", fillgradient=dict(
                type="vertical", colorscale=[[0, f"rgba({rgb}, 0)"], [1, f"rgba({rgb}, 0.22)"]]))
        fig.add_trace(traza)

    if tendencia and df["_fecha"].dt.normalize().nunique() >= 4:
        dias = df.groupby(df["_fecha"].dt.normalize()).agg(x=("_x", "mean"), area=("area", "mean"))
        fig.add_trace(go.Scatter(
            x=dias["x"], y=dias["area"].rolling(VENTANA_TENDENCIA, min_periods=2).mean(),
            name=f"Tendencia ({VENTANA_TENDENCIA} días)", mode="lines",
            line=dict(color=colores.get("Tendencia", COLOR_TENDENCIA), width=1.6, dash="dot", shape="spline"),
            hoverinfo="skip",
        ))

    _marcar_alertas(fig, df, umbral, alertas, colores.get("Alerta", COLOR_ALERTA))
    _eje_x_por_dias(fig, df, 4 if compacta else MAX_ETIQUETAS_X)
    estilo_base(fig, leyenda=not compacta)
    fig.update_xaxes(tickangle=0)
    # El eje Y arranca exactamente en 0: así la línea del eje X queda sobre el cero, como en un plano cartesiano
    tope = max(float(df["area"].max()), float(umbral or 0))
    fig.update_yaxes(range=[0, tope * 1.12], autorange=False, tickformat="~s")
    fig.update_layout(barmode="overlay" if tipo == "Tallos" else "group", bargap=0.25)
    return fig

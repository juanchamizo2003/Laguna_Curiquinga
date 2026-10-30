"""Lo que se está viendo (origen, filtros, pestaña...) se guarda en la dirección de la página.

Al recargar (F5) Streamlit empieza una sesión nueva y solo sobrevive la dirección: de ahí se recupera todo. Al abrir
la app de nuevo, sin esos parámetros, cada cosa arranca en su valor normal. Solo se escribe lo que difiere de ese
valor, así que la dirección queda limpia. El tema y los ajustes de las gráficas no van aquí: viven en otro sitio y se
mantienen siempre.

Streamlit borra el valor de un widget cuando deja de dibujarse (al cambiar de módulo), por eso los widgets guardan
además una copia propia ("_v_<clave>").
"""
import re
from datetime import date

import streamlit as st

_DIA = r"\d{4}-\d{2}-\d{2}"
_MES = r"\d{4}-\d{2}"
_ANIO = r"\d{4}"


def _texto(t):
    return t


def _opcion(*opciones):
    return lambda t: t if t in opciones else None


def _entero(t):
    return int(t) if re.fullmatch(r"\d{1,6}", t) else None


def _ventana(t):
    return int(t) if t in ("7", "14", "31") else None


def _si(t):
    return True if t == "1" else None


def _lista(patron=None):
    return lambda t: [v for v in t.split(",") if v and (patron is None or re.fullmatch(patron, v))]


def _fecha(t):
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


_PERIODOS = ("Días", "Meses", "Años")

# Clave de session_state: (parámetro de la dirección, valor normal, cómo leerlo). Lo que viene de la dirección puede
# estar escrito a mano: aquí se comprueba el formato, y widget() que sea una opción existente.
_ESTADO = {
    # Inicio
    "tipo_seleccion": ("periodo", "En vivo", _opcion(*_PERIODOS)),
    "limite_dias": ("ventana", 7, _ventana),
    "fechas_seleccionadas": ("dias", [], _lista(_DIA)),
    "meses_seleccionados": ("meses", [], _lista(_MES)),
    "anios_seleccionados": ("anios", [], _lista(_ANIO)),
    # Cargar y procesar · Registros
    "reg_tipo_seleccion": ("reg_periodo", "Días", _opcion(*_PERIODOS)),
    "reg_fechas_seleccionadas": ("reg_dias", [], _lista(_DIA)),
    "reg_meses_seleccionados": ("reg_meses", [], _lista(_MES)),
    "reg_anios_seleccionados": ("reg_anios", [], _lista(_ANIO)),
    # Cargar y procesar · Resultados visuales
    "visual_dia_v": ("fotos_dia", None, _fecha),
    "visual_pag": ("fotos_pag", 0, _entero),
}
_WIDGETS = {
    "inicio_modo": ("origen", "Ambos", _texto),
    "chk_filtrado_tabla": ("reg_filtro", False, _si),
    "tabla_estados": ("reg_estados", [], _lista()),
    "tabla_orden": ("reg_orden", "Más recientes", _texto),
    "alertas_filtro": ("alertas", "Todas", _texto),
    "srv_filtro_log": ("registro", "Todo", _texto),
}
_PESTANAS = {
    "cargar_tab": ("pestana", 0, _entero),
    "config_tab": ("ajuste", 0, _entero),
}


def _destino(clave):
    return clave if clave in _ESTADO else f"_v_{clave}"


def _todo():
    return {**_ESTADO, **_WIDGETS, **_PESTANAS}


def _escribir(valor):
    if isinstance(valor, list):
        return ",".join(valor)
    if isinstance(valor, bool):
        return "1" if valor else ""
    return valor.isoformat() if isinstance(valor, date) else str(valor)


def restaurar():
    """Al empezar la sesión (abrir o recargar) recupera lo que indica la dirección."""
    ss = st.session_state
    if ss.get("_recordar_listo"):
        return
    ss["_recordar_listo"] = True
    for clave, (parametro, _, leer) in _todo().items():
        if parametro in st.query_params:
            valor = leer(st.query_params[parametro])
            if valor not in (None, []):
                ss[_destino(clave)] = valor


def widget(clave, opciones):
    """Se llama justo antes de dibujar el widget: le devuelve su valor y descarta lo que ya no sea una opción."""
    ss = st.session_state
    defecto = _WIDGETS[clave][1]
    valor = ss.get(clave)
    if valor is None:
        valor = ss.get(_destino(clave), defecto)
    if isinstance(defecto, list):
        ss[clave] = [v for v in valor if v in opciones]
    else:
        ss[clave] = valor if valor in opciones else defecto


def pestanas(clave, etiquetas):
    """st.tabs que recuerda la pestaña abierta; elegir otra relanza la app para poder guardarla."""
    ss = st.session_state
    # Se fija por su clave y no con default=: si default cambia entre pasadas, Streamlit lo toma por otro widget y
    # la pestaña salta a la anterior
    if ss.get(clave) not in etiquetas:
        guardada = ss.get(_destino(clave), 0)
        ss[clave] = etiquetas[guardada if guardada < len(etiquetas) else 0]
    tabs = st.tabs(etiquetas, key=clave, on_change="rerun")
    ss[_destino(clave)] = etiquetas.index(ss[clave])
    return tabs


def sincronizar():
    """Pasa a la dirección lo que se está viendo; se quita lo que está en su valor normal."""
    ss = st.session_state
    for clave, (parametro, defecto, _) in _todo().items():
        if clave in _WIDGETS and clave in ss:
            # Desmarcar la opción activa de un selector deja None: equivale al valor normal
            ss[_destino(clave)] = defecto if ss[clave] is None else ss[clave]
        valor = ss.get(_destino(clave), defecto)
        texto = _escribir(valor) if valor != defecto else ""
        if not texto:
            st.query_params.pop(parametro, None)
        elif st.query_params.get(parametro) != texto:
            st.query_params[parametro] = texto

import os
import pandas as pd
import streamlit as st

from backend.data_base import obtener_registros, DB_PATH
from backend.calidad import estado_validacion, marcar_atipicas, COLORES_ESTADO, EXCLUIDOS
from backend import config as cfg

def _marca_bd():
    # La fecha de modificación del archivo invalida la caché también cuando escribe el vigilante (otro proceso)
    return os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0

_CLAVES_ATIPICAS = ("atipico_pct", "atipico_ventana_h", "atipico_vecinas")

@st.cache_data(show_spinner=False, max_entries=4)
def _cargar(marca, umbrales):
    return marcar_atipicas(obtener_registros(), dict(umbrales))

def refrescar():
    """Vuelve a leer la base aunque la caché crea que no cambió."""
    _cargar.clear()

def registros():
    """Registros con la marca 'atipica' calculada; la caché se renueva al cambiar la BD o los umbrales."""
    q = cfg.cargar()["calidad"]
    return _cargar(_marca_bd(), tuple((k, q[k]) for k in _CLAVES_ATIPICAS))

def df_registros():
    """DataFrame ordenado por fecha de captura, con la columna 'validacion' calculada."""
    regs = registros()
    if not regs:
        return pd.DataFrame()
    df = pd.DataFrame(regs).sort_values("fecha_captura").reset_index(drop=True)
    umbral = cfg.cargar()["calidad"]["confianza_min"]
    df["validacion"] = [estado_validacion(r, umbral) for r in df.to_dict("records")]
    return df

def color_estado(estado):
    return COLORES_ESTADO.get(estado, "#8b95a3")

def solo_confiables(df):
    if df.empty:
        return df
    return df[~df["validacion"].isin(EXCLUIDOS)].reset_index(drop=True)

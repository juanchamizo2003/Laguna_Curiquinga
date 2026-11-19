import calendar
from datetime import date

import pandas as pd
import streamlit as st

from frontend.components import recordar
from frontend.components.formato import MESES_CORTOS, fecha_legible

TIPOS = ["Días", "Meses", "Años"]               # filtro de la tabla de registros y de la galería de resultados
TIPOS_GRAFICA = ["En vivo"] + TIPOS              # filtro de la gráfica del inicio
VENTANAS_DIAS = (7, 14, 31)                      # atajos de la gráfica: últimos N días con datos
MAX_DIAS_MARCADOS = 31                           # en el calendario se marcan los días a mano, hasta un mes completo
N_EN_VIVO = 10                                   # capturas que muestra el modo en vivo
SEGUNDOS_EN_VIVO = 30                            # cada cuánto se refresca la gráfica en vivo
DIAS_SEMANA = ["L", "M", "X", "J", "V", "S", "D"]
MESES_LARGOS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                "Septiembre", "Octubre", "Noviembre", "Diciembre"]
ANIOS_POR_PAGINA = 12

# El estado del filtro vive en claves globales; la tabla de registros y la galería de resultados usan las suyas
# (prefijos REGISTROS y VISUAL), para que filtrar una no cambie lo que muestran las demás
REGISTROS = "reg_"
VISUAL = "vis_"
CLAVE_POR_TIPO = {"Días": "fechas_seleccionadas", "Meses": "meses_seleccionados", "Años": "anios_seleccionados"}

def _inicializar_estado():
    st.session_state.setdefault("tipo_seleccion", "En vivo")   # al abrir la app, la gráfica arranca en vivo
    st.session_state.setdefault("limite_dias", 7)
    for prefijo in ("", REGISTROS, VISUAL):
        if prefijo:
            st.session_state.setdefault(prefijo + "tipo_seleccion", "Días")
        st.session_state.setdefault(prefijo + "fechas_seleccionadas", [])   # ["2026-04-26", ...]
        st.session_state.setdefault(prefijo + "meses_seleccionados", [])    # ["2026-04", ...]
        st.session_state.setdefault(prefijo + "anios_seleccionados", [])    # ["2026", ...]

def _fechas_de(df):
    if df.empty or "fecha_captura" not in df.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(df["fecha_captura"], errors="coerce")

def _texto_mes(clave):
    """'2026-04' -> 'abr 2026'"""
    anio, mes = clave.split("-")
    return f"{MESES_CORTOS[int(mes) - 1]} {anio}"

def _copiar_a_global(key, clave_global, vacio):
    st.session_state[clave_global] = st.session_state[key] or vacio

def _selector_tipo(key_prefix, opciones=TIPOS, prefijo=""):
    key = f"{key_prefix}_compact_tipo"
    st.session_state[key] = st.session_state[prefijo + "tipo_seleccion"]
    st.segmented_control(
        "Tipo", opciones, key=key, label_visibility="collapsed",
        on_change=_copiar_a_global, args=(key, prefijo + "tipo_seleccion", opciones[0])
    )

def restablecer_filtro():
    """Vuelve a En vivo y borra los días, meses y años marcados."""
    st.session_state.tipo_seleccion = "En vivo"
    st.session_state.limite_dias = 7
    for clave in CLAVE_POR_TIPO.values():
        st.session_state[clave] = []

def _fijar_limite(dias):
    """Atajo 7/14/31: muestra los últimos N días con datos, así que se quitan los días marcados a mano."""
    st.session_state.limite_dias = dias
    st.session_state.fechas_seleccionadas = []

def en_vivo():
    _inicializar_estado()
    return st.session_state.tipo_seleccion == "En vivo"

def aplicar_filtro_temporal(df, ventana_dias=True, prefijo=None):
    """Filtra df según el estado del filtro. Devuelve (df_filtrado, descripción legible).

    ventana_dias=True (gráfica): "En vivo" toma las últimas N_EN_VIVO capturas y Días sin días marcados
    toma los últimos 7/14/31 días con registros. La tabla y la galería pasan False y sin selección ven todo.
    prefijo: de quién es el filtro; por defecto el de la gráfica o, con ventana_dias=False, el de la tabla.
    """
    _inicializar_estado()
    fechas = _fechas_de(df)
    if fechas.dropna().empty:
        return df, "Sin muestras registradas"

    if prefijo is None:
        prefijo = "" if ventana_dias else REGISTROS
    tipo = st.session_state[prefijo + "tipo_seleccion"]
    if tipo == "En vivo":
        ultimas = fechas.dropna().sort_values().index[-N_EN_VIVO:]
        return df[fechas.index.isin(ultimas)], f"En vivo · últimas {N_EN_VIVO} capturas"

    mascara = fechas.notna()
    descripcion = "Todo el historial"
    if tipo == "Días":
        dias = st.session_state[prefijo + "fechas_seleccionadas"]
        if dias:
            mascara = fechas.dt.strftime("%Y-%m-%d").isin(dias)
            descripcion = (fecha_legible(dias[0], con_hora=False) if len(dias) == 1
                           else f"{len(dias)} día(s) marcado(s)")
        elif ventana_dias:
            # Últimos N días *con registros*: con capturas espaciadas una ventana de calendario
            # dejaría la gráfica casi vacía; con capturas diarias ambas cosas coinciden.
            n = st.session_state.limite_dias
            dias_con_datos = sorted(fechas.dropna().dt.normalize().unique())[-n:]
            mascara = fechas.dt.normalize().isin(dias_con_datos)
            descripcion = f"Últimos {n} días con datos"
    elif tipo == "Meses" and st.session_state[prefijo + "meses_seleccionados"]:
        meses = st.session_state[prefijo + "meses_seleccionados"]
        mascara = fechas.dt.strftime("%Y-%m").isin(meses)
        descripcion = ", ".join(_texto_mes(m) for m in sorted(meses))
    elif tipo == "Años" and st.session_state[prefijo + "anios_seleccionados"]:
        anios = st.session_state[prefijo + "anios_seleccionados"]
        mascara = fechas.dt.strftime("%Y").isin(anios)
        descripcion = ", ".join(sorted(anios))

    return df[mascara.to_numpy()], descripcion

def _resumen_seleccion(tipo, prefijo=""):
    """Texto del botón del calendario: lo elegido (un día, mes o año se nombra; varios, se cuentan)."""
    elegidos = st.session_state[prefijo + CLAVE_POR_TIPO[tipo]]
    n = len(elegidos)
    if n == 1:
        return {"Días": lambda v: fecha_legible(v, con_hora=False), "Meses": _texto_mes, "Años": str}[tipo](elegidos[0])
    if tipo == "Días":
        return f"{n} días marcados" if n else "Elegir días"
    if tipo == "Meses":
        return f"{n} meses" if n else "Todos los meses"
    return f"{n} años" if n else "Todos los años"

def render_filtro_compacto(df, key_prefix="default"):
    """Fila de filtros de la gráfica: tipo, ventana de días, calendario y restablecer."""
    _inicializar_estado()
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"{key_prefix}_filtros"):
        _selector_tipo(key_prefix, TIPOS_GRAFICA)
        tipo = st.session_state.tipo_seleccion

        if tipo == "En vivo":
            st.markdown(f"<span class='en-vivo'><i></i>Últimas {N_EN_VIVO} capturas · se actualiza cada "
                        f"{SEGUNDOS_EN_VIVO} s</span>", unsafe_allow_html=True, width="content")
        else:
            if tipo == "Días":
                # Con días marcados a mano ningún atajo queda resaltado: manda lo elegido en el calendario
                manual = bool(st.session_state.fechas_seleccionadas)
                for dias in VENTANAS_DIAS:
                    st.button(f"{dias} días", key=f"{key_prefix}_btn_{dias}d", on_click=_fijar_limite, args=(dias,),
                              type="primary" if not manual and st.session_state.limite_dias == dias else "secondary")
            if st.button(_resumen_seleccion(tipo), icon=":material/calendar_month:", key=f"{key_prefix}_btn_cal",
                         help="Elegir en el calendario"):
                _abrir_borrador(df, "")
                _dialogo_periodo(df)

        st.button("", icon=":material/restart_alt:", key=f"{key_prefix}_btn_reset", help="Restablecer filtro",
                  on_click=restablecer_filtro, type="tertiary")
    # Esta fila se relanza dentro de un fragmento: sin esto, el cambio no llegaría a la dirección
    recordar.sincronizar()

# ---------------------------------------------------------------- calendario (ventana emergente)
# Se edita un borrador (claves cal_*) y solo "Aplicar" lo pasa al filtro; cerrar la ventana lo descarta.
# Streamlit borra el valor de un widget cuando deja de dibujarse (p. ej. el selector de mes al pasar a
# "Meses"), así que el estado vive en claves propias (*_v) y los widgets se rellenan desde ellas cada vez.

def _sincronizar(clave_widget, clave_valor):
    """Callback: copia lo elegido en el widget a la clave propia (si se deselecciona, se conserva lo anterior)."""
    valor = st.session_state.get(clave_widget)
    if valor is not None:
        st.session_state[clave_valor] = valor

def _preparar_widget(clave_widget, clave_valor):
    st.session_state[clave_widget] = st.session_state[clave_valor]

def _abrir_borrador(df, prefijo=""):
    """Copia al borrador el filtro de quien abre la ventana (prefijo: "" la gráfica, REGISTROS, VISUAL)."""
    ss = st.session_state
    ss.cal_prefijo = prefijo
    tipo = ss[prefijo + "tipo_seleccion"]
    ss.cal_tipo_v = tipo if tipo in TIPOS else "Días"
    ss.cal_dias = list(ss[prefijo + "fechas_seleccionadas"])
    ss.cal_meses = list(ss[prefijo + "meses_seleccionados"])
    ss.cal_anios = list(ss[prefijo + "anios_seleccionados"])
    # La vista arranca en el último día marcado, o en la captura más reciente
    fechas = _fechas_de(df).dropna()
    referencia = (pd.Timestamp(max(ss.cal_dias)) if ss.cal_dias else
                  fechas.max() if not fechas.empty else pd.Timestamp(date.today()))
    ss.cal_mes_v = referencia.month
    ss.cal_anio_v = referencia.year
    ss.cal_anio_meses = referencia.year
    ss.cal_pagina_anios = referencia.year - ANIOS_POR_PAGINA + 1

def _alternar(clave_lista, valor, limite=None):
    lista = st.session_state[clave_lista]
    if valor in lista:
        lista.remove(valor)
    elif limite and len(lista) >= limite:
        # Aviso dentro de la ventana: un st.toast lanzado desde aquí rompía la página
        st.session_state.cal_aviso = f"Ya marcaste {limite} días, el máximo. Desmarca uno para elegir otro."
    else:
        lista.append(valor)

def _mover_mes(paso):
    ss = st.session_state
    total = ss.cal_anio_v * 12 + ss.cal_mes_v - 1 + paso
    ss.cal_anio_v, ss.cal_mes_v = total // 12, total % 12 + 1

def _sumar(clave, paso):
    st.session_state[clave] += paso

# Solo se pueden marcar días, meses y años con capturas ("sin" sale desactivado): uno vacío dejaba la gráfica
# sin nada. Uno ya marcado sigue activo aunque no tenga datos, para poder desmarcarlo.
def _estado(valor, seleccion, con_datos):
    return "sel" if valor in seleccion else ("con" if valor in con_datos else "sin")

def _cuadricula_dias(con_datos, anios):
    ss = st.session_state
    # Solo la gráfica limita los días (más de un mes de puntos no se lee); la tabla y la galería no
    limite = MAX_DIAS_MARCADOS if ss.cal_prefijo == "" else None
    # El aviso ocupa el sitio de la ayuda: así nada se mueve cuando aparece
    aviso = ss.pop("cal_aviso", None)
    if aviso:
        st.markdown(f"<div class='cal-ayuda cal-aviso'>{aviso}</div>", unsafe_allow_html=True)
    else:
        tope = f" (hasta {limite})" if limite else ""
        st.markdown(f"<div class='cal-ayuda'>Marca los días con capturas que quieras ver{tope}, "
                    f"en cualquier mes o año · <b>{len(ss.cal_dias)}</b> marcados</div>", unsafe_allow_html=True)

    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="cal_nav"):
        st.button("", icon=":material/chevron_left:", key="cal_mes_ant", on_click=_mover_mes, args=(-1,))
        _preparar_widget("cal_vista_mes", "cal_mes_v")
        st.selectbox("Mes", list(range(1, 13)), key="cal_vista_mes", format_func=lambda m: MESES_LARGOS[m - 1],
                     label_visibility="collapsed", on_change=_sincronizar, args=("cal_vista_mes", "cal_mes_v"))
        if ss.cal_anio_v not in anios:
            anios = sorted(set(anios) | {ss.cal_anio_v})
        _preparar_widget("cal_vista_anio", "cal_anio_v")
        st.selectbox("Año", anios, key="cal_vista_anio", label_visibility="collapsed",
                     on_change=_sincronizar, args=("cal_vista_anio", "cal_anio_v"))
        st.button("", icon=":material/chevron_right:", key="cal_mes_sig", on_click=_mover_mes, args=(1,))

    anio, mes = ss.cal_anio_v, ss.cal_mes_v
    for col, letra in zip(st.columns(7, gap="small"), DIAS_SEMANA):
        col.markdown(f"<div class='cal-semana'>{letra}</div>", unsafe_allow_html=True)
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        for col, dia in zip(st.columns(7, gap="small"), semana):
            iso = dia.isoformat()
            estado = _estado(iso, ss.cal_dias, con_datos)
            fuera = "f" if dia.month != mes else "m"
            col.button(str(dia.day), key=f"cal_d_{estado}_{fuera}_{iso}", width="stretch",
                       type="primary" if estado == "sel" else "secondary", disabled=estado == "sin",
                       on_click=_alternar, args=("cal_dias", iso, limite))

def _cuadricula_meses(con_datos):
    ss = st.session_state
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="center", key="cal_nav_m"):
        st.button("", icon=":material/chevron_left:", key="cal_anio_ant", on_click=_sumar, args=("cal_anio_meses", -1))
        st.markdown(f"<div class='cal-titulo'>{ss.cal_anio_meses}</div>", unsafe_allow_html=True, width="content")
        st.button("", icon=":material/chevron_right:", key="cal_anio_sig", on_click=_sumar, args=("cal_anio_meses", 1))
    for fila in range(3):
        for col, mes in zip(st.columns(4, gap="small"), range(fila * 4 + 1, fila * 4 + 5)):
            clave = f"{ss.cal_anio_meses}-{mes:02d}"
            estado = _estado(clave, ss.cal_meses, con_datos)
            col.button(MESES_LARGOS[mes - 1], key=f"cal_m_{estado}_{clave}", width="stretch",
                       type="primary" if estado == "sel" else "secondary", disabled=estado == "sin",
                       on_click=_alternar, args=("cal_meses", clave))

def _cuadricula_anios(con_datos):
    ss = st.session_state
    inicio = ss.cal_pagina_anios
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="center", key="cal_nav_a"):
        st.button("", icon=":material/chevron_left:", key="cal_pag_ant", on_click=_sumar,
                  args=("cal_pagina_anios", -ANIOS_POR_PAGINA))
        st.markdown(f"<div class='cal-titulo'>{inicio} – {inicio + ANIOS_POR_PAGINA - 1}</div>",
                    unsafe_allow_html=True, width="content")
        st.button("", icon=":material/chevron_right:", key="cal_pag_sig", on_click=_sumar,
                  args=("cal_pagina_anios", ANIOS_POR_PAGINA))
    for fila in range(ANIOS_POR_PAGINA // 4):
        for col, anio in zip(st.columns(4, gap="small"), range(inicio + fila * 4, inicio + fila * 4 + 4)):
            clave = str(anio)
            estado = _estado(clave, ss.cal_anios, con_datos)
            col.button(clave, key=f"cal_a_{estado}_{clave}", width="stretch",
                       type="primary" if estado == "sel" else "secondary", disabled=estado == "sin",
                       on_click=_alternar, args=("cal_anios", clave))

def _aplicar_borrador(tipo):
    ss = st.session_state
    prefijo = ss.cal_prefijo
    ss[prefijo + "tipo_seleccion"] = tipo
    ss[prefijo + "fechas_seleccionadas"] = sorted(ss.cal_dias)
    ss[prefijo + "meses_seleccionados"] = sorted(ss.cal_meses)
    ss[prefijo + "anios_seleccionados"] = sorted(ss.cal_anios)

def _limpiar_borrador():
    clave = {"Días": "cal_dias", "Meses": "cal_meses", "Años": "cal_anios"}[st.session_state.cal_tipo_v]
    st.session_state[clave] = []

@st.dialog("Elegir periodo", width="medium")
def _dialogo_periodo(df):
    ss = st.session_state
    fechas = _fechas_de(df).dropna()
    # Los atajos 7/14/31 viven solo en la fila de la gráfica: aquí los días se marcan a mano
    tipo = ss.cal_tipo_v
    _preparar_widget("cal_tipo", "cal_tipo_v")
    st.segmented_control("Tipo de periodo", TIPOS, key="cal_tipo", label_visibility="collapsed", width="stretch",
                         on_change=_sincronizar, args=("cal_tipo", "cal_tipo_v"))

    if tipo == "Días":
        anios = sorted(set(fechas.dt.year) | {date.today().year})
        _cuadricula_dias(set(fechas.dt.strftime("%Y-%m-%d")), list(range(anios[0] - 1, anios[-1] + 1)))
    elif tipo == "Meses":
        _cuadricula_meses(set(fechas.dt.strftime("%Y-%m")))
    else:
        _cuadricula_anios(set(fechas.dt.strftime("%Y")))

    st.markdown("<div class='cal-ayuda'><i class='cal-punto'></i> con capturas · sin marcar = "
                + (f"los últimos {ss.limite_dias} días con datos" if tipo == "Días" and ss.cal_prefijo == ""
                   else "todo el historial") + "</div>",
                unsafe_allow_html=True)
    with st.container(horizontal=True, gap="small", key="cal_pie"):
        st.button("Limpiar", icon=":material/close:", key="cal_limpiar", width="stretch", on_click=_limpiar_borrador)
        # El paso al filtro va en el callback: corre siempre antes de la recarga, aunque la ventana
        # se haya abierto desde un fragmento
        if st.button("Aplicar", icon=":material/check:", key="cal_aplicar", type="primary", width="stretch",
                     on_click=_aplicar_borrador, args=(tipo,)):
            st.rerun()

def restablecer_periodo(prefijo):
    """Quita los días, meses y años elegidos: vuelve a verse todo."""
    for clave in CLAVE_POR_TIPO.values():
        st.session_state[prefijo + clave] = []

def periodo_filtrado(prefijo):
    """True si el filtro de periodo de la tabla o de la galería tiene algo elegido."""
    _inicializar_estado()
    ss = st.session_state
    return bool(ss[prefijo + CLAVE_POR_TIPO[ss[prefijo + "tipo_seleccion"]]])

def render_filtro_periodo(df, prefijo, key_prefix):
    """El filtro del Inicio para la tabla de registros y la galería de resultados: un botón con lo elegido que abre
    la misma ventana (Días / Meses / Años, solo los que tienen capturas) y ↺ para quitarlo. Sin elegir nada se ve todo."""
    ss = st.session_state
    filtrado = periodo_filtrado(prefijo)
    tipo = ss[prefijo + "tipo_seleccion"]
    if st.button(_resumen_seleccion(tipo, prefijo) if filtrado else "Elegir periodo", icon=":material/calendar_month:",
                 key=f"{key_prefix}_btn_cal", type="primary" if filtrado else "secondary",
                 help="Filtrar por días, meses o años con capturas"):
        _abrir_borrador(df, prefijo)
        _dialogo_periodo(df)
    st.button("", icon=":material/restart_alt:", key=f"{key_prefix}_btn_reset", type="tertiary",
              help="Restablecer filtro: ver todo", disabled=not filtrado, on_click=restablecer_periodo, args=(prefijo,))

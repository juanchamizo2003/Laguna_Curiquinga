import os
import calendar
import re
import html
import json
import hashlib
from datetime import datetime, timedelta
import streamlit as st

from backend import acceso
from backend.miniaturas import crear_miniatura, ruta_miniatura
from frontend.components.formato import formatear_m2, fecha_legible
from frontend.components.filtro_temporal import DIAS_SEMANA, MESES_LARGOS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Streamlit sirve frontend/static en /app/static (server.enableStaticServing): el navegador cachea las fotos
DIR_ESTATICO = os.path.join(BASE_DIR, "frontend", "static", "visor")
ANCHO_VISOR = 1600
N_CARRUSEL = 10
FOTOS_POR_PAGINA = 12  # 4 filas de 3
COLUMNAS_GALERIA = 3
SEGUNDOS_ROTACION = 15

def js_seguro(html):
    """DOMPurify (st.html) borra los <script> cuyo texto contiene etiquetas: dentro del script
    cada '<' que abre una etiqueta se escribe como \x3c, que en JS es el mismo carácter."""
    return re.sub(r"<script>(.*?)</script>",
                  lambda m: "<script>" + re.sub(r"<(?=[/\w!])", lambda _: "\\x3c", m.group(1)) + "</script>",
                  html, flags=re.S)

def texto_confianza(item):
    confianza = item.get("confianza")
    # Registros anteriores a la columna 'confianza' llegan como None/NaN
    return f"{confianza:.0%}" if isinstance(confianza, (int, float)) and confianza == confianza else "—"

def _copia_reducida(item, clave):
    """Ruta en disco de una copia de la foto a ANCHO_VISOR px; la genera si falta o quedó vieja ("" si no hay foto)."""
    origen = os.path.join(BASE_DIR, str(item.get(clave) or ""))
    if not os.path.isfile(origen):
        return ""
    prefijo = "o_" if clave == "ruta_original" else "p_"
    destino = os.path.join(DIR_ESTATICO, prefijo + os.path.splitext(os.path.basename(origen))[0] + ".jpg")
    if not (os.path.exists(destino) and os.path.getmtime(destino) >= os.path.getmtime(origen)):
        if not crear_miniatura(origen, destino, ancho=ANCHO_VISOR):
            return ""
    return destino

def borrar_copias(item):
    """Quita las copias reducidas de una captura eliminada (si no, su foto seguiría en la carpeta del visor)."""
    for clave, prefijo in (("ruta_original", "o_"), ("ruta_procesada", "p_")):
        nombre = os.path.splitext(os.path.basename(str(item.get(clave) or "")))[0]
        ruta = os.path.join(DIR_ESTATICO, f"{prefijo}{nombre}.jpg")
        if nombre and os.path.isfile(ruta):
            os.remove(ruta)

def _url_estatica(item, clave):
    """URL servida por Streamlit de la copia reducida (el navegador la cachea)."""
    destino = _copia_reducida(item, clave)
    if not destino:
        return ""
    return f"/app/static/visor/{os.path.basename(destino)}?v={int(os.path.getmtime(destino))}"

def _datos_carrusel(registros):
    return [{
        "o": _url_estatica(r, "ruta_original"),
        "p": _url_estatica(r, "ruta_procesada"),
        "fecha": fecha_legible(r.get("fecha_captura", "")),
        "area": formatear_m2(r.get("area", 0)),
        "conf": texto_confianza(r),
        "color": str(r.get("color_hex") or "#8b95a3").upper(),
    } for r in registros[:N_CARRUSEL]]

def boton_tema():
    """Interruptor claro/oscuro de la barra lateral; el clic y su etiqueta los atiende el script de app.py."""
    pase = f' data-pase="{acceso.emitir_pase()}"' if acceso.protegido() and st.session_state.get("autenticado") else ""
    st.html(f'<button class="tema-toggle" type="button" aria-label="Cambiar entre tema claro y oscuro"{pase}>'
            '<i class="t-sol"></i><i class="t-luna"></i></button>', width="content")

def _texto_vivo(n):
    return "Última captura en vivo" if n == 1 else f"Últimas {n} capturas en vivo"

def render_visor_laguna(registros, todas=None, key_prefix="visor_default", periodo=None):
    """Carrusel de las últimas capturas: rota solo, se amplía al pulsar la foto y sus miniaturas
    muestran las siguientes. Todo corre en el navegador para no relanzar el script cada 15 s.
    todas: registros (más recientes primero) para la galería. periodo: texto del filtro de la gráfica
    cuando hay uno; entonces la galería muestra solo las fotos de ese periodo (el carrusel no cambia)."""
    with st.container(key=f"{key_prefix}_card"):
        if not registros:
            # El mismo aviso gris que la gráfica sin datos
            st.markdown("<div class='graf-vacio'><b>Todavía no hay fotos</b>"
                        "<span>Aquí aparecerán las últimas capturas de este origen.</span></div>",
                        unsafe_allow_html=True)
            return
        datos = json.dumps(_datos_carrusel(registros)).replace("</", "<\\/")
        uid = "vl" + hashlib.md5(datos.encode()).hexdigest()[:10]
        iconos = json.dumps({k: _SVG.format(v) for k, v in _ICONOS.items()})
        st.html(js_seguro(_PLANTILLA.replace("__UID__", uid).replace("__DATOS__", datos).replace("__ICONOS__", iconos)
                          .replace("__MS__", str(SEGUNDOS_ROTACION * 1000))
                          .replace("__VIVO__", _texto_vivo(min(len(registros), N_CARRUSEL)))), unsafe_allow_javascript=True)
        todas = todas if todas is not None else registros
        if periodo:
            etiqueta, clave = f"Ver fotos del periodo ({len(todas)})", f"{key_prefix}_ver_periodo"
        else:
            etiqueta = "Ver la última foto" if len(todas) == 1 else f"Ver las últimas {len(todas)} fotos"
            clave = f"{key_prefix}_ver_todas"
        if st.button(etiqueta, icon=":material/photo_library:", width="stretch", key=clave, disabled=not todas,
                     help=f"Fotos del periodo filtrado en la gráfica: {periodo}" if periodo else None):
            st.session_state.galeria_sel = None
            st.session_state.galeria_pag = 0
            st.session_state.pop("galeria_dia_v", None)
            st.session_state.pop("galeria_dia_mes", None)
            _modo_comparar(False)
            galeria_fotos(todas, periodo)
        elif st.session_state.pop("galeria_reabrir", False):
            galeria_fotos(todas, periodo)

def _metricas_foto(r):
    """Datos de la foto abierta, con el mismo aspecto que la ampliación del carrusel."""
    color = str(r.get("color_hex") or "#8b95a3").upper()
    return f"""<div class="vl-met vl-met-modal">
        <div><span>Área</span><b>{formatear_m2(r.get("area", 0))}</b></div>
        <div><span>Confianza</span><b>{texto_confianza(r)}</b></div>
        <div><span>Color</span><b><i class="vl-sw" style="background:{color}"></i>{color}</b></div>
        <div><span>Fecha y hora</span><b>{fecha_legible(r.get("fecha_captura", ""))}</b></div>
    </div>"""

def _datos_foto(r, orden=0):
    """Datos fijos sobre la parte baja de cada foto de la galería; orden: su número al comparar (1 o 2)."""
    color = str(r.get("color_hex") or "#8b95a3").upper()
    marca = f"<span class='gal-orden'>{orden}</span>" if orden else ""
    return (f"<div class='gal-datos'>{marca}<b>{formatear_m2(r.get('area', 0))}</b>"
            f"<span>{fecha_legible(r.get('fecha_captura', ''))}</span>"
            f"<span><i class='vl-sw' style='background:{color}'></i>{color}</span>"
            f"<span title='Confianza del modelo'>{texto_confianza(r)}</span></div>")

def _texto_galeria(registros, periodo, dia=None):
    """Encabezado: en vivo, las últimas capturas; con filtro, el periodo y sus fechas reales;
    con un día elegido, ese día, sus capturas y entre qué áreas se movió."""
    n = len(registros)
    if dia:
        chip = ("<span class='gal-chip filtro'><i></i>Filtro</span>" if periodo
                else "<span class='gal-chip vivo'><i></i>En vivo</span>")
        areas = [float(r.get("area", 0)) for r in registros]
        rango = f" · de {formatear_m2(min(areas))} a {formatear_m2(max(areas))}" if n > 1 else ""
        return (f"<div class='gal-titulo'>{chip}{fecha_legible(dia, con_hora=False)} · "
                f"{n} captura(s){rango}</div>")
    if not periodo:
        return (f"<div class='gal-titulo'><span class='gal-chip vivo'><i></i>En vivo</span>"
                f"Últimas {n} captura(s), de la más reciente a la más antigua</div>")
    fechas = sorted(str(r.get("fecha_captura")) for r in registros if r.get("fecha_captura"))
    rango = ""
    if fechas:
        desde, hasta = fecha_legible(fechas[0], con_hora=False), fecha_legible(fechas[-1], con_hora=False)
        rango = f" · {desde}" if desde == hasta else f" · del {desde} al {hasta}"
    return (f"<div class='gal-titulo'><span class='gal-chip filtro'><i></i>Filtro</span>"
            f"{html.escape(periodo)} · {n} captura(s){rango}</div>")

def _ir_foto(indice):
    st.session_state.galeria_sel = indice

def _cerrar_foto():
    """Vuelve a la cuadrícula, en la página de la foto que se estaba viendo."""
    sel = st.session_state.get("galeria_sel")
    if sel is not None:
        st.session_state.galeria_pag = sel // FOTOS_POR_PAGINA
    st.session_state.galeria_sel = None

def _ir_pagina(pagina):
    st.session_state.galeria_pag = pagina

def _al_cerrar_galeria():
    """La X del diálogo: con una foto abierta vuelve a la cuadrícula; comparando, al panel de comparar con las
    mismas fechas (para cambiar solo una y volver a comparar). En la cuadrícula cierra la galería."""
    ss = st.session_state
    if ss.get("galeria_sel") is not None:
        _cerrar_foto()
        ss.galeria_reabrir = True
    elif ss.get("galeria_comparar") and len(ss.get("galeria_elegidas", [])) == 2:
        ss.galeria_elegidas = []
        ss.galeria_reabrir = True
    else:
        _modo_comparar(False)

def _modo_comparar(activo):
    ss = st.session_state
    ss.galeria_comparar = activo
    ss.galeria_elegidas = []
    # Las fechas del panel se recuerdan solo mientras se sigue comparando
    for lado in ("Antes", "Después"):
        for clave in (f"galeria_cmp_sel_{lado}", f"galeria_cmp_dia_{lado}_v", f"galeria_cmp_mes_{lado}"):
            ss.pop(clave, None)

def _pulsar_foto(indice):
    """Clic en una foto: la abre o, en modo comparar, la marca (como mucho dos)."""
    ss = st.session_state
    if not ss.get("galeria_comparar"):
        _ir_foto(indice)
        return
    elegidas = ss.setdefault("galeria_elegidas", [])
    if indice in elegidas:
        elegidas.remove(indice)
    elif len(elegidas) < 2:
        elegidas.append(indice)

def _fecha_de(r):
    try:
        return datetime.fromisoformat(str(r.get("fecha_captura")))
    except ValueError:
        return None

def _elegir_par(a, b):
    st.session_state.galeria_elegidas = [a, b]

def _elegir_dia(lado, dia):
    st.session_state[f"galeria_cmp_dia_{lado}_v"] = dia

def _mover_mes(clave_mes, meses):
    ss = st.session_state
    anio, mes = ss[clave_mes]
    total = anio * 12 + mes - 1 + meses
    ss[clave_mes] = (total // 12, total % 12 + 1)

def _calendario(slug, clave_mes, cuenta, dia_actual, al_elegir, args=()):
    """Calendario pequeño para dentro de un menú emergente: solo los días con capturas (con punto) se pueden
    pulsar y el elegido va resaltado; ‹ › cambian de mes y « » de año. Al pulsar un día el script de app.py
    cierra el menú. cuenta: {fecha: nº de capturas}; al_elegir(*args, dia).
    Sin día elegido (dia_actual None) abre en el mes de la captura más reciente."""
    ss = st.session_state
    if clave_mes not in ss:
        referencia = dia_actual or max(cuenta)
        ss[clave_mes] = (referencia.year, referencia.month)
    anio, mes = ss[clave_mes]
    with st.container(key=f"galeria_cmp_calendario_{slug}"):
        with st.container(horizontal=True, vertical_alignment="center", gap=None, key=f"galeria_cmp_calnav_{slug}"):
            for icono, meses in ((":material/keyboard_double_arrow_left:", -12), (":material/chevron_left:", -1)):
                st.button("", icon=icono, key=f"galeria_{slug}_mover_{meses}", on_click=_mover_mes,
                          args=(clave_mes, meses), type="tertiary")
            st.markdown(f"<div class='cal-titulo'>{MESES_LARGOS[mes - 1]} {anio}</div>", unsafe_allow_html=True,
                        width="stretch")
            for icono, meses in ((":material/chevron_right:", 1), (":material/keyboard_double_arrow_right:", 12)):
                st.button("", icon=icono, key=f"galeria_{slug}_mover_{meses}", on_click=_mover_mes,
                          args=(clave_mes, meses), type="tertiary")
        for col, letra in zip(st.columns(7, gap=None), DIAS_SEMANA):
            col.markdown(f"<div class='cal-semana'>{letra}</div>", unsafe_allow_html=True)
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
            for col, dia in zip(st.columns(7, gap=None), semana):
                con = dia in cuenta
                estado = "sel" if dia == dia_actual else ("con" if con else "sin")
                fuera = "f" if dia.month != mes else "m"
                col.button(str(dia.day), key=f"cal_d_{estado}_{fuera}_{slug}_{dia.isoformat()}", width="stretch",
                           type="primary" if estado == "sel" else "tertiary", disabled=not con,
                           on_click=al_elegir, args=(*args, dia))

def _selector_fecha(registros, por_dia, lado, por_defecto):
    """Día (menú con calendario) y captura de ese día para una de las dos fotos, en una sola línea.
    Devuelve (índice de la captura, aviso). Al volver de una comparación arranca en las fotos comparadas."""
    dias = sorted(por_dia)
    ss = st.session_state
    previa = ss.get(f"galeria_cmp_sel_{lado}")
    if previa is not None and 0 <= previa < len(registros) and _fecha_de(registros[previa]):
        por_defecto = _fecha_de(registros[previa]).date()
    dia = ss.get(f"galeria_cmp_dia_{lado}_v") or por_defecto
    aviso = ""
    if dia not in por_dia:
        cercano = min(dias, key=lambda d: abs((d - dia).days))
        aviso = (f"No hay capturas el {fecha_legible(dia, con_hora=False)}; "
                 f"se usa el {fecha_legible(cercano, con_hora=False)}.")
        dia = cercano
    indices = por_dia[dia]
    area = lambda i: float(registros[i].get("area", 0))
    hora = lambda i: f"{_fecha_de(registros[i]):%H:%M}"
    texto = lambda i: f"{hora(i)} · {formatear_m2(area(i))}"
    slug = "antes" if lado == "Antes" else "despues"

    st.markdown(f"<span class='cmp-lbl'>{lado}</span>", unsafe_allow_html=True, width="content")
    with st.popover(fecha_legible(dia, con_hora=False), icon=":material/calendar_month:", key=f"galeria_cmp_pop_{slug}",
                    help=f"{len(indices)} captura(s) ese día" + (f" · de {formatear_m2(min(map(area, indices)))} a "
                                                                  f"{formatear_m2(max(map(area, indices)))}"
                                                                  if len(indices) > 1 else "")):
        _calendario(slug, f"galeria_cmp_mes_{lado}", {d: len(v) for d, v in por_dia.items()}, dia, _elegir_dia, (lado,))

    # Con una foto por minuto un día tiene cientos: arriba van resúmenes del día y debajo todas, por hora
    # (al escribir "14:3" la lista se filtra). Por defecto la mediana: la mayor o la menor suelen ser fotos raras
    # (niebla parcial, reflejos), la mediana es la captura típica del día, como en las alertas.
    resumen = {}
    if len(indices) > 1:
        por_area = sorted(indices, key=area)
        minutos = lambda i: _fecha_de(registros[i]).hour * 60 + _fecha_de(registros[i]).minute
        mediodia = min(indices, key=lambda i: abs(minutos(i) - 720))
        lejos = abs(minutos(mediodia) - 720) > 90
        resumen = {
            "mediana": ("≈ Mediana del día", por_area[(len(por_area) - 1) // 2]),
            "max": ("▲ Mayor área", por_area[-1]),
            "min": ("▼ Menor área", por_area[0]),
            "mediodia": ("☀ Más cercana a mediodía" if lejos else "☀ Mediodía", mediodia),
        }
    opciones = list(resumen) + indices
    inicial = previa if previa in indices else ("mediana" if resumen else indices[0])
    elegido = st.selectbox(
        "Captura", opciones, index=opciones.index(inicial), key=f"galeria_cmp_hora_{lado}_{dia}", width=230,
        format_func=lambda o: f"{resumen[o][0]} · {texto(resumen[o][1])}" if o in resumen else texto(o),
        label_visibility="collapsed")
    return (resumen[elegido][1] if elegido in resumen else elegido), aviso

def _panel_comparar(registros):
    """Una línea: Antes [día] [captura] → Después [día] [captura] [Comparar]; debajo, atajos en texto.
    Marcar dos fotos en la cuadrícula sigue valiendo."""
    por_dia = {}
    for i, r in enumerate(registros):
        fecha = _fecha_de(r)
        if fecha:
            por_dia.setdefault(fecha.date(), []).append(i)
    if not por_dia:
        return
    for indices in por_dia.values():
        indices.sort(key=lambda i: _fecha_de(registros[i]))
    dias = sorted(por_dia)
    con_fecha = [i for i in range(len(registros)) if _fecha_de(registros[i])]
    primera = min(con_fecha, key=lambda i: _fecha_de(registros[i]))
    ultima = max(con_fecha, key=lambda i: _fecha_de(registros[i]))
    fecha_ultima = _fecha_de(registros[ultima])

    with st.container(key="galeria_cmp_fechas"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_cmp_fila"):
            antes, aviso_a = _selector_fecha(registros, por_dia, "Antes", dias[0])
            st.markdown("<span class='cmp-flecha'>→</span>", unsafe_allow_html=True, width="content")
            despues, aviso_b = _selector_fecha(registros, por_dia, "Después", dias[-1])
            st.space("stretch")
            st.button("Comparar", icon=":material/compare:", type="primary", key="galeria_cmp_ir",
                      on_click=_elegir_par, args=(antes, despues), disabled=antes == despues,
                      help="Elige dos capturas distintas" if antes == despues else None)
        # Atajos como enlaces; solo los que tienen sentido con estas fotos
        atajos = [("Primera y última", primera)] if primera != ultima else []
        for etiqueta, dias_atras in (("Hace 1 semana", 7), ("Hace 1 mes", 30), ("Hace 1 año", 365)):
            objetivo = fecha_ultima - timedelta(days=dias_atras)
            previa = min(con_fecha, key=lambda i: abs((_fecha_de(registros[i]) - objetivo).total_seconds()))
            if previa != ultima and fecha_ultima - _fecha_de(registros[previa]) >= timedelta(days=dias_atras / 2):
                atajos.append((etiqueta, previa))
        if atajos:
            with st.container(horizontal=True, vertical_alignment="center", gap=None, key="galeria_cmp_atajos"):
                st.markdown("<span class='cmp-atajos-tit'>Rápido:</span>", unsafe_allow_html=True, width="content")
                for etiqueta, previa in atajos:
                    st.button(etiqueta, key=f"galeria_cmp_atajo_{etiqueta}", type="tertiary", on_click=_elegir_par,
                              args=(previa, ultima), help=f"Compara la última captura con la de "
                                                         f"{fecha_legible(registros[previa].get('fecha_captura'))}")
        for aviso in filter(None, (aviso_a, aviso_b)):
            st.markdown(f"<p class='cmp-sel-aviso'>{aviso}</p>", unsafe_allow_html=True)

def _tiempo_entre(a, b):
    """'24 días', '3 h'... entre dos fechas de captura."""
    try:
        segundos = abs((datetime.fromisoformat(str(b)) - datetime.fromisoformat(str(a))).total_seconds())
    except ValueError:
        return "—"
    dias = int(segundos // 86400)
    if dias >= 365:
        return f"{dias / 365:.1f} años".replace(".", ",")
    if dias >= 1:
        return f"{dias} día" + ("s" if dias != 1 else "")
    return f"{int(segundos // 3600)} h" if segundos >= 3600 else f"{int(segundos // 60)} min"

def _metricas_comparacion(antes, despues):
    a, b = float(antes.get("area", 0)), float(despues.get("area", 0))
    dif = b - a
    pct = dif / a * 100 if a else 0
    tono = "up" if dif > 0 else ("down" if dif < 0 else "")
    signo = "+" if dif > 0 else ("−" if dif < 0 else "")
    ca, cb = (str(r.get("color_hex") or "#8b95a3").upper() for r in (antes, despues))
    tiempo = _tiempo_entre(antes.get("fecha_captura"), despues.get("fecha_captura"))
    return f"""<div class="vl-met vl-met-modal cmp-met">
        <div><span>Área</span><b>{formatear_m2(a).removesuffix(" m²")} → {formatear_m2(b)}</b></div>
        <div><span>Cambio</span><b class="cmp-{tono}">{signo}{formatear_m2(abs(dif))} · {signo}{f"{abs(pct):.1f}".replace(".", ",")} %</b></div>
        <div><span>Color del agua</span><b><i class="vl-sw" style="background:{ca}"></i>{ca}
            → <i class="vl-sw" style="background:{cb}"></i>{cb}</b></div>
        <div><span>Tiempo entre fotos</span><b>{tiempo}</b></div>
    </div>"""

_COMPARADOR = """
<div class="cmp __MODO__" id="__UID__">
  <div class="cmp-lado"><img src="__A__" alt="Antes"><span class="cmp-et">Antes · __FA__</span></div>
  <div class="cmp-lado cmp-b"><img src="__B__" alt="Después"><span class="cmp-et">Después · __FB__</span></div>
  <div class="cmp-linea"><i></i></div>
  <input type="range" min="0" max="100" value="50" step="0.5" aria-label="Deslizar entre antes y después">
</div>
<script>
(() => {
  const caja = document.getElementById("__UID__");
  if (!caja || caja.dataset.listo) return;
  caja.dataset.listo = "1";
  const rango = caja.querySelector("input");
  const mover = () => caja.style.setProperty("--pos", rango.value + "%");
  rango.addEventListener("input", mover);
  mover();
})();
</script>"""

def _volver_a_elegir():
    st.session_state.galeria_elegidas = []

def _comparacion(registros, elegidas):
    """Dos capturas: la más antigua a la izquierda ("Antes") y la reciente a la derecha ("Después"),
    con un deslizador para pasar de una a otra o una al lado de la otra."""
    i_antes, i_despues = sorted(elegidas, key=lambda i: str(registros[i].get("fecha_captura")))
    antes, despues = registros[i_antes], registros[i_despues]
    # Al volver con la X, el panel de comparar arranca en estas dos fotos
    st.session_state.galeria_cmp_sel_Antes, st.session_state["galeria_cmp_sel_Después"] = i_antes, i_despues
    st.session_state.galeria_cmp_dia_Antes_v = _fecha_de(antes).date() if _fecha_de(antes) else None
    st.session_state["galeria_cmp_dia_Después_v"] = _fecha_de(despues).date() if _fecha_de(despues) else None
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_barra"):
        # Lo mismo que la X, pero a la vista: volver al panel con estas fechas para cambiar una
        st.button("Cambiar fotos", icon=":material/arrow_back:", key="galeria_cmp_volver", type="tertiary",
                  on_click=_volver_a_elegir, help="Volver a elegir las fechas (se mantienen las de ahora)")
        modo = st.segmented_control("Modo", ["Deslizador", "Lado a lado"], default="Deslizador",
                                    key="galeria_cmp_modo", label_visibility="collapsed") or "Deslizador"
        vista = st.segmented_control("Vista", ["Original", "Procesada (IA)"], default="Procesada (IA)",
                                     key="galeria_cmp_vista", label_visibility="collapsed") or "Procesada (IA)"
    clave = "ruta_original" if vista == "Original" else "ruta_procesada"
    url_a, url_b = _url_estatica(antes, clave), _url_estatica(despues, clave)
    if not (url_a and url_b):
        st.warning("No se encuentra el archivo de alguna de las dos imágenes.")
    else:
        uid = "cmp" + hashlib.md5(f"{url_a}{url_b}{modo}".encode()).hexdigest()[:10]
        st.html(js_seguro(_COMPARADOR.replace("__UID__", uid).replace("__A__", url_a).replace("__B__", url_b)
                          .replace("__MODO__", "deslizar" if modo == "Deslizador" else "lado")
                          .replace("__FA__", html.escape(fecha_legible(antes.get("fecha_captura", ""))))
                          .replace("__FB__", html.escape(fecha_legible(despues.get("fecha_captura", ""))))),
                unsafe_allow_javascript=True)
    st.markdown(_metricas_comparacion(antes, despues), unsafe_allow_html=True)

def foto_ampliada(registros, sel, extra=None):
    """Una foto en grande, como la ampliación del carrusel: flechas y Original/Procesada arriba, datos debajo.
    La usan la galería del Inicio y los resultados de la carga; extra() dibuja algo más en la barra de arriba."""
    total, r = len(registros), registros[sel]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_barra"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_nav",
                          width="content"):
            st.button("", icon=":material/chevron_left:", key="galeria_ant", disabled=sel == 0,
                      on_click=_ir_foto, args=(sel - 1,), help="Foto anterior")
            st.markdown(f"<p class='gal-pag'>{sel + 1}/{total}</p>", unsafe_allow_html=True, width="content")
            st.button("", icon=":material/chevron_right:", key="galeria_sig", disabled=sel == total - 1,
                      on_click=_ir_foto, args=(sel + 1,), help="Foto siguiente")
        vista = st.segmented_control("Vista", ["Original", "Procesada (IA)"], default="Procesada (IA)",
                                     key="galeria_vista", label_visibility="collapsed",
                                     width="stretch") or "Procesada (IA)"
        if extra:
            with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_extra",
                              width="content"):
                extra()
    ruta = _copia_reducida(r, "ruta_original" if vista == "Original" else "ruta_procesada")
    with st.container(key="galeria_foto_grande"):
        if ruta:
            st.image(ruta, width="stretch")
        else:
            st.warning("No se encuentra el archivo de esta imagen.")
    st.markdown(_metricas_foto(r), unsafe_allow_html=True)

def galeria_fotos(registros, periodo=None):
    """Abre la galería; el título dice si son las últimas capturas en vivo o las del filtro de la gráfica."""
    titulo = "Fotos del filtro" if periodo else "Foto en vivo · la última" if len(registros) == 1 \
        else f"Fotos en vivo · últimas {len(registros)}"
    st.dialog(titulo, width="large", on_dismiss=_al_cerrar_galeria)(_galeria)(registros, periodo)

def filtrar_por_dia(registros, dia):
    """Devuelve (fotos de ese día o todas, {fecha: nº de capturas}, día elegido; None si ya no tiene fotos)."""
    por_dia = {}
    for r in registros:
        fecha = _fecha_de(r)
        if fecha:
            por_dia[fecha.date()] = por_dia.get(fecha.date(), 0) + 1
    if dia not in por_dia:
        return registros, por_dia, None
    return [r for r in registros if _fecha_de(r) and _fecha_de(r).date() == dia], por_dia, dia

def selector_dia(por_dia, dia, total, clave_mes, al_elegir):
    """Un día concreto: menú con calendario (solo días con fotos) y, si hay uno elegido, volver a todos."""
    with st.popover(fecha_legible(dia, con_hora=False) if dia else f"Todos los días ({total})",
                    icon=":material/calendar_month:", key="galeria_dia_pop", help="Ver solo un día"):
        _calendario("dia", clave_mes, por_dia, dia, al_elegir)
    if dia:
        st.button("", icon=":material/restart_alt:", key="galeria_dia_todos", on_click=al_elegir,
                  args=(None,), help="Restablecer: ver todos los días")

def _poner_dia(dia):
    """Otro día en la galería (None = todos): se vuelve a la primera página y lo marcado para comparar ya no vale."""
    ss = st.session_state
    ss.galeria_dia_v = dia
    ss.galeria_pag = 0
    ss.galeria_sel = None
    _modo_comparar(ss.get("galeria_comparar", False))

def foto_cuadricula(r, i, al_pulsar, args=(), orden=0):
    """Una foto de una cuadrícula con sus datos encima; un botón invisible la cubre para que toda sea clicable."""
    with st.container(key=f"galeria_gfoto_{i}" + ("_elegida" if orden else "")):
        ruta = _copia_reducida(r, "ruta_procesada") or ruta_miniatura(r)
        if os.path.isfile(ruta):
            st.image(ruta, width="stretch")
        else:
            st.markdown("<div class='gal-sin-foto'>Foto no disponible</div>", unsafe_allow_html=True)
        st.markdown(_datos_foto(r, orden), unsafe_allow_html=True)
        st.button(f"Ver foto {i + 1}", key=f"galeria_abrir_{i}", on_click=al_pulsar, args=args)

def _galeria(registros, periodo=None):
    """Galería de las capturas (más recientes primero), 12 por página en tres columnas, con los datos
    de cada foto encima; al pulsarla se abre en grande. Con un filtro de varios días se puede elegir
    uno solo: desde ahí todo (cuadrícula, foto abierta y comparar) trabaja con las fotos de ese día."""
    ss = st.session_state
    todas = len(registros)
    registros, por_dia, dia = filtrar_por_dia(registros, ss.get("galeria_dia_v"))
    total = len(registros)
    sel = ss.get("galeria_sel")
    if sel is not None and 0 <= sel < total:
        foto_ampliada(registros, sel)
        return
    comparar = ss.get("galeria_comparar", False)
    elegidas = [i for i in ss.get("galeria_elegidas", []) if 0 <= i < total]
    if comparar and len(elegidas) == 2:
        _comparacion(registros, elegidas)
        return

    paginas = max(1, -(-total // FOTOS_POR_PAGINA))
    pag = min(ss.get("galeria_pag", 0), paginas - 1)
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_paginas"):
        if comparar:
            st.markdown(f"<div class='gal-titulo'><span class='gal-chip comparar'><i></i>Comparar</span>"
                        f"Elige las fechas o marca dos fotos abajo ({len(elegidas)}/2): la más antigua será «Antes»</div>",
                        unsafe_allow_html=True)
        else:
            st.markdown(_texto_galeria(registros, periodo, dia), unsafe_allow_html=True)
        st.space("stretch")
        if len(por_dia) > 1:
            selector_dia(por_dia, dia, todas, "galeria_dia_mes", _poner_dia)
        if comparar:
            st.button("Cancelar", icon=":material/close:", key="galeria_cmp_cancelar", on_click=_modo_comparar,
                      args=(False,), type="tertiary")
        elif total >= 2:
            st.button("Comparar", icon=":material/compare:", key="galeria_cmp_activar", on_click=_modo_comparar,
                      args=(True,), type="tertiary", help="Elegir dos fotos y verlas antes / después")
        if paginas > 1:
            # Paginador compacto en una sola cápsula: ‹ 1 / 3 ›
            with st.container(horizontal=True, vertical_alignment="center", gap=None, key="galeria_pager",
                              width="content"):
                st.button("", icon=":material/chevron_left:", key="galeria_pag_ant", disabled=pag == 0,
                          on_click=_ir_pagina, args=(pag - 1,), type="tertiary", help="Página anterior")
                st.markdown(f"<p class='gal-pag'>{pag + 1} / {paginas}</p>", unsafe_allow_html=True, width="content")
                st.button("", icon=":material/chevron_right:", key="galeria_pag_sig", disabled=pag == paginas - 1,
                          on_click=_ir_pagina, args=(pag + 1,), type="tertiary", help="Página siguiente")

    if comparar and total < 2:
        # P. ej. un día con una sola foto: el panel mostraría la misma en "Antes" y "Después"
        st.markdown("<p class='cmp-sel-aviso'>Este día solo tiene una foto: elige otro día o vuelve a "
                    "«Todos los días» (↺) para comparar.</p>", unsafe_allow_html=True)
    elif comparar:
        _panel_comparar(registros)
    inicio = pag * FOTOS_POR_PAGINA
    pagina = registros[inicio:inicio + FOTOS_POR_PAGINA]
    # Solo esta zona se desplaza: el título y la paginación quedan fijos arriba
    with st.container(key="galeria_grilla"):
        for fila in range(0, len(pagina), COLUMNAS_GALERIA):
            filas = enumerate(pagina[fila:fila + COLUMNAS_GALERIA], start=inicio + fila)
            for col, (i, r) in zip(st.columns(COLUMNAS_GALERIA, gap="small"), filas):
                # Al comparar, pulsar la marca en lugar de abrirla
                orden = elegidas.index(i) + 1 if comparar and i in elegidas else 0
                with col:
                    foto_cuadricula(r, i, _pulsar_foto, (i,), orden)

_ICONOS = {
    "prev": "<path d='m15 18-6-6 6-6'/>",
    "next": "<path d='m9 18 6-6-6-6'/>",
    "expand": "<path d='M15 3h6v6'/><path d='M9 21H3v-6'/><path d='M21 3l-7 7'/><path d='M3 21l7-7'/>",
    "cerrar": "<path d='M18 6 6 18'/><path d='m6 6 12 12'/>",
    "pausa": "<rect x='6' y='4' width='4' height='16' rx='1'/><rect x='14' y='4' width='4' height='16' rx='1'/>",
    "play": "<path d='M6 4.5v15a1 1 0 0 0 1.5.87l12.5-7.5a1 1 0 0 0 0-1.74L7.5 3.63A1 1 0 0 0 6 4.5z'/>",
}
_SVG = "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{}</svg>"

_PLANTILLA = """
<div class="vl" id="__UID__">
  <div class="vl-nav">
    <button class="vl-btn" data-act="prev" title="Anterior"><i data-ico="prev"></i></button>
    <span class="vl-cont"></span>
    <button class="vl-btn" data-act="next" title="Siguiente"><i data-ico="next"></i></button>
    <div class="vl-seg vl-seg-nav">
      <button data-modo="o">Original</button><button data-modo="p">Procesada</button>
    </div>
    <button class="vl-btn vl-btn-exp" data-act="expand" title="Ampliar la captura"><i data-ico="expand"></i></button>
  </div>
  <div class="vl-foto" data-act="expand" title="Clic para ampliar">
    <img alt="Captura de la laguna">
    <span class="vl-vivo"><i></i>__VIVO__</span>
    <div class="vl-foto-pie">
      <span class="vl-fecha"></span>
      <button class="vl-pausa" data-act="pausa" title="Pausar el carrusel">
        <span class="vl-ico-pausa"><i data-ico="pausa"></i></span>
        <span class="vl-ico-play"><i data-ico="play"></i></span>
      </button>
    </div>
    <i class="vl-barra"></i>
  </div>
  <div class="vl-met vl-met-corta"></div>
  <div class="vl-thumbs"></div>
</div>
<script>
(() => {
  const root = document.getElementById("__UID__");
  if (!root) return;
  const datos = __DATOS__;
  const MS = __MS__;
  const ICONOS = __ICONOS__;
  // st.html quita los SVG del HTML (DOMPurify): se insertan desde aquí
  const iconos = (el) => el.querySelectorAll("[data-ico]").forEach(i => { i.outerHTML = ICONOS[i.dataset.ico] || ""; });
  iconos(root);
  const previo = window.__vl;
  // Una recarga de Streamlit con los mismos datos conserva la foto y la vista en curso
  const vl = window.__vl = {
    root, datos, uid: "__UID__",
    i: previo && previo.uid === "__UID__" ? previo.i : 0,
    modo: previo ? previo.modo : "p",
    sobre: false,
    // La pausa la decide el usuario y se mantiene aunque Streamlit vuelva a dibujar el visor
    pausado: previo ? !!previo.pausado : false,
    transcurrido: 0,
  };
  if (previo && previo.timer) clearInterval(previo.timer);

  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const muestra = (r) => `
    <div><span>Área</span><b>${esc(r.area)}</b></div>
    <div><span>Confianza</span><b>${esc(r.conf)}</b></div>
    <div><span>Color</span><b><i class="vl-sw" style="background:${esc(r.color)}"></i>${esc(r.color)}</b></div>
    <div><span>Fecha y hora</span><b>${esc(r.fecha)}</b></div>`;
  // Debajo de la foto solo área, confianza y color: la fecha va sobre la propia foto para dejarle más alto
  const muestraCorta = (r) => muestra(r).split("</div>").slice(0, 3).join("</div>") + "</div>";

  vl.render = () => {
    const n = datos.length, r = datos[vl.i];
    root.querySelector(".vl-cont").textContent = `${vl.i + 1}/${n}`;
    const img = root.querySelector(".vl-foto img");
    img.src = r[vl.modo] || r.o || r.p;
    root.querySelectorAll(".vl-seg button").forEach(b => b.classList.toggle("on", b.dataset.modo === vl.modo));
    root.querySelector(".vl-met").innerHTML = muestraCorta(r);
    root.querySelector(".vl-fecha").textContent = r.fecha;
    // Miniaturas: las capturas que vienen después de la actual (la actual no se repite abajo)
    const siguientes = [];
    for (let k = 1; k < Math.min(n, 5); k++) siguientes.push((vl.i + k) % n);
    root.querySelector(".vl-thumbs").innerHTML = siguientes.map(j =>
      `<button data-idx="${j}" title="${esc(datos[j].fecha)}"><img src="${esc(datos[j].p || datos[j].o)}" alt=""></button>`).join("");
    vl.transcurrido = 0;
    vl.pintarPausa();
  };
  // Estado del botón de pausa y barra de progreso de la rotación
  vl.pintarPausa = () => {
    root.classList.toggle("pausado", vl.pausado);
    const boton = root.querySelector(".vl-pausa");
    boton.title = vl.pausado ? "Reanudar el carrusel" : "Pausar el carrusel";
    const barra = root.querySelector(".vl-barra");
    barra.style.width = datos.length > 1 ? `${Math.min(100, vl.transcurrido / MS * 100)}%` : "0";
  };

  const ir = (j) => { vl.i = (j + datos.length) % datos.length; vl.render(); };

  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act], [data-modo], [data-idx]");
    if (!t) return;
    if (t.dataset.idx !== undefined) ir(+t.dataset.idx);
    else if (t.dataset.modo) { vl.modo = t.dataset.modo; vl.render(); }
    else if (t.dataset.act === "prev") ir(vl.i - 1);
    else if (t.dataset.act === "next") ir(vl.i + 1);
    else if (t.dataset.act === "expand") vl.abrir();
    else if (t.dataset.act === "pausa") { vl.pausado = !vl.pausado; vl.pintarPausa(); }
  });
  // Mientras el ratón está sobre el visor la rotación se detiene, para poder pulsar sin que cambie la foto
  root.addEventListener("mouseenter", () => { vl.sobre = true; });
  root.addEventListener("mouseleave", () => { vl.sobre = false; });

  // Reloj de la rotación: cuenta solo mientras el carrusel corre, así la barra y el cambio de foto coinciden
  const PASO = 250;
  vl.timer = setInterval(() => {
    if (!document.body.contains(root)) { clearInterval(vl.timer); return; }
    if (vl.pausado || vl.sobre || vl.modal || datos.length < 2) return;
    vl.transcurrido += PASO;
    if (vl.transcurrido >= MS) ir(vl.i + 1);
    else vl.pintarPausa();
  }, PASO);

  // ---- Ventana ampliada (se crea una vez y la reutilizan todas las recargas)
  let modal = document.getElementById("vl-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "vl-modal";
    modal.innerHTML = `
      <div class="vl-modal-caja">
        <div class="vl-modal-cab">
          <div class="vl-modal-nav">
            <button class="vl-btn" data-paso="-1" title="Anterior (←)"><i data-ico="prev"></i></button>
            <span class="vl-cont vl-modal-cont"></span>
            <button class="vl-btn" data-paso="1" title="Siguiente (→)"><i data-ico="next"></i></button>
          </div>
          <div class="vl-seg"><button data-modo="o">Original</button><button data-modo="p">Procesada (IA)</button></div>
          <button class="vl-btn" data-cerrar title="Cerrar"><i data-ico="cerrar"></i></button>
        </div>
        <img alt="Captura ampliada">
        <div class="vl-met vl-met-modal"></div>
      </div>`;
    iconos(modal);
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => {
      const v = window.__vl;
      const t = e.target.closest("[data-modo], [data-cerrar], [data-paso]");
      if (e.target === modal || (t && t.dataset.cerrar !== undefined)) return v.cerrar();
      if (t && t.dataset.paso) v.mover(+t.dataset.paso);
      else if (t && t.dataset.modo) { v.modoModal = t.dataset.modo; v.pintarModal(); }
    });
    // Teclado en la vista ampliada: Esc cierra, ← y → pasan a la captura anterior o siguiente
    document.addEventListener("keydown", (e) => {
      const v = window.__vl;
      if (!v || !v.modal) return;
      if (e.key === "Escape") v.cerrar();
      else if (e.key === "ArrowLeft") v.mover(-1);
      else if (e.key === "ArrowRight") v.mover(1);
    });
  }
  vl.pintarModal = () => {
    const r = datos[vl.i];
    modal.querySelector("img").src = r[vl.modoModal] || r.o || r.p;
    modal.querySelectorAll(".vl-seg button").forEach(b => b.classList.toggle("on", b.dataset.modo === vl.modoModal));
    modal.querySelector(".vl-met").innerHTML = muestra(r);
    modal.querySelector(".vl-modal-cont").textContent = `${vl.i + 1}/${datos.length}`;
  };
  // Navegar en la vista ampliada mueve también el carrusel de detrás, que queda en la misma foto al cerrar
  vl.mover = (paso) => { vl.i = (vl.i + paso + datos.length) % datos.length; vl.render(); vl.pintarModal(); };
  vl.abrir = () => { vl.modal = true; vl.modoModal = vl.modo; vl.pintarModal(); modal.classList.add("abierto"); };
  vl.cerrar = () => { vl.modal = false; modal.classList.remove("abierto"); };
  if (previo && previo.modal) vl.abrir(); else vl.cerrar();

  vl.render();
})();
</script>
"""

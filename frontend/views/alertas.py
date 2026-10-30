import html
import streamlit as st

from backend import config as cfg
from backend.alertas import evaluar_registro, NIVELES
from backend.data_base import obtener_alertas, marcar_alertas_leidas, eliminar_alertas, obtener_registros
from frontend.components.formato import fecha_legible
from frontend.components.tarjetas import tarjeta_kpi, punto, ICONO_CHECK, ICONO_PROMEDIO, ICONO_SERVIDOR

COLOR_NIVEL = {"critica": "#f0616d", "aviso": "#f5a742", "info": "#3cc9b4"}
TIPOS = {"area_baja": "Área baja", "cambio_brusco": "Cambio brusco", "sin_fotos": "Sin capturas", "prueba": "Prueba"}
ICONO_CAMPANA = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' "
                 "stroke-linejoin='round'><path d='M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9'/>"
                 "<path d='M10.3 21a1.94 1.94 0 0 0 3.4 0'/></svg>")

@st.dialog("Revisar el historial")
def _evaluar_historial():
    st.markdown("Aplica las reglas de alerta actuales a todas las mediciones guardadas, en orden cronológico. "
                "Sirve para ver qué habría avisado el sistema en el pasado. **No envía notificaciones.**")
    if st.button("Evaluar historial", type="primary", width="stretch"):
        todos = sorted(obtener_registros(), key=lambda r: r["fecha_captura"])
        config = cfg.cargar()
        creadas = 0
        for i, r in enumerate(todos):
            creadas += len(evaluar_registro(r, config, registros=todos[:i + 1], notificar=False))
        st.session_state["alertas_msg"] = f"Historial evaluado: {creadas} alerta(s) nuevas."
        st.rerun()

def _fila_alerta(a):
    color = COLOR_NIVEL.get(a["nivel"], "#8b95a3")
    nueva = "" if a["leida"] else "<span class='alerta-nueva'>Nueva</span>"
    envio = f"<span class='alerta-envio'>{html.escape(a['envio'])}</span>" if a.get("envio") else ""
    # En una sola línea: con sangría, Markdown convertiría las filas siguientes en bloques de código
    return (
        f"<div class='alerta-fila{' leida' if a['leida'] else ''}'>"
        f"<div class='alerta-nivel' style='background:{color}'></div>"
        f"<div class='alerta-cuerpo'><div class='alerta-cabecera'><b>{TIPOS.get(a['tipo'], a['tipo'])}</b>"
        f"<span>{NIVELES.get(a['nivel'], a['nivel'])} · {fecha_legible(a['fecha'])}</span>{nueva}</div>"
        f"<div class='alerta-mensaje'>{html.escape(a['mensaje'])}</div>{envio}</div></div>"
    )

def render_alertas():
    alertas = obtener_alertas(limite=500)
    no_leidas = [a for a in alertas if not a["leida"]]
    reglas = cfg.cargar()["alertas"]

    col_tit, col_acc = st.columns([1.4, 1], vertical_alignment="center")
    with col_tit:
        st.markdown("""
            <div class='header-title'>Alertas</div>
            <div class='header-sub' style='margin-bottom:0 !important'>Cambios bruscos, áreas bajas y falta de capturas</div>
        """, unsafe_allow_html=True)
    with col_acc, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
        if st.button("Revisar historial", icon=":material/history:"):
            _evaluar_historial()
        if st.button("Marcar todas como leídas", icon=":material/done_all:", disabled=not no_leidas, type="primary"):
            marcar_alertas_leidas()
            st.rerun()

    if st.session_state.get("alertas_msg"):
        st.toast(st.session_state.pop("alertas_msg"), icon=":material/notifications:")

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        tarjeta_kpi(ICONO_CAMPANA, "Sin leer", str(len(no_leidas)), tono="warn" if no_leidas else "ok")
    with k2:
        criticas = sum(1 for a in alertas if a["nivel"] == "critica")
        tarjeta_kpi(ICONO_PROMEDIO, "Críticas", str(criticas), tono="danger" if criticas else "")
    with k3:
        tarjeta_kpi(ICONO_CHECK, "Total registradas", str(len(alertas)))
    with k4:
        canales = cfg.cargar()["notificaciones"]
        activos = [n for n, c in (("Telegram", canales["telegram"]), ("Correo", canales["correo"])) if c["activo"]]
        tarjeta_kpi(ICONO_SERVIDOR, "Notificaciones", " + ".join(activos) if activos else "Desactivadas",
                    tono="ok" if activos else "warn")

    col_lista, col_reglas = st.columns([2.05, 1], gap="medium")
    with col_lista, st.container(key="alertas_lista_card"):
        c1, c2 = st.columns([1.5, 1], vertical_alignment="center")
        with c1:
            st.markdown("<div class='card-title'>Historial</div><div class='card-sub'>Las más recientes primero</div>",
                        unsafe_allow_html=True)
        with c2, st.container(horizontal=True, horizontal_alignment="right"):
            filtro = st.segmented_control("Filtro", ["Todas", "Sin leer"], default="Todas", key="alertas_filtro",
                                          label_visibility="collapsed") or "Todas"
        visibles = no_leidas if filtro == "Sin leer" else alertas
        if not visibles:
            st.markdown("<div class='card-sub' style='padding:24px 0'>No hay alertas para mostrar.</div>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<div class='alertas-lista'>" + "".join(_fila_alerta(a) for a in visibles[:100]) + "</div>",
                        unsafe_allow_html=True)

    with col_reglas:
        with st.container(key="alertas_reglas_card"):
            estado = f"{punto('#2fd27a')}Activas" if reglas["activas"] else f"{punto('#f0616d')}Desactivadas"
            filas = [
                ("Estado", estado),
                ("Cambio entre mediciones", f"± {reglas['cambio_pct']} %"),
                ("Mediana de", f"{reglas['mediana_h']} h de capturas"),
                ("Área mínima", f"{reglas['area_min']:,} m²".replace(",", ".")),
                ("Sin capturas durante", f"{reglas['horas_sin_fotos']} h"),
            ]
            st.markdown(
                "<div class='card-title'>Reglas</div><div class='card-sub'>Se cambian en Configuración</div>"
                "<div class='lista-datos'>" + "".join(f"<div><span>{k}</span><b>{v}</b></div>" for k, v in filas) + "</div>",
                unsafe_allow_html=True,
            )
            st.caption("Solo se evalúan las mediciones confiables: las rechazadas, no aptas o atípicas no generan alertas. "
                       "Se compara la mediana de cada ventana, no una foto suelta.")
        with st.container(key="alertas_borrar_card"):
            st.markdown("<div class='card-title'>Limpiar historial</div>", unsafe_allow_html=True)
            confirmar = st.checkbox("Entiendo que se borran todas las alertas", key="alertas_conf_borrar")
            if st.button("Borrar historial", icon=":material/delete:", disabled=not (confirmar and alertas), width="stretch"):
                eliminar_alertas()
                st.rerun()

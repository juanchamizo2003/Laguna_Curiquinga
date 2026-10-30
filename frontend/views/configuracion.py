import os
import cv2
import numpy as np
import pandas as pd
import streamlit as st

from backend import config as cfg
from backend import acceso
from backend.calidad import revisar_agua
from backend.data_base import guardar_alerta, marcar_observacion
from backend.alertas import notificar_alerta
from backend.respaldo import crear_respaldo, listar_respaldos
from backend.servicio import EXTENSIONES_IMAGEN
from frontend.components.datos import registros
from frontend.components.formato import formatear_m2, fecha_legible

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ESQUINAS = ["Superior izquierda", "Superior derecha", "Inferior izquierda", "Inferior derecha"]
PREFIJO_AGUA = "Agua sin color"

def _guardado(mensaje):
    st.session_state["config_msg"] = mensaje
    st.rerun()

def _tarjeta(key, titulo, sub):
    contenedor = st.container(key=key)
    contenedor.markdown(f"<div class='card-title'>{titulo}</div><div class='card-sub'>{sub}</div>", unsafe_allow_html=True)
    return contenedor

# ---------------------------------------------------------------- calibración

def _dibujar_calibracion(ruta, calibracion):
    img = cv2.imread(ruta)
    if img is None:
        return None
    capa = img.copy()
    h = calibracion["homografia"]
    poligono = np.array([h[0], h[1], h[3], h[2]], dtype=np.int32)  # TL, TR, BR, BL
    cv2.fillPoly(capa, [poligono], (180, 201, 60))
    img = cv2.addWeighted(capa, 0.18, img, 0.82, 0)
    cv2.polylines(img, [poligono], True, (180, 201, 60), 3)
    for x, y, tipo in calibracion["puntos_sam"]:
        color = (122, 210, 47) if tipo == 1 else (109, 97, 240)
        cv2.circle(img, (int(x), int(y)), 14, (255, 255, 255), -1)
        cv2.circle(img, (int(x), int(y)), 10, color, -1)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def _calibracion_desde_editores(df_puntos, df_homografia, m2, m):
    puntos = [[int(r.X), int(r.Y), 1 if r.Tipo == "Agua" else 0]
              for r in df_puntos.dropna(subset=["X", "Y"]).itertuples()]
    homografia = [[int(r.X), int(r.Y)] for r in df_homografia.itertuples()]
    return {"puntos_sam": puntos, "homografia": homografia, "m2_por_px": float(m2), "m_por_px": float(m)}

def _tab_calibracion(config):
    calib = config["calibracion"]
    todos = sorted(registros(), key=lambda r: r["fecha_captura"], reverse=True)
    col_form, col_vista = st.columns([1, 1.35], gap="medium")

    with col_form, _tarjeta("cfg_calib_card", "Puntos y plano de referencia",
                            "Coordenadas en la foto original (1920×1080)"):
        st.markdown("<div class='img-titulo'>Puntos para SAM · al menos uno de tipo Agua</div>", unsafe_allow_html=True)
        df_puntos = st.data_editor(
            pd.DataFrame([{"X": x, "Y": y, "Tipo": "Agua" if t == 1 else "No agua"} for x, y, t in calib["puntos_sam"]]),
            num_rows="dynamic", hide_index=True, width="stretch", key="cfg_puntos",
            column_config={
                "X": st.column_config.NumberColumn(min_value=0, max_value=4000, step=1, required=True),
                "Y": st.column_config.NumberColumn(min_value=0, max_value=4000, step=1, required=True),
                "Tipo": st.column_config.SelectboxColumn(options=["Agua", "No agua"], required=True),
            },
        )
        st.markdown("<div class='img-titulo'>Esquinas del plano para la homografía</div>", unsafe_allow_html=True)
        df_homografia = st.data_editor(
            pd.DataFrame([{"Esquina": e, "X": p[0], "Y": p[1]} for e, p in zip(ESQUINAS, calib["homografia"])]),
            hide_index=True, width="stretch", key="cfg_homografia", disabled=["Esquina"],
            column_config={
                "X": st.column_config.NumberColumn(min_value=0, max_value=4000, step=1, required=True),
                "Y": st.column_config.NumberColumn(min_value=0, max_value=4000, step=1, required=True),
            },
        )
        c1, c2 = st.columns(2)
        m2 = c1.number_input("m² por píxel", value=float(calib["m2_por_px"]), format="%.6f", step=0.001, key="cfg_m2")
        m = c2.number_input("m por píxel (perímetro)", value=float(calib["m_por_px"]), format="%.4f", step=0.01, key="cfg_m")

        candidata = _calibracion_desde_editores(df_puntos, df_homografia, m2, m)
        valida = any(p[2] == 1 for p in candidata["puntos_sam"])
        if not valida:
            st.warning("Hace falta al menos un punto de tipo Agua.")

        with st.container(horizontal=True, gap="small"):
            if st.button("Guardar calibración", type="primary", disabled=not valida, icon=":material/save:"):
                cfg.actualizar("calibracion", candidata)
                st.session_state.pop("cfg_prueba", None)
                _guardado("Calibración guardada")
            if st.button("Valores por defecto", icon=":material/restart_alt:"):
                cfg.actualizar("calibracion", cfg.POR_DEFECTO["calibracion"])
                for k in ("cfg_puntos", "cfg_homografia", "cfg_m2", "cfg_m", "cfg_prueba"):
                    st.session_state.pop(k, None)
                _guardado("Calibración restablecida a los valores por defecto")
        st.caption("Tras cambiar la calibración, reprocesa los registros desde Cargar y procesar → Registros "
                   "para que todas las mediciones usen los mismos valores.")

    with col_vista, _tarjeta("cfg_vista_card", "Vista previa", "Verde: agua · rojo: no agua · recuadro: plano de referencia"):
        if not todos:
            st.info("Procesa al menos una foto para ver la calibración sobre ella.")
            return
        por_id = {r["id"]: r for r in todos}
        elegido = por_id[st.selectbox("Foto", list(por_id), key="cfg_foto", label_visibility="collapsed",
                                      format_func=lambda i: f"{fecha_legible(por_id[i]['fecha_captura'])} · {por_id[i]['nombre_foto']}")]
        ruta = os.path.join(BASE_DIR, elegido["ruta_original"])
        prueba = st.session_state.get("cfg_prueba")
        if prueba and prueba["id"] == elegido["id"] and prueba["calibracion"] == candidata:
            st.image(prueba["imagen"], width="stretch")
            diferencia = (prueba["area"] - elegido["area"]) / elegido["area"] * 100 if elegido["area"] else 0
            st.markdown(f"""
                <div class="visor-metricas">
                    <div><span>Área con esta calibración</span><b>{formatear_m2(prueba['area'])}</b></div>
                    <div><span>Área guardada</span><b>{formatear_m2(elegido['area'])}</b></div>
                    <div><span>Diferencia</span><b>{diferencia:+.1f}%</b></div>
                </div>
            """, unsafe_allow_html=True)
        else:
            vista = _dibujar_calibracion(ruta, candidata)
            if vista is None:
                st.warning("No se encuentra la foto original de este registro.")
            else:
                st.image(vista, width="stretch")
        if st.button("Probar segmentación con estos valores", icon=":material/science:", disabled=not valida,
                     width="stretch"):
            from backend.motor import analizar_laguna
            with st.spinner("Segmentando con SAM…"):
                exito, msg, datos = analizar_laguna(ruta, candidata)
            if exito:
                st.session_state["cfg_prueba"] = {"id": elegido["id"], "calibracion": candidata,
                                                  "imagen": datos["img_visual"], "area": datos["area"]}
                st.rerun()
            st.error(f"No se pudo segmentar: {msg}")

# ---------------------------------------------------------------- calidad

def _tab_calidad(config):
    q = config["calidad"]
    col_form, col_info = st.columns([1.35, 1], gap="medium")
    with col_form, _tarjeta("cfg_calidad_card", "Control de calidad", "Umbrales que se aplican a cada foto nueva"):
        with st.form("form_calidad", border=False):
            st.markdown("<div class='img-titulo'>Antes de SAM: la foto se descarta si no cumple</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            brillo_min = c1.number_input("Brillo mínimo", 0, 255, int(q["brillo_min"]), help="Noche o cámara tapada")
            brillo_max = c2.number_input("Brillo máximo", 0, 255, int(q["brillo_max"]), help="Imagen quemada")
            contraste = c1.number_input("Contraste mínimo", 0, 128, int(q["contraste_min"]), help="Niebla densa o lente cubierto")
            nitidez = c2.number_input("Nitidez mínima", 0, 5000, int(q["nitidez_min"]), help="Desenfoque o lente empañado")
            st.markdown("<div class='img-titulo'>Después de SAM</div>", unsafe_allow_html=True)
            c3, c4 = st.columns(2)
            sat = c3.number_input("Saturación mínima del agua", 0.0, 1.0, float(q["saturacion_agua_min"]), step=0.01,
                                  help="Si el agua sale casi gris hay niebla sobre la laguna: se guarda como no apta")
            conf = c4.number_input("Confianza para validar", 0.0, 1.0, float(q["confianza_min"]), step=0.01,
                                   help="Por debajo, la captura queda en estado Revisar")
            st.markdown("<div class='img-titulo'>Valores atípicos: se excluyen solos de la gráfica y las alertas</div>",
                        unsafe_allow_html=True)
            c5, c6, c7 = st.columns(3)
            atip_pct = c5.number_input("Desviación máxima (%)", 1, 100, int(q["atipico_pct"]),
                                       help="Respecto a la mediana de las capturas cercanas")
            atip_h = c6.number_input("Ventana (± horas)", 1, 48, int(q["atipico_ventana_h"]),
                                     help="Horas antes y después que cuentan como capturas cercanas")
            atip_n = c7.number_input("Capturas cercanas mín.", 1, 50, int(q["atipico_vecinas"]),
                                     help="Con menos no se juzga: las cargas manuales espaciadas nunca son atípicas")
            if st.form_submit_button("Guardar umbrales", type="primary", icon=":material/save:"):
                cfg.actualizar("calidad", {"brillo_min": brillo_min, "brillo_max": brillo_max, "contraste_min": contraste,
                                           "nitidez_min": nitidez, "saturacion_agua_min": sat, "confianza_min": conf,
                                           "atipico_pct": atip_pct, "atipico_ventana_h": atip_h,
                                           "atipico_vecinas": atip_n})
                _guardado("Umbrales de calidad guardados")

    with col_info, _tarjeta("cfg_calidad_aplicar_card", "Aplicar a lo ya registrado",
                            "Revisa el color del agua de todos los registros sin volver a pasar SAM"):
        todos = registros()
        cambios = []
        for r in todos:
            obs_actual = r.get("observacion") or None
            nueva = revisar_agua(r["color_hex"], q)
            # Solo se tocan observaciones de esta regla; las de otros motivos se respetan
            if obs_actual and not obs_actual.startswith(PREFIJO_AGUA):
                continue
            if nueva != obs_actual:
                cambios.append((r, nueva))
        marcar = sum(1 for _, n in cambios if n)
        limpiar = len(cambios) - marcar
        st.markdown(f"""
            <div class='lista-datos'>
                <div><span>Registros revisados</span><b>{len(todos)}</b></div>
                <div><span>Pasarían a no aptos</span><b>{marcar}</b></div>
                <div><span>Dejarían de ser no aptos</span><b>{limpiar}</b></div>
            </div>
        """, unsafe_allow_html=True)
        for r, n in cambios[:6]:
            st.caption(f"#{r['id']} · {fecha_legible(r['fecha_captura'], con_hora=False)} · {n or 'apto'}")
        if st.button("Aplicar", icon=":material/rule:", disabled=not cambios, width="stretch"):
            for r, n in cambios:
                marcar_observacion(r["id"], n, conservar_revision=True)
            _guardado(f"Control del agua aplicado a {len(cambios)} registro(s)")

# ---------------------------------------------------------------- alertas y notificaciones

def _tab_alertas(config):
    a, n = config["alertas"], config["notificaciones"]
    col_reglas, col_canales = st.columns([1, 1.35], gap="medium")
    with col_reglas, _tarjeta("cfg_reglas_card", "Reglas de alerta", "Se evalúan con cada medición confiable"):
        with st.form("form_reglas", border=False):
            activas = st.toggle("Alertas activas", value=a["activas"])
            cambio = st.number_input("Cambio entre mediciones (%)", 1, 100, int(a["cambio_pct"]))
            mediana_h = st.number_input("Mediana de (horas)", 1, 24, int(a["mediana_h"]),
                                        help="Se compara la mediana de las capturas de esta ventana con la anterior; "
                                             "una foto suelta no dispara alertas")
            area_min = st.number_input("Área mínima (m²)", 0, 1_000_000, int(a["area_min"]), step=1000)
            horas = st.number_input("Horas sin capturas", 1, 168, int(a["horas_sin_fotos"]))
            if st.form_submit_button("Guardar reglas", type="primary", icon=":material/save:"):
                cfg.actualizar("alertas", {"activas": activas, "cambio_pct": cambio, "mediana_h": mediana_h,
                                           "area_min": area_min, "horas_sin_fotos": horas})
                _guardado("Reglas de alerta guardadas")

    with col_canales, _tarjeta("cfg_canales_card", "Notificaciones",
                               "Las claves se guardan en base_datos/config.json, que no se sube a git"):
        with st.form("form_canales", border=False):
            st.markdown("<div class='img-titulo'>Telegram</div>", unsafe_allow_html=True)
            t1, t2, t3 = st.columns([0.6, 1.6, 1])
            tg_activo = t1.toggle("Activo", value=n["telegram"]["activo"], key="cfg_tg_activo")
            tg_token = t2.text_input("Token del bot", type="password", placeholder="Guardado" if n["telegram"]["token"] else "123456:ABC…",
                                     help="Créalo con @BotFather. Déjalo vacío para conservar el actual.")
            tg_chat = t3.text_input("Chat ID", value=n["telegram"]["chat_id"])
            st.markdown("<div class='img-titulo'>Correo (SMTP con STARTTLS)</div>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.6, 1.6, 1])
            co_activo = c1.toggle("Activo", value=n["correo"]["activo"], key="cfg_co_activo")
            co_servidor = c2.text_input("Servidor", value=n["correo"]["servidor"])
            co_puerto = c3.number_input("Puerto", 1, 65535, int(n["correo"]["puerto"]))
            c4, c5 = st.columns(2)
            co_usuario = c4.text_input("Usuario", value=n["correo"]["usuario"])
            co_clave = c5.text_input("Clave", type="password", placeholder="Guardada" if n["correo"]["clave"] else "",
                                     help="Con Gmail usa una contraseña de aplicación. Vacío conserva la actual.")
            co_dest = st.text_input("Destinatarios", value=n["correo"]["destinatarios"], placeholder="a@ejemplo.com, b@ejemplo.com")
            if st.form_submit_button("Guardar notificaciones", type="primary", icon=":material/save:"):
                cfg.actualizar("notificaciones", {
                    "telegram": {"activo": tg_activo, "token": tg_token or n["telegram"]["token"], "chat_id": tg_chat.strip()},
                    "correo": {"activo": co_activo, "servidor": co_servidor.strip(), "puerto": co_puerto,
                               "usuario": co_usuario.strip(), "clave": co_clave or n["correo"]["clave"],
                               "destinatarios": co_dest},
                })
                _guardado("Notificaciones guardadas")
        if st.button("Enviar alerta de prueba", icon=":material/send:", width="stretch"):
            mensaje = "Mensaje de prueba del panel de monitoreo"
            alerta_id = guardar_alerta("prueba", "info", mensaje)
            with st.spinner("Enviando…"):
                resultado = notificar_alerta(alerta_id, "info", mensaje)
            (st.success if "error" not in resultado and "Sin canales" not in resultado else st.warning)(resultado)

# ---------------------------------------------------------------- cámara y respaldos

def _tab_operacion(config):
    o, r = config["origen"], config["respaldos"]
    col_cam, col_resp = st.columns(2, gap="medium")
    with col_cam, _tarjeta("cfg_camara_card", "Cámara", "De dónde trae las fotos el vigilante"):
        with st.form("form_origen", border=False):
            nombre = st.text_input("Nombre de la cámara", value=o["nombre_camara"])
            carpeta = st.text_input("Carpeta de origen", value=o["carpeta"],
                                    placeholder=r"\\servidor\camara\curiquinga  o  D:\camara",
                                    help="Carpeta local o de red donde la cámara (o su FTP) deja las fotos. "
                                         "El vigilante copia las nuevas a ingesta_camara. Vacío = desactivado.")
            intervalo = st.number_input("Revisar cada (s)", 5, 3600, int(o["intervalo_s"]))
            if st.form_submit_button("Guardar", type="primary", icon=":material/save:"):
                cfg.actualizar("origen", {"nombre_camara": nombre.strip() or "Cámara", "carpeta": carpeta.strip().strip('"'),
                                          "intervalo_s": intervalo})
                _guardado("Datos de la cámara guardados")
        if o["carpeta"]:
            if os.path.isdir(o["carpeta"]):
                n_fotos = sum(1 for f in os.listdir(o["carpeta"]) if f.lower().endswith(EXTENSIONES_IMAGEN))
                st.success(f"Carpeta accesible: {n_fotos} foto(s). El vigilante las sincroniza mientras está en línea.")
            else:
                st.error("La carpeta de origen no existe o no es accesible desde este equipo.")
        else:
            st.info("Sin carpeta de origen: solo se procesa lo que llegue directamente a flujo_imagenes/ingesta_camara.")

    with col_resp, _tarjeta("cfg_respaldos_card", "Respaldos de la base de datos",
                            "El vigilante los crea automáticamente; aquí puedes forzar uno"):
        with st.form("form_respaldos", border=False):
            c1, c2 = st.columns(2)
            cada = c1.number_input("Cada (horas)", 1, 720, int(r["cada_horas"]))
            conservar = c2.number_input("Conservar los últimos", 1, 365, int(r["conservar"]))
            if st.form_submit_button("Guardar", type="primary", icon=":material/save:"):
                cfg.actualizar("respaldos", {"cada_horas": cada, "conservar": conservar})
                _guardado("Ajustes de respaldo guardados")
        if st.button("Crear respaldo ahora", icon=":material/backup:", width="stretch"):
            ruta = crear_respaldo()
            _guardado(f"Respaldo creado: {os.path.basename(ruta)}")
        respaldos = listar_respaldos()
        if not respaldos:
            st.caption("Todavía no hay respaldos.")
        for nombre_r, ruta_r, tamano, fecha in respaldos[:5]:
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.markdown(f"<div class='card-sub'>{fecha:%d/%m/%Y %H:%M} · {tamano / 1024:.0f} KB</div>", unsafe_allow_html=True)
            with open(ruta_r, "rb") as f:
                c2.download_button("", f.read(), file_name=nombre_r, icon=":material/download:", key=f"dl_{nombre_r}",
                                   help=f"Descargar {nombre_r}")

# ---------------------------------------------------------------- acceso

def _tab_acceso(config):
    protegido = acceso.protegido()
    col, col_pie = st.columns([1, 1.35], gap="medium")
    with col, _tarjeta("cfg_acceso_card", "Contraseña del panel",
                       "Activa: se pide al abrir el panel" if protegido else "Desactivada: cualquiera con el enlace entra"):
        with st.form("form_clave", border=False, clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password") if protegido else ""
            nueva = st.text_input("Nueva contraseña", type="password", help="Mínimo 8 caracteres")
            repetir = st.text_input("Repite la nueva contraseña", type="password")
            if st.form_submit_button("Cambiar contraseña" if protegido else "Activar contraseña", type="primary",
                                     icon=":material/lock:"):
                if protegido and not acceso.comprobar(actual):
                    st.error("La contraseña actual no es correcta.")
                elif len(nueva) < 8:
                    st.error("La nueva contraseña debe tener al menos 8 caracteres.")
                elif nueva != repetir:
                    st.error("Las contraseñas no coinciden.")
                else:
                    acceso.establecer_clave(nueva)
                    st.session_state["autenticado"] = True
                    _guardado("Contraseña guardada")
        if protegido:
            # En un formulario: el valor del campo viaja junto con el clic (suelto, podía llegar vacío)
            with st.popover("Quitar contraseña", icon=":material/lock_open:", width="stretch"), \
                    st.form("form_quitar_clave", border=False, clear_on_submit=True):
                actual_q = st.text_input("Contraseña actual", type="password", key="cfg_quitar_clave")
                if st.form_submit_button("Quitar", type="primary", width="stretch"):
                    if acceso.comprobar(actual_q):
                        acceso.establecer_clave("")
                        _guardado("Contraseña desactivada")
                    st.error("La contraseña no es correcta.")

    pie = config["pie"]
    with col_pie, _tarjeta("cfg_pie_card", "Pie de página", "Autores y contacto que se muestran al final de cada página"):
        with st.form("form_pie", border=False):
            autores = st.text_input("Autor(es)", value=pie["autores"], placeholder="Nombre Apellido, Nombre Apellido")
            correo = st.text_input("Correo de contacto", value=pie["correo"], placeholder="correo@institucion.edu.co")
            institucion = st.text_input("Institución (opcional)", value=pie["institucion"])
            if st.form_submit_button("Guardar", type="primary", icon=":material/save:"):
                cfg.actualizar("pie", {"autores": autores.strip(), "correo": correo.strip(),
                                       "institucion": institucion.strip()})
                _guardado("Pie de página guardado")

def render_configuracion():
    st.markdown("""
        <div class='header-title'>Configuración</div>
        <div class='header-sub'>Calibración del modelo, control de calidad, alertas, cámara, respaldos y acceso</div>
    """, unsafe_allow_html=True)
    if st.session_state.get("config_msg"):
        st.toast(st.session_state.pop("config_msg"), icon=":material/check_circle:")

    config = cfg.cargar()
    tabs = st.tabs([":material/my_location: Calibración", ":material/high_quality: Calidad",
                    ":material/notifications: Alertas", ":material/videocam: Cámara y respaldos",
                    ":material/lock: Acceso y créditos"])
    with tabs[0]:
        _tab_calibracion(config)
    with tabs[1]:
        _tab_calidad(config)
    with tabs[2]:
        _tab_alertas(config)
    with tabs[3]:
        _tab_operacion(config)
    with tabs[4]:
        _tab_acceso(config)

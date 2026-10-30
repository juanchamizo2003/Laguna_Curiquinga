import os
import re
import html
import json
import hashlib
import streamlit as st

from backend import acceso
from backend.data_base import marcar_revision
from backend.calidad import estado_validacion
from backend.miniaturas import crear_miniatura, ruta_miniatura
from frontend.components.datos import color_estado
from frontend.components.formato import formatear_m2, fecha_legible

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Streamlit sirve frontend/static en /app/static (server.enableStaticServing): el navegador cachea las fotos
DIR_ESTATICO = os.path.join(BASE_DIR, "frontend", "static", "visor")
ANCHO_VISOR = 1600
N_CARRUSEL = 10
FOTOS_POR_PAGINA = 10
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

def render_revision(item, key_prefix):
    """Botones para aprobar o rechazar a mano la segmentación de una captura."""
    if item.get("id") is None:
        return
    revision = item.get("revision")
    revision = None if revision != revision else revision  # NaN de pandas
    with st.container(horizontal=True, gap="small", key=f"{key_prefix}_revision"):
        if revision != "aprobada" and st.button("Aprobar", icon=":material/check:", key=f"{key_prefix}_aprobar",
                                                 width="stretch", help="La medición es correcta"):
            marcar_revision(int(item["id"]), "aprobada")
            st.rerun()
        if revision != "rechazada" and st.button("Rechazar", icon=":material/close:", key=f"{key_prefix}_rechazar",
                                                  width="stretch", help="Excluir de la gráfica y de las alertas"):
            marcar_revision(int(item["id"]), "rechazada")
            st.rerun()
        if revision and st.button("Deshacer", icon=":material/undo:", key=f"{key_prefix}_deshacer",
                                  width="stretch", help="Volver al estado automático"):
            marcar_revision(int(item["id"]), None)
            st.rerun()

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
    """Interruptor claro/oscuro del encabezado; el clic lo atiende el script de tema de app.py."""
    pase = f' data-pase="{acceso.emitir_pase()}"' if acceso.protegido() and st.session_state.get("autenticado") else ""
    st.html(f'<button class="tema-toggle" type="button" title="Cambiar entre tema claro y oscuro"{pase}>'
            '<i class="t-sol"></i><i class="t-luna"></i></button>', width="content")

def render_visor_laguna(registros, todas=None, key_prefix="visor_default", periodo=None):
    """Carrusel de las últimas capturas: rota solo, se amplía al pulsar la foto y sus miniaturas
    muestran las siguientes. Todo corre en el navegador para no relanzar el script cada 15 s.
    todas: registros (más recientes primero) para la galería. periodo: texto del filtro de la gráfica
    cuando hay uno; entonces la galería muestra solo las fotos de ese periodo (el carrusel no cambia)."""
    with st.container(key=f"{key_prefix}_card"):
        if not registros:
            st.info("No hay capturas disponibles para mostrar.")
            return
        datos = json.dumps(_datos_carrusel(registros)).replace("</", "<\\/")
        uid = "vl" + hashlib.md5(datos.encode()).hexdigest()[:10]
        iconos = json.dumps({k: _SVG.format(v) for k, v in _ICONOS.items()})
        st.html(js_seguro(_PLANTILLA.replace("__UID__", uid).replace("__DATOS__", datos).replace("__ICONOS__", iconos)
                          .replace("__MS__", str(SEGUNDOS_ROTACION * 1000))), unsafe_allow_javascript=True)
        todas = todas if todas is not None else registros
        if periodo:
            etiqueta, clave = f"Ver fotos del periodo ({len(todas)})", f"{key_prefix}_ver_periodo"
        else:
            etiqueta, clave = f"Ver todas las fotos ({len(todas)})", f"{key_prefix}_ver_todas"
        if st.button(etiqueta, icon=":material/photo_library:", width="stretch", key=clave, disabled=not todas,
                     help=f"Fotos del periodo filtrado en la gráfica: {periodo}" if periodo else None):
            st.session_state.galeria_sel = None
            st.session_state.galeria_pag = 0
            galeria_fotos(todas, periodo)

def _metricas_foto(r):
    color = str(r.get("color_hex") or "#8b95a3").upper()
    estado = estado_validacion(r)
    return f"""<div class="visor-metricas galeria-metricas">
        <div><span>Fecha y hora</span><b>{fecha_legible(r.get("fecha_captura", ""))}</b></div>
        <div><span>Área</span><b>{formatear_m2(r.get("area", 0))}</b></div>
        <div><span>Color</span><b><i class="vl-sw" style="background:{color}"></i>{color}</b></div>
        <div><span>Confianza</span><b>{texto_confianza(r)}</b></div>
        <div><span>Estado</span><b><i style="background:{color_estado(estado)}"></i>{estado}</b></div>
    </div>"""

def _datos_hover(r):
    """Datos que aparecen sobre la miniatura al pasar el ratón."""
    color = str(r.get("color_hex") or "#8b95a3").upper()
    return (f"<div class='gal-datos'><b>{formatear_m2(r.get('area', 0))}</b>"
            f"<span>{fecha_legible(r.get('fecha_captura', ''))}</span>"
            f"<span><i class='vl-sw' style='background:{color}'></i>{color} · {texto_confianza(r)}</span></div>")

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

def _foto_ampliada(registros, sel):
    """Una foto a tamaño completo sin desplazarse: controles en una fila, la imagen al alto libre y sus datos."""
    total, r = len(registros), registros[sel]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_nav"):
        st.button("Cerrar foto", icon=":material/close:", key="galeria_volver", on_click=_cerrar_foto,
                  help="Volver a todas las fotos")
        st.button("", icon=":material/chevron_left:", key="galeria_ant", disabled=sel == 0,
                  on_click=_ir_foto, args=(sel - 1,))
        st.markdown(f"<p class='visor-contador'>{sel + 1}/{total}</p>", unsafe_allow_html=True, width="content")
        st.button("", icon=":material/chevron_right:", key="galeria_sig", disabled=sel == total - 1,
                  on_click=_ir_foto, args=(sel + 1,))
        vista = st.segmented_control("Vista", ["Original", "Procesada (IA)"], default="Procesada (IA)",
                                     key="galeria_vista", label_visibility="collapsed") or "Procesada (IA)"
    ruta = _copia_reducida(r, "ruta_original" if vista == "Original" else "ruta_procesada")
    with st.container(key="galeria_foto_grande"):
        if ruta:
            st.image(ruta, width="stretch")
        else:
            st.warning("No se encuentra el archivo de esta imagen.")
    st.markdown(_metricas_foto(r), unsafe_allow_html=True)

@st.dialog("Fotos", width="large")
def galeria_fotos(registros, periodo=None):
    """Galería de todas las capturas (más recientes primero), 10 por página en dos columnas.
    Al pasar el ratón se ven los datos de cada foto; al pulsarla se abre en grande."""
    ss = st.session_state
    total = len(registros)
    sel = ss.get("galeria_sel")
    if sel is not None and 0 <= sel < total:
        _foto_ampliada(registros, sel)
        return

    paginas = max(1, -(-total // FOTOS_POR_PAGINA))
    pag = min(ss.get("galeria_pag", 0), paginas - 1)
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="galeria_paginas"):
        origen = (f"<span class='filtro-badge'>{html.escape(periodo)}</span> " if periodo
                  else "<b>Todas las fotos</b> · ")
        st.markdown(f"<div class='card-sub'>{origen}{total} captura(s), de la más reciente a la más antigua · "
                    f"pasa el ratón sobre una foto para ver sus datos</div>", unsafe_allow_html=True)
        st.space("stretch")
        st.button("", icon=":material/chevron_left:", key="galeria_pag_ant", disabled=pag == 0,
                  on_click=_ir_pagina, args=(pag - 1,))
        st.markdown(f"<p class='visor-contador'>Página {pag + 1} de {paginas}</p>", unsafe_allow_html=True, width="content")
        st.button("", icon=":material/chevron_right:", key="galeria_pag_sig", disabled=pag == paginas - 1,
                  on_click=_ir_pagina, args=(pag + 1,))

    inicio = pag * FOTOS_POR_PAGINA
    pagina = registros[inicio:inicio + FOTOS_POR_PAGINA]
    # Solo esta zona se desplaza: el título y la paginación quedan fijos arriba
    with st.container(key="galeria_grilla"):
        for fila in range(0, len(pagina), 2):
            for col, (i, r) in zip(st.columns(2, gap="small"), enumerate(pagina[fila:fila + 2], start=inicio + fila)):
                # Un botón invisible cubre la foto para que toda ella sea clicable; los datos salen al pasar el ratón
                with col, st.container(key=f"galeria_gfoto_{i}"):
                    ruta = _copia_reducida(r, "ruta_procesada") or ruta_miniatura(r)
                    if os.path.isfile(ruta):
                        st.image(ruta, width="stretch")
                    st.markdown(_datos_hover(r), unsafe_allow_html=True)
                    st.button(f"Ver foto {i + 1}", key=f"galeria_abrir_{i}", on_click=_ir_foto, args=(i,))

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
    <span class="vl-vivo"><i></i>Últimas 10 capturas</span>
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

"""Tooltip propio para las gráficas de Plotly: solo valores con su icono, y el color en un cuadrito
con su código al lado."""
import streamlit as st

from frontend.components.graficos_dashboard import TOOLTIP
from frontend.components.visor_laguna import js_seguro

_ICONOS = {
    "fecha": "<rect x='3' y='4' width='18' height='18' rx='2'/><path d='M16 2v4M8 2v4M3 10h18'/>",
    "area": "<path d='M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>"
            "<path d='M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>"
            "<path d='M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1'/>",
    "conf": "<path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'/><path d='M22 4 12 14.01l-3-3'/>",
}

def _svg(clave):
    return (f"<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' "
            f"stroke-linecap='round' stroke-linejoin='round'>{_ICONOS[clave]}</svg>")

def activar_tooltip():
    st.html(js_seguro("""<script>
(() => {
  if (window.__ttLaguna) return;
  window.__ttLaguna = true;
  const META = "__META__";
  const tip = document.createElement("div");
  tip.className = "tt-laguna";
  document.body.appendChild(tip);
  let ocultar = null, dentro = false;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  const mostrar = (ev) => {
    const p = ev.points && ev.points.find(p => p.data && p.data.meta === META);
    if (!p || !p.customdata) return;
    clearTimeout(ocultar);
    const [fecha, area, color, conf] = p.customdata;
    tip.innerHTML = `
      <div>__FECHA__<b>${esc(fecha)}</b></div>
      <div>__AREA__<b>${esc(area)}</b></div>
      <div><span class="tt-sw" style="background:${esc(color)}"></span><b>${esc(color)}</b></div>
      <div>__CONF__<b>${esc(conf)}</b></div>`;
    const e = ev.event, ancho = tip.offsetWidth || 190, alto = tip.offsetHeight || 120;
    let x = e.clientX + 10, y = e.clientY + 10;
    if (x + ancho > innerWidth - 8) x = e.clientX - ancho - 10;
    if (y + alto > innerHeight - 8) y = e.clientY - alto - 10;
    tip.style.left = x + "px"; tip.style.top = y + "px";
    tip.classList.add("visible");
  };
  // Se oculta con un pequeño retraso para que dé tiempo a entrar al tooltip y pasar por el cuadrito
  const programarOcultar = () => { clearTimeout(ocultar); ocultar = setTimeout(() => { if (!dentro) tip.classList.remove("visible"); }, 450); };
  tip.addEventListener("mouseenter", () => { dentro = true; clearTimeout(ocultar); });
  tip.addEventListener("mouseleave", () => { dentro = false; programarOcultar(); });

  // Las gráficas se recrean al relanzar Streamlit: se engancha cada una la primera vez que aparece
  setInterval(() => {
    document.querySelectorAll(".js-plotly-plot").forEach(gd => {
      if (gd.__ttLaguna || typeof gd.on !== "function") return;
      gd.__ttLaguna = true;
      gd.on("plotly_hover", mostrar);
      gd.on("plotly_unhover", programarOcultar);
    });
  }, 700);
})();
</script>""".replace("__META__", TOOLTIP).replace("__FECHA__", _svg("fecha"))
            .replace("__AREA__", _svg("area")).replace("__CONF__", _svg("conf"))), unsafe_allow_javascript=True)

"""Reordenar tarjetas arrastrándolas por su asa (≡). Las tarjetas son contenedores de Streamlit, así que
el JS solo detecta el arrastre en la página y devuelve a Python el nuevo orden; Python vuelve a dibujarlas."""
import streamlit as st

# Cada tarjeta lleva la clase st-key-<prefijo><tipo>_card y un asa .gm-asa con data-item=<tipo>
_JS = """
export default function (component) {
  const { setTriggerValue, data } = component;
  // Las escuchas se registran una sola vez; cada montaje actualiza el orden y la función de envío
  window.__gm = { enviar: setTriggerValue, orden: data.orden };
  if (window.__gmListo) return;
  window.__gmListo = true;

  let origen = null;
  const tarjeta = (el) => el && el.closest('[class*="st-key-"][class*="_gm_"][class*="_card"]');
  const item = (card) => card && card.querySelector(".gm-asa") && card.querySelector(".gm-asa").dataset.item;
  const limpiar = () => document.querySelectorAll(".gm-sobre, .gm-arrastrando")
    .forEach(c => c.classList.remove("gm-sobre", "gm-arrastrando"));

  document.addEventListener("dragstart", (e) => {
    const asa = e.target.closest && e.target.closest(".gm-asa");
    if (!asa) return;
    origen = asa.dataset.item;
    const card = tarjeta(asa);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", origen);
    if (card) { e.dataTransfer.setDragImage(card, 24, 24); setTimeout(() => card.classList.add("gm-arrastrando"), 0); }
  });
  document.addEventListener("dragover", (e) => {
    const card = tarjeta(e.target);
    if (!origen || !card) return;
    e.preventDefault();
    document.querySelectorAll(".gm-sobre").forEach(c => c !== card && c.classList.remove("gm-sobre"));
    if (item(card) !== origen) card.classList.add("gm-sobre");
  });
  document.addEventListener("drop", (e) => {
    const card = tarjeta(e.target);
    const destino = item(card);
    if (origen && destino && destino !== origen) {
      e.preventDefault();
      const orden = window.__gm.orden.filter(t => t !== origen);
      orden.splice(window.__gm.orden.indexOf(destino), 0, origen);
      window.__gm.enviar("orden", orden);
    }
    origen = null;
    limpiar();
  });
  document.addEventListener("dragend", () => { origen = null; limpiar(); });
}
"""

_componente = st.components.v2.component("ordenar_graficas", js=_JS, isolate_styles=False)

def nuevo_orden(orden, key):
    """Monta el detector de arrastre. Devuelve la lista reordenada si el usuario soltó una tarjeta, si no None."""
    resultado = _componente(key=key, data={"orden": list(orden)}, on_orden_change=lambda: None)
    return resultado.orden

def asa(item):
    """HTML del asa ≡ para la esquina de una tarjeta."""
    return (f"<span class='gm-asa' draggable='true' data-item='{item}' title='Arrastra para cambiar el orden'>"
            "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round'>"
            "<path d='M4 7h16M4 12h16M4 17h16'/></svg></span>")

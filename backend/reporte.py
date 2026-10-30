"""Reporte PDF del periodo seleccionado: resumen, gráfica, comparación de capturas, tabla y alertas.

Usa las fuentes base de fpdf2 (Latin-1), por eso todo el texto pasa por _t().
"""
import os
from datetime import datetime
from fpdf import FPDF, FontFace

from backend import config as cfg
from backend.calidad import estado_validacion, es_confiable
from backend.data_base import obtener_alertas

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACENTO = (60, 201, 180)
TINTA = (20, 26, 33)
SUAVE = (110, 120, 132)
LINEA = (220, 225, 230)
ROJO = (220, 80, 90)

def _t(texto):
    reemplazos = {"—": "-", "–": "-", "…": "...", "≥": ">=", "→": "->", "·": "·"}
    texto = "".join(reemplazos.get(c, c) for c in str(texto))
    return texto.encode("latin-1", "replace").decode("latin-1")

def _m2(valor):
    return f"{int(valor):,} m²".replace(",", ".")

def _fecha(texto, con_hora=True):
    try:
        f = datetime.strptime(str(texto)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(texto)
    return f.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")

class _PDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", size=8)
        self.set_text_color(*SUAVE)
        self.cell(0, 6, _t(f"Laguna Curiquinga · Monitoreo lacustre · Página {self.page_no()}/{{nb}}"), align="C")

def _titulo_seccion(pdf, texto):
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 8, _t(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACENTO)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 18, pdf.get_y())
    pdf.ln(3)

def _resumen(pdf, confiables, total):
    areas = [r["area"] for r in confiables]
    variacion = "-"
    if len(areas) > 1 and areas[0]:
        variacion = f"{(areas[-1] - areas[0]) / areas[0] * 100:+.1f}%"
    datos = [
        ("Mediciones confiables", f"{len(confiables)} de {total}"),
        ("Área más reciente", _m2(areas[-1]) if areas else "-"),
        ("Promedio", _m2(sum(areas) / len(areas)) if areas else "-"),
        ("Mínimo", _m2(min(areas)) if areas else "-"),
        ("Máximo", _m2(max(areas)) if areas else "-"),
        ("Variación del periodo", variacion),
    ]
    ancho = (pdf.w - pdf.l_margin - pdf.r_margin - 10) / 3
    x0, y0 = pdf.l_margin, pdf.get_y()
    for i, (etiqueta, valor) in enumerate(datos):
        x = x0 + (i % 3) * (ancho + 5)
        y = y0 + (i // 3) * 22
        pdf.set_draw_color(*LINEA)
        pdf.set_line_width(0.3)
        pdf.rect(x, y, ancho, 18, round_corners=True, style="D")
        pdf.set_xy(x + 4, y + 2.5)
        pdf.set_font("helvetica", size=8)
        pdf.set_text_color(*SUAVE)
        pdf.cell(ancho - 8, 5, _t(etiqueta))
        pdf.set_xy(x + 4, y + 8)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(*TINTA)
        pdf.cell(ancho - 8, 7, _t(valor))
    pdf.set_y(y0 + 44)

def _grafica(pdf, registros):
    """Línea de área en el tiempo dibujada a mano: las confiables unidas, las excluidas como cruces."""
    x0, y0 = pdf.l_margin + 14, pdf.get_y() + 2
    ancho, alto = pdf.w - pdf.l_margin - pdf.r_margin - 16, 62
    puntos = [r for r in registros if r.get("area")]
    if len(puntos) < 2:
        pdf.set_font("helvetica", size=9)
        pdf.set_text_color(*SUAVE)
        pdf.cell(0, 8, _t("No hay suficientes mediciones para dibujar la gráfica."), new_x="LMARGIN", new_y="NEXT")
        return
    tope = max(r["area"] for r in puntos) * 1.1
    paso = ancho / (len(puntos) - 1)

    pdf.set_font("helvetica", size=7)
    pdf.set_text_color(*SUAVE)
    pdf.set_line_width(0.2)
    for i in range(5):
        valor = tope * i / 4
        y = y0 + alto - alto * i / 4
        pdf.set_draw_color(*LINEA)
        pdf.dashed_line(x0, y, x0 + ancho, y, 1, 1)
        pdf.set_xy(x0 - 15, y - 2)
        pdf.cell(13, 4, f"{valor / 1000:.0f}k", align="R")

    coords = [(x0 + i * paso, y0 + alto - alto * r["area"] / tope, r) for i, r in enumerate(puntos)]
    confiables = [(x, y) for x, y, r in coords if es_confiable(r)]
    pdf.set_draw_color(*ACENTO)
    pdf.set_line_width(0.7)
    for (xa, ya), (xb, yb) in zip(confiables, confiables[1:]):
        pdf.line(xa, ya, xb, yb)
    for x, y, r in coords:
        if es_confiable(r):
            pdf.set_fill_color(*ACENTO)
            pdf.ellipse(x - 1, y - 1, 2, 2, style="F")
        else:
            pdf.set_draw_color(*SUAVE)
            pdf.set_line_width(0.4)
            pdf.line(x - 1.3, y - 1.3, x + 1.3, y + 1.3)
            pdf.line(x - 1.3, y + 1.3, x + 1.3, y - 1.3)

    # Etiquetas del eje X: como mucho 8 fechas repartidas
    salto = max(1, len(coords) // 8)
    pdf.set_text_color(*SUAVE)
    for i, (x, _, r) in enumerate(coords):
        if i % salto == 0 or i == len(coords) - 1:
            pdf.set_xy(x - 10, y0 + alto + 1.5)
            pdf.cell(20, 4, _fecha(r["fecha_captura"], con_hora=False), align="C")
    pdf.set_y(y0 + alto + 9)
    pdf.set_font("helvetica", size=8)
    pdf.cell(0, 4, _t("Línea: mediciones confiables · Cruces: capturas rechazadas, no aptas o atípicas"),
             new_x="LMARGIN", new_y="NEXT")

def _comparacion(pdf, confiables):
    con_imagen = [r for r in confiables if os.path.exists(os.path.join(BASE_DIR, r["ruta_procesada"]))]
    if len(con_imagen) < 1:
        return
    _titulo_seccion(pdf, "Comparación de capturas")
    pares = [con_imagen[0], con_imagen[-1]] if len(con_imagen) > 1 else [con_imagen[0]]
    ancho = (pdf.w - pdf.l_margin - pdf.r_margin - 6) / 2
    alto = ancho * 9 / 16
    if pdf.get_y() + alto + 14 > pdf.h - pdf.b_margin:
        pdf.add_page()
    y = pdf.get_y()
    for i, r in enumerate(pares):
        x = pdf.l_margin + i * (ancho + 6)
        pdf.image(os.path.join(BASE_DIR, r["ruta_procesada"]), x=x, y=y, w=ancho, h=alto)
        pdf.set_xy(x, y + alto + 1.5)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(*TINTA)
        etiqueta = "Primera" if i == 0 and len(pares) > 1 else "Más reciente"
        pdf.cell(ancho, 5, _t(f"{etiqueta} · {_fecha(r['fecha_captura'])} · {_m2(r['area'])}"))
    pdf.set_y(y + alto + 9)

def _tabla(pdf, registros):
    if pdf.get_y() > pdf.h - pdf.b_margin - 50:  # que el título no quede solo al pie de la página
        pdf.add_page()
    _titulo_seccion(pdf, "Mediciones del periodo")
    pdf.set_fill_color(255, 255, 255)  # la gráfica deja el color de acento como relleno activo
    pdf.set_font("helvetica", size=8)
    pdf.set_text_color(*TINTA)
    pdf.set_draw_color(*LINEA)
    pdf.set_line_width(0.2)
    with pdf.table(col_widths=(28, 20, 24, 22, 20, 22, 46), text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "LEFT", "LEFT"),
                   headings_style=FontFace(emphasis="BOLD", color=TINTA, fill_color=(238, 242, 245)),
                   cell_fill_color=(248, 250, 251), cell_fill_mode="ROWS", line_height=5.5, first_row_as_headings=True) as tabla:
        encabezado = tabla.row()
        for titulo in ("Captura", "Origen", "Área", "Perímetro", "Confianza", "Estado", "Observación"):
            encabezado.cell(_t(titulo))
        for r in reversed(registros):
            fila = tabla.row()
            confianza = r.get("confianza")
            fila.cell(_fecha(r["fecha_captura"]))
            fila.cell("Manual" if "Manual" in str(r["estado"]) else _t("Automático"))
            fila.cell(_t(_m2(r["area"])))
            fila.cell(f"{r['perimetro']} m")
            fila.cell(f"{confianza:.0%}" if isinstance(confianza, float) and confianza == confianza else "-")
            fila.cell(_t(estado_validacion(r)))
            observacion = r.get("observacion")
            fila.cell(_t(observacion if isinstance(observacion, str) else ""))

def _alertas(pdf, registros):
    """Alertas de los registros del periodo y avisos de inactividad posteriores a su inicio."""
    ids = {r["id"] for r in registros}
    desde = registros[0]["fecha_captura"][:10]
    alertas = [a for a in obtener_alertas(limite=500)
               if a["registro_id"] in ids or (a["registro_id"] is None and a["fecha"][:10] >= desde)]
    _titulo_seccion(pdf, "Alertas")
    pdf.set_font("helvetica", size=9)
    if not alertas:
        pdf.set_text_color(*SUAVE)
        pdf.cell(0, 6, _t("Sin alertas registradas en el periodo."), new_x="LMARGIN", new_y="NEXT")
        return
    for a in alertas[:40]:
        pdf.set_text_color(*(ROJO if a["nivel"] == "critica" else TINTA))
        pdf.multi_cell(0, 5, _t(f"{_fecha(a['fecha'])} · {a['mensaje']}"), new_x="LMARGIN", new_y="NEXT")

def generar_reporte(registros, periodo="Todo el historial"):
    """registros: lista de dicts (los del periodo). Devuelve el PDF en bytes."""
    registros = sorted(registros, key=lambda r: r["fecha_captura"])
    confiables = [r for r in registros if es_confiable(r)]

    pdf = _PDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_fill_color(*ACENTO)
    pdf.rect(0, 0, pdf.w, 3, style="F")
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 10, _t("Laguna Curiquinga · Reporte de monitoreo"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=10)
    pdf.set_text_color(*SUAVE)
    rango = (f"{_fecha(registros[0]['fecha_captura'], False)} a {_fecha(registros[-1]['fecha_captura'], False)}"
             if registros else "sin datos")
    pdf.cell(0, 6, _t(f"Periodo: {periodo} ({rango}) · {cfg.cargar()['origen']['nombre_camara']}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _t(f"Generado el {datetime.now():%d/%m/%Y a las %H:%M}"), new_x="LMARGIN", new_y="NEXT")

    _titulo_seccion(pdf, "Resumen")
    _resumen(pdf, confiables, len(registros))
    _titulo_seccion(pdf, "Área superficial en el tiempo")
    _grafica(pdf, registros)
    _comparacion(pdf, confiables)
    if registros:
        _tabla(pdf, registros)
        _alertas(pdf, registros)
    return bytes(pdf.output())

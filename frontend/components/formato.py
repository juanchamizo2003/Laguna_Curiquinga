import pandas as pd

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

def formatear_m2(valor):
    return f"{int(valor):,} m²".replace(",", ".")

def fecha_legible(fecha_texto, con_hora=True):
    """'2026-04-26 13:24:36' -> '26 abr 2026 · 13:24'"""
    fecha = pd.to_datetime(fecha_texto, errors="coerce")
    if pd.isna(fecha):
        return str(fecha_texto)
    texto = f"{fecha.day} {MESES_CORTOS[fecha.month - 1]} {fecha.year}"
    return f"{texto} · {fecha:%H:%M}" if con_hora else texto

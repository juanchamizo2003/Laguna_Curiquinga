from datetime import datetime, timedelta

import numpy as np
import pytest

from backend import data_base, config as cfg, acceso, respaldo
from backend.alertas import evaluar_registro, verificar_inactividad
from backend.calidad import revisar_imagen, revisar_agua, estado_validacion, es_confiable, marcar_atipicas
from backend.procesamiento import procesar_imagen
from backend.servicio import extraer_fecha_hora_de_nombre
from tests.conftest import nuevo_registro

# ---------------------------------------------------------------- nombres de archivo

def test_fecha_desde_nombre():
    assert extraer_fecha_hora_de_nombre("Curiquinga_20260426_132436M.jpg") == ("2026-04-26", "13:24:36")

def test_fecha_sin_patron_usa_ahora():
    fecha, hora = extraer_fecha_hora_de_nombre("foto.jpg")
    assert fecha == datetime.now().strftime("%Y-%m-%d") and len(hora) == 8

# ---------------------------------------------------------------- calidad

def _imagen_textura(brillo=120, amplitud=60, semilla=0):
    rng = np.random.default_rng(semilla)
    ruido = rng.integers(-amplitud, amplitud, size=(1080, 1920, 3))
    return np.clip(brillo + ruido, 0, 255).astype(np.uint8)

def test_imagen_normal_es_apta():
    apta, motivo, _ = revisar_imagen(_imagen_textura())
    assert apta and motivo is None

def test_imagen_nocturna_se_descarta():
    apta, motivo, _ = revisar_imagen(_imagen_textura(brillo=10, amplitud=5))
    assert not apta and "oscura" in motivo

def test_imagen_sin_contraste_se_descarta():
    apta, motivo, _ = revisar_imagen(np.full((1080, 1920, 3), 128, np.uint8))
    assert not apta and "contraste" in motivo

def test_agua_gris_es_niebla():
    assert revisar_agua("#A0A8A5") is not None   # caso real del 2 mar 2025
    assert revisar_agua("#71C1B8") is None

def test_estado_validacion_prioriza_revision_humana():
    base = {"confianza": 0.5, "observacion": "niebla", "revision": None}
    assert estado_validacion(base, 0.85) == "No apta"
    assert estado_validacion({**base, "revision": "aprobada"}, 0.85) == "Aprobada"
    assert estado_validacion({**base, "revision": "rechazada"}, 0.85) == "Rechazada"
    assert estado_validacion({"confianza": 0.9}, 0.85) == "Validada"
    assert estado_validacion({"confianza": 0.5}, 0.85) == "Revisar"
    assert estado_validacion({"confianza": float("nan")}, 0.85) == "Pendiente"
    assert not es_confiable({**base}, 0.85) and es_confiable({"confianza": 0.5}, 0.85)

UMBRALES_ATIPICOS = {"atipico_pct": 10, "atipico_ventana_h": 2, "atipico_vecinas": 3}

def _serie(areas, inicio="2026-01-01 08:00:00", paso_min=10, **extra):
    t0 = datetime.strptime(inicio, "%Y-%m-%d %H:%M:%S")
    return [{"id": i, "area": a, "confianza": 0.95,
             "fecha_captura": (t0 + timedelta(minutes=paso_min * i)).strftime("%Y-%m-%d %H:%M:%S"), **extra}
            for i, a in enumerate(areas)]

def test_atipica_se_excluye_sola():
    regs = marcar_atipicas(_serie([50000, 50400, 49800, 31000, 50200, 49900]), UMBRALES_ATIPICOS)
    assert [r["atipica"] for r in regs] == [False, False, False, True, False, False]
    assert estado_validacion(regs[3], 0.85) == "Atípica" and not es_confiable(regs[3], 0.85)

def test_atipica_respeta_aprobacion_y_capturas_espaciadas():
    regs = _serie([50000, 50400, 49800, 31000, 50200])
    regs[3]["revision"] = "aprobada"
    assert not any(r["atipica"] for r in marcar_atipicas(regs, UMBRALES_ATIPICOS))
    # Una captura al día (cargas manuales): sin vecinas en la ventana no se juzga
    espaciadas = _serie([50000, 50400, 31000, 50200], paso_min=24 * 60)
    assert not any(r["atipica"] for r in marcar_atipicas(espaciadas, UMBRALES_ATIPICOS))

def test_cambio_real_sostenido_no_es_atipico():
    # La laguna baja de verdad y se queda: tras unas pocas capturas la mediana alcanza el nuevo nivel
    regs = marcar_atipicas(_serie([50000] * 12 + [40000] * 12), UMBRALES_ATIPICOS)
    assert not any(r["atipica"] for r in regs[18:])

# ---------------------------------------------------------------- base de datos y alertas

def test_migracion_y_revision(bd_temporal):
    r = nuevo_registro("a_20260101_120000.jpg", "2026-01-01", 50000)
    data_base.marcar_revision(r["id"], "rechazada")
    assert data_base.obtener_registro(r["id"])["revision"] == "rechazada"
    # Volver a guardar la misma foto (reprocesado) borra la revisión anterior
    nuevo_registro("a_20260101_120000.jpg", "2026-01-01", 51000)
    assert data_base.obtener_registro(r["id"])["revision"] is None

def test_alerta_cambio_brusco_y_area_baja(bd_temporal):
    cfg.actualizar("alertas", {"cambio_pct": 15, "area_min": 30000})
    nuevo_registro("a.jpg", "2026-01-01", 50000)
    r = nuevo_registro("b.jpg", "2026-01-02", 25000)
    ids = evaluar_registro(r, notificar=False)
    tipos = {a["tipo"] for a in data_base.obtener_alertas()}
    assert len(ids) == 2 and tipos == {"cambio_brusco", "area_baja"}
    # Evaluar de nuevo el mismo registro no duplica
    assert evaluar_registro(r, notificar=False) == []

def test_alerta_ignora_mediciones_no_confiables(bd_temporal):
    nuevo_registro("a.jpg", "2026-01-01", 50000)
    nuevo_registro("niebla.jpg", "2026-01-02", 20000, observacion="Agua sin color")
    r = nuevo_registro("c.jpg", "2026-01-03", 51000)
    # La comparación es contra la última confiable (50.000), no contra la de niebla
    assert evaluar_registro(r, notificar=False) == []

def _captura(nombre, fecha_hora, area):
    return data_base.obtener_registro(data_base.guardar_registro(
        nombre_foto=nombre, fecha_subida=fecha_hora, fecha_captura=fecha_hora, area=area, perimetro=500,
        color_hex="#71C1B8", estado="Procesado (Automático)", ruta_original=nombre, ruta_procesada=nombre,
        confianza=0.95))

def test_alerta_usa_mediana_y_no_se_repite(bd_temporal):
    cfg.actualizar("alertas", {"cambio_pct": 15, "area_min": 30000, "mediana_h": 1})
    t0 = datetime(2026, 1, 1, 8, 0)
    creadas = []
    # Dos horas estables, una foto mala suelta y luego una bajada real y sostenida
    areas = [50000] * 12 + [20000] + [50000] * 5 + [40000] * 12
    for i, area in enumerate(areas):
        r = _captura(f"f{i}.jpg", (t0 + timedelta(minutes=10 * i)).strftime("%Y-%m-%d %H:%M:%S"), area)
        creadas += evaluar_registro(r, notificar=False)
    alertas = data_base.obtener_alertas()
    # La foto de 20.000 no dispara nada (atípica) y la bajada real avisa una sola vez
    assert [a["tipo"] for a in alertas] == ["cambio_brusco"]
    assert "mediana de" in alertas[0]["mensaje"]

def test_inactividad_avisa_una_vez(bd_temporal):
    cfg.actualizar("alertas", {"horas_sin_fotos": 6})
    nuevo_registro("a.jpg", "2026-01-01", 50000)
    ahora = datetime(2026, 1, 1, 20, 0)
    assert verificar_inactividad(ahora=ahora) is not None
    assert verificar_inactividad(ahora=ahora + timedelta(hours=1)) is None
    # Recién iniciado el servicio no se avisa aunque no haya capturas
    data_base.eliminar_alertas()
    assert verificar_inactividad(ahora=ahora, inicio_servicio=ahora - timedelta(minutes=5)) is None

# ---------------------------------------------------------------- configuración, acceso y respaldos

def test_config_fusiona_valores_por_defecto(bd_temporal):
    cfg.actualizar("alertas", {"cambio_pct": 40})
    config = cfg.cargar()
    assert config["alertas"]["cambio_pct"] == 40
    assert config["alertas"]["area_min"] == cfg.POR_DEFECTO["alertas"]["area_min"]

def test_contrasena(bd_temporal):
    assert not acceso.protegido()
    acceso.establecer_clave("clave-de-prueba")
    assert acceso.protegido() and acceso.comprobar("clave-de-prueba") and not acceso.comprobar("otra")
    acceso.establecer_clave("")
    assert not acceso.protegido()

def test_pase_de_sesion(bd_temporal):
    acceso.establecer_clave("clave-de-prueba")
    pase = acceso.emitir_pase(ahora=1000)
    assert acceso.pase_valido(pase, ahora=1000)
    assert not acceso.pase_valido(pase, ahora=1000 + acceso.VALIDEZ_PASE + 1)   # vencido
    vence, _, firma = pase.partition(".")
    assert not acceso.pase_valido(f"{int(vence) + 999}.{firma}", ahora=1000)     # alterado
    assert not acceso.pase_valido("basura", ahora=1000) and not acceso.pase_valido(None)
    acceso.establecer_clave("otra-clave")
    assert not acceso.pase_valido(pase, ahora=1000)                               # la clave cambió

def test_respaldo_conserva_los_ultimos(bd_temporal, monkeypatch):
    nuevo_registro("a.jpg", "2026-01-01", 50000)
    marcas = iter(range(100))
    monkeypatch.setattr(respaldo, "datetime", type("D", (), {"now": staticmethod(lambda: datetime(2026, 1, 1, 0, 0, next(marcas))),
                                                             "fromtimestamp": staticmethod(datetime.fromtimestamp)}))
    for _ in range(4):
        respaldo.crear_respaldo(conservar=2)
    assert len(respaldo.listar_respaldos()) == 2

# ---------------------------------------------------------------- flujo completo sin SAM

def test_procesar_imagen_con_analizador_falso(bd_temporal, tmp_path, monkeypatch):
    import cv2
    from backend import procesamiento, miniaturas
    monkeypatch.setattr(procesamiento, "DIR_PROCESADAS", str(tmp_path / "procesadas"))
    monkeypatch.setattr(procesamiento, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(miniaturas, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(miniaturas, "DIR_MINIATURAS", str(tmp_path / "mini"))
    ruta = tmp_path / "Curiquinga_20260426_132436M.jpg"
    cv2.imwrite(str(ruta), _imagen_textura())

    def falso(ruta_img, calibracion):
        return True, "ok", {"area": 42000, "perimetro": 600, "color_hex": "#71C1B8", "confianza": 0.97,
                            "img_visual": np.zeros((1080, 1920, 3), np.uint8)}

    r = procesar_imagen(str(ruta), "Manual", evaluar_alertas=False, analizar=falso)
    assert r["resultado"] == "registrada"
    assert r["registro"]["fecha_captura"] == "2026-04-26 13:24:36"
    assert (tmp_path / "mini" / "trazo_Curiquinga_20260426_132436M.jpg").exists()

def test_agua_sin_color_se_descarta_sin_guardar(bd_temporal, tmp_path, monkeypatch):
    """Niebla sobre la laguna: el área no sirve, así que no se guarda registro ni trazo."""
    import cv2
    from backend import procesamiento
    monkeypatch.setattr(procesamiento, "DIR_PROCESADAS", str(tmp_path / "proc"))
    ruta = tmp_path / "Curiquinga_20260426_132436M.jpg"
    cv2.imwrite(str(ruta), _imagen_textura())

    def gris(ruta_img, calibracion):
        return True, "ok", {"area": 42000, "perimetro": 600, "color_hex": "#A0A8A5", "confianza": 0.97,
                            "img_visual": np.zeros((1080, 1920, 3), np.uint8)}

    r = procesar_imagen(str(ruta), "Manual", evaluar_alertas=False, analizar=gris)
    assert r["resultado"] == "descartada" and r["mensaje"]
    assert data_base.obtener_registros() == []
    assert not (tmp_path / "proc").exists()

def test_procesar_imagen_oscura_no_llama_a_sam(bd_temporal, tmp_path):
    import cv2
    ruta = tmp_path / "noche.jpg"
    cv2.imwrite(str(ruta), _imagen_textura(brillo=8, amplitud=4))
    r = procesar_imagen(str(ruta), "Automático", analizar=lambda *a: pytest.fail("no debía llamar a SAM"))
    assert r["resultado"] == "descartada"

# ---------------------------------------------------------------- sincronización con la cámara

def test_origen_no_reimporta_lo_ya_traido(bd_temporal, tmp_path, monkeypatch):
    import os, time
    import vigilante
    origen, ingesta = tmp_path / "camara", tmp_path / "ingesta"
    origen.mkdir(); ingesta.mkdir()
    monkeypatch.setattr(vigilante, "DIR_INGESTA", str(ingesta))
    monkeypatch.setattr(vigilante, "DIR_DESCARTES", str(tmp_path))
    monkeypatch.setattr(vigilante, "RUTA_IMPORTADAS", str(tmp_path / "importadas.txt"))
    monkeypatch.setattr(vigilante, "registrar", lambda *a: None)  # no escribir en el log real del vigilante
    foto = origen / "Curiquinga_20261027_090000M.jpg"
    foto.write_bytes(b"x")
    viejo = time.time() - 60
    os.utime(foto, (viejo, viejo))

    vigilante.sincronizar_origen(str(origen))
    assert (ingesta / foto.name).exists()
    # Se borra el registro y la copia (como hace el panel): no debe volver a traerse
    (ingesta / foto.name).unlink()
    vigilante.sincronizar_origen(str(origen))
    assert not (ingesta / foto.name).exists()

def test_descarte_borra_la_foto_y_no_la_reimporta(bd_temporal, tmp_path, monkeypatch):
    import vigilante
    ingesta, descartes = tmp_path / "ingesta", tmp_path / "descartes"
    ingesta.mkdir(); descartes.mkdir()
    monkeypatch.setattr(vigilante, "DIR_INGESTA", str(ingesta))
    monkeypatch.setattr(vigilante, "DIR_DESCARTES", str(descartes))
    monkeypatch.setattr(vigilante, "RUTA_MOTIVOS", str(descartes / "_motivos.jsonl"))
    monkeypatch.setattr(vigilante, "RUTA_IMPORTADAS", str(tmp_path / "importadas.txt"))
    foto = ingesta / "Curiquinga_20261027_030000M.jpg"
    foto.write_bytes(b"x")

    vigilante.descartar(str(foto), "Imagen demasiado oscura")
    assert not foto.exists() and list(descartes.iterdir()) == [descartes / "_motivos.jsonl"]
    assert foto.name in vigilante._ya_conocidas()

def test_eliminar_registro_borra_sus_alertas(bd_temporal):
    nuevo_registro("a.jpg", "2026-01-01", 50000)
    r = nuevo_registro("b.jpg", "2026-01-02", 20000)
    evaluar_registro(r, notificar=False)
    assert data_base.obtener_alertas()
    data_base.eliminar_registro(r["id"])
    assert data_base.obtener_alertas() == []

def test_fotos_descartadas_cuentan_como_actividad(bd_temporal):
    """De noche llegan fotos que se descartan por oscuras: la cámara funciona, no hay que avisar."""
    cfg.actualizar("alertas", {"horas_sin_fotos": 6})
    nuevo_registro("a.jpg", "2026-01-01", 50000)          # última registrada: 01/01 12:00
    ahora = datetime(2026, 1, 2, 3, 0)                     # 15 h después, de madrugada
    assert verificar_inactividad(ahora=ahora, ultima_llegada=ahora - timedelta(minutes=10)) is None
    assert verificar_inactividad(ahora=ahora) is not None  # sin ninguna foto, sí avisa

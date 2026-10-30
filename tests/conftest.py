import os
import pytest

from backend import data_base, config as cfg, respaldo

@pytest.fixture
def bd_temporal(tmp_path, monkeypatch):
    """Base de datos, configuración y respaldos en una carpeta temporal: nunca se toca base_datos/."""
    monkeypatch.setattr(data_base, "DB_PATH", str(tmp_path / "registros.db"))
    monkeypatch.setattr(data_base, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "RUTA_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(respaldo, "DIR_RESPALDOS", str(tmp_path / "respaldos"))
    data_base.inicializar_bd()
    return tmp_path

def nuevo_registro(nombre, fecha, area, **extra):
    datos = dict(nombre_foto=nombre, fecha_subida=f"{fecha} 12:00:00", fecha_captura=f"{fecha} 12:00:00", area=area,
                 perimetro=500, color_hex="#71C1B8", estado="Procesado (Automático)",
                 ruta_original=os.path.join("x", nombre), ruta_procesada=os.path.join("y", nombre), confianza=0.95)
    datos.update(extra)
    return data_base.obtener_registro(data_base.guardar_registro(**datos))

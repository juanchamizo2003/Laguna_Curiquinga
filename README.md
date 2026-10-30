# Laguna Curiquinga

Herramienta de monitoreo del área superficial de la laguna Curiquinga. Cada fotografía de la cámara se segmenta con el modelo **SAM (Segment Anything, ViT-B)** para aislar el espejo de agua. A partir de la máscara se calculan el área (m²), el perímetro (m), el color medio del agua y la confianza del modelo, y los resultados se guardan en una base SQLite que alimenta un panel en Streamlit.

## Estructura

```
backend/
  motor.py           Segmentación con SAM, homografía y cálculo de área/perímetro/color/confianza
  procesamiento.py   Flujo común de una foto: calidad → SAM → trazo y miniatura → registro → alertas
  calidad.py         Control de calidad de imagen y estado de validación de cada registro
  alertas.py         Reglas de alerta y envío por Telegram o correo
  config.py          Configuración editable desde el panel (base_datos/config.json)
  data_base.py       Base SQLite (base_datos/registros.db), alertas y migraciones
  respaldo.py        Copias de seguridad de la base
  reporte.py         Reporte PDF del periodo
  servicio.py        Latido, log y arranque/parada del vigilante
  acceso.py          Contraseña opcional del panel
  miniaturas.py      Miniaturas para la galería y el carrusel
frontend/
  app.py             Punto de entrada de Streamlit, tema, navegación y acceso
  views/             Inicio, Cargar y procesar, Alertas, Control de servidor, Configuración
  components/        Gráfica, visor, filtro temporal, tabla, formulario de carga, tarjetas
flujo_imagenes/
  carga_manual/      Fotos subidas desde la página "Cargar y procesar"
  ingesta_camara/    Fotos de la cámara (las vigila vigilante.py)
  fotos_procesadas/  Fotos con el contorno de la laguna dibujado (trazo_*.jpg)
  miniaturas/        Versiones pequeñas para la galería
  descartes_historicos/  Fotos que no pasaron el control de calidad (motivos en _motivos.jsonl)
base_datos/          registros.db, config.json, respaldos/ y servicio/ (latido y log): no se suben a git
modelos/             Pesos de SAM (no se suben al repositorio)
scripts/             instalar_tarea.ps1: vigilante y panel como tareas de Windows
tests/               Pruebas (pytest)
vigilante.py         Servicio que procesa automáticamente lo que entra a ingesta_camara
run.py               Arranca el vigilante y Streamlit a la vez
```
## Instalación

Requiere Python 3.10 o superior (desarrollado con 3.14). Los pasos son para Windows (PowerShell),
ejecutados desde la carpeta raíz del proyecto:

```powershell
# 1. Crear el entorno virtual (solo la primera vez)
py -m venv .venv

# 2. Activarlo (cada vez que se abra una terminal nueva)
.\.venv\Scripts\Activate.ps1

# 3. Actualizar pip
python -m pip install --upgrade pip

# 4. Instalar todas las librerías (Streamlit, Plotly, SAM, torch, etc.)
pip install -r requirements.txt

# 5. Descargar los pesos del modelo SAM (~375 MB) a la carpeta modelos/
Invoke-WebRequest https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth -OutFile modelos\sam_vit_b_01ec64.pth
```

Si PowerShell no deja activar el entorno ("la ejecución de scripts está deshabilitada"), ejecuta una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve al paso 2.

En Linux / macOS: `python3 -m venv .venv`, `source .venv/bin/activate` y luego los pasos 3 a 5
(el paso 5 con `curl -o modelos/sam_vit_b_01ec64.pth <enlace>`).

Ya no hace falta instalar aparte `segment-anything`, `plotly` ni `streamlit-calendar`: los dos primeros
vienen en `requirements.txt` y el calendario ahora es propio del panel.

Para usar la GPU, instala la variante CUDA de `torch` y `torchvision` siguiendo https://pytorch.org/get-started/locally/. Sin GPU el modelo corre en CPU, pero cada imagen tarda bastante más.

### Pesos del modelo

El archivo `.pth` pesa unos 375 MB y no se sube a git (está en `.gitignore`); la carpeta `modelos/`
sí está en el repositorio, con un `LEEME.md` que lo recuerda. Debe quedar como
`modelos/sam_vit_b_01ec64.pth`, descargado de:

https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth

## Ejecución

Con el entorno virtual activado (paso 2):

```powershell
py run.py                                 # vigilante + panel, a la vez
python -m streamlit run frontend/app.py   # solo el panel
```

El panel se abre en http://localhost:8501.

### Dejarlo corriendo en un servidor Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1                  # al iniciar sesión
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1 -AlIniciarEquipo  # al encender el equipo (como administrador)
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1 -Desinstalar
```

Crea dos tareas programadas ("Curiquinga - Vigilante" y "Curiquinga - Panel") que se reinician solas si fallan.
El vigilante se niega a arrancar si ya hay otro en línea, así que no se duplica aunque también se inicie desde el panel.

## Flujos de datos

Las tres entradas pasan por el mismo flujo (`backend/procesamiento.py`):

1. **Control de calidad previo.** Si la foto es nocturna, está quemada, no tiene contraste (niebla densa, lente cubierto) o está desenfocada, se descarta sin pasar por SAM.
2. **Segmentación con SAM** y cálculo de área, perímetro, color del agua y confianza.
3. **Control posterior.** Si el agua segmentada sale casi gris hay niebla sobre la laguna: el registro se guarda pero queda **No apto** y no entra en la gráfica ni en las alertas.
4. **Registro, miniatura y alertas.**

- **Manual:** en *Cargar y procesar* se suben una o varias fotos (se guardan en `flujo_imagenes/carga_manual/`).
- **Automático:** `vigilante.py` procesa cada foto que aparece en `flujo_imagenes/ingesta_camara/`. Si en *Configuración → Cámara* se indica una carpeta de origen (local o de red, por ejemplo donde el FTP de la cámara deja las fotos), el vigilante copia de ahí las nuevas cada pocos segundos. Al arrancar procesa también las que llegaron mientras estaba apagado.
- **Reprocesar:** en *Cargar y procesar → Registros* se pueden volver a analizar los registros seleccionados, los que no tienen confianza o todos, por ejemplo tras recalibrar.

La fecha y la hora de captura se toman del nombre del archivo, con el formato `Curiquinga_AAAAMMDD_HHMMSS*.jpg`.

## Validación

Cada registro tiene un estado: **Validada** (confianza de SAM ≥ umbral), **Revisar** (por debajo), **No apta** (falló el control posterior), **Pendiente** (sin confianza guardada) o, si alguien lo revisó a mano, **Aprobada** / **Rechazada**. Se aprueba o rechaza desde el visor de Inicio, la carga o la tabla de registros. Con *Solo confiables* activo, el panel excluye las rechazadas y no aptas de los indicadores y de la línea, y las muestra como cruces grises.

## Alertas

Se avisa cuando el área cambia más de un porcentaje respecto a la medición confiable anterior, cuando baja de un mínimo y cuando el vigilante pasa varias horas sin recibir capturas. Las reglas y los canales (Telegram y correo SMTP) se configuran en *Configuración → Alertas*; ahí también hay un botón para enviar una alerta de prueba. *Alertas → Revisar historial* aplica las reglas a las mediciones ya guardadas sin enviar nada.

## Respaldos, reporte y acceso

- El vigilante respalda `registros.db` cada 24 h en `base_datos/respaldos/` y conserva los últimos 14 (configurable). También se puede respaldar desde *Control de servidor* o *Configuración*.
- *Inicio → Exportar* descarga los datos en CSV o un **reporte PDF** del periodo de la gráfica.
- *Configuración → Acceso* activa una contraseña para el panel (se guarda solo su hash).

## Pruebas

```bash
pip install pytest
python -m pytest
```

## Calibración

Los puntos guía de SAM, las esquinas del plano usado para la homografía y los factores m²/píxel y m/píxel se editan en *Configuración → Calibración*. La vista previa los dibuja sobre cualquier foto y el botón *Probar segmentación* calcula el área con los valores nuevos antes de guardarlos.

Si la cámara se mueve o cambia de resolución hay que recalibrar; si no, las áreas serán incorrectas aunque la segmentación se vea bien. Después de guardar una calibración nueva conviene reprocesar los registros para que todos usen los mismos valores.

## Confianza

La confianza es el IoU que el propio SAM predice para la máscara (de 0 a 100 %). Sirve para detectar segmentaciones dudosas, por ejemplo con niebla o de noche. Los registros procesados antes de añadir esta columna la muestran como "—" hasta que se vuelvan a procesar.

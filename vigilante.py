import os
import time
import shutil
import cv2
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.data_base import inicializar_bd, guardar_registro
from backend.motor import analizar_laguna

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLUJO_DIR = os.path.join(BASE_DIR, "flujo_imagenes")

DIR_INGESTA = os.path.join(FLUJO_DIR, "ingesta_camara")
DIR_PROCESADAS = os.path.join(FLUJO_DIR, "fotos_procesadas")
DIR_DESCARTES = os.path.join(FLUJO_DIR, "descartes_historicos")

os.makedirs(DIR_INGESTA, exist_ok=True)
os.makedirs(DIR_PROCESADAS, exist_ok=True)
os.makedirs(DIR_DESCARTES, exist_ok=True)

class ImageHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            return

        filename = os.path.basename(event.src_path)
        print(f"\n[VIGILANTE] Nueva imagen detectada: {filename}")
        time.sleep(1.5)

        try:
            exito, msg_ia, datos = analizar_laguna(event.src_path)

            if not exito or datos["area"] == 0:
                ruta_descarte = os.path.join(DIR_DESCARTES, f"descarte_{filename}")
                if os.path.exists(event.src_path):
                    shutil.move(event.src_path, ruta_descarte)
                print(f" [X] Análisis no válido ({msg_ia}). Movido a descartes.")
            else:
                ruta_procesada_abs = os.path.join(DIR_PROCESADAS, f"trazo_{filename}")
                cv2.imwrite(ruta_procesada_abs, cv2.cvtColor(datos["img_visual"], cv2.COLOR_RGB2BGR))

                ruta_original_rel = os.path.join("flujo_imagenes", "ingesta_camara", filename)
                ruta_procesada_rel = os.path.join("flujo_imagenes", "fotos_procesadas", f"trazo_{filename}")

                f_subida = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                partes = filename.split('_')
                f_captura = partes[1] if len(partes) > 1 else datetime.now().strftime("%Y%m%d")

                guardar_registro(
                    nombre_foto=filename,
                    fecha_subida=f_subida,
                    fecha_captura=f_captura,
                    area=datos["area"],
                    perimetro=datos["perimetro"],
                    color_hex=datos["color_hex"],
                    estado="Procesado",
                    ruta_original=ruta_original_rel,
                    ruta_procesada=ruta_procesada_rel
                )
                print(f" [✓] Registro procesado y guardado en BD.")

        except Exception as e:
            print(f" [!] Error en servicio de vigilancia: {str(e)}")

if __name__ == "__main__":
    inicializar_bd()
    observer = Observer()
    observer.schedule(ImageHandler(), path=DIR_INGESTA, recursive=False)
    observer.start()
    print(f"👁️ Servicio Vigilante iniciado. Escuchando: {DIR_INGESTA}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
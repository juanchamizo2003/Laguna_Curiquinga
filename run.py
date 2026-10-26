import subprocess
import sys

def iniciar_proyecto():
    print("🚀 Iniciando servicios de Proyecto Ingeominas...\n")
    
    # 1. Inicia vigilante.py en segundo plano
    p_vigilante = subprocess.Popen([sys.executable, "vigilante.py"])
    
    # 2. Inicia Streamlit
    p_streamlit = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "frontend/app.py"])

    try:
        p_vigilante.wait()
        p_streamlit.wait()
    except KeyboardInterrupt:
        print("\n⏹️ Deteniendo todos los servicios...")
        p_vigilante.terminate()
        p_streamlit.terminate()

if __name__ == "__main__":
    iniciar_proyecto()
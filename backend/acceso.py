"""Contraseña opcional del panel. Se guarda solo el hash PBKDF2 en base_datos/config.json."""
import os
import hmac
import hashlib
import time

from backend import config as cfg

ITERACIONES = 200_000

def crear_hash(clave):
    sal = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal.hex()}${digest.hex()}"

def verificar(clave, hash_guardado):
    try:
        _, iteraciones, sal, digest = hash_guardado.split("$")
        calculado = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calculado.hex(), digest)

def protegido():
    return bool(cfg.cargar()["acceso"]["clave_hash"])

def establecer_clave(clave):
    cfg.actualizar("acceso", {"clave_hash": crear_hash(clave) if clave else ""})

def comprobar(clave):
    return verificar(clave, cfg.cargar()["acceso"]["clave_hash"])

# Pase de sesión para la recarga que hace el cambio de tema: el navegador lo guarda en una cookie de
# un minuto y la sesión nueva lo canjea. Va firmado con el hash de la clave, así que cambiarla lo anula.
VALIDEZ_PASE = 12 * 3600

def _firma(texto):
    return hmac.new(cfg.cargar()["acceso"]["clave_hash"].encode(), texto.encode(), hashlib.sha256).hexdigest()

def emitir_pase(ahora=None):
    vence = int((ahora if ahora is not None else time.time()) + VALIDEZ_PASE)
    return f"{vence}.{_firma(str(vence))}"

def pase_valido(pase, ahora=None):
    if not pase or not protegido():
        return False
    vence, _, firma = str(pase).partition(".")
    if not vence.isdigit() or int(vence) < (ahora if ahora is not None else time.time()):
        return False
    return hmac.compare_digest(firma, _firma(vence))

# iazar/utils/randomx_wrapper.py
import ctypes
import os
import binascii

# Ruta ABSOLUTA a la DLL, siempre válida para ejecución profesional Windows/Linux
DLL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "libs", "randomx.dll")
)
if not os.path.isfile(DLL_PATH):
    raise FileNotFoundError(f"randomx.dll no encontrada en: {DLL_PATH}")
randomx = ctypes.CDLL(DLL_PATH)

# Constantes estándar RandomX
RANDOMX_FLAG_DEFAULT = 0
RANDOMX_HASH_SIZE = 32
BLOB_NONCE_OFFSET = 39  # Offset real del nonce en blob Monero

def hex_to_bytes(hex_str: str) -> bytes:
    """Convierte cadena hex a bytes."""
    return binascii.unhexlify(hex_str.strip())

def compute_randomx_hash(blob_hex: str, nonce: int, seed_hash_hex: str) -> str:
    """
    Calcula el hash RandomX para un blob Monero y nonce dado.
    Args:
        blob_hex (str): blob hex string del trabajo pool.
        nonce (int): nonce entero a insertar.
        seed_hash_hex (str): seed hash en hex.
    Returns:
        str: hash hexadecimal (64 chars).
    """
    # 1. Preparar blob y clave
    blob = bytearray(hex_to_bytes(blob_hex))
    blob[BLOB_NONCE_OFFSET:BLOB_NONCE_OFFSET+4] = int(nonce).to_bytes(4, "little")
    key = hex_to_bytes(seed_hash_hex)

    # 2. Reservar e inicializar cache
    randomx_alloc_cache = randomx.randomx_alloc_cache
    randomx_alloc_cache.restype = ctypes.c_void_p
    cache = randomx_alloc_cache(RANDOMX_FLAG_DEFAULT)

    randomx_init_cache = randomx.randomx_init_cache
    randomx_init_cache.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    randomx_init_cache.restype = None
    randomx_init_cache(cache, ctypes.c_char_p(key), ctypes.c_size_t(len(key)))

    # 3. Crear máquina virtual
    randomx_create_vm = randomx.randomx_create_vm
    randomx_create_vm.restype = ctypes.c_void_p
    vm = randomx_create_vm(RANDOMX_FLAG_DEFAULT, cache, None)

    # 4. Preparar función de hash
    randomx_calculate_hash = randomx.randomx_calculate_hash
    randomx_calculate_hash.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    randomx_calculate_hash.restype = None

    # 5. Calcular hash
    out_hash = (ctypes.c_ubyte * RANDOMX_HASH_SIZE)()
    randomx_calculate_hash(
        vm,
        ctypes.c_char_p(bytes(blob)),
        ctypes.c_size_t(len(blob)),
        ctypes.byref(out_hash)
    )

    # 6. Liberar recursos
    randomx.randomx_destroy_vm(vm)
    randomx.randomx_release_cache(cache)

    return bytes(out_hash).hex()

def hash_meets_target(hash_hex: str, target_hex: str) -> bool:
    """
    Verifica si el hash cumple la dificultad (menor o igual al target).
    Args:
        hash_hex (str): Hash calculado (hex string, 64 chars).
        target_hex (str): Target de dificultad (hex string, típicamente 8 chars para Monero).
    Returns:
        bool: True si cumple, False si no.
    """
    return int(hash_hex, 16) <= int(target_hex, 16)

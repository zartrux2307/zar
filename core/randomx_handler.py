import ctypes
import os
import binascii
import platform
import threading
import logging
import random  # Added for generate_random_nonce()
from functools import lru_cache

logger = logging.getLogger("RandomXWrapper")

# Configuración multi-plataforma
SYSTEM = platform.system()
DLL_NAMES = {
    "Windows": "randomx.dll",
    "Linux": "librandomx.so",
    "Darwin": "librandomx.dylib"
}

# Buscar DLL en múltiples ubicaciones
def find_randomx_lib():
    base_dirs = [
        os.path.join(os.path.dirname(__file__), "..", "..", "libs"),
        "/usr/local/lib",
        "/usr/lib",
        os.getenv("RANDOMX_LIB_PATH", "")
    ]
    
    for base in base_dirs:
        if not base: continue
        for name in DLL_NAMES.values():
            path = os.path.join(base, name)
            if os.path.isfile(path):
                logger.info(f"Usando biblioteca RandomX: {path}")
                return path
    
    raise FileNotFoundError("No se encontró biblioteca RandomX")

# Constantes
RANDOMX_FLAG_DEFAULT = 0
RANDOMX_HASH_SIZE = 32
BLOB_NONCE_OFFSET = {
    "monero": 39,
    "wownero": 43,
    "default": 39
}

# Cargar DLL
randomx = ctypes.CDLL(find_randomx_lib())

# Definición de tipos y funciones
randomx.randomx_alloc_cache.restype = ctypes.c_void_p
randomx.randomx_alloc_cache.argtypes = [ctypes.c_uint32]
randomx.randomx_init_cache.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
randomx.randomx_release_cache.argtypes = [ctypes.c_void_p]
randomx.randomx_create_vm.restype = ctypes.c_void_p
randomx.randomx_create_vm.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
randomx.randomx_destroy_vm.argtypes = [ctypes.c_void_p]
randomx.randomx_calculate_hash.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p
]

# Caché de VMs por seed
_vm_cache = {}
_cache_lock = threading.Lock()

def get_vm(seed: bytes, flags=RANDOMX_FLAG_DEFAULT):
    """Obtiene VM para un seed, reutilizando si es posible"""
    with _cache_lock:
        seed_key = seed.hex()
        if seed_key in _vm_cache:
            return _vm_cache[seed_key]
        
        # Crear nueva VM
        cache = randomx.randomx_alloc_cache(flags)
        if not cache:
            raise MemoryError("Error asignando caché RandomX")
        
        randomx.randomx_init_cache(cache, seed, len(seed))
        
        vm = randomx.randomx_create_vm(flags, cache, None)
        if not vm:
            randomx.randomx_release_cache(cache)
            raise RuntimeError("Error creando VM RandomX")
        
        _vm_cache[seed_key] = (vm, cache)
        return vm

def release_vm(seed: bytes):
    """Libera recursos de una VM"""
    with _cache_lock:
        seed_key = seed.hex()
        if seed_key in _vm_cache:
            vm, cache = _vm_cache.pop(seed_key)
            randomx.randomx_destroy_vm(vm)
            randomx.randomx_release_cache(cache)

def compute_randomx_hash(
    blob: bytes, 
    nonce: int, 
    seed: bytes,
    coin: str = "monero",
    flags: int = RANDOMX_FLAG_DEFAULT
) -> bytes:
    """Calcula hash RandomX optimizado"""
    # Insertar nonce en posición correcta
    offset = BLOB_NONCE_OFFSET.get(coin, BLOB_NONCE_OFFSET["default"])
    mutable_blob = bytearray(blob)
    mutable_blob[offset:offset+4] = nonce.to_bytes(4, "little")
    
    # Obtener VM
    vm = get_vm(seed, flags)
    
    # Calcular hash
    result = (ctypes.c_ubyte * RANDOMX_HASH_SIZE)()
    randomx.randomx_calculate_hash(
        vm, 
        ctypes.c_char_p(mutable_blob), 
        len(mutable_blob), 
        result
    )
    return bytes(result)

def batch_compute_randomx_hashes(
    blob: bytes,
    nonces: list[int],
    seed: bytes,
    coin: str = "monero",
    flags: int = RANDOMX_FLAG_DEFAULT
) -> list[bytes]:
    """Calcula múltiples hashes eficientemente"""
    vm = get_vm(seed, flags)
    mutable_blob = bytearray(blob)
    offset = BLOB_NONCE_OFFSET.get(coin, BLOB_NONCE_OFFSET["default"])
    results = []
    
    for nonce in nonces:
        mutable_blob[offset:offset+4] = nonce.to_bytes(4, "little")
        result = (ctypes.c_ubyte * RANDOMX_HASH_SIZE)()
        randomx.randomx_calculate_hash(
            vm, 
            ctypes.c_char_p(mutable_blob), 
            len(mutable_blob), 
            result
        )
        results.append(bytes(result))
    
    return results

def hash_meets_target(hash_bytes: bytes, target_bytes: bytes) -> bool:
    """Compara hash con target (más eficiente que con hex)"""
    return int.from_bytes(hash_bytes, "little") <= int.from_bytes(target_bytes, "little")

# ADDED CLASS IMPLEMENTATION BELOW
class RandomXHandler:
    def __init__(self):
        self.flags = RANDOMX_FLAG_DEFAULT
        self.cache = None
        
    def init_cache(self, seed: bytes):
        """Inicializa la caché de RandomX"""
        # Actual implementation uses the global VM cache
        self.cache = seed
        logger.info("🧠 Caché RandomX inicializada")
        
    def mine(self, job: dict, nonce: int) -> bytes:
        """Calcula el hash para un trabajo y nonce específico"""
        try:
            blob = bytes.fromhex(job['blob']) if isinstance(job['blob'], str) else job['blob']
            seed_hash = bytes.fromhex(job['seed_hash']) if isinstance(job['seed_hash'], str) else job['seed_hash']
            
            return compute_randomx_hash(
                blob=blob,
                nonce=nonce,
                seed=seed_hash,
                flags=self.flags
            )
        except Exception as e:
            logger.error(f"❌ Error en minería: {e}", exc_info=True)
            return None

    def generate_random_nonce(self) -> int:
        """Genera un nonce aleatorio válido"""
        return random.randint(0, 2**32 - 1)
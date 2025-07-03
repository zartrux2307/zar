import ctypes
import os
import binascii

DLL_PATH = r'C:/zarturxia/src/libs/randomx.dll'
randomx = ctypes.CDLL(DLL_PATH)

RANDOMX_FLAG_DEFAULT = 0
RANDOMX_HASH_SIZE = 32

def hex_to_bytes(hex_str):
    return binascii.unhexlify(hex_str.strip())

def compute_randomx_hash(blob_hex, nonce, seed_hash_hex):
    blob = bytearray(hex_to_bytes(blob_hex))
    # Inserta el nonce (little endian, offset estándar Monero)
    blob[39:43] = nonce.to_bytes(4, "little")
    key = hex_to_bytes(seed_hash_hex)
    # -- 1. Reserva cache
    randomx_alloc_cache = randomx.randomx_alloc_cache
    randomx_alloc_cache.restype = ctypes.c_void_p
    cache = randomx_alloc_cache(RANDOMX_FLAG_DEFAULT)
    # -- 2. Inicializa cache
    randomx.randomx_init_cache(cache, ctypes.c_char_p(key), ctypes.c_size_t(len(key)))
    # -- 3. Crea VM
    randomx_create_vm = randomx.randomx_create_vm
    randomx_create_vm.restype = ctypes.c_void_p
    vm = randomx_create_vm(RANDOMX_FLAG_DEFAULT, cache, None)
    # -- 4. Calcula hash
    out_hash = (ctypes.c_ubyte * RANDOMX_HASH_SIZE)()
    randomx.randomx_calculate_hash(vm, ctypes.c_char_p(bytes(blob)), ctypes.c_size_t(len(blob)), out_hash)
    # -- 5. Libera recursos
    randomx.randomx_destroy_vm(vm)
    randomx.randomx_release_cache(cache)
    return bytes(out_hash).hex()

def hash_meets_target(hash_hex, target_hex):
    """
    Compara un hash con el target en formato hexadecimal.
    Retorna True si el hash es menor o igual que el target (cumple dificultad).
    """
    return int(hash_hex, 16) <= int(target_hex, 16)

# Prueba simple
if __name__ == "__main__":
    # Usa valores reales para probarlo con tus blobs, nonces y seed_hash
    blob = "1010f2fc95c3062d020bc6f0915f296df47399c7842fba5baa341b184c9fc9e28f7750ac21638a00000000c00795ef84a620f24fb9f4d5738e35377a8b3964ae814d1529fef96a5d428c0536"
    nonce = 123456
    seed_hash = "90bfb6bfc6d0f639326ebb1daf0acb3222be05e285bc278d0843435fb7cf4a34"
    target = "04e90000"
    hash_hex = compute_randomx_hash(blob, nonce, seed_hash)
    print(f"hash: {hash_hex}")
    print("Cumple target:", hash_meets_target(hash_hex, target))

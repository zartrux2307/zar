import struct
import logging
import time  # Importación faltante
from multiprocessing import shared_memory, RLock
import numpy as np

# Tamaños optimizados para Monero (bytes)
SHM_SPEC = {
    "job_id": 36,      # 32 bytes + 4 de alineación
    "blob": 152,        # Tamaño real de blob en RandomX
    "target": 8,         # uint64
    "height": 4,         # uint32
    "nonce_result": 4,   # uint32
    "control": 1         # Flags de estado
}

# Locks por segmento
segment_locks = {key: RLock() for key in SHM_SPEC}

class SharedMemoryManager:
    def __init__(self, prefix="xmr_shm"):
        self.prefix = prefix
        self.segments = {}
        
        for key, size in SHM_SPEC.items():
            shm_name = f"{self.prefix}_{key}"
            try:
                shm = shared_memory.SharedMemory(
                    name=shm_name,
                    create=True,
                    size=size
                )
                # Inicializar memoria
                shm.buf[:] = bytearray(size)
            except FileExistsError:
                shm = shared_memory.SharedMemory(name=shm_name)
            
            self.segments[key] = shm

    def write_mining_job(self, job: dict):
        """Escribe un trabajo de minería optimizado"""
        with segment_locks["control"], segment_locks["blob"]:
            # Blob (152 bytes)
            self.segments["blob"].buf[:] = job["blob"]
            
            # Target (uint64 little-endian)
            target_bytes = struct.pack('<Q', job["target"])
            self.segments["target"].buf[:] = target_bytes
            
            # Height (uint32)
            height_bytes = struct.pack('<I', job["height"])
            self.segments["height"].buf[:] = height_bytes
            
            # Job ID (32 bytes + padding)
            job_id = job["job_id"].encode().ljust(32, b'\0')
            self.segments["job_id"].buf[:32] = job_id
            
            # Reset result
            self.segments["nonce_result"].buf[:4] = b'\0\0\0\0'
            
            # Activar bandera
            self.segments["control"].buf[0] = 1  # 1 = trabajo disponible

    def read_result(self, timeout_ms=100) -> int:
        """Lee nonce resultante con timeout"""
        start = time.perf_counter()
        while (time.perf_counter() - start) * 1000 < timeout_ms:
            with segment_locks["control"]:
                if self.segments["control"].buf[0] == 2:  # Resultado listo
                    nonce_bytes = bytes(self.segments["nonce_result"].buf[:4])
                    return struct.unpack('<I', nonce_bytes)[0]
            time.sleep(0.001)
        raise TimeoutError("No se recibió resultado en el tiempo especificado")

    # Métodos especializados para acceso directo
    def get_blob_buffer(self) -> memoryview:
        """Devuelve vista directa al blob (evita copias)"""
        return self.segments["blob"].buf

    def set_result_nonce(self, nonce: int):
        """Escribe el resultado del nonce atómicamente"""
        with segment_locks["nonce_result"], segment_locks["control"]:
            nonce_bytes = struct.pack('<I', nonce)
            self.segments["nonce_result"].buf[:] = nonce_bytes
            self.segments["control"].buf[0] = 2  # Marcar como completo

    def cleanup(self):
        """Libera recursos y elimina segmentos"""
        for shm in self.segments.values():
            shm.close()
            shm.unlink()
            
    # --- Métodos requeridos para la integración con el proxy ---
    def set_job(self, job_data: dict):
        """Actualiza el trabajo en memoria compartida (alias para write_mining_job)"""
        self.write_mining_job(job_data)

    def is_solution_ready(self) -> bool:
        """Verifica si hay una solución lista (control flag = 2)"""
        with segment_locks["control"]:
            return self.segments["control"].buf[0] == 2
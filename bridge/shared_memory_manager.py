import struct
import logging
import time
from multiprocessing import shared_memory, RLock

# Tamaños corregidos para Monero (RandomX)
SHM_SPEC = {
    "job_id": 36,       # 32 bytes + 4 padding
    "blob": 84,          # Tamaño máximo de blob en RandomX
    "target": 8,         # uint64
    "height": 4,         # uint32
    "nonce_result": 4,   # uint32
    "control": 1         # Flags de estado
}

# Gestor de bloqueo global
lock_manager = RLock()

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
        """Escribe trabajo de minería optimizado"""
        with lock_manager:  # Usar bloqueo global
            # Blob (máx 84 bytes)
            blob_data = job["blob"]
            if len(blob_data) > 84:
                blob_data = blob_data[:84]
            self.segments["blob"].buf[:len(blob_data)] = blob_data
            
            # Target (uint64 little-endian)
            target_bytes = struct.pack('<Q', job["target"])
            self.segments["target"].buf[:] = target_bytes
            
            # Height (uint32)
            height_bytes = struct.pack('<I', job["height"])
            self.segments["height"].buf[:] = height_bytes
            
            # Job ID (32 bytes + padding)
            job_id = job["job_id"].encode().ljust(32, b'\0')
            self.segments["job_id"].buf[:32] = job_id
            
            # Resetear resultado
            self.segments["nonce_result"].buf[:4] = b'\0\0\0\0'
            
            # Activar bandera
            self.segments["control"].buf[0] = 1  # 1 = trabajo disponible

    def read_result(self, timeout_ms=100) -> int:
        """Lee nonce resultante con timeout"""
        start = time.perf_counter()
        while (time.perf_counter() - start) * 1000 < timeout_ms:
            with lock_manager:
                if self.segments["control"].buf[0] == 2:  # Resultado listo
                    nonce_bytes = bytes(self.segments["nonce_result"].buf[:4])
                    return struct.unpack('<I', nonce_bytes)[0]
            time.sleep(0.001)
        raise TimeoutError("No se recibió resultado a tiempo")

    def set_result_nonce(self, nonce: int):
        """Escribe nonce atómicamente"""
        with lock_manager:
            nonce_bytes = struct.pack('<I', nonce)
            self.segments["nonce_result"].buf[:] = nonce_bytes
            self.segments["control"].buf[0] = 2  # Marcar completo

    def cleanup(self):
        """Libera recursos"""
        for shm in self.segments.values():
            shm.close()
            try:
                shm.unlink()
            except FileNotFoundError:
                pass  # Ya liberado
            
    def set_job(self, job_data: dict):
        self.write_mining_job(job_data)

    def is_solution_ready(self) -> bool:
        with lock_manager:
            return self.segments["control"].buf[0] == 2
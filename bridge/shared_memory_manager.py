import mmap
import os
import struct
import time
import logging
import sys
import platform
from filelock import FileLock, Timeout
from pathlib import Path
from typing import Optional

# Configuración de logging
logger = logging.getLogger("SharedMemoryManager")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class SharedMemoryManager:

    def __init__(self, name: str, size: int):
    self.name = name
    self.size = size
    
    # Manejo especial para Windows
    if platform.system() == 'Windows':
        self.file_path = f"C:\\Windows\\Temp\\{name}.shm"
    else:
        self.file_path = f"/dev/shm/{name}"
    
    def __init__(self, segment_name: str, segment_size: int = 8):
        """
        Gestor de memoria compartida multiplataforma
        
        Args:
            segment_name: Nombre único del segmento de memoria
            segment_size: Tamaño en bytes del segmento (por defecto 8 para enteros de 64 bits)
        """
        self.segment_name = segment_name
        self.segment_size = segment_size
        
        # Configurar rutas multiplataforma
        temp_dir = Path(os.getenv('TEMP', '/tmp'))
        self.file_path = temp_dir / f"{segment_name}.bin"
        self.lock_path = temp_dir / f"{segment_name}.lock"
        
        self.file = None
        self.mapped_memory = None
        self.lock = FileLock(self.lock_path, timeout=10)
        
        logger.info(f"Inicializando segmento: {self.segment_name} ({segment_size} bytes)")
        self._initialize_memory()
    
    def _initialize_memory(self):
        """Crea o abre el archivo de memoria compartida"""
        try:
            # Crear directorio si no existe
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Crear archivo si no existe
            if not self.file_path.exists():
                with self.lock:
                    with open(self.file_path, 'wb') as f:
                        f.write(b'\x00' * self.segment_size)
                        logger.debug(f"Archivo creado: {self.file_path}")
            
            # Abrir archivo en modo lectura/escritura binario
            self.file = open(self.file_path, 'r+b')
            
            # Mapear a memoria
            self.mapped_memory = mmap.mmap(
                self.file.fileno(),
                self.segment_size,
                access=mmap.ACCESS_WRITE
            )
            
            logger.info(f"Memoria compartida inicializada: {self.file_path}")
            
        except Exception as e:
            logger.error(f"Error inicializando memoria: {str(e)}")
            raise
    
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        
    def write_data(self, data: int) -> bool:
        """Escribe un entero en la memoria compartida con locking"""
        try:
            with self.lock:
                self.mapped_memory.seek(0)
                self.mapped_memory.write(struct.pack('Q', data))
                self.mapped_memory.flush()
                logger.debug(f"Dato escrito: {data} en {self.segment_name}")
                return True
        except Timeout:
            logger.warning(f"Timeout al escribir en {self.segment_name}")
            return False
        except Exception as e:
            logger.error(f"Error escribiendo dato: {str(e)}")
            return False
            
    def read_data(self, timeout: float = 1.0) -> Optional[int]:
        """Lee un entero de la memoria compartida con timeout"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Intentar adquirir lock sin bloquear
                if self.lock.is_locked:
                    time.sleep(0.01)
                    continue
                    
                with self.lock:
                    self.mapped_memory.seek(0)
                    data_bytes = self.mapped_memory.read(self.segment_size)
                    if len(data_bytes) >= 8:
                        return struct.unpack('Q', data_bytes[:8])[0]
            except Timeout:
                logger.debug(f"Timeout temporal en lectura de {self.segment_name}")
            except Exception as e:
                logger.error(f"Error leyendo dato: {str(e)}")
                return None
                
            time.sleep(0.01)
        
        logger.warning(f"Timeout leyendo de {self.segment_name} después de {timeout}s")
        return None
        
    def close(self):
        """Libera todos los recursos de manera segura"""
        try:
            if self.mapped_memory:
                self.mapped_memory.flush()
                self.mapped_memory.close()
                logger.debug(f"Memoria mapeada cerrada: {self.segment_name}")
                
            if self.file:
                self.file.close()
                logger.debug(f"Archivo cerrado: {self.file_path}")
                
            logger.info(f"Recursos liberados para {self.segment_name}")
        except Exception as e:
            logger.error(f"Error cerrando recursos: {str(e)}")
            
    def __del__(self):
        self.close()


# Ejemplo de uso
if __name__ == "__main__":
    # Configurar logging para demostración
    logger.setLevel(logging.DEBUG)
    
    # Crear instancia de memoria compartida
    with SharedMemoryManager("test_segment", 8) as shm:
        # Escribir dato
        shm.write_data(123456789)
        
        # Leer dato
        data = shm.read_data()
        print(f"Dato leído: {data}")
        
        # Prueba de concurrencia
        print("Simulando acceso concurrente...")
        data = shm.read_data(timeout=0.5)
        print(f"Dato con timeout: {data}")
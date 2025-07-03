import time
import os
import json
import logging
import hashlib
from pathlib import Path
from filelock import FileLock, Timeout
from typing import List, Optional
from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor

from iazar.evaluation import NonceQualityFilter
from iazar.utils.nonce_validator import HexNonceValidator

# Configuración avanzada
class Config:
    NONCES_DIR = Path("iazar/bridge/generated/")
    NONCES_PATTERN = "nonces_*.json"
    INJECTION_LOG = Path("logs/inyectados.log")
    MAX_NONCE_LENGTH = 64
    LOCK_TIMEOUT = 5  # segundos
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5
    BUFFER_FLUSH_SIZE = 100  # Número de nonces para flush automático
    BUFFER_FLUSH_TIME = 5    # Segundos entre flushes
    BATCH_SIZE = 500         # Tamaño de lote para procesamiento paralelo

# ✅ Crear directorio de logs si no existe
log_dir = os.path.dirname(Config.INJECTION_LOG)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "module": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
    handlers=[
        RotatingFileHandler(
            Config.INJECTION_LOG,
            maxBytes=Config.LOG_MAX_SIZE,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NonceInjector")

class NonceInjectionError(Exception):
    """Excepción base para errores de inyección de nonces"""
    pass

class NonceLoader:
    @staticmethod
    def find_latest_nonces_file() -> Optional[Path]:
        try:
            nonce_files = sorted(
                Config.NONCES_DIR.glob(Config.NONCES_PATTERN),
                key=os.path.getmtime,
                reverse=True
            )
            return nonce_files[0] if nonce_files else None
        except Exception as e:
            logger.error(f"Error buscando archivos de nonces: {str(e)}")
            return None

    @staticmethod
    def validate_nonce_structure(nonces: List[str]) -> bool:
        validator = HexNonceValidator(
            min_length=8,
            max_length=Config.MAX_NONCE_LENGTH
        )
        return all(validator.is_valid(nonce) for nonce in nonces)

class NonceInjector:
    def __init__(self):
        self.lock = FileLock(Config.INJECTION_LOG.with_suffix(".lock"), timeout=Config.LOCK_TIMEOUT)
        self.nonce_file = None
        self.buffer = []
        self.last_flush = time.time()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _flush_buffer(self) -> None:
        """Escribe el contenido del búfer en el archivo de log"""
        if not self.buffer:
            return

        try:
            with self.lock:
                with open(Config.INJECTION_LOG, "a", encoding="utf-8") as log:
                    for nonce in self.buffer:
                        log_entry = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "nonce": nonce,
                            "nonce_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
                            "source_file": self.nonce_file.name if self.nonce_file else "unknown"
                        }
                        log.write(json.dumps(log_entry) + "\n")
            self.buffer = []
        except Exception as e:
            logger.error(f"Error escribiendo en log: {str(e)}")
        finally:
            self.last_flush = time.time()

    def _atomic_log_injection(self, nonces: List[str]) -> None:
        """Registro optimizado con búfer y flush periódico"""
        self.buffer.extend(nonces)
        if (len(self.buffer) >= Config.BUFFER_FLUSH_SIZE or
            (time.time() - self.last_flush) >= Config.BUFFER_FLUSH_TIME):
            self._flush_buffer()

    def _process_nonces(self, nonces: List[str]) -> None:
        validator = HexNonceValidator(min_length=8, max_length=64)
        filtered = [n for n in nonces if validator.is_valid(n)]

        if not filtered:
            logger.warning("No hay nonces válidos después del filtro inicial")
            return

        batches = [
            filtered[i:i + Config.BATCH_SIZE]
            for i in range(0, len(filtered), Config.BATCH_SIZE)
        ]

        future_results = [
            self.executor.submit(NonceQualityFilter.evaluar_nonces, batch)
            for batch in batches
        ]

        results = []
        for future in future_results:
            try:
                results.extend(future.result())
            except Exception as e:
                logger.error(f"Error procesando lote: {str(e)}")

        final_nonces = [
            n for n in results
            if hashlib.sha256(n.encode()).hexdigest()[:8] != "00000000"
        ]

        if not final_nonces:
            logger.error("No hay nonces válidos después de la validación de hash")
            return

        if not NonceLoader.validate_nonce_structure(final_nonces):
            logger.error("Nonces no superaron validación final de estructura")
            raise NonceInjectionError("Validación post-procesamiento fallida")

        self._atomic_log_injection(final_nonces)
        logger.info(f"Inyección exitosa: {len(final_nonces)}/{len(nonces)} nonces")

    def inject(self) -> None:
        try:
            self.nonce_file = NonceLoader.find_latest_nonces_file()
            if not self.nonce_file:
                logger.warning("No se encontraron archivos de nonces válidos")
                return

            with open(self.nonce_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("Formato de archivo inválido: se esperaba lista")

            self._process_nonces(data)

            archive_path = self.nonce_file.with_name(f"processed_{self.nonce_file.name}")
            self.nonce_file.rename(archive_path)

        except json.JSONDecodeError:
            logger.error("Error decodificando archivo JSON")
            raise NonceInjectionError("Formato JSON inválido")
        except PermissionError as pe:
            logger.error(f"Error de permisos: {str(pe)}")
            raise NonceInjectionError("Problema de permisos de archivo")
        except Exception as e:
            logger.error(f"Error inesperado durante inyección: {str(e)}")
            raise NonceInjectionError("Error general de inyección")
        finally:
            self._flush_buffer()
            self.executor.shutdown(wait=False)
            logger.info("Recursos liberados")

def send_nonces_to_proxy():
    injector = NonceInjector()
    injector.inject()

def main():
    try:
        send_nonces_to_proxy()
    except NonceInjectionError as nie:
        logger.error(f"Fallo crítico en inyección: {str(nie)}")
        return 1
    except Exception as e:
        logger.critical(f"Error no manejado: {str(e)}", exc_info=True)
        return 2
    return 0

if __name__ == "__main__":
    exit(main())

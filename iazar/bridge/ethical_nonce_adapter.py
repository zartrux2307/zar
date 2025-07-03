import json
import os
import logging
import hashlib
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from functools import lru_cache
from logging.handlers import RotatingFileHandler

from iazar.evaluation.entropy_analysis import EntropyAnalysis
from iazar.evaluation import NonceQualityFilter
from iazar.evaluation.correlation_analysis import CorrelationAnalyzer
from iazar.utils.hex_validator import HexNonceValidator
from iazar.utils.config_manager import ConfigManager

# Configuración
@dataclass
class EthicsConfig:
    INPUT_PATH: Path = Path("iazar/bridge/nonces_ready.json")
    OUTPUT_PATH: Path = Path("iazar/bridge/nonces_filtered.json")
    LOG_PATH: Path = Path("logs/ethics_processor.log")
    MIN_ENTROPY: float = 3.5
    MIN_CORRELATION: float = 0.7
    LOG_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5
    NONCE_MIN_LENGTH: int = 8
    NONCE_MAX_LENGTH: int = 64

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "service": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
    handlers=[
        RotatingFileHandler(
            EthicsConfig.LOG_PATH,
            maxBytes=EthicsConfig.LOG_MAX_SIZE,
            backupCount=EthicsConfig.LOG_BACKUP_COUNT,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EthicsProcessor")

class EthicsProcessingError(Exception):
    """Base exception for ethics processing errors"""
    pass

class InvalidNonceFormatError(EthicsProcessingError):
    """Raised when a nonce has invalid format"""
    pass

class EthicalNonceAdapter:
    """
    Procesador/adaptador principal para filtrar nonces bajo criterios éticos.
    """
    def __init__(self, config: EthicsConfig = EthicsConfig()):
        self.config = config
        self.validator = HexNonceValidator(
            min_length=config.NONCE_MIN_LENGTH,
            max_length=config.NONCE_MAX_LENGTH
        )

    @lru_cache(maxsize=1)
    def _load_raw_nonces(self) -> Optional[List[str]]:
        """Carga y valida nonces con cache y bloqueo de archivo"""
        try:
            if not self.config.INPUT_PATH.exists():
                logger.warning("No se encontró archivo de entrada de nonces")
                return None

            with open(self.config.INPUT_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list) or not all(isinstance(n, str) for n in data):
                raise ValueError("Formato de archivo inválido")

            return data

        except Exception as e:
            logger.error(f"Error cargando nonces: {str(e)}")
            raise EthicsProcessingError("Error crítico en carga de datos") from e

    def _validate_nonce(self, nonce: str) -> bool:
        """Valida formato y características básicas del nonce"""
        return self.validator.is_valid(nonce)

    def _calculate_metrics(self, nonce: str) -> Dict[str, float]:
        """Calcula métricas éticas clave para un nonce"""
        try:
            byte_values = [int(nonce[i:i+2], 16) for i in range(0, len(nonce), 2)]
            return {
                "entropy": EntropyAnalysis.shannon_entropy(nonce),
                "correlation": CorrelationAnalyzer.autocorrelacion(byte_values),
                "hash_diversity": self._calculate_hash_diversity(nonce)
            }
        except Exception as e:
            logger.error(f"Error calculando métricas para {nonce[:8]}...: {str(e)}")
            raise

    def _calculate_hash_diversity(self, nonce: str) -> float:
        """Calcula diversidad de hash usando diferentes algoritmos"""
        hashes = [
            hashlib.sha256(nonce.encode()).hexdigest(),
            hashlib.blake2b(nonce.encode()).hexdigest()
        ]
        return sum(h1 != h2 for h1, h2 in zip(hashes, hashes[1:])) / len(hashes)

    def _ethical_filter(self, nonce: str) -> bool:
        """Aplica todos los filtros éticos al nonce"""
        if not self._validate_nonce(nonce):
            return False

        metrics = self._calculate_metrics(nonce)
        return (
            metrics["entropy"] >= self.config.MIN_ENTROPY and
            metrics["correlation"] >= self.config.MIN_CORRELATION and
            metrics["hash_diversity"] > 0.5
        )

    def _process_batch(self, nonces: List[str]) -> List[str]:
        """Procesamiento por lotes con múltiples etapas de filtrado"""
        try:
            # Filtrado ético
            ethical_nonces = [n for n in nonces if self._ethical_filter(n)]

            # Filtrado de calidad adicional
            return NonceQualityFilter.evaluar_nonces(ethical_nonces)

        except Exception as e:
            logger.error(f"Error en procesamiento por lotes: {str(e)}")
            raise EthicsProcessingError("Error de filtrado") from e

    def _save_results(self, nonces: List[str]) -> None:
        """Guarda resultados con verificación de integridad"""
        try:
            with open(self.config.OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump({
                    "nonces": nonces,
                    "metadata": {
                        "hash_validation": hashlib.sha256(
                            ''.join(nonces).encode()
                        ).hexdigest(),
                        "nonce_count": len(nonces),
                        "config": self.config.__dict__
                    }
                }, f, indent=2)

            logger.info(f"Nonces éticos guardados: {len(nonces)}")

        except Exception as e:
            logger.error(f"Error guardando resultados: {str(e)}")
            raise EthicsProcessingError("Error en persistencia de datos") from e

    def execute_pipeline(self) -> None:
        """Ejecuta el pipeline completo de procesamiento ético"""
        try:
            raw_nonces = self._load_raw_nonces()
            if not raw_nonces:
                logger.info("No hay nonces para procesar")
                return

            processed_nonces = self._process_batch(raw_nonces)

            if processed_nonces:
                self._save_results(processed_nonces)
                logger.info(f"Procesamiento completo. Nonces aprobados: {len(processed_nonces)}")
            else:
                logger.warning("Ningún nonce superó los filtros éticos")

        except EthicsProcessingError as epe:
            logger.error(f"Error en pipeline ético: {str(epe)}")
            raise
        except Exception as e:
            logger.critical(f"Error no controlado: {str(e)}", exc_info=True)
            raise EthicsProcessingError("Fallo crítico en pipeline") from e

# Exportación explícita para import *
__all__ = ["EthicalNonceAdapter"]

if __name__ == "__main__":
    processor = EthicalNonceAdapter()
    try:
        processor.execute_pipeline()
    except EthicsProcessingError:
        exit(1)

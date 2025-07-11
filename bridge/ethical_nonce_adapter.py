import json
import os
import sys

import pandas as pd
import logging
import hashlib
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from functools import lru_cache
from logging.handlers import RotatingFileHandler

from iazar.evaluation.entropy_analysis import EntropyAnalysis
from iazar.evaluation.nonce_quality_filter import NonceQualityFilter

from iazar.evaluation.correlation_analysis import CorrelationAnalyzer
from iazar.utils.hex_validator import HexNonceValidator
from iazar.utils.feature_utils import guardar_nonces_csv, COLUMNS
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Columnas estándar globales
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]


def leer_nonces_csv(path):
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
    if not os.path.exists(path):
        pd.DataFrame(columns=COLUMNS).to_csv(path, index=False)
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    missing = [col for col in COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = 0
    df = df[COLUMNS]
    df = df.dropna()  # Opcional, borra filas incompletas
    return df


def guardar_nonces_csv(df, path):
    """Guarda un DataFrame de nonces con la cabecera y orden estándar."""
    if not set(COLUMNS).issubset(df.columns):
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
    df = df[COLUMNS]
    df.to_csv(path, index=False)


def leer_nonces_json(path):
    """Lee un JSON de nonces como lista de dicts."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
        return []
    with open(path, 'r') as f:
        data = json.load(f)
    # Completa campos faltantes
    for item in data:
        for col in COLUMNS:
            if col not in item:
                item[col] = 0
    return data


def guardar_nonces_json(lista, path):
    """Guarda una lista de dicts como JSON de nonces."""
    with open(path, 'w') as f:
        json.dump(lista, f, indent=2)

# Utilidades para blobs binarios


def hexstr_to_bytes(blob_hex):
    return bytes.fromhex(blob_hex) if isinstance(blob_hex, str) else blob_hex


def bytes_to_hexstr(blob_bytes):
    return blob_bytes.hex() if isinstance(blob_bytes, (bytes, bytearray)) else blob_bytes

# Ejemplo de uso:
# df = leer_nonces_csv("ruta.csv")
# guardar_nonces_csv(df, "nueva_ruta.csv")
# nonces = leer_nonces_json("ruta.json")
# guardar_nonces_json(nonces, "nueva_ruta.json")

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


class InvalidNonceFormatError(EthicsProcessingError):
    """Raised when a nonce has invalid format"""


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
            byte_values = [int(nonce[i:i + 2], 16) for i in range(0, len(nonce), 2)]
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

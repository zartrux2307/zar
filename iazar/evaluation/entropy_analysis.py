import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Union, Optional, Any
import pandas as pd
import joblib
from functools import lru_cache
import numpy as np
from collections import Counter
from scipy.stats import entropy as scipy_entropy, variation, skew, kurtosis

# IMPORTACIÓN CONFIG GLOBAL
from iazar.utils.config_manager import ConfigManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NonceLoader:
    """Carga eficiente de datos de nonces desde múltiples fuentes con validación y caché."""
    def __init__(self, config: Optional[ConfigManager] = None):
        self.config_manager = config or ConfigManager()
        self.config = self.config_manager.get_config('ia_config')
        self._validate_paths()

    def _validate_paths(self):
        """Verifica la existencia de rutas críticas"""
        paths = [
            self.config['paths']['log_dir'],
            self.config['paths']['data_dir'],
            self.config['paths']['model_dir'],
        ]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                logger.warning(f"Directorio creado: {path}")

    @lru_cache(maxsize=4)
    def load_valid_nonces(self) -> List[int]:
        """Carga nonces exitosos desde archivo de texto"""
        path = os.path.join(self.config['paths']['log_dir'], 'nonces_exitosos.txt')
        nonces = []
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.isdigit():
                            nonces.append(int(stripped))
                        else:
                            logger.warning(f"Nonce inválido detectado: {stripped}")
            else:
                logger.warning(f"Archivo no encontrado: {path}")
        except Exception as e:
            logger.error(f"Error cargando nonces válidos: {str(e)}")
        return nonces

    @lru_cache(maxsize=4)
    def load_hash_data(self) -> pd.DataFrame:
        """Carga datos históricos de hashes desde CSV con validación"""
        path = os.path.join(self.config['paths']['log_dir'], 'nonces_hash.csv')
        df = pd.DataFrame()
        try:
            if os.path.exists(path):
                df = pd.read_csv(
                    path,
                    usecols=['timestamp', 'nonce', 'hash_score'],
                    parse_dates=['timestamp'],
                    dtype={'nonce': 'uint32', 'hash_score': 'float32'},
                    on_bad_lines='warn'
                )
                if not df.empty and df['nonce'].isnull().any():
                    logger.warning("Nonces nulos detectados, eliminando...")
                    df = df.dropna(subset=['nonce'])
            else:
                logger.warning(f"Archivo no encontrado: {path}")
        except Exception as e:
            logger.error(f"Error cargando datos de hash: {str(e)}")
        return df

    def load_injected_nonces(self, days: int = 7) -> List[Dict]:
        """Carga nonces inyectados desde log con filtro temporal"""
        path = os.path.join(self.config['paths']['log_dir'], 'inyectados.log')
        cutoff = datetime.now() - timedelta(days=days)
        entries = []
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            entry_time = datetime.fromisoformat(entry['timestamp'])
                            if entry_time >= cutoff:
                                entry['nonce'] = int(entry['nonce'])
                                entries.append(entry)
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"Entrada corrupta: {line.strip()} - {str(e)}")
            else:
                logger.warning(f"Archivo no encontrado: {path}")
        except Exception as e:
            logger.error(f"Error cargando nonces inyectados: {str(e)}")
        return entries

    @lru_cache(maxsize=2)
    def load_training_data(self) -> pd.DataFrame:
        """Carga dataset de entrenamiento con validación de estructura"""
        path = os.path.join(self.config['paths']['data_dir'], 'C:/zarturxia/src/iazar/data/nonce_training_data.csv')
        required_columns = {
            'nonce': 'uint32',
            'block_timestamp': 'datetime64[s]',
            'difficulty': 'float32',
            'accepted': 'bool'
        }
        try:
            if os.path.exists(path):
                df = pd.read_csv(
                    path,
                    dtype=required_columns,
                    parse_dates=['block_timestamp'],
                    usecols=required_columns.keys()
                )
                if not df.empty:
                    df = df[df['block_timestamp'].between(
                        datetime(2020, 1, 1),
                        datetime.now()
                    )]
                return df
            else:
                logger.warning(f"Archivo no encontrado: {path}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error cargando datos de entrenamiento: {str(e)}")
            return pd.DataFrame()

    def load_models(self) -> Dict[str, Any]:
        """Carga modelos IA desde disco con verificación de versiones"""
        models = {}
        model_paths = {
            'ethical': os.path.join(self.config['paths']['model_dir'], 'ethical_nonce_model.joblib'),
            'classifier': os.path.join(self.config['paths']['model_dir'], 'hash_classifier_model.joblib')
        }
        for name, path in model_paths.items():
            try:
                if os.path.exists(path):
                    models[name] = joblib.load(path)
                    logger.info(f"Modelo {name} cargado correctamente")
                else:
                    logger.warning(f"Modelo no encontrado: {path}")
                    models[name] = None
            except Exception as e:
                logger.error(f"Error cargando modelo {name}: {str(e)}")
                models[name] = None
        return models

    def load_all(self) -> Dict[str, Union[List, pd.DataFrame]]:
        """Carga todos los datos de nonces en un solo llamado"""
        return {
            'valid': self.load_valid_nonces(),
            'hashes': self.load_hash_data(),
            'injected': self.load_injected_nonces(),
            'training': self.load_training_data(),
            'models': self.load_models()
        }

# ======================
# ANÁLISIS DE ENTROPÍA
# ======================

def calculate_entropy(nonces: List[int]) -> float:
    """Calcula la entropía de Shannon sobre una lista de nonces enteros."""
    if not nonces:
        logger.warning("Lista de nonces vacía, entropía 0.")
        return 0.0
    counts = Counter(nonces)
    probs = np.array(list(counts.values())) / len(nonces)
    entropy_value = float(scipy_entropy(probs, base=2))
    logger.debug(f"Entropía calculada: {entropy_value}")
    return entropy_value

class EntropyAnalysis:
    """
    Realiza un análisis estadístico avanzado sobre nonces para evaluar
    aleatoriedad, distribución y patrones sospechosos.
    """
    def __init__(self, nonces: List[int]):
        if not nonces:
            raise ValueError("La lista de nonces no puede estar vacía.")
        self.nonces = np.array(nonces, dtype=np.uint64)

    def shannon_entropy(self) -> float:
        """Entropía de Shannon normalizada"""
        return calculate_entropy(self.nonces.tolist())

    def uniqueness_ratio(self) -> float:
        """Proporción de nonces únicos respecto al total"""
        return len(np.unique(self.nonces)) / len(self.nonces)

    def zero_density(self) -> float:
        """Proporción de bits con valor 0 en los nonces (32-bit esperados)"""
        if len(self.nonces) == 0:
            return 0.0
        bitstring = ''.join(f'{n:032b}' for n in self.nonces)
        return bitstring.count('0') / len(bitstring)

    def statistical_summary(self) -> Dict[str, float]:
        """Resumen estadístico avanzado"""
        if len(self.nonces) == 0:
            return {k: 0.0 for k in [
                'mean', 'std', 'min', 'max', 'variation',
                'skewness', 'kurtosis', 'entropy',
                'uniqueness_ratio', 'zero_density'
            ]}
        stats = {
            'mean': float(np.mean(self.nonces)),
            'std': float(np.std(self.nonces)),
            'min': float(np.min(self.nonces)),
            'max': float(np.max(self.nonces)),
            'variation': float(variation(self.nonces)) if np.mean(self.nonces) != 0 else 0.0,
            'skewness': float(skew(self.nonces)),
            'kurtosis': float(kurtosis(self.nonces)),
            'entropy': self.shannon_entropy(),
            'uniqueness_ratio': self.uniqueness_ratio(),
            'zero_density': self.zero_density()
        }
        logger.debug(f"Resumen estadístico: {stats}")
        return stats

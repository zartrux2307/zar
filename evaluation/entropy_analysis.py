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
import sys

# IMPORTACIÓN CONFIG GLOBAL
from iazar.utils.config_manager import ConfigManager
from iazar.utils.nonce_loader import NonceLoader

# Configuración de logging mejorada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("entropy_analysis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EntropyAnalysis")

class NonceLoaderEnhanced(NonceLoader):
    """Extensión del cargador de nonces con validación mejorada y manejo de errores robusto"""
    REQUIRED_COLUMNS = ['nonce', 'block_timestamp', 'difficulty', 'accepted']
    
    def __init__(self, config: Optional[ConfigManager] = None):
        super().__init__(config)
        self.base_loader = NonceLoader(config)
        
    def _validate_columns(self, df: pd.DataFrame, required_columns: List[str]) -> pd.DataFrame:
        """Verifica y completa columnas faltantes con valores por defecto"""
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
            logger.warning(f"Columnas faltantes: {', '.join(missing_cols)} - Añadiendo con valores por defecto")
            
            for col in missing_cols:
                if col == 'nonce':
                    df[col] = 0
                elif col == 'block_timestamp':
                    df[col] = datetime.now()
                elif col == 'difficulty':
                    df[col] = 1.0
                elif col == 'accepted':
                    df[col] = False
        
        return df[required_columns] if all(col in df.columns for col in required_columns) else df

    @lru_cache(maxsize=4)
    def load_valid_nonces(self) -> List[int]:
        """Carga nonces exitosos con manejo de errores mejorado"""
        path = os.path.join(self.base_loader.log_dir, 'nonces_exitosos.txt')
        nonces = []
        
        if not os.path.exists(path):
            logger.error(f"Archivo no encontrado: {path}")
            return nonces
        
        try:
            with open(path, 'r') as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        nonce_val = int(stripped)
                        nonces.append(nonce_val)
                    except ValueError:
                        logger.warning(f"Línea {i}: Nonce inválido '{stripped}' - omitido")
            logger.info(f"Cargados {len(nonces)} nonces válidos desde {path}")
        except Exception as e:
            logger.exception(f"Error crítico cargando nonces válidos: {str(e)}")
        
        return nonces

    @lru_cache(maxsize=4)
    def load_hash_data(self) -> pd.DataFrame:
        """Carga datos históricos de hashes con validación de estructura"""
        path = os.path.join(self.base_loader.log_dir, 'nonces_hash.csv')
        df = pd.DataFrame()
        
        if not os.path.exists(path):
            logger.error(f"Archivo no encontrado: {path}")
            return df
        
        try:
            # Leer sin suposiciones sobre columnas
            df = pd.read_csv(path, on_bad_lines='warn')
            
            # Validar columnas requeridas
            required_cols = ['timestamp', 'nonce', 'hash_score']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.error(f"Columnas requeridas faltantes: {', '.join(missing_cols)}")
                return pd.DataFrame()
            
            # Convertir tipos de datos
            df = df[required_cols]
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df['nonce'] = pd.to_numeric(df['nonce'], errors='coerce').astype('UInt32')
            df['hash_score'] = pd.to_numeric(df['hash_score'], errors='coerce').astype('float32')
            
            # Limpieza de datos
            initial_count = len(df)
            df = df.dropna(subset=['nonce', 'timestamp'])
            cleaned_count = initial_count - len(df)
            
            if cleaned_count > 0:
                logger.warning(f"Eliminados {cleaned_count} registros inválidos")
            
            logger.info(f"Datos de hash cargados: {len(df)} registros válidos")
            return df
        except Exception as e:
            logger.exception(f"Error crítico cargando datos de hash: {str(e)}")
            return pd.DataFrame()

    def load_training_data(self) -> pd.DataFrame:
        """Carga dataset de entrenamiento con validación robusta de estructura"""
        path = os.path.join(self.base_loader.training_dir, 'nonce_training_data.csv')
        df = pd.DataFrame()
        
        if not os.path.exists(path):
            logger.error(f"Archivo de entrenamiento no encontrado: {path}")
            return df
        
        try:
            # Cargar datos sin suposiciones
            df = pd.read_csv(path, on_bad_lines='warn')
            
            # Validar y completar columnas requeridas
            df = self._validate_columns(df, self.REQUIRED_COLUMNS)
            
            # Convertir tipos de datos
            df['nonce'] = pd.to_numeric(df['nonce'], errors='coerce').astype('UInt32')
            df['difficulty'] = pd.to_numeric(df['difficulty'], errors='coerce').astype('float32')
            
            # Manejar fechas
            if not pd.api.types.is_datetime64_any_dtype(df['block_timestamp']):
                df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], errors='coerce')
            
            # Filtrar fechas inválidas
            min_date = datetime(2020, 1, 1)
            max_date = datetime.now()
            initial_count = len(df)
            
            df = df[
                (df['block_timestamp'] >= min_date) & 
                (df['block_timestamp'] <= max_date)
            ]
            
            cleaned_count = initial_count - len(df)
            if cleaned_count > 0:
                logger.warning(f"Eliminados {cleaned_count} registros con fechas inválidas")
            
            # Limpieza final
            df = df.dropna(subset=self.REQUIRED_COLUMNS)
            logger.info(f"Datos de entrenamiento cargados: {len(df)} registros válidos")
            return df
        except Exception as e:
            logger.exception(f"Error crítico cargando datos de entrenamiento: {str(e)}")
            return pd.DataFrame()

    def load_models(self) -> Dict[str, Any]:
        """Carga modelos IA con verificación de versiones y consistencia"""
        models = {}
        model_files = {
            'ethical': 'ethical_nonce_model.joblib',
            'classifier': 'hash_classifier_model.joblib'
        }
        
        for name, filename in model_files.items():
            path = os.path.join(self.base_loader.model_dir, filename)
            
            if not os.path.exists(path):
                logger.error(f"Modelo no encontrado: {path}")
                models[name] = None
                continue
                
            try:
                model = joblib.load(path)
                
                # Verificación básica de modelo
                if not hasattr(model, 'predict'):
                    logger.error(f"Modelo inválido: {path} no tiene método 'predict'")
                    models[name] = None
                else:
                    models[name] = model
                    logger.info(f"Modelo {name} cargado correctamente desde {path}")
            except Exception as e:
                logger.exception(f"Error cargando modelo {name}: {str(e)}")
                models[name] = None
        
        return models

    def load_all(self) -> Dict[str, Union[List, pd.DataFrame]]:
        """Carga todos los datos con manejo de errores granular"""
        data = {}
        
        try:
            data['valid'] = self.load_valid_nonces()
        except Exception as e:
            logger.error(f"Error cargando nonces válidos: {str(e)}")
            data['valid'] = []
        
        try:
            data['hashes'] = self.load_hash_data()
        except Exception as e:
            logger.error(f"Error cargando datos de hash: {str(e)}")
            data['hashes'] = pd.DataFrame()
        
        try:
            data['training'] = self.load_training_data()
        except Exception as e:
            logger.error(f"Error cargando datos de entrenamiento: {str(e)}")
            data['training'] = pd.DataFrame()
        
        try:
            data['models'] = self.load_models()
        except Exception as e:
            logger.error(f"Error cargando modelos: {str(e)}")
            data['models'] = {}
        
        return data

# ======================
# ANÁLISIS DE ENTROPÍA MEJORADO
# ======================

def calculate_entropy(nonces: List[int]) -> float:
    """Calcula la entropía de Shannon sobre una lista de nonces enteros con validación mejorada"""
    if not nonces:
        logger.warning("Lista de nonces vacía, entropía 0.")
        return 0.0
    
    try:
        counts = Counter(nonces)
        total = sum(counts.values())
        probs = np.array([count / total for count in counts.values()])
        entropy_value = float(scipy_entropy(probs, base=2))
        logger.info(f"Entropía calculada: {entropy_value} para {len(nonces)} nonces")
        return entropy_value
    except Exception as e:
        logger.exception(f"Error calculando entropía: {str(e)}")
        return 0.0

class EntropyAnalysis:
    """
    Realiza un análisis estadístico avanzado sobre nonces con validación robusta
    y manejo de casos límite.
    """
    def __init__(self, nonces: List[int]):
        if not nonces:
            logger.error("La lista de nonces está vacía. Usando lista vacía para análisis.")
            self.nonces = np.array([], dtype=np.uint64)
        else:
            try:
                self.nonces = np.array(nonces, dtype=np.uint64)
            except Exception as e:
                logger.exception(f"Error convirtiendo nonces: {str(e)}")
                self.nonces = np.array([], dtype=np.uint64)

    def _validate_data(self) -> bool:
        """Verifica que hay datos válidos para análisis"""
        if len(self.nonces) == 0:
            logger.warning("No hay nonces para analizar")
            return False
        return True

    def shannon_entropy(self) -> float:
        """Entropía de Shannon normalizada con validación"""
        return calculate_entropy(self.nonces.tolist()) if self._validate_data() else 0.0

    def uniqueness_ratio(self) -> float:
        """Proporción de nonces únicos con validación"""
        if not self._validate_data():
            return 0.0
        return len(np.unique(self.nonces)) / len(self.nonces)

    def zero_density(self) -> float:
        """Proporción de bits con valor 0 con manejo de errores"""
        if not self._validate_data():
            return 0.0
        
        try:
            bitstring = ''.join(f'{n:032b}' for n in self.nonces)
            total_bits = len(bitstring)
            zero_count = bitstring.count('0')
            return zero_count / total_bits
        except Exception as e:
            logger.exception(f"Error calculando densidad de ceros: {str(e)}")
            return 0.0

    def statistical_summary(self) -> Dict[str, float]:
        """Resumen estadístico avanzado con manejo robusto de errores"""
        if not self._validate_data():
            return {
                'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0,
                'variation': 0.0, 'skewness': 0.0, 'kurtosis': 0.0,
                'entropy': 0.0, 'uniqueness_ratio': 0.0, 'zero_density': 0.0
            }
        
        try:
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
            logger.info(f"Resumen estadístico calculado para {len(self.nonces)} nonces")
            return stats
        except Exception as e:
            logger.exception(f"Error calculando resumen estadístico: {str(e)}")
            return {
                'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0,
                'variation': 0.0, 'skewness': 0.0, 'kurtosis': 0.0,
                'entropy': 0.0, 'uniqueness_ratio': 0.0, 'zero_density': 0.0
            }

def main():
    """Función principal para ejecutar análisis completo"""
    try:
        logger.info("="*60)
        logger.info("INICIANDO ANÁLISIS DE ENTROPÍA DE NONCES")
        logger.info("="*60)
        
        # Inicializar cargador mejorado
        loader = NonceLoaderEnhanced()
        
        # Cargar datos de entrenamiento
        logger.info("Cargando datos de entrenamiento...")
        training_df = loader.load_training_data()
        
        if training_df.empty:
            logger.error("No se pudieron cargar datos de entrenamiento. Abortando.")
            return 1
        
        # Verificar columnas críticas
        critical_columns = ['nonce']
        missing_critical = [col for col in critical_columns if col not in training_df.columns]
        
        if missing_critical:
            logger.error(f"Columnas críticas faltantes: {', '.join(missing_critical)}")
            return 2
        
        # Extraer nonces para análisis
        nonces = training_df['nonce'].tolist()
        logger.info(f"Se analizarán {len(nonces)} nonces")
        
        # Realizar análisis de entropía
        analyzer = EntropyAnalysis(nonces)
        stats = analyzer.statistical_summary()
        
        # Guardar resultados
        results = {
            "timestamp": datetime.now().isoformat(),
            "data_source": "nonce_training_data.csv",
            "nonce_count": len(nonces),
            "stats": stats
        }
        
        results_dir = os.path.join(loader.base_loader.data_dir, "entropy_results")
        os.makedirs(results_dir, exist_ok=True)
        
        results_path = os.path.join(results_dir, f"entropy_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Resultados guardados en: {results_path}")
        logger.info("="*60)
        logger.info("ANÁLISIS COMPLETADO EXITOSAMENTE")
        logger.info("="*60)
        
        return 0
    except Exception as e:
        logger.exception(f"Error fatal en el proceso principal: {str(e)}")
        return 3

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
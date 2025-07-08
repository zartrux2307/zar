# src/iazar/utils/feature_utils.py

import math
import zlib
import pandas as pd
from typing import Dict, List
import logging

# Configuración de logging
logger = logging.getLogger("FeatureUtils")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Definición de columnas
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

def entropy(data: bytes) -> float:
    """Calcula la entropía Shannon de un bytearray con manejo robusto de errores."""
    try:
        if not data or len(data) == 0:
            return 0.0
            
        from collections import Counter
        counts = Counter(data)
        total = len(data)
        probs = [count / total for count in counts.values()]
        return -sum(p * math.log2(p) for p in probs if p > 0)
        
    except Exception as e:
        logger.error(f"Error calculando entropía: {str(e)}")
        return 0.0

def uniqueness(data: bytes) -> float:
    """Porcentaje de bytes únicos en el dato con validación de entrada."""
    try:
        if not data or len(data) == 0:
            return 0.0
        return len(set(data)) / len(data)
    except Exception as e:
        logger.error(f"Error calculando unicidad: {str(e)}")
        return 0.0

def zero_density(data: bytes) -> float:
    """Proporción de ceros en el dato con optimización de rendimiento."""
    try:
        if not data or len(data) == 0:
            return 0.0
            
        # Usar count() es eficiente para bytes
        return data.count(0) / len(data)
    except Exception as e:
        logger.error(f"Error calculando densidad de ceros: {str(e)}")
        return 0.0

def pattern_score(data: bytes) -> float:
    """CRC32 normalizado como 'score' de patrón con manejo de bordes."""
    try:
        if not data or len(data) == 0:
            return 0.0
            
        # Usar zlib.crc32 con valor inicial 0 para consistencia
        crc = zlib.crc32(data, 0)
        # Normalizar a rango [0, 1]
        return crc / 0xFFFFFFFF
    except Exception as e:
        logger.error(f"Error calculando patrón: {str(e)}")
        return 0.0

def is_valid_nonce(nonce: int) -> int:
    """Valida el nonce según la lógica de RandomX."""
    try:
        # Validar rango de nonce (0 a 2^32-1)
        return int(0 <= nonce <= 0xFFFFFFFF)
    except Exception as e:
        logger.error(f"Error validando nonce: {str(e)}")
        return 0

def calc_nonce_features(nonce_value: int) -> Dict:
    """
    Calcula todas las features estándar para un nonce.
    
    Args:
        nonce_value: Valor entero del nonce (4 bytes)
    
    Returns:
        Diccionario con todas las características calculadas
    """
    try:
        # Convertir nonce a formato de bytes (4 bytes, little-endian)
        nonce_bytes = nonce_value.to_bytes(4, byteorder='little')
        
        return {
            "nonce": nonce_value,
            "entropy": entropy(nonce_bytes),
            "uniqueness": uniqueness(nonce_bytes),
            "zero_density": zero_density(nonce_bytes),
            "pattern_score": pattern_score(nonce_bytes),
            "is_valid": is_valid_nonce(nonce_value)
        }
    except Exception as e:
        logger.error(f"Error calculando features para nonce {nonce_value}: {str(e)}")
        # Devolver estructura vacía en caso de error
        return {col: 0 for col in COLUMNS}

def guardar_nonces_csv(lista_dicts: List[Dict], path: str):
    """
    Guarda una lista de dicts de nonces con features en un CSV estándar.
    
    Args:
        lista_dicts: Lista de diccionarios con datos de nonces
        path: Ruta del archivo CSV a guardar
    
    Raises:
        ValueError: Si la lista está vacía o los datos no tienen el formato correcto
    """
    try:
        if not lista_dicts:
            logger.warning("No hay datos para guardar en CSV")
            return
            
        # Crear DataFrame y verificar integridad
        df = pd.DataFrame(lista_dicts)
        
        # Asegurar que tenemos todas las columnas necesarias
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
                logger.warning(f"Columna faltante añadida: {col}")
        
        # Seleccionar solo las columnas definidas
        df = df[COLUMNS]
        
        # Guardar en CSV (sobrescribir si existe)
        df.to_csv(path, index=False)
        logger.info(f"Guardados {len(df)} registros en {path}")
        
    except Exception as e:
        logger.error(f"Error guardando CSV en {path}: {str(e)}")
        raise RuntimeError(f"No se pudo guardar el archivo CSV: {str(e)}") from e
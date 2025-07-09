"""
entropy_tools.py - Herramientas profesionales de entropía para análisis IA.
© 2025 Zartrux AI Mining Project
"""

import math
import logging
from collections import Counter
from typing import Any, List, Optional, Union
import os
import pandas as pd
import json

# Columnas estándar globales - eliminada importación conflictiva
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

def leer_nonces_csv(path):
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    
    try:
        df = pd.read_csv(path)
        # Manejar CSV vacío
        if df.empty:
            return pd.DataFrame(columns=COLUMNS)
        
        # Asegurar columnas requeridas
        missing = [col for col in COLUMNS if col not in df.columns]
        for col in missing:
            df[col] = 0
        return df[COLUMNS].dropna()
    except Exception as e:
        logging.error(f"Error leyendo CSV: {e}")
        return pd.DataFrame(columns=COLUMNS)

def guardar_nonces_csv(df, path):
    """Guarda un DataFrame de nonces con la cabecera y orden estándar."""
    # Crear directorio si es necesario
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # Asegurar columnas requeridas
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = 0
    df[COLUMNS].to_csv(path, index=False)

def leer_nonces_json(path):
    """Lee un JSON de nonces como lista de dicts."""
    if not os.path.exists(path):
        return []
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Manejar JSON vacío/inválido
        if not isinstance(data, list):
            return []
            
        # Completar campos faltantes
        for item in data:
            for col in COLUMNS:
                if col not in item:
                    item[col] = 0
        return data
    except Exception as e:
        logging.error(f"Error leyendo JSON: {e}")
        return []

def guardar_nonces_json(lista, path):
    """Guarda una lista de dicts como JSON de nonces."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(lista, f, indent=2)

# Utilidades para blobs binarios
def hexstr_to_bytes(blob_hex):
    return bytes.fromhex(blob_hex) if isinstance(blob_hex, str) else blob_hex

def bytes_to_hexstr(blob_bytes):
    return blob_bytes.hex() if isinstance(blob_bytes, (bytes, bytearray)) else blob_bytes

logger = logging.getLogger("EntropyTools")

class ShannonEntropyCalculator:
    """
    Calculadora de entropía de Shannon para cadenas, listas y bytes.
    Útil para estimar la aleatoriedad o dispersión de datos, como nonces.
    """

    @staticmethod
    def calculate(data: Union[str, bytes, List[Any]]) -> float:
        """
        Calcula la entropía de Shannon de una secuencia.

        Args:
            data (str|bytes|List[Any]): Datos a analizar.

        Returns:
            float: Entropía de Shannon (0=sin aleatoriedad, >4=alta aleatoriedad).
        """
        if not data or len(data) == 0:
            logger.warning("Se recibió una secuencia vacía para calcular entropía.")
            return 0.0

        # Soporta string, bytes y listas
        if isinstance(data, (str, bytes)):
            items = data
        else:
            items = list(data)

        counts = Counter(items)
        total = float(len(items))
        entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
        logger.debug(f"Entropía de Shannon calculada: {entropy:.4f}")
        return entropy

    @staticmethod
    def from_file(filepath: str, encoding: Optional[str] = None) -> float:
        """Calcula la entropía de un archivo (modo texto o binario)."""
        try:
            if encoding:
                with open(filepath, 'r', encoding=encoding) as f:
                    data = f.read()
            else:
                with open(filepath, 'rb') as f:
                    data = f.read()
            return ShannonEntropyCalculator.calculate(data)
        except Exception as ex:
            logger.error(f"Error leyendo archivo para entropía: {ex}")
            return 0.0

class EntropyTools:
    """
    Utilidades avanzadas para cálculo y comparación de entropía.
    Se integra fácilmente en análisis IA para filtrado de nonces, hash, streams, etc.
    """

    @staticmethod
    def shannon_entropy(data: Union[str, bytes, List[Any]]) -> float:
        """
        Interfaz directa para calcular entropía de Shannon.
        """
        return ShannonEntropyCalculator.calculate(data)

    @staticmethod
    def compare_entropy(a: Union[str, bytes, List[Any]],
                        b: Union[str, bytes, List[Any]]) -> float:
        """
        Compara la entropía de dos muestras, útil para detectar diferencias
        significativas en la dispersión de nonces entre dos lotes.

        Returns:
            float: Diferencia absoluta de entropía.
        """
        ea = EntropyTools.shannon_entropy(a)
        eb = EntropyTools.shannon_entropy(b)
        diff = abs(ea - eb)
        logger.info(f"Comparación de entropía: A={ea:.3f} B={eb:.3f} Δ={diff:.3f}")
        return diff

    @staticmethod
    def is_random_enough(data: Union[str, bytes, List[Any]], threshold: float = 3.5) -> bool:
        """
        Determina si la entropía de los datos supera el umbral recomendado.
        """
        entropy = EntropyTools.shannon_entropy(data)
        logger.info(f"Entropía={entropy:.3f} (umbral={threshold})")
        return entropy >= threshold

# Exports principales para importar en otros módulos:
__all__ = [
    "ShannonEntropyCalculator",
    "EntropyTools"
]
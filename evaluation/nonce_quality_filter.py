"""
Nonce Quality Filter Module

Provides functionality to filter nonces based on quality metrics:
- Entropy threshold
- Pattern detection
- Statistical properties

Usage:
    from nonce_quality_filter import filter_nonces

    filtered = filter_nonces(nonces, min_entropy=0.8)
"""
import os
import sys
import pandas as pd
import math
import numpy as np
from typing import List, Tuple, Union
from iazar.analytics.entropy_tools import EntropyTools, hexstr_to_bytes
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)



# Establecer el directorio del proyecto
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

def filter_nonces(nonces: List[Union[str, bytes]], 
                 min_entropy: float = None, 
                 max_pattern_score: float = None) -> List[Union[str, bytes]]:
    """
    Filter nonces based on quality metrics
    
    Args:
        nonces: List of nonce values (hex strings or bytes)
        min_entropy: Minimum Shannon entropy threshold (0-8 scale)
        max_pattern_score: Maximum allowed pattern repetition score (0-1 scale)
    
    Returns:
        List of filtered nonces in original format
    """
    # Obtener configuración global si no se especifican parámetros
    config_manager = ConfigManager()
    app_config = config_manager.get_config('global_config')
    ia_config = app_config.get('ia', {})
    
    if min_entropy is None:
        min_entropy = ia_config.get('min_entropy', 3.5)
    
    if max_pattern_score is None:
        max_pattern_score = ia_config.get('max_pattern_score', 0.3)
    
    filtered = []
    
    for nonce in nonces:
        # Convertir a bytes si es necesario
        if isinstance(nonce, str):
            try:
                nonce_bytes = hexstr_to_bytes(nonce)
            except ValueError:
                continue
        else:
            nonce_bytes = nonce
        
        # Analizar calidad del nonce
        metrics = EntropyTools.analyze_nonce_quality(nonce_bytes)
        
        # Aplicar filtros
        if metrics['entropy'] >= min_entropy and metrics['pattern_score'] <= max_pattern_score:
            filtered.append(nonce)
    
    return filtered


class NonceQualityFilter:
    """Filtro de calidad avanzado para nonces en minería de RandomX/Monero"""
    
    @staticmethod
    def evaluate_nonce(nonce: Union[str, bytes]) -> float:
        """
        Evalúa la calidad de un nonce usando características estadísticas
        
        Args:
            nonce: Cadena hexadecimal o bytes que representa el nonce
        
        Returns:
            Puntuación de calidad entre 0.0 (mala) y 1.0 (excelente)
        """
        # Convertir a bytes si es necesario
        if isinstance(nonce, str):
            try:
                nonce_bytes = hexstr_to_bytes(nonce)
            except ValueError:
                return 0.0
        else:
            nonce_bytes = nonce
        
        # Obtener métricas de calidad
        metrics = EntropyTools.analyze_nonce_quality(nonce_bytes)
        return metrics['quality_score']

    @staticmethod
    def filter_nonces(nonces: List[Union[str, bytes]], 
                     threshold: float = 0.75) -> List[Union[str, bytes]]:
        """
        Filtra nonces que superan el umbral de calidad
        
        Args:
            nonces: Lista de nonces a evaluar
            threshold: Umbral de calidad (0.0-1.0)
        
        Returns:
            Lista de nonces que superan el umbral
        """
        return [n for n in nonces if NonceQualityFilter.evaluate_nonce(n) >= threshold]

    @staticmethod
    def batch_evaluate(nonces: List[Union[str, bytes]]) -> List[Tuple[Union[str, bytes], float]]:
        """Evalúa un lote de nonces de manera eficiente"""
        return [(nonce, NonceQualityFilter.evaluate_nonce(nonce)) for nonce in nonces]

# Funciones de utilidad para compatibilidad
def leer_nonces_csv(path: str) -> pd.DataFrame:
    """Mantiene compatibilidad con versiones anteriores"""
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()

def guardar_nonces_csv(df: pd.DataFrame, path: str) -> None:
    """Mantiene compatibilidad con versiones anteriores"""
    df.to_csv(path, index=False)
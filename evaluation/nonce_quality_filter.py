import math
import numpy as np
import os
import pandas as pd
import json
from collections import Counter
from typing import List, Dict, Tuple, Optional

# Standard global columns - using local definition for consistency
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

def leer_nonces_csv(path: str) -> pd.DataFrame:
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
    if not os.path.exists(path):
        pd.DataFrame(columns=COLUMNS).to_csv(path, index=False)
        return pd.DataFrame(columns=COLUMNS)
    
    df = pd.read_csv(path)
    missing = [col for col in COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = 0.0 if col != "is_valid" else False
    
    df = df[COLUMNS]
    return df.dropna().reset_index(drop=True)

def guardar_nonces_csv(df: pd.DataFrame, path: str) -> None:
    """Guarda un DataFrame de nonces con la cabecera y orden estándar."""
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = 0.0 if col != "is_valid" else False
    
    df[COLUMNS].to_csv(path, index=False)

def leer_nonces_json(path: str) -> List[Dict]:
    """Lee un JSON de nonces como lista de dicts."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
        return []
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    for item in data:
        for col in COLUMNS:
            if col not in item:
                item[col] = 0.0 if col != "is_valid" else False
    
    return data

def guardar_nonces_json(data: List[Dict], path: str) -> None:
    """Guarda una lista de dicts como JSON de nonces."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def hexstr_to_bytes(blob_hex: str) -> bytes:
    """Convierte un string hexadecimal a bytes."""
    return bytes.fromhex(blob_hex)

def bytes_to_hexstr(blob_bytes: bytes) -> str:
    """Convierte bytes a string hexadecimal."""
    return blob_bytes.hex()

class NonceQualityFilter:
    """Filtro de calidad avanzado para nonces en minería de RandomX/Monero"""
    
    # Parámetros optimizados para el filtrado
    WEIGHTS = {
        'entropy': 0.35,
        'autocorr': 0.25,
        'chi2': 0.25,
        'runs': 0.15
    }
    
    # Umbrales para las pruebas estadísticas
    CHI2_THRESHOLD = 0.01
    AUTOCORR_THRESHOLD = 0.15
    MIN_ENTROPY = 6.8
    RUNS_Z_THRESHOLD = 3.0

    @staticmethod
    def evaluate_nonce(nonce: str) -> float:
        """
        Evalúa la calidad de un nonce usando características estadísticas
        relevantes para la minería de RandomX.

        Args:
            nonce: Cadena hexadecimal que representa el nonce

        Returns:
            Puntuación de calidad entre 0.0 (mala) y 1.0 (excelente)
        """
        try:
            # Convertir a representación binaria
            if len(nonce) % 2 != 0:
                nonce = '0' + nonce  # Padding para longitud uniforme
            
            binary_rep = bin(int(nonce, 16))[2:].zfill(len(nonce)*4)
            byte_values = [int(nonce[i:i+2], 16) for i in range(0, len(nonce), 2)]
        except ValueError:
            return 0.0

        # Calcular métricas clave
        metrics = {
            'entropy': NonceQualityFilter._shannon_entropy(byte_values),
            'autocorr': NonceQualityFilter._autocorrelation(byte_values),
            'chi2': NonceQualityFilter._chi_square_test(byte_values),
            'runs': NonceQualityFilter._runs_test(binary_rep)
        }

        # Calcular puntuaciones individuales
        entropy_score = min(1.0, metrics['entropy'] / 8.0)  # Normalizado a 0-1
        autocorr_score = max(0.0, 1.0 - abs(metrics['autocorr']) / NonceQualityFilter.AUTOCORR_THRESHOLD)
        chi2_score = 1.0 if metrics['chi2'] > NonceQualityFilter.CHI2_THRESHOLD else 0.0
        runs_score = max(0.0, 1.0 - min(1.0, metrics['runs'] / NonceQualityFilter.RUNS_Z_THRESHOLD))

        # Combinar puntuaciones con pesos
        total_score = (
            NonceQualityFilter.WEIGHTS['entropy'] * entropy_score +
            NonceQualityFilter.WEIGHTS['autocorr'] * autocorr_score +
            NonceQualityFilter.WEIGHTS['chi2'] * chi2_score +
            NonceQualityFilter.WEIGHTS['runs'] * runs_score
        )

        return max(0.0, min(1.0, total_score))

    @staticmethod
    def filter_nonces(nonces: List[str], threshold: float = 0.75) -> List[str]:
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
    def _shannon_entropy(data: List[int]) -> float:
        """Calcula la entropía de Shannon en bits por byte"""
        if len(data) < 2:
            return 0.0

        counts = Counter(data)
        total = len(data)
        probs = [count / total for count in counts.values()]
        
        return -sum(p * math.log2(p) for p in probs)

    @staticmethod
    def _autocorrelation(data: List[int], lag: int = 1) -> float:
        """Calcula la autocorrelación para un lag específico"""
        if len(data) < lag + 1:
            return 0.0

        mean = np.mean(data)
        numerator = sum(
            (data[i] - mean) * (data[i + lag] - mean)
            for i in range(len(data) - lag)
        )
        denominator = sum((x - mean) ** 2 for x in data)

        return numerator / denominator if denominator != 0 else 0.0

    @staticmethod
    def _chi_square_test(data: List[int]) -> float:
        """Prueba de chi-cuadrado para distribución uniforme (devuelve p-value)"""
        if len(data) < 256:
            return 0.0  # Muestra demasiado pequeña

        # Inicializar bins para todos los bytes posibles
        bins = [0] * 256
        for byte in data:
            if 0 <= byte < 256:
                bins[byte] += 1

        total = len(data)
        expected = total / 256.0
        chi2_stat = sum((count - expected) ** 2 / expected for count in bins)

        # Aproximación normal para distribución chi-cuadrado
        k = 255  # grados de libertad
        Z = (chi2_stat - k) / math.sqrt(2 * k)
        p_value = 0.5 * math.erfc(Z / math.sqrt(2))  # Función de supervivencia
        
        return p_value

    @staticmethod
    def _runs_test(binary_str: str) -> float:
        """Prueba de rachas para detectar patrones no aleatorios (devuelve z-score)"""
        n = len(binary_str)
        if n < 2:
            return 0.0

        runs = 1
        for i in range(1, n):
            if binary_str[i] != binary_str[i-1]:
                runs += 1

        n1 = binary_str.count('1')
        n0 = n - n1

        # Evitar división por cero
        if n0 == 0 or n1 == 0:
            return 0.0

        expected_runs = 2 * n0 * n1 / n + 1
        variance = (2 * n0 * n1 * (2 * n0 * n1 - n)) / (n ** 2 * (n - 1))
        
        if variance <= 0:
            return 0.0

        z = (runs - expected_runs) / math.sqrt(variance)
        return abs(z)  # Valor absoluto para considerar ambas colas

    @staticmethod
    def batch_evaluate(nonces: List[str]) -> List[Tuple[str, float]]:
        """Evalúa un lote de nonces de manera eficiente"""
        return [(nonce, NonceQualityFilter.evaluate_nonce(nonce)) for nonce in nonces]

# Ejemplo de uso:
# df = leer_nonces_csv("ruta.csv")
# guardar_nonces_csv(df, "nueva_ruta.csv")
# 
# nonces = ["a1b2c3d4", "00000000", "deadbeef", "12345678"]
# filtered = NonceQualityFilter.filter_nonces(nonces)
# 
# scores = NonceQualityFilter.batch_evaluate(nonces)
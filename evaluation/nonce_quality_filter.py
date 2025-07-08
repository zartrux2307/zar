import math
import numpy as np
import os
import pandas as pd
import json
from collections import Counter
from typing import List
from iazar.utils.feature_utils import calc_nonce_features, guardar_nonces_csv, COLUMNS


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

class NonceQualityFilter:
    """Filtro de calidad para nonces en minería de RandomX/Monero"""

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
        # 1. Convertir a representación binaria
        try:
            binary_rep = bin(int(nonce, 16))[2:].zfill(len(nonce)*4)
        except ValueError:
            return 0.0

        # 2. Calcular características clave
        byte_values = [int(nonce[i:i+2], 16) for i in range(0, len(nonce), 2)]

        # 3. Entropía de Shannon (bits por byte)
        entropy = NonceQualityFilter._shannon_entropy(byte_values)

        # 4. Autocorrelación (debe ser baja para buena aleatoriedad)
        autocorr = NonceQualityFilter._autocorrelation(byte_values)

        # 5. Distribución de bytes (test chi-cuadrado)
        chi2 = NonceQualityFilter._chi_square_test(byte_values)

        # 6. Prueba de rachas (runs test)
        runs_score = NonceQualityFilter._runs_test(binary_rep)

        # 7. Combinar métricas (pesos basados en importancia para RandomX)
        entropy_score = min(1.0, entropy / 7.5)  # Normalizar a 0-1 (7.5 es excelente)
        autocorr_score = max(0.0, 1.0 - abs(autocorr) * 10)  # Invertir y normalizar
        chi2_score = 1.0 if chi2 > 0.05 else 0.0  # Pasa test chi-cuadrado?
        runs_score = min(1.0, runs_score / 0.5)  # Normalizar

        # Ponderación de factores
        weights = {
            'entropy': 0.35,
            'autocorr': 0.25,
            'chi2': 0.20,
            'runs': 0.20
        }

        total_score = (
            weights['entropy'] * entropy_score +
            weights['autocorr'] * autocorr_score +
            weights['chi2'] * chi2_score +
            weights['runs'] * runs_score
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
        if not data:
            return 0.0

        counts = Counter(data)
        total = len(data)
        entropy = 0.0

        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)

        return entropy

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
        """Prueba de chi-cuadrado para distribución uniforme"""
        observed = Counter(data)
        expected = len(data) / 256
        chi2 = sum((obs - expected) ** 2 / expected for obs in observed.values())

        # Grados de libertad = 256 - 1 = 255
        # Usamos aproximación para grandes muestras
        return 1.0 - math.erf(abs(chi2 - 255) / (math.sqrt(2 * 255)))

    @staticmethod
    def _runs_test(binary_str: str) -> float:
        """Prueba de rachas para detectar patrones no aleatorios"""
        if len(binary_str) < 2:
            return 0.0

        runs = 1
        for i in range(1, len(binary_str)):
            if binary_str[i] != binary_str[i-1]:
                runs += 1

        n = len(binary_str)
        n1 = binary_str.count('1')
        n0 = n - n1

        expected_runs = 2 * n0 * n1 / n + 1
        std_dev = math.sqrt(2 * n0 * n1 * (2 * n0 * n1 - n) / (n**2 * (n - 1)))

        # Normalizar diferencia respecto al valor esperado
        z = abs(runs - expected_runs) / std_dev if std_dev > 0 else 0.0
        return max(0.0, 1.0 - z / 4.0)  # z > 4 sería extremadamente raro

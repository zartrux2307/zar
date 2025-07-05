import math
import numpy as np
from collections import Counter
from typing import List

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

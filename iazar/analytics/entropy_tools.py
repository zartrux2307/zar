"""
entropy_tools.py - Herramientas profesionales de entropía para análisis IA.
© 2025 Zartrux AI Mining Project
"""

import math
import logging
from collections import Counter
from typing import Any, List, Optional, Union

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

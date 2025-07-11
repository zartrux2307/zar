# src/iazar/utils/feature_utils.py

import math
import zlib
import pandas as pd
from typing import Dict, List
import logging
import unittest
import os
import sys

import tempfile

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
        return abs(crc / 0xFFFFFFFF)  # Valor absoluto para evitar negativos
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

def calc_nonce_features(nonce_input) -> Dict:
    """
    Calcula todas las features estándar para un nonce, aceptando diferentes formatos.

    Args:
        nonce_input: Valor del nonce en formato int, str hexadecimal, o bytes

    Returns:
        Diccionario con todas las características calculadas
    """
    try:
        # Convertir diferentes formatos de entrada a entero
        if isinstance(nonce_input, str):
            # Manejar prefijos hexadecimales (0x, \x, etc.)
            if nonce_input.startswith(('0x', '\\x')):
                nonce_input = nonce_input[2:]
            nonce_value = int(nonce_input, 16)
        elif isinstance(nonce_input, bytes):
            # Convertir bytes a entero (little-endian)
            nonce_value = int.from_bytes(nonce_input, byteorder='little')
        else:
            nonce_value = int(nonce_input)
    except (ValueError, TypeError) as e:
        logger.error(f"Formato de nonce inválido: {nonce_input} - {str(e)}")
        nonce_value = 0
    
    try:
        # Manejar valores fuera del rango de 32 bits
        if nonce_value > 0xFFFFFFFF:
            logger.warning(f"Nonce demasiado grande (0x{nonce_value:X}), truncando a 32 bits")
            nonce_value = nonce_value & 0xFFFFFFFF
            is_valid = 0
        elif nonce_value < 0:
            logger.warning(f"Nonce negativo ({nonce_value}), usando valor absoluto")
            nonce_value = abs(nonce_value) & 0xFFFFFFFF
            is_valid = 0
        else:
            is_valid = is_valid_nonce(nonce_value)

        # Convertir nonce a formato de bytes (4 bytes, little-endian)
        nonce_bytes = nonce_value.to_bytes(4, byteorder='little')

        return {
            "nonce": nonce_value,
            "entropy": entropy(nonce_bytes),
            "uniqueness": uniqueness(nonce_bytes),
            "zero_density": zero_density(nonce_bytes),
            "pattern_score": pattern_score(nonce_bytes),
            "is_valid": is_valid
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

# ==============================
# Tests Unitarios
# ==============================
class TestFeatureUtils(unittest.TestCase):
    def setUp(self):
        self.valid_nonce = 123456789
        self.invalid_nonce = 0xFFFFFFFF + 1
        self.zero_nonce = 0x00000000
        self.max_nonce = 0xFFFFFFFF
        self.hex_nonce = "1a2b3c4d"
        self.large_nonce = "1a2b3c4d5e6f7a8b"
        
    def test_entropy(self):
        # Todos los bytes iguales (entropía mínima)
        self.assertAlmostEqual(entropy(b'\x00\x00\x00\x00'), 0.0, delta=0.001)
        
        # Bytes diferentes (entropía alta)
        self.assertAlmostEqual(entropy(b'\x00\x01\x02\x03'), 2.0, delta=0.1)
        
        # Caso vacío
        self.assertEqual(entropy(b''), 0.0)

    def test_uniqueness(self):
        # Todos los bytes iguales
        self.assertAlmostEqual(uniqueness(b'\x00\x00\x00\x00'), 0.25, delta=0.001)
        
        # Todos los bytes diferentes
        self.assertAlmostEqual(uniqueness(b'\x00\x01\x02\x03'), 1.0, delta=0.001)
        
        # Caso vacío
        self.assertEqual(uniqueness(b''), 0.0)

    def test_zero_density(self):
        # Todos ceros
        self.assertAlmostEqual(zero_density(b'\x00\x00\x00\x00'), 1.0, delta=0.001)
        
        # Sin ceros
        self.assertAlmostEqual(zero_density(b'\x01\x02\x03\x04'), 0.0, delta=0.001)
        
        # Mitad ceros
        self.assertAlmostEqual(zero_density(b'\x00\x01\x00\x01'), 0.5, delta=0.001)
        
        # Caso vacío
        self.assertEqual(zero_density(b''), 0.0)

    def test_pattern_score(self):
        # Valor conocido para patrón específico
        known_crc = zlib.crc32(b'\x00\x01\x02\x03', 0)
        expected = abs(known_crc / 0xFFFFFFFF)
        self.assertAlmostEqual(pattern_score(b'\x00\x01\x02\x03'), expected, delta=0.001)
        
        # Debe estar entre 0 y 1
        score = pattern_score(b'\x00\x01\x02\x03')
        self.assertTrue(0.0 <= score <= 1.0)
        
        # Caso vacío
        self.assertEqual(pattern_score(b''), 0.0)

    def test_is_valid_nonce(self):
        # Nonce válido
        self.assertEqual(is_valid_nonce(self.valid_nonce), 1)
        self.assertEqual(is_valid_nonce(self.zero_nonce), 1)
        self.assertEqual(is_valid_nonce(self.max_nonce), 1)
        
        # Nonce inválido
        self.assertEqual(is_valid_nonce(self.invalid_nonce), 0)
        self.assertEqual(is_valid_nonce(-1), 0)

    def test_calc_nonce_features(self):
        # Nonce válido
        features = calc_nonce_features(self.valid_nonce)
        self.assertEqual(features["nonce"], self.valid_nonce)
        self.assertTrue(0.0 <= features["entropy"] <= 8.0)
        self.assertTrue(0.0 <= features["uniqueness"] <= 1.0)
        self.assertTrue(0.0 <= features["zero_density"] <= 1.0)
        self.assertTrue(0.0 <= features["pattern_score"] <= 1.0)
        self.assertEqual(features["is_valid"], 1)
        
        # Nonce inválido
        features = calc_nonce_features(self.invalid_nonce)
        self.assertEqual(features["nonce"], self.invalid_nonce & 0xFFFFFFFF)
        self.assertEqual(features["is_valid"], 0)
        
        # Nonce hexadecimal
        hex_value = int(self.hex_nonce, 16)
        features = calc_nonce_features(self.hex_nonce)
        self.assertEqual(features["nonce"], hex_value)
        self.assertEqual(features["is_valid"], 1)
        
        # Nonce grande (64 bits)
        features = calc_nonce_features(self.large_nonce)
        expected_value = int(self.large_nonce, 16) & 0xFFFFFFFF
        self.assertEqual(features["nonce"], expected_value)
        self.assertEqual(features["is_valid"], 0)
        
        # Verificar todas las columnas están presentes
        self.assertCountEqual(features.keys(), COLUMNS)

    def test_guardar_nonces_csv(self):
        # Crear datos de prueba
        test_data = [
            calc_nonce_features(123),
            calc_nonce_features(456),
            calc_nonce_features(789),
        ]
        
        # Usar archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmpfile:
            tmp_path = tmpfile.name
        
        try:
            # Guardar y verificar
            guardar_nonces_csv(test_data, tmp_path)
            self.assertTrue(os.path.exists(tmp_path))
            
            # Cargar y verificar contenido
            df = pd.read_csv(tmp_path)
            self.assertEqual(len(df), 3)
            self.assertCountEqual(df.columns.tolist(), COLUMNS)
            
            # Verificar valores
            self.assertEqual(df['nonce'].tolist(), [123, 456, 789])
            self.assertTrue((df['is_valid'] == 1).all())
            
        finally:
            # Limpiar
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

# ==============================
# Punto de entrada para pruebas
# ==============================
if __name__ == "__main__":
    # Ejecutar tests unitarios
    unittest.main(argv=[''], exit=False)
    
    # Ejemplo de uso adicional
    print("\nEjemplo de cálculo de features para nonce 42:")
    print(calc_nonce_features(42))
    print("\nEjemplo de cálculo para nonce hexadecimal '1a2b3c4d':")
    print(calc_nonce_features("1a2b3c4d"))
    print("\nEjemplo de cálculo para nonce grande '1a2b3c4d5e6f7a8b':")
    print(calc_nonce_features("1a2b3c4d5e6f7a8b"))
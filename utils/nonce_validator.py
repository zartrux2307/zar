# nonce_validator.py
"""
Validador de nonces para Zartrux (modular, sin imports relativos rotos).
Puede usarse como módulo o ejecutarse directo para test.
"""

__all__ = ["HexNonceValidator", "is_valid_nonce"]


class HexNonceValidator:
    def __init__(self, min_length=8, max_length=8):  # Longitudes por defecto para nonces de 4 bytes
        """
        Inicializa el validador con rangos de longitud
        
        Args:
            min_length (int): Longitud mínima permitida para el nonce hexadecimal
            max_length (int): Longitud máxima permitida para el nonce hexadecimal
        """
        self.min_length = min_length
        self.max_length = max_length
        
    def validate(self, nonce_hex: str) -> bool:
        """
        Valida si un nonce hexadecimal cumple con los requisitos
        
        Args:
            nonce_hex (str): Cadena hexadecimal a validar
            
        Returns:
            bool: True si el nonce es válido, False en caso contrario
        """
        # 1. Verificar que sea string
        if not isinstance(nonce_hex, str):
            return False
            
        # 2. Verificar longitud
        length = len(nonce_hex)
        if not (self.min_length <= length <= self.max_length):
            return False
            
        # 3. Verificar que todos los caracteres sean hexadecimales
        try:
            int(nonce_hex, 16)
            return True
        except ValueError:
            return False

    # Mantener alias para compatibilidad
    is_valid = validate


def is_valid_nonce(nonce: str) -> bool:
    """Devuelve True si el nonce es válido hexadecimal (longitud y caracteres)."""
    return HexNonceValidator().validate(nonce)


if __name__ == "__main__":
    # Pruebas de validación
    tests = [
        ("1a2b3c4d", True),    # Válido
        ("1A2B3C4D", True),    # Válido (mayúsculas)
        ("deadbeef", True),    # Válido
        ("12345678", True),    # Válido
        ("1234abcd", True),    # Válido
        ("1a2b3c4", False),    # Muy corto (7 caracteres)
        ("1a2b3c4de", False),  # Muy largo (9 caracteres)
        ("1g2b3c4d", False),   # Carácter no hexadecimal
        ("", False),            # Vacío
        (12345678, False),      # No es string
        ("1a2b3c4z", False),   # Carácter inválido
    ]
    
    validator = HexNonceValidator()
    
    print("Pruebas de validación de nonces:")
    for nonce, expected in tests:
        result = validator.validate(nonce)
        print(f"Nonce '{nonce}': {'✅ Válido' if result == expected else '❌ Fallo'}")
        print(f"  Esperado: {expected}, Obtenido: {result}")
    
    print("\nPrueba de función helper:")
    test_nonce = "1a2b3c4d"
    print(f"Nonce {test_nonce} válido?: {is_valid_nonce(test_nonce)}")
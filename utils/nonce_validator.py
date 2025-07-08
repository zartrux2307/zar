# nonce_validator.py
"""
Validador de nonces para Zartrux (modular, sin imports relativos rotos).
Puede usarse como módulo o ejecutarse directo para test.
"""

from iazar.utils.hex_validator import HexNonceValidator

__all__ = ["HexNonceValidator"]

def is_valid_nonce(nonce: str) -> bool:
    """Devuelve True si el nonce es válido hexadecimal (longitud y caracteres)."""
    return HexNonceValidator().is_valid(nonce)

if __name__ == "__main__":
    test_nonce = "1a2b3c4d"
    print(f"Nonce {test_nonce} válido?: {is_valid_nonce(test_nonce)}")

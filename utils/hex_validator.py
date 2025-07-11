import re

def is_valid_hex(s: str, length=None) -> bool:
    """Valida si un string es un hexadecimal válido (opcionalmente de cierta longitud)."""
    if not isinstance(s, str):
        return False
    pattern = r'^[0-9a-fA-F]+$'
    if not re.match(pattern, s):
        return False
    if length is not None and len(s) != length:
        return False
    return True

def hex_to_int(s: str) -> int:
    """Convierte un string hexadecimal en entero."""
    try:
        return int(s, 16)
    except Exception:
        raise ValueError(f"'{s}' no es un hexadecimal válido.")

def int_to_hex(n: int, length=None) -> str:
    """Convierte un entero a string hexadecimal (opcionalmente de cierta longitud)."""
    h = hex(n)[2:]
    if length:
        h = h.zfill(length)
    return h

class HexNonceValidator:
    """Validador profesional para nonces en formato hexadecimal."""
    def __init__(self, length=8):
        self.length = length

    def is_valid(self, s: str) -> bool:
        return is_valid_hex(s, self.length)

    def validate_and_convert(self, s: str) -> int:
        if not self.is_valid(s):
            raise ValueError(f"Nonce no válido: {s}")
        return hex_to_int(s)

# Ejemplo de uso real:
if __name__ == "__main__":
    val = HexNonceValidator(length=8)
    print(val.is_valid("1a2b3c4d"))      # True
    print(val.validate_and_convert("1a2b3c4d"))  # 439041101
    print(is_valid_hex("abcdef", 6))     # True
    print(int_to_hex(255, 4))            # 00ff

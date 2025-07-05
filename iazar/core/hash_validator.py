import binascii
from iazar.utils.randomx_wrapper import compute_randomx_hash

class HashValidator:
    @staticmethod
    def hex_to_bytes(hex_str: str) -> bytes:
        return binascii.unhexlify(hex_str)

    @staticmethod
    def bytes_to_hex(byte_data: bytes) -> str:
        return binascii.hexlify(byte_data).decode()

    @staticmethod
    def meets_target(hash_bytes: bytes, target: int) -> bool:
        """
        Verifica si el hash cumple con el objetivo de dificultad (target).
        """
        hash_int = int.from_bytes(hash_bytes, byteorder='little')
        return hash_int < target

    @staticmethod
    def is_valid_nonce(nonce: int) -> bool:
        """
        Verifica si el nonce es un entero válido (32 bits).
        """
        return 0 <= nonce <= 0xFFFFFFFF

    @staticmethod
    def validate_submission(blob_hex: str, nonce_hex: str, expected_hash_hex: str, target: int) -> bool:
        """
        Valida un resultado de minería recibido desde mining.submit:
        - Inserta el nonce en el blob
        - Calcula el hash con RandomX
        - Compara con el hash enviado
        - Verifica si cumple el target
        """
        try:
            blob_bytes = bytearray(bytes.fromhex(blob_hex))
            nonce = int(nonce_hex, 16)

            # Insertar nonce little-endian en offset 39 (posición estándar Monero)
            blob_bytes[39:43] = nonce.to_bytes(4, 'little')

            # Calcular el hash usando RandomX
            computed_hash = compute_randomx_hash(bytes(blob_bytes))
            computed_hash_hex = computed_hash.hex()

            return (
                computed_hash_hex.lower() == expected_hash_hex.lower()
                and HashValidator.meets_target(computed_hash, target)
            )
        except Exception as e:
            print(f"[ERROR] Error al validar submission: {e}")
            return False

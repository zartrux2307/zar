"""
block_builder.py - Construcción de blobs de bloque Monero para minería IA-Zartrux.
Evita dependencias externas. Usa utilidades y formatos de producción.

IMPORTANTE:
- Usar los campos reales requeridos por la pool/protocolo.
- Solo funciones productivas.
"""

import binascii
import struct
from iazar.utils.randomx_wrapper import compute_randomx_hash

def build_block_header_blob(header_fields: dict, nonce: int) -> bytes:
    """
    Construye el blob de cabecera de bloque Monero en formato real de pool.
    Args:
        header_fields (dict): Debe incluir:
            - 'major_version' (int)
            - 'minor_version' (int)
            - 'timestamp' (int)
            - 'prev_id' (hex str, 32 bytes)
        nonce (int): Nonce válido (0-2^32).
    Returns:
        bytes: Blob serializado listo para hashing.
    """
    major = header_fields['major_version']
    minor = header_fields['minor_version']
    timestamp = header_fields['timestamp']
    prev_id = binascii.unhexlify(header_fields['prev_id'])
    nonce_bytes = struct.pack("<I", nonce)  # Nonce: 4 bytes little-endian
    # Empaquetar cabecera Monero (básica, puedes ampliar según protocolo/pool)
    blob = (
        struct.pack("<B", major) +
        struct.pack("<B", minor) +
        struct.pack("<I", timestamp) +
        prev_id +
        nonce_bytes
    )
    return blob

def compute_block_hash(block_blob: bytes, seed_hash: bytes) -> bytes:
    """
    Calcula el hash del bloque usando RandomX real y semilla.
    """
    return compute_randomx_hash(block_blob, seed_hash=seed_hash)

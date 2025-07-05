"""
randomx_handler.py - Encapsula uso de RandomX para hashing en minería Monero/IA.
Depende del wrapper real, sin dummy ni simulaciones.
"""

from iazar.utils.randomx_wrapper import compute_randomx_hash

class RandomXHandler:
    def __init__(self):
        self.current_seed = None

    def calculate_hash(self, blob: bytes, nonce: int, seed_hash: bytes) -> bytes:
        """
        Calcula el hash RandomX usando el wrapper (hash de bloque real).
        """
        return compute_randomx_hash(blob, nonce, seed_hash)

    def reinitialize_for_new_block(self, new_seed: bytes):
        """
        Reinicializa la caché para un nuevo bloque si es necesario (gestionado por wrapper).
        """
        self.current_seed = new_seed

    def __del__(self):
        pass  # Limpieza si hace falta, wrapper ya gestiona recursos.

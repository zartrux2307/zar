"""
difficulty_manager.py - Gestión de dificultad de bloque Monero para IA-Zartrux.
Sin dependencias externas ni lógica dummy.
"""

class DifficultyManager:
    @staticmethod
    def target_from_difficulty(difficulty: int) -> int:
        """
        Calcula el target a partir de dificultad (Monero estándar).
        """
        # Monero usa un target de 2^256 // difficulty
        return (1 << 256) // difficulty

    @staticmethod
    def difficulty_from_target(target: int) -> int:
        """
        Calcula la dificultad a partir del target.
        """
        return (1 << 256) // target

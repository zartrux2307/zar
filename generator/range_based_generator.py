import random
import numpy as np
from .nonce_generator import NonceGenerator

class RangeBasedGenerator(NonceGenerator):
    def __init__(self):
        super().__init__()
        self.ranges = self.calculate_ranges()
        
    def calculate_ranges(self):
        # Cargar datos históricos (implementar según tu estructura)
        # Por ahora, rangos de ejemplo
        return [
            (0, 100000000),
            (200000000, 300000000),
            (400000000, 500000000)
        ]
        
    def generate(self, count):
        selected_range = random.choice(self.ranges)
        nonces = [random.randint(*selected_range) for _ in range(count)]
        return self._ensure_unique(nonces)
import random
from .nonce_generator import NonceGenerator
from .range_based_generator import RangeBasedGenerator
from .ml_based_generator import MLBasedGenerator

class HybridGenerator(NonceGenerator):
    def __init__(self):
        super().__init__()
        self.range_generator = RangeBasedGenerator()
        self.ml_generator = MLBasedGenerator()
        
    def generate(self, count):
        # Mezclar técnicas
        half = count // 2
        range_nonces = self.range_generator.generate(half)
        ml_nonces = self.ml_generator.generate(count - half)
        return range_nonces + ml_nonces
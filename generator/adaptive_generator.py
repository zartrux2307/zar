import random
from .nonce_generator import NonceGenerator

class AdaptiveGenerator(NonceGenerator):
    def __init__(self):
        super().__init__()
        self.last_successful = None
        
    def generate(self, count):
        if self.last_successful:
            # Generar cerca del último nonce exitoso
            start = max(0, self.last_successful - 500000)
            end = min(2**32-1, self.last_successful + 500000)
            return [random.randint(start, end) for _ in range(count)]
        else:
            return [random.randint(0, 2**32-1) for _ in range(count)]
    
    def update_success(self, nonce):
        """Actualizar con nonce exitoso (llamar desde fuera)"""
        self.last_successful = nonce
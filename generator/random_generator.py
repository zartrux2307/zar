import random
from .nonce_generator import NonceGenerator

class RandomGenerator(NonceGenerator):
    def generate(self, count):
        return [random.randint(0, 2**32-1) for _ in range(count)]
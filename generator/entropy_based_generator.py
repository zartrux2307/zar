import random
from iazar.generator.nonce_generator import NonceGenerator
from iazar.analytics.entropy_tools import EntropyTools
from iazar.utils.config_manager import ConfigManager
from iazar.utils.nonce_data_manager import append_nonces
class EntropyBasedGenerator(NonceGenerator):
   


# Dentro de tu función principal...
for nonce in nonces_validados:
    append_nonces([nonce], extra_cols={"is_valid": 1, "generator": "entropy"})


    """
    Generador de nonces que filtra en tiempo real por:
    - Entropía
    - Unicidad de bytes
    - Zero density
    - Pattern score
    - is_valid (estructura)
    """
    def __init__(self, min_entropy=None, min_uniqueness=None, max_zero_density=None, min_pattern_score=None):
        super().__init__()
        config = ConfigManager().get_config('global_config')
        self.min_entropy = min_entropy if min_entropy is not None else config.get('ia', {}).get('min_entropy', 3.5)
        self.min_uniqueness = min_uniqueness if min_uniqueness is not None else config.get('ia', {}).get('min_uniqueness', 0.8)
        self.max_zero_density = max_zero_density if max_zero_density is not None else config.get('ia', {}).get('max_zero_density', 0.7)
        self.min_pattern_score = min_pattern_score if min_pattern_score is not None else config.get('ia', {}).get('min_pattern_score', 0.8)

    def is_nonce_valid(self, candidate_bytes):
        features = EntropyTools.analyze_nonce_quality(candidate_bytes)
        # Puedes imprimir features para debug avanzado si quieres
        return (
            features['entropy'] >= self.min_entropy and
            features['uniqueness'] >= self.min_uniqueness and
            features['zero_density'] <= self.max_zero_density and
            features['pattern_score'] >= self.min_pattern_score and
            features['is_valid']
        )

    def generate(self, count):
        nonces = []
        while len(nonces) < count:
            candidate = random.getrandbits(32)
            candidate_bytes = candidate.to_bytes(4, byteorder='big')
            if self.is_nonce_valid(candidate_bytes):
                nonces.append(candidate)
        return nonces

# Test:
if __name__ == "__main__":
    gen = EntropyBasedGenerator()
    nonces = gen.generate(10)
    print("Nonces de alta calidad:", nonces)
  from iazar.utils.nonce_data_manager import append_nonces


  

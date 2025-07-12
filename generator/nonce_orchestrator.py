import threading
import time
from iazar.analytics.entropy_tools import EntropyTools
from iazar.utils.config_manager import ConfigManager

# Importa aquí todos los generadores que uses
from iazar.generator.nonce_generator import NonceGenerator
from iazar.generator.entropy_based_generator import EntropyBasedGenerator
from iazar.utils.nonce_data_manager import append_nonces

class NonceOrchestrator:
    def __init__(self, generadores=None, generator_nonces=1000):
        self.lock = threading.Lock()
        self.sent_nonces = set()
        self.generator_nonces = generator_nonces
        self.generadores = generadores or [
            EntropyBasedGenerator(),  # Usa tu generador mejorado
            NonceGenerator(),         # Generador de rangos (puedes añadir ML, random, etc.)
        ]
        self.generator_idx = 0

    def get_next_generator(self):
        # Rota los generadores si tienes varios
        gen = self.generadores[self.generator_idx]
        self.generator_idx = (self.generator_idx + 1) % len(self.generadores)
        return gen

    def quality_filter(self, nonce, 
                      min_entropy=None, min_uniqueness=None, 
                      max_zero_density=None, min_pattern_score=None):
        config = ConfigManager().get_config('global_config')
        min_entropy = min_entropy if min_entropy is not None else config.get('ia', {}).get('min_entropy', 3.5)
        min_uniqueness = min_uniqueness if min_uniqueness is not None else config.get('ia', {}).get('min_uniqueness', 0.8)
        max_zero_density = max_zero_density if max_zero_density is not None else config.get('ia', {}).get('max_zero_density', 0.7)
        min_pattern_score = min_pattern_score if min_pattern_score is not None else config.get('ia', {}).get('min_pattern_score', 0.8)
        nonce_bytes = nonce.to_bytes(4, byteorder='big')
        features = EntropyTools.analyze_nonce_quality(nonce_bytes)
        return (
            features['entropy'] >= min_entropy and
            features['uniqueness'] >= min_uniqueness and
            features['zero_density'] <= max_zero_density and
            features['pattern_score'] >= min_pattern_score and
            features['is_valid']
        )

    def generate_nonces(self):
        generator = self.get_next_generator()
        try:
            new_nonces = generator.generate(self.generator_nonces)
            with self.lock:
                filtered_nonces = []
                for n in new_nonces:
                    if n not in self.sent_nonces and self.quality_filter(n):
                        filtered_nonces.append(n)
                self.sent_nonces.update(filtered_nonces)
                return filtered_nonces
        except Exception as e:
            print(f"Error en generador {type(generator).__name__}: {str(e)}")
            return []

    def enviar_nonces_continuo(self):
        print(f"🚀 Orquestador lanzando {self.generator_nonces} nonces/segundo (solo de alta calidad)")
        try:
            while True:
                inicio_segundo = time.time()
                lote = self.generate_nonces()
                self.simular_envio(lote)
                tiempo_transcurrido = time.time() - inicio_segundo
                if tiempo_transcurrido < 1.0:
                    time.sleep(1.0 - tiempo_transcurrido)
        except KeyboardInterrupt:
            print("\n✅ Orquestador detenido por el usuario")

    def simular_envio(self, lote):
        # Imprime muestra, puedes sustituir por el hook real de envío
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        muestra = lote[:5] if len(lote) > 5 else lote
        print(f"[{timestamp}] 📤 Enviados {len(lote):,} nonces de alta calidad | Muestra: {muestra}")

if __name__ == "__main__":
    orchestrator = NonceOrchestrator(generator_nonces=1000)
    orchestrator.enviar_nonces_continuo()

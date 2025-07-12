from .nonce_generator import NonceGenerator

class SequenceBasedGenerator(NonceGenerator):
    def __init__(self):
        super().__init__()
        self.sequences = self.load_sequences()
        self.current_sequence = 0
        
    def load_sequences(self):
        # Cargar secuencias desde archivo (implementar)
        return [
            [123456, 123457, 123458, ...],
            [987654, 987655, 987656, ...]
        ]
        
    def generate(self, count):
        if not self.sequences:
            return []
            
        seq = self.sequences[self.current_sequence]
        self.current_sequence = (self.current_sequence + 1) % len(self.sequences)
        
        return seq[:min(count, len(seq))]
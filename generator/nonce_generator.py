import csv
import time
import random
import numpy as np
from collections import defaultdict
from datetime import datetime

# Configuración específica según tus indicaciones
CONFIG = {
    'input_csv': 'nonce_training_data.csv',  # Archivo de entrada
    'num_rangos': 10,                       # Dividir en 10 rangos
    'top_rangos': 3,                        # Usar los 3 mejores rangos
    'nonces_per_second': 1000,              # 1000 nonces por segundo
    'max_nonce': 2**32 - 1,                 # Máximo valor de nonce (32 bits)
}

class NonceGenerator:
    def __init__(self):
        self.rangos = []
        self.probabilidades = []
        self.top_rangos = []
        self.cargar_datos()
        self.calcular_probabilidades()
        self.seleccionar_top_rangos()

    def cargar_datos(self):
        """Carga todos los nonces del archivo CSV"""
        self.nonces = []
        try:
            with open(CONFIG['input_csv'], 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        nonce = int(row['nonce'])
                        if 0 <= nonce <= CONFIG['max_nonce']:
                            self.nonces.append(nonce)
                    except (ValueError, KeyError):
                        continue
            print(f"✅ Cargados {len(self.nonces)} nonces de {CONFIG['input_csv']}")
        except FileNotFoundError:
            print(f"❌ Error: Archivo {CONFIG['input_csv']} no encontrado")
            exit(1)

    def calcular_probabilidades(self):
        """Calcula las probabilidades por rango"""
        # Crear 10 rangos iguales
        tamano_rango = CONFIG['max_nonce'] // CONFIG['num_rangos']
        self.rangos = [
            (i * tamano_rango, (i + 1) * tamano_rango - 1) 
            for i in range(CONFIG['num_rangos'])
        ]
        
        # Ajustar el último rango para incluir el máximo
        self.rangos[-1] = (self.rangos[-1][0], CONFIG['max_nonce'])
        
        # Contar apariciones en cada rango
        conteos = [0] * CONFIG['num_rangos']
        for nonce in self.nonces:
            for i, (inicio, fin) in enumerate(self.rangos):
                if inicio <= nonce <= fin:
                    conteos[i] += 1
                    break
        
        # Calcular probabilidades
        total = sum(conteos)
        self.probabilidades = [count / total if total > 0 else 0 for count in conteos]
        
        # Imprimir estadísticas
        print("\n📊 Estadísticas de rangos:")
        for i, ((inicio, fin), prob) in enumerate(zip(self.rangos, self.probabilidades)):
            print(f"Rango {i+1}: {inicio:,} - {fin:,} | Prob: {prob*100:.2f}%")

    def seleccionar_top_rangos(self):
        """Selecciona los rangos con mayor probabilidad"""
        indices_ordenados = np.argsort(self.probabilidades)[::-1]  # De mayor a menor
        self.top_rangos = [self.rangos[i] for i in indices_ordenados[:CONFIG['top_rangos']]]
        
        # Calcular probabilidades normalizadas para los top rangos
        prob_total_top = sum(self.probabilidades[i] for i in indices_ordenados[:CONFIG['top_rangos']])
        self.prob_normalizadas = [self.probabilidades[i] / prob_total_top for i in indices_ordenados[:CONFIG['top_rangos']]]
        
        print("\n🎯 Rangos seleccionados:")
        for i, (inicio, fin) in enumerate(self.top_rangos):
            print(f"Top {i+1}: {inicio:,} - {fin:,} | Prob: {self.prob_normalizadas[i]*100:.2f}%")

    def generar_nonce(self):
        """Genera un nonce de los rangos prioritarios"""
        # Seleccionar un rango basado en probabilidad
        rango_idx = np.random.choice(len(self.top_rangos), p=self.prob_normalizadas)
        inicio, fin = self.top_rangos[rango_idx]
        
        # Generar nonce aleatorio dentro del rango
        return random.randint(inicio, fin)

    def enviar_nonces_continuo(self):
        """Envía nonces continuamente a la tasa especificada"""
        print("\n🚀 Iniciando envío de nonces...")
        print(f"⚡ Velocidad: {CONFIG['nonces_per_second']} nonces/segundo")
        print(f"🎯 Rangos activos: {len(self.top_rangos)}")
        print("🛑 Presiona Ctrl+C para detener\n")
        
        try:
            while True:
                inicio_segundo = time.time()
                lote = []
                
                # Generar lote completo para este segundo
                for _ in range(CONFIG['nonces_per_second']):
                    lote.append(self.generar_nonce())
                
                # Enviar lote (aquí iría la conexión real al minero)
                self.simular_envio(lote)
                
                # Ajuste preciso del tiempo
                tiempo_transcurrido = time.time() - inicio_segundo
                if tiempo_transcurrido < 1.0:
                    time.sleep(1.0 - tiempo_transcurrido)
        except KeyboardInterrupt:
            print("\n✅ Envío detenido por el usuario")

    def simular_envio(self, lote):
        """Simula el envío mostrando una muestra"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        muestra = random.sample(lote, min(5, len(lote)))
        print(f"[{timestamp}] 📤 Enviados {len(lote):,} nonces | Muestra: {muestra}")

if __name__ == "__main__":
    generador = NonceGenerator()
    generador.enviar_nonces_continuo()
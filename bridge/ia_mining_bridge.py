import time
import threading
import os
import sys
from queue import Queue
from iazar.models.nonce_predictor import NoncePredictor


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
class IAMiningBridge:
    def __init__(self, model_path='models/rf_nonce_model.joblib'):
        self.model = NoncePredictor.load(model_path)
        self.nonce_queue = Queue(maxsize=1000)
        self.running = False
        self.generator_thread = None

    def start_service(self):
        self.running = True
        self.generator_thread = threading.Thread(target=self.nonce_generator_service)
        self.generator_thread.daemon = True
        self.generator_thread.start()

    def stop_service(self):
        self.running = False
        if self.generator_thread:
            self.generator_thread.join()

    def nonce_generator_service(self):
        while self.running:
            # Obtener datos del trabajo actual (simulado)
            job_data = self.get_current_job_data()

            # Generar nonces con prioridad
            priority_nonces = self.model.predict_batch(job_data, count=100)

            for nonce in priority_nonces:
                if self.nonce_queue.full():
                    self.nonce_queue.get()  # Eliminar el más antiguo
                self.nonce_queue.put(nonce)

            time.sleep(5)

    def get_priority_nonce(self, job_data):
        if not self.nonce_queue.empty():
            return self.nonce_queue.get()
        return None

    def get_current_job_data(self):
        # En implementación real se obtendría del trabajo actual
        return {
            "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
            "difficulty": 1000000
        }

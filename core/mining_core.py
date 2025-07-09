import threading
import time
import json
import os
import struct  # Añadido para empaquetamiento binario
from iazarr.core.andomx_handler import RandomXHandler
from iazar.bridge.stratum_adapter import StratumClient
from iazar.utils.cpu_optimizer import CPUMonitor
from iazar.bridge.ia_mining_bridge import IAMiningBridge
from iazar.utils.config_manager import ConfigManager

class MiningCore:
    def __init__(self):
        self.config = ConfigManager().config
        self.running = False
        self.threads = []
        self.stratum_client = StratumClient(self.config['pools'])
        self.randomx = RandomXHandler(self.config['randomx'])
        self.ia_bridge = IAMiningBridge()
        self.cpu_monitor = CPUMonitor()

    def start(self):
        if not self.stratum_client.connect():
            return False
        
        self.running = True
        thread_count = self.cpu_monitor.get_optimal_thread_count()
        
        for i in range(thread_count):
            thread = threading.Thread(target=self.mining_worker)
            thread.daemon = True
            thread.start()
            self.threads.append(thread)
        
        return True

    def stop(self):
        self.running = False
        for thread in self.threads:
            thread.join()
        self.stratum_client.disconnect()

    def mining_worker(self):
        while self.running:
            job = self.stratum_client.get_current_job()
            if not job:
                time.sleep(1)
                continue
            
            # Obtener nonce de IA o generar aleatorio
            nonce = self.ia_bridge.get_priority_nonce(job) or self.generate_random_nonce()
            
            # Construir bloque con nonce
            block_header = self.build_block_header(job, nonce)
            
            # Calcular hash con RandomX
            hash_result = self.randomx.hash(block_header)
            
            # Verificar si cumple dificultad
            if self.verify_hash(hash_result, job['target']):
                self.stratum_client.submit_share(job['job_id'], nonce.hex(), hash_result.hex())
            
            # Ajustar rendimiento por temperatura
            self.cpu_monitor.adjust_performance()

    def build_block_header(self, job, nonce):
        # Empaquetar datos binarios en lugar de concatenar strings
        return struct.pack(
            '<32s32s32s8s',
            bytes.fromhex(job['prev_hash']),
            bytes.fromhex(job['coinb1']),
            bytes.fromhex(job['extra_nonce']),
            nonce
        )

    def generate_random_nonce(self):
        # Devolver bytes en lugar de string hexadecimal
        return os.urandom(8)

    def verify_hash(self, hash_value, target):
        hash_int = int.from_bytes(hash_value, byteorder='big')
        return hash_int < target
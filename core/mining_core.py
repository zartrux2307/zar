import threading
import time
import os
import struct
import logging
from iazar.core.randomx_handler import RandomXHandler
from iazar.bridge.stratum_adapter import StratumClient
from iazar.utils.cpu_optimizer import CPUMonitor
from iazar.bridge.ia_mining_bridge import IAMiningBridge
from iazar.utils.config_manager import ConfigManager

# Configurar logger
logger = logging.getLogger("MiningCore")

class MiningCore:
    def __init__(self):
        self.config = ConfigManager.get_config()
        self.running = False
        self.threads = []
        self.stratum_client = StratumClient(
            pool_host=self.config['stratum']['pool_host'],
            pool_port=self.config['stratum']['pool_port'],
            wallet=self.config['stratum']['wallet']
        )
        self.randomx = RandomXHandler(self.config['randomx'])
        self.ia_bridge = IAMiningBridge()
        self.cpu_monitor = CPUMonitor()
        
        logger.info("MiningCore inicializado con configuración: %s", self.config)

    def start(self):
        logger.info("Conectando a pool Stratum...")
        if not self.stratum_client.connect():
            logger.error("Fallo al conectar con el pool Stratum")
            return False

        self.running = True
        thread_count = self.cpu_monitor.get_optimal_thread_count()
        logger.info("Iniciando %d hilos de minería", thread_count)

        for i in range(thread_count):
            thread = threading.Thread(target=self.mining_worker, name=f"Miner-{i+1}")
            thread.daemon = True
            thread.start()
            self.threads.append(thread)

        return True

    def stop(self):
        logger.info("Deteniendo MiningCore...")
        self.running = False
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)
        self.stratum_client.disconnect()
        logger.info("MiningCore detenido correctamente")

    def mining_worker(self):
        thread_name = threading.current_thread().name
        logger.info("%s iniciado", thread_name)
        
        while self.running:
            job = self.stratum_client.get_current_job()
            if not job:
                logger.debug("%s: Esperando trabajo...", thread_name)
                time.sleep(1)
                continue

            # Obtener nonce de IA o generar aleatorio
            nonce = self.ia_bridge.get_priority_nonce(job) or self.generate_random_nonce()
            logger.debug("%s: Nonce utilizado: %s", thread_name, nonce.hex())

            # Construir bloque con nonce
            block_header = self.build_block_header(job, nonce)

            # Calcular hash con RandomX
            hash_result = self.randomx.hash(block_header)
            
            # Verificar si cumple dificultad
            if self.verify_hash(hash_result, job['target']):
                logger.info("%s: ¡Solución encontrada! Job: %s, Nonce: %s", 
                           thread_name, job['job_id'], nonce.hex())
                self.stratum_client.submit_share(
                    job_id=job['job_id'],
                    nonce=nonce.hex(),
                    hash_result=hash_result.hex()
                )

            # Ajustar rendimiento por temperatura
            self.cpu_monitor.adjust_performance()

    def build_block_header(self, job, nonce):
        """Construye el encabezado del bloque en formato binario"""
        try:
            return struct.pack(
                '<32s32s32s8s',
                bytes.fromhex(job['prev_hash']),
                bytes.fromhex(job['coinb1']),
                bytes.fromhex(job['extra_nonce']),
                nonce
            )
        except Exception as e:
            logger.error("Error construyendo bloque: %s", str(e))
            return b''

    def generate_random_nonce(self):
        """Genera un nonce aleatorio de 8 bytes"""
        return os.urandom(8)

    def verify_hash(self, hash_value, target):
        """Verifica si el hash cumple con el target de dificultad"""
        try:
            hash_int = int.from_bytes(hash_value, byteorder='big')
            return hash_int < target
        except Exception as e:
            logger.error("Error verificando hash: %s", str(e))
            return False
import logging
import threading
import time
import os
import sys
from iazar.bridge.shared_memory_manager import SharedMemoryManager
from iazar.core.randomx_handler import RandomXHandler
from iazar.utils.config_manager import get_ia_config

logger = logging.getLogger("JobSync")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

class JobSync:
    def __init__(self, stratum_adapter):
        self.stratum_adapter = stratum_adapter
        self.miner = RandomXHandler()
        self.current_job = None
        self.job_lock = threading.Lock()
        self.is_running = True
        self.config = get_ia_config()

        # Configuración de memoria compartida
        shm_config = {
            "prefix": self.config.get("shm_name", "zartrux_shared"),
            "create": False  # Conectarse a memoria existente
        }
        self.shm = SharedMemoryManager(**shm_config)

        # Estadísticas y configuración
        self.ia_enabled = self.config.get("ia_enabled", True)
        self.ia_timeout = self.config.get("ia_timeout", 1.0)  # segundos
        self.ia_success_count = 0
        self.ia_total_attempts = 0

    def process_job(self, job):
        if not job or job.difficulty <= 0:
            logger.warning("❌ Trabajo inválido")
            return

        with self.job_lock:
            self.current_job = job

        logger.info(f"🔄 Procesando Job {job.id} | Dificultad: {job.difficulty:.2f}")

        # Enviar trabajo a IA si está habilitada
        nonce = None
        ia_success = False

        if self.ia_enabled:
            # Verificar si la IA está lista para recibir trabajo
            if self.shm.is_ready_for_job():
                # Preparar datos para IA
                job_data = {
                    "job_id": job.id,
                    "blob": job.blob,
                    "target": job.target,
                    "seed_hash": job.seed_hash,
                    "height": getattr(job, 'height', 0)
                }

                # Enviar trabajo a IA
                self.shm.set_job(job_data)
                logger.debug(f"📤 Trabajo enviado a IA: {job.id}")

                # Esperar solución con timeout configurable
                start_time = time.time()
                while time.time() - start_time < self.ia_timeout:
                    if self.shm.is_solution_ready():
                        solution = self.shm.get_solution()
                        if solution["job_id"] == job.id:
                            nonce = solution["nonce"]
                            ia_success = True
                            self.ia_success_count += 1
                            logger.info(f"✅ Nonce IA válido recibido: 0x{nonce:08x}")
                            break
                    time.sleep(0.01)  # Polling de 10ms

                # Resetear estado si se usó solución
                if ia_success:
                    self.shm.reset()

        self.ia_total_attempts += 1

        # Fallback a minería tradicional si IA no proporcionó solución
        if not ia_success:
            if self.ia_enabled:
                logger.warning("⏳ Timeout IA, usando minería tradicional")
            nonce = self.miner.generate_random_nonce()

        # Procesar minería
        try:
            result_hash = self.miner.mine(job, nonce)
            if result_hash:
                logger.info(f"🚀 Hash válido: {result_hash[:12]}... enviado")
                self.stratum_adapter.submit_solution(job.id, nonce, result_hash)
            else:
                logger.debug("❌ Hash no válido")
        except Exception as e:
            logger.exception(f"💥 Error durante minería: {e}")

    @property
    def ia_success_rate(self) -> float:
        """Calcula tasa de éxito de la IA"""
        if self.ia_total_attempts == 0:
            return 0.0
        return self.ia_success_count / self.ia_total_attempts

    def job_updater(self):
        while self.is_running:
            try:
                job = self.stratum_adapter.get_next_job()
                if job and job.id != getattr(self.current_job, 'id', None):
                    self.process_job(job)
                else:
                    time.sleep(0.05)  # Menor tiempo de espera
            except Exception as e:
                logger.exception(f"💥 Error en job_updater: {e}")
                time.sleep(1)

    def start(self):
        self.is_running = True
        threading.Thread(
            target=self.job_updater,
            daemon=True,
            name="JobSync-Updater"
        ).start()
        logger.info("🚦 JobSync iniciado")

    def stop(self):
        self.is_running = False
        logger.info("🛑 JobSync detenido")
        # Cerrar conexión a memoria compartida
        self.shm.cleanup()

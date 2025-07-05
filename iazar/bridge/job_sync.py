# src/iazar/bridge/job_sync.py
# Módulo central de distribución de trabajos entre IA y mineros Stratum
# Profesional, sincronizado, sin simulaciones

import threading

class JobDistributor:
    _lock = threading.Lock()
    _latest_job = None

    @classmethod
    def set_latest_job(cls, job_data: dict):
        with cls._lock:
            cls._latest_job = job_data.copy()  # Copia por seguridad

    @classmethod
    def get_latest_job(cls) -> dict:
        with cls._lock:
            return cls._latest_job.copy() if cls._latest_job else None

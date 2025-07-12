"""
Módulo avanzado de gestión de configuración con locking robusto
para acceso concurrente seguro y prevención de corrupción
"""

import os
import json
import hashlib
import logging
import jsonschema
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from filelock import FileLock, Timeout

# Import absoluto (universal, NO relativo)
from iazar.security.AESNonceEncryptor import AESNonceEncryptor

load_dotenv()
logger = logging.getLogger('ZartruxConfigManager')

class ConfigValidationError(Exception):
    """Excepción personalizada para errores de validación de configuración"""

class LockManager:
    """Gestor centralizado de locks para archivos de configuración"""
    _locks: Dict[str, FileLock] = {}
    
    @classmethod
    def get_lock(cls, file_path: Path) -> FileLock:
        """Obtiene o crea un lock para un archivo específico"""
        lock_key = str(file_path.resolve())
        
        if lock_key not in cls._locks:
            cls._locks[lock_key] = FileLock(f"{lock_key}.lock", timeout=10)
        
        return cls._locks[lock_key]

class ConfigManager:
    _instance = None
    _configs: Dict[str, Dict[str, Any]] = {}
    _schemas: Dict[str, Dict[str, Any]] = {}
    _encryption_key: Optional[bytes] = None

    # Esquemas base para validación (actualizados)
    BASE_SCHEMAS = {
        'global_config': {
            "type": "object",
            "properties": {
                "shm": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "size": {"type": "integer", "minimum": 1024}
                    },
                    "required": ["name", "size"]
                },
                "stratum": {
                    "type": "object",
                    "properties": {
                        "pool_host": {"type": "string"},
                        "pool_port": {"type": "integer", "minimum": 1, "maximum": 65535}
                    },
                    "required": ["pool_host", "pool_port"]
                },
                "logging": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                        "format": {"type": "string"}
                    },
                    "required": ["level", "format"]
                }
            },
            "required": ["shm", "stratum", "logging"]
        },
        # ... [El resto de los esquemas permanece igual] ...
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    # ... [El resto de los métodos de ConfigManager permanece igual] ...

# ==== ALIAS COMPATIBLES PARA IMPORTS ====

def get_ia_config() -> Dict[str, Any]:
    """Alias para configuración de IA"""
    return ConfigManager().get_config('ia_config')

def get_hub_config() -> Dict[str, Any]:
    """Alias para configuración de hub"""
    return ConfigManager().get_config('hub_config')

def get_miner_config() -> Dict[str, Any]:
    """Alias para configuración de minero"""
    return ConfigManager().get_config('miner_config')

def get_global_config() -> Dict[str, Any]:
    """Alias para configuración global"""
    return ConfigManager().get_config('global_config')

def get_config(config_name: str) -> Dict[str, Any]:
    """Alias genérico para obtener configuración por nombre"""
    return ConfigManager().get_config(config_name)

def get_shm_config() -> Dict[str, Any]:
    """Alias para configuración de memoria compartida"""
    return ConfigManager().get_shm_config()

def get_ia_params() -> Dict[str, Any]:
    """Alias para parámetros de IA"""
    return ConfigManager().get_ia_params()

def get_config_value(section: str, key: str, default=None) -> Any:
    """Alias público para acceso a valores de configuración anidados"""
    return ConfigManager().get_config_value(section, key, default)

# ===== NUEVOS ALIAS PARA GLOBAL CONFIG =====
def get_logging_config() -> Dict[str, Any]:
    """Alias para configuración de logging"""
    return ConfigManager().get_logging_config()

def get_stratum_config() -> Dict[str, Any]:
    """Alias para configuración de stratum"""
    return ConfigManager().get_stratum_config()

def get_shm_global_config() -> Dict[str, Any]:
    """Alias para configuración global de memoria compartida"""
    return ConfigManager().get_shm_global_config()

# ===== FUNCIÓN DE INICIALIZACIÓN =====
def initialize_system_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Alias para inicializar/obtener configuración del sistema"""
    return get_global_config()
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


config = initialize_system_config()
print(config["shm"]["name"])  # Ejemplo de acceso
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
        'ia_config': {
            "type": "object",
            "properties": {
                "data_paths": {
                    "type": "object",
                    "properties": {
                        "successful_nonces": {"type": "string"},
                        "nonce_hashes": {"type": "string"},
                        "injected_nonces": {"type": "string"},
                        "nonce_training_data_path": {"type": "string"}
                    },
                    "required": [
                        "successful_nonces",
                        "nonce_hashes",
                        "injected_nonces",
                        "nonce_training_data_path"
                    ]
                },
                "processing_params": {
                    "type": "object",
                    "properties": {
                        "temporal_window": {"type": "number", "minimum": 1},
                        "entropy_window": {"type": "number", "minimum": 10},
                        "candidate_count": {"type": "integer", "minimum": 100, "maximum": 50000},
                        "top_candidates": {"type": "integer", "minimum": 10, "maximum": 1000},
                        "polling_interval": {"type": "number", "minimum": 0.001, "maximum": 1.0}
                    },
                    "required": ["temporal_window"]
                },
                "shared_memory": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "enabled": {"type": "boolean"}
                    },
                    "required": ["name", "enabled"]
                }
            },
            "required": ["data_paths", "processing_params", "shared_memory"]
        },
        'hub_config': {
            "type": "object",
            "properties": {
                "hub_endpoint": {"type": "string"},
                "sync_interval": {"type": "number", "minimum": 5},
                "max_nodes": {"type": "number", "minimum": 1},
                "shm_sync": {"type": "boolean"}
            },
            "required": ["hub_endpoint"]
        },
        'miner_config': {
            "type": "object",
            "properties": {
                "pool_address": {"type": "string"},
                "wallet": {"type": "string"},
                "threads": {"type": "integer", "minimum": 1},
                "cpu_affinity": {"type": "string"},
                "difficulty": {"type": "integer"},
                "mode": {"type": "string", "enum": ["solo", "pool", "hybrid", "ia"]},
                "donation_level": {"type": "integer", "minimum": 0, "maximum": 100},
                "backup_pool": {"type": "string"},
                "ia_enabled": {"type": "boolean"},
                "ia_timeout": {"type": "number", "minimum": 0.1, "maximum": 10.0}
            },
            "required": ["pool_address", "wallet", "threads", "mode"]
        },
        'shared_memory': {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "size": {"type": "integer", "minimum": 1024, "maximum": 1048576},
                "enabled": {"type": "boolean"},
                "polling_interval": {"type": "number", "minimum": 0.001, "maximum": 1.0},
                "timeout": {"type": "number", "minimum": 0.1, "maximum": 10.0},
                "segments": {
                    "type": "object",
                    "properties": {
                        "blob": {"type": "integer", "minimum": 16, "maximum": 256},
                        "target": {"type": "integer", "minimum": 4, "maximum": 32},
                        "seed": {"type": "integer", "minimum": 16, "maximum": 64},
                        "status": {"type": "integer", "minimum": 1, "maximum": 4},
                        "nonce": {"type": "integer", "minimum": 4, "maximum": 8}
                    }
                }
            },
            "required": ["name", "enabled"]
        }
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        # Buscar en múltiples ubicaciones posibles
        possible_dirs = [
            Path(__file__).resolve().parent.parent / 'config',  # src/../config
            Path(os.getcwd()) / 'config',                        # ./config
            Path(os.getcwd()) / 'src' / 'config',                # ./src/config
            Path(os.getcwd()) / 'data',                          # ./data
            Path(os.getcwd()) / 'iazar' / 'data'                 # ./iazar/data
        ]

        for config_dir in possible_dirs:
            if config_dir.exists():
                self.config_dir = config_dir
                logger.info(f"Usando directorio de configuración: {config_dir}")
                break
        else:
            self.config_dir = Path(os.getcwd()) / 'config'
            self.config_dir.mkdir(exist_ok=True)
            logger.warning(f"Creando directorio de configuración: {self.config_dir}")

        # Crear directorio de backups
        (self.config_dir / "backups").mkdir(exist_ok=True)
        
        self._load_encryption_key()
        self._load_all_schemas()

        # Generar configuraciones esenciales si faltan con locking
        for config_name in ['global_config', 'shared_memory', 'ia_config']:
            try:
                self.generate_default_config(config_name)
            except Exception as e:
                logger.error(f"Error generando configuración {config_name}: {str(e)}")

    def _load_encryption_key(self):
        key = os.getenv('CONFIG_ENCRYPTION_KEY')
        if key:
            self._encryption_key = key.encode()
            logger.info("Clave de cifrado de configuración cargada desde entorno")
        else:
            # Generar clave por defecto si no está configurada
            logger.warning("No se encontró clave de cifrado, generando una temporal")
            self._encryption_key = Fernet.generate_key()
            # Guardar en .env para uso futuro
            with open('.env', 'a') as env_file:
                env_file.write(f"\nCONFIG_ENCRYPTION_KEY={self._encryption_key.decode()}")
            logger.info("Clave temporal guardada en .env")

    def _load_all_schemas(self):
        self._schemas = self.BASE_SCHEMAS.copy()
        custom_schemas_path = self.config_dir / 'config_schemas'
        if custom_schemas_path.exists():
            for schema_file in custom_schemas_path.glob('*.json'):
                with open(schema_file) as f:
                    schema_name = schema_file.stem
                    self._schemas[schema_name] = json.load(f)

    def _decrypt_config(self, encrypted_data: bytes) -> Dict:
        if not self._encryption_key:
            raise ValueError("Clave de cifrado no disponible")
        encryptor = AESNonceEncryptor(self._encryption_key)
        return encryptor.decrypt(encrypted_data)

    def _apply_environment_overrides(self, config: Dict, prefix: str) -> Dict:
        for key in config.copy():
            env_key = f"{prefix}_{key.upper()}"
            if env_key in os.environ:
                try:
                    config[key] = json.loads(os.environ[env_key])
                except json.JSONDecodeError:
                    config[key] = os.environ[env_key]
                logger.debug(f"Override aplicado: {env_key} = {config[key]}")

        # Manejo especial para segmentos de memoria compartida
        if prefix == "SHARED_MEMORY" and "SEGMENTS" in os.environ:
            try:
                segments = json.loads(os.environ["SEGMENTS"])
                if "segments" in config:
                    config["segments"].update(segments)
                else:
                    config["segments"] = segments
            except json.JSONDecodeError:
                logger.warning("Formato inválido en variable SEGMENTS")
                
        # Manejo especial para configuración de logging
        if prefix == "GLOBAL_CONFIG" and "LOGGING_LEVEL" in os.environ:
            level = os.environ["LOGGING_LEVEL"].upper()
            if level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                config["logging"]["level"] = level
                logger.debug(f"Override aplicado a LOGGING_LEVEL = {level}")

        return config

    def _validate_config(self, config: Dict, schema_name: str) -> bool:
        schema = self._schemas.get(schema_name)
        if not schema:
            raise ConfigValidationError(f"Esquema {schema_name} no encontrado")
        try:
            jsonschema.validate(instance=config, schema=schema)
            return True
        except jsonschema.ValidationError as ve:
            logger.error(f"Error de validación en {schema_name}: {ve.message}")
            raise ConfigValidationError(f"Configuración inválida: {ve.message}") from ve

    def get_config(self, config_name: str, refresh: bool = False) -> Dict[str, Any]:
        if not refresh and config_name in self._configs:
            return self._configs[config_name]

        config_path = self.config_dir / f"{config_name}.json"
        encrypted_path = self.config_dir / f"{config_name}.enc"

        # Obtener lock para el archivo de configuración
        lock = LockManager.get_lock(config_path if not encrypted_path.exists() else encrypted_path)
        
        try:
            with lock:
                return self._load_config_under_lock(config_name, config_path, encrypted_path)
        except Timeout:
            logger.error(f"Timeout obteniendo lock para {config_name}")
            raise
        except Exception as e:
            logger.error(f"Error cargando {config_name}: {str(e)}")
            raise

    def _load_config_under_lock(self, config_name, config_path, encrypted_path):
        """Carga la configuración bajo protección de lock"""
        if encrypted_path.exists():
            with open(encrypted_path, 'rb') as f:
                config_data = self._decrypt_config(f.read())
        else:
            if not config_path.exists():
                # Generar bajo el mismo lock
                self._generate_default_under_lock(config_name, config_path)
                
            try:
                with open(config_path) as f:
                    config_data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error de sintaxis en {config_path}: {e}")
                # Crear respaldo del archivo corrupto con lock
                self._backup_corrupt_file(config_path)
                # Regenerar configuración bajo el mismo lock
                self._generate_default_under_lock(config_name, config_path)
                # Recargar configuración
                return self.get_config(config_name, refresh=True)

        self._validate_config(config_data, config_name)
        config_data = self._apply_environment_overrides(config_data, config_name.upper())
        self._configs[config_name] = config_data
        logger.info(f"Configuración {config_name} cargada y validada")
        return config_data

    def _backup_corrupt_file(self, file_path: Path):
        """Crea un backup de un archivo corrupto con timestamp"""
        backup_dir = self.config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{file_path.stem}_corrupt_{timestamp}{file_path.suffix}"
        
        try:
            file_path.rename(backup_path)
            logger.warning(f"Archivo corrupto movido a: {backup_path}")
        except Exception as e:
            logger.error(f"No se pudo crear backup: {str(e)}")

    def _generate_default_under_lock(self, config_name: str, config_path: Path):
        """Genera configuración por defecto bajo protección de lock"""
        try:
            default_configs = {
                'global_config': {
                    "shm": {
                        "name": "zar_shared_mem",
                        "size": 4096
                    },
                    "stratum": {
                        "pool_host": "pool.hashvault.pro",
                        "pool_port": 443
                    },
                    "logging": {
                        "level": "INFO",
                        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                    }
                },
                'ia_config': {
                    'data_paths': {
                        'successful_nonces': 'src/iazar/data/nonces_exitosos.csv',
                        'nonce_hashes': 'src/iazar/data/nonce_hashes.bin',
                        'injected_nonces': 'src/iazar/logs/injected.csv',
                        'nonce_training_data_path': 'src/iazar/data/nonce_training_data.csv'
                    },
                    'processing_params': {
                        'temporal_window': 60,
                        'entropy_window': 100,
                        'candidate_count': 10000,
                        'top_candidates': 300,
                        'polling_interval': 0.01
                    },
                    'shared_memory': {
                        'name': 'zartrux_shared',
                        'enabled': True
                    }
                },
                'hub_config': {
                    'hub_endpoint': 'tcp://hub.zartrux.mining:5555',
                    'sync_interval': 30,
                    'max_nodes': 100,
                    'shm_sync': False
                },
                'miner_config': {
                    'pool_address': 'pool.hashvault.pro:443',
                    'wallet': 
                    '44crWF5Y7gWDLCwhNSH7cbAbCPT6xScpCRFMMYhbCpFijJVUpPwze39GbvRRR1GsRZCvNMKZpU4sPT8bqRY3FY29Loyx1zc',
                    'threads': os.cpu_count() or 4,  # Valor por defecto si no se detectan cores
                    'mode': 'hybrid',
                    'ia_enabled': True,
                    'ia_timeout': 0.5
                },
                'shared_memory': {
                    'name': 'zartrux_shared',
                    'enabled': True,
                    'size': 4096,
                    'polling_interval': 0.001,
                    'timeout': 1.0,
                    'segments': {
                        'blob': 152,
                        'target': 8,
                        'seed': 32,
                        'status': 1,
                        'nonce': 4
                    }
                }
            }
            
            default_config = default_configs.get(config_name, {})
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Configuración por defecto generada para {config_name} en {config_path}")
            
            # Crear backup automático
            self._create_config_backup(config_path)
        except Exception as e:
            logger.error(f"Error generando configuración {config_name}: {str(e)}")
            raise

    def _create_config_backup(self, config_path: Path):
        """Crea un backup de la configuración con timestamp"""
        backup_dir = self.config_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{config_path.stem}_{timestamp}{config_path.suffix}"
        
        try:
            with open(config_path, 'r') as src, open(backup_path, 'w') as dst:
                dst.write(src.read())
            logger.info(f"Backup de configuración creado: {backup_path}")
        except Exception as e:
            logger.error(f"Error creando backup: {str(e)}")

    def generate_default_config(self, config_name: str):
        """Versión pública con locking para generar configuración"""
        config_path = self.config_dir / f"{config_name}.json"
        lock = LockManager.get_lock(config_path)
        
        try:
            with lock:
                self._generate_default_under_lock(config_name, config_path)
        except Timeout:
            logger.error(f"Timeout generando configuración {config_name}")

    def update_remote_config(self, config_name: str, new_config: Dict):
        """Sincronización remota de configuraciones (implementación futura)"""
        # TODO: Implementar sincronización con servidor central
        logger.warning("Sincronización remota no implementada aún")

    def config_hash(self, config_name: str) -> str:
        """Genera hash SHA256 de la configuración para verificar integridad"""
        config = self.get_config(config_name)
        config_str = json.dumps(config, sort_keys=True).encode()
        return hashlib.sha256(config_str).hexdigest()

    def get_shm_config(self) -> Dict[str, Any]:
        """Obtiene configuración específica de memoria compartida"""
        return self.get_config('shared_memory')

    def get_ia_params(self) -> Dict[str, Any]:
        """Obtiene parámetros específicos de IA"""
        ia_config = self.get_config('ia_config')
        return ia_config.get('processing_params', {})

    def get_shm_segment_size(self, segment_name: str) -> int:
        """Obtiene el tamaño configurado para un segmento específico"""
        shm_config = self.get_shm_config()
        segments = shm_config.get('segments', {})
        return segments.get(segment_name, 0)

    def get_config_value(self, section: str, key: str, default=None) -> Any:
        """Obtiene un valor de configuración con soporte para rutas anidadas"""
        try:
            config = self.get_config(section)
            # Soporte para claves anidadas
            keys = key.split('.')
            value = config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except Exception as e:
            logger.debug(f"Error obteniendo {section}.{key}: {str(e)}")
            return default

    # ===== MÉTODOS PARA GLOBAL CONFIG =====
    def get_logging_config(self) -> Dict[str, Any]:
        """Obtiene configuración específica de logging"""
        global_config = self.get_config('global_config')
        return global_config.get('logging', {})

    def get_stratum_config(self) -> Dict[str, Any]:
        """Obtiene configuración específica de stratum"""
        global_config = self.get_config('global_config')
        return global_config.get('stratum', {})

    def get_shm_global_config(self) -> Dict[str, Any]:
        """Obtiene configuración global de memoria compartida"""
        global_config = self.get_config('global_config')
        return global_config.get('shm', {})

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

def initialize_system_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Alias para inicializar/obtener configuración del sistema"""
    return ConfigManager().get_config('global_config')  



"""
Módulo avanzado de gestión de configuración para Zartrux-Miner
Incluye validación de esquemas, cifrado, sobreescritura por variables de entorno y sincronización remota
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
import jsonschema
from cryptography.fernet import Fernet

# Import absoluto (universal, NO relativo)
from iazar.security.AESNonceEncryptor import AESNonceEncryptor

load_dotenv()
logger = logging.getLogger('ZartruxConfigManager')

class ConfigValidationError(Exception):
    """Excepción personalizada para errores de validación de configuración"""
    pass

class ConfigManager:
    _instance = None
    _configs: Dict[str, Dict[str, Any]] = {}
    _schemas: Dict[str, Dict[str, Any]] = {}
    _encryption_key: Optional[bytes] = None

    # Esquemas base para validación
    BASE_SCHEMAS = {
        'ia_config': {
            "type": "object",
            "properties": {
                "data_paths": {
                    "type": "object",
                    "properties": {
                        "successful_nonces": {"type": "string"},
                        "nonce_hashes": {"type": "string"},
                        "injected_nonces": {"type": "string"}
                    },
                    "required": ["successful_nonces", "nonce_hashes"]
                },
                "processing_params": {
                    "type": "object",
                    "properties": {
                        "temporal_window": {"type": "number", "minimum": 1},
                        "entropy_window": {"type": "number", "minimum": 10}
                    },
                    "required": ["temporal_window"]
                }
            },
            "required": ["data_paths", "processing_params"]
        },
        'hub_config': {
            "type": "object",
            "properties": {
                "hub_endpoint": {"type": "string"},
                "sync_interval": {"type": "number", "minimum": 5},
                "max_nodes": {"type": "number", "minimum": 1}
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
                "backup_pool": {"type": "string"}
            },
            "required": ["pool_address", "wallet", "threads", "mode"]
        }
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        # Carpeta config universal
        src_dir = Path(__file__).resolve().parent.parent
        config_dir = src_dir / 'config'
        if not config_dir.exists():
            config_dir = Path(os.getcwd()) / 'config'
        self.config_dir = config_dir
        self._load_encryption_key()
        self._load_all_schemas()

    def _load_encryption_key(self):
        key = os.getenv('CONFIG_ENCRYPTION_KEY')
        if key:
            self._encryption_key = key.encode()
            logger.info("Clave de cifrado de configuración cargada desde entorno")

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

        try:
            if encrypted_path.exists():
                with open(encrypted_path, 'rb') as f:
                    config_data = self._decrypt_config(f.read())
            else:
                with open(config_path) as f:
                    config_data = json.load(f)

            self._validate_config(config_data, config_name)
            config_data = self._apply_environment_overrides(config_data, config_name.upper())
            
            self._configs[config_name] = config_data
            logger.info(f"Configuración {config_name} cargada y validada")
            return config_data

        except FileNotFoundError:
            logger.error(f"Archivo de configuración {config_name} no encontrado")
            raise
        except Exception as e:
            logger.error(f"Error cargando {config_name}: {str(e)}")
            raise

    def generate_default_config(self, config_name: str):
        default_configs = {
            'ia_config': {
                'data_paths': {
                    'successful_nonces': 'data/nonces_exitosos.csv',
                    'nonce_hashes': 'data/nonce_hashes.bin',
                    'injected_nonces': 'logs/inyectados.log'
                },
                'processing_params': {
                    'temporal_window': 60,
                    'entropy_window': 100
                }
            },
            'hub_config': {
                'hub_endpoint': 'tcp://hub.zartrux.mining:5555',
                'sync_interval': 30,
                'max_nodes': 100
            }
        }
        config_path = self.config_dir / f"{config_name}.json"
        if not config_path.exists():
            default_config = default_configs.get(config_name, {})
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Configuración por defecto generada para {config_name}")

    def update_remote_config(self, config_name: str, new_config: Dict):
        pass  # Implementar si se desea sincronización remota

    def config_hash(self, config_name: str) -> str:
        config = self.get_config(config_name)
        config_str = json.dumps(config, sort_keys=True).encode()
        return hashlib.sha256(config_str).hexdigest()

# ==== ALIAS COMPATIBLES PARA IMPORTS ====
def get_ia_config() -> Dict[str, Any]:
    return ConfigManager().get_config('ia_config')

def get_hub_config() -> Dict[str, Any]:
    return ConfigManager().get_config('hub_config')

def get_miner_config() -> Dict[str, Any]:
    return ConfigManager().get_config('miner_config')

def get_config(config_name: str) -> Dict[str, Any]:
    """Alias genérico compatible con los módulos que hacen import get_config"""
    return ConfigManager().get_config(config_name)

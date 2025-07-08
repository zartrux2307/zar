import os
import json
import logging
import logging.handlers  # Added missing import
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from filelock import FileLock, Timeout
import pandas as pd
import hashlib
import time  # Added for time operations

from iazar.utils.feature_utils import COLUMNS

# --- CONFIGURACIÓN MEJORADA ---
DATA_DIR = Path("src/iazar/data")
NONCES_JSON = DATA_DIR / "nonces_ready.json"
INJECTION_LOG = DATA_DIR / "inyectados.log"
NONCES_CSV = DATA_DIR / "nonces_exitosos.csv"
LOCK_FILE = DATA_DIR / "nonces_injector.lock"
BACKUP_DIR = DATA_DIR / "backups"

# Configuración de bloqueo
LOCK_TIMEOUT = 30  # Segundos
MAX_RETRIES = 3
RETRY_DELAY = 2  # Segundos

# --- LOGGING PROFESIONAL ---
def setup_logging():
    """Configura logging avanzado con rotación y niveles diferenciados"""
    logger = logging.getLogger("NonceInjector")
    logger.setLevel(logging.DEBUG)
    
    # Formato estándar
    log_format = logging.Formatter(
        '[%(asctime)s][%(levelname)8s][%(module)15s:%(lineno)3d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para archivo (con rotación)
    file_handler = logging.handlers.RotatingFileHandler(  # Fixed with correct import
        str(INJECTION_LOG),
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

def ensure_directories():
    """Crea los directorios necesarios si no existen"""
    for directory in [DATA_DIR, BACKUP_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    logger.debug("Directorios de datos verificados")

def create_backup(file_path: Path):
    """Crea un backup con timestamp del archivo"""
    if not file_path.exists():
        return
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = BACKUP_DIR / backup_name
    
    try:
        with open(file_path, 'rb') as src, open(backup_path, 'wb') as dst:
            dst.write(src.read())
        logger.info(f"Backup creado: {backup_path}")
    except Exception as e:
        logger.error(f"Error al crear backup: {e}")

def safe_read_json(file_path: Path) -> List[Dict]:
    """Lee un archivo JSON con manejo robusto de errores"""
    try:
        if not file_path.exists():
            logger.warning(f"Archivo JSON no encontrado: {file_path}")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            logger.error(f"Formato JSON inválido: Se esperaba lista, se obtuvo {type(data)}")
            return []
            
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Error de decodificación JSON: {e}")
    except Exception as e:
        logger.error(f"Error inesperado al leer JSON: {e}")
    
    return []

def validate_nonce_dict(nonce_dict: Dict) -> bool:
    """Valida exhaustivamente un diccionario de nonce"""
    # Verificar presencia de todas las columnas requeridas
    if not all(col in nonce_dict for col in COLUMNS):
        missing = [col for col in COLUMNS if col not in nonce_dict]
        logger.warning(f"Campos faltantes: {missing}")
        return False
    
    # Validar tipo de nonce
    if not isinstance(nonce_dict.get('nonce'), int):
        logger.warning("Nonce debe ser entero")
        return False
    
    # Validar rango de nonce (0 a 2^32-1)
    nonce = nonce_dict['nonce']
    if nonce < 0 or nonce > 4294967295:
        logger.warning(f"Nonce fuera de rango: {nonce}")
        return False
    
    # Validación adicional de tipos
    for col, value in nonce_dict.items():
        if col.startswith('feature_') and not isinstance(value, (int, float)):
            logger.warning(f"Tipo inválido para {col}: {type(value)}")
            return False
    
    return True

def calculate_dict_hash(nonce_dict: Dict) -> str:
    """Calcula hash MD5 de un diccionario para detección de cambios"""
    return hashlib.md5(json.dumps(nonce_dict, sort_keys=True).encode('utf-8')).hexdigest()

def guardar_nonces_csv(df: pd.DataFrame, csv_path: Path):
    """Guarda un DataFrame en un archivo CSV con configuraciones óptimas"""
    try:
        # Guardar en archivo temporal primero
        temp_path = csv_path.with_suffix('.tmp')
        df.to_csv(temp_path, index=False)
        
        # Reemplazar el archivo original de forma atómica
        os.replace(temp_path, csv_path)
        logger.info(f"Datos guardados en {csv_path}")
    except Exception as e:
        logger.error(f"Error al guardar CSV: {e}")
        # Intentar eliminar el temporal si existe
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass

def inject_nonces(nonces: List[Dict], csv_path: Path):
    """Proceso principal de inyección con optimización de memoria"""
    if not nonces:
        logger.warning("No hay nonces para inyectar.")
        return
    
    # Filtrar y validar nonces
    valid_nonces = []
    seen_hashes = set()
    
    for nonce_dict in nonces:
        if not validate_nonce_dict(nonce_dict):
            continue
            
        # Detectar duplicados usando hash del contenido
        nonce_hash = calculate_dict_hash(nonce_dict)
        if nonce_hash in seen_hashes:
            logger.debug(f"Duplicado detectado: nonce {nonce_dict['nonce']}")
            continue
            
        seen_hashes.add(nonce_hash)
        valid_nonces.append(nonce_dict)
    
    if not valid_nonces:
        logger.error("Ningún nonce válido después de la validación")
        return
    
    logger.info(f"{len(valid_nonces)} nonces válidos para inyectar")

    try:
        # Cargar datos existentes con chunks si el archivo es grande
        existing_df = pd.DataFrame()
        if csv_path.exists():
            # Estimación de tamaño para uso de chunks
            file_size = csv_path.stat().st_size
            use_chunks = file_size > 10 * 1024 * 1024  # >10MB
            
            if use_chunks:
                logger.info("Usando carga por chunks para archivo grande")
                chunks = []
                for chunk in pd.read_csv(csv_path, chunksize=10000):
                    chunks.append(chunk)
                existing_df = pd.concat(chunks, ignore_index=True)
            else:
                existing_df = pd.read_csv(csv_path)
    
        # Combinar con nuevos datos
        new_df = pd.DataFrame(valid_nonces, columns=COLUMNS)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        # Eliminar duplicados manteniendo la última aparición
        pre_dedup_count = len(combined_df)
        combined_df.drop_duplicates(subset=["nonce"], keep='last', inplace=True)
        dup_count = pre_dedup_count - len(combined_df)
        
        if dup_count > 0:
            logger.info(f"Eliminados {dup_count} duplicados")
        
        # Guardar el archivo CSV
        guardar_nonces_csv(combined_df, csv_path)
        logger.info(f"CSV actualizado con éxito. Total registros: {len(combined_df)}")
        
        # Registrar en log individual
        for nonce in valid_nonces:
            logger.info(f"[NONCE_INJECTED] {nonce}")
        
    except Exception as e:
        logger.error(f"Error crítico durante la inyección: {e}")
        raise

def main():
    ensure_directories()
    logger.info("=== Inicio de inyección de nonces ===")
    
    # Bloqueo con reintentos
    for attempt in range(MAX_RETRIES):
        try:
            with FileLock(str(LOCK_FILE), timeout=LOCK_TIMEOUT):
                logger.info("Bloqueo adquirido")
                
                # Crear backup preventivo
                if NONCES_CSV.exists():
                    create_backup(NONCES_CSV)
                
                # Leer y procesar nonces
                nonces = safe_read_json(NONCES_JSON)
                if nonces:
                    inject_nonces(nonces, NONCES_CSV)
                    
                    # Limpiar archivo JSON después de procesar
                    try:
                        NONCES_JSON.unlink()
                        logger.info("Archivo JSON de nonces eliminado")
                    except Exception as e:
                        logger.error(f"Error al eliminar JSON: {e}")
                else:
                    logger.warning("No se encontraron nonces válidos para inyectar")
                
                return  # Salir después de éxito
                
        except Timeout:
            logger.warning(f"Intento {attempt+1}: Bloqueo ocupado, reintentando...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.critical(f"Error fatal: {e}")
            break
    
    logger.error("No se pudo adquirir el bloqueo después de múltiples intentos")

if __name__ == "__main__":
    start_time = time.time()
    
    try:
        main()
    except Exception as e:
        logger.exception("Error no manejado en el proceso principal")
    finally:
        duration = time.time() - start_time
        logger.info(f"Proceso completado en {duration:.2f} segundos")
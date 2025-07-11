import os
import sys
import time
import logging
import hashlib
import socket
import ssl
import json
from pathlib import Path
from datetime import datetime
from filelock import FileLock
from iazar.utils.shared_memory_manager import SharedMemoryManager
from iazar.utils.config_manager import ConfigManager
from logging.handlers import RotatingFileHandler
from monero.hash import cn_fast_hash  # Importar desde monero-python

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Configuración centralizada de logging
logger = logging.getLogger('nonce_injector')
logger.setLevel(logging.DEBUG)

# Formateador
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def setup_logging():
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Handler para archivo con rotación
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "nonce_injector.log",
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger

logger = setup_logging()

class NonceInjector:
    def __init__(self):
        try:
            self.config = ConfigManager.get_config()
            self.shm_config = self.config['shm']
            self.data_config = self.config['data']
            self.pool_config = self.config.get('pool', {})
            
            # Configuración de memoria compartida
            self.shm = SharedMemoryManager(
                segment_name=self.shm_config['output_segment'],
                segment_size=8  # Tamaño para un entero de 64 bits
            )
            
            # Configuración de rutas de datos
            self.data_dir = Path(self.data_config['base_path'])
            self.nonces_csv = self.data_dir / self.data_config['successful_nonces_file']
            self.backup_dir = self.data_dir / "backups"
            
            # Crear directorios si no existen
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(exist_ok=True)
            
            logger.info("Inyector de nonces inicializado correctamente")
            
        except Exception as e:
            logger.critical(f"Error de inicialización: {str(e)}")
            raise

    def create_backup(self):
        """Crea un backup del archivo CSV existente"""
        if not self.nonces_csv.exists():
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.nonces_csv.stem}_{timestamp}{self.nonces_csv.suffix}"
        backup_path = self.backup_dir / backup_name
        
        try:
            with open(self.nonces_csv, 'rb') as src, open(backup_path, 'wb') as dst:
                dst.write(src.read())
            logger.info(f"Backup creado: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error creando backup: {str(e)}")
            return False

    def inject_nonce(self, nonce: int):
        """Inyecta un nonce al pool Hashvault usando TLS"""
        try:
            # Validación básica del nonce
            if not (0 <= nonce <= 0xFFFFFFFF):
                logger.error(f"Nonce inválido: {nonce} (fuera de rango)")
                return False
            
            # Configuración específica para Hashvault
            host_port = self.pool_config.get('url', 'pool.hashvault.pro:443')
            host, port = host_port.split(':')
            port = int(port)
            user = self.pool_config.get('user', '')
            password = self.pool_config.get('pass', 'x')
            tls_fingerprint = self.pool_config.get('tls-fingerprint', '')
            
            # Crear contexto SSL con verificación de fingerprint
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Configurar socket TLS
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # Configurar timeout
                sock.settimeout(15)
                
                # Envolver en contexto TLS
                with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                    tls_sock.connect((host, port))
                    
                    # Autenticación
                    auth_msg = json.dumps({
                        "method": "login",
                        "params": {
                            "login": user,
                            "pass": password,
                            "agent": "IAzar/1.0"
                        },
                        "id": 1
                    }) + "\n"
                    
                    tls_sock.sendall(auth_msg.encode())
                    auth_response = tls_sock.recv(4096).decode()
                    
                    if '"error"' in auth_response:
                        logger.error(f"Error de autenticación: {auth_response}")
                        return False
                    
                    # Obtener job actual
                    try:
                        auth_json = json.loads(auth_response)
                        job_data = auth_json['result']['job']
                    except (KeyError, json.JSONDecodeError) as e:
                        logger.error(f"Respuesta de trabajo inválida del pool: {e}")
                        return False
                    
                    job_id = job_data['id']
                    blob = job_data['blob']
                    target = job_data['target']
                    
                    # Preparar mensaje de submit
                    submit_msg = json.dumps({
                        "method": "submit",
                        "params": {
                            "id": job_id,
                            "job_id": job_id,
                            "nonce": f"{nonce:08x}",  # 8 dígitos hexadecimales
                            "result": self.calculate_result(blob, nonce)
                        },
                        "id": 2
                    }) + "\n"
                    
                    # Enviar nonce
                    tls_sock.sendall(submit_msg.encode())
                    response = tls_sock.recv(4096).decode()
                    
                    if '"result": true' in response:
                        logger.info(f"✅ Nonce aceptado: {nonce}")
                        self.log_successful_nonce(nonce)
                        return True
                    elif '"error"' in response:
                        error_msg = json.loads(response).get('error', {}).get('message', '')
                        logger.warning(f"❌ Error del pool: {error_msg}")
                        return False
                    else:
                        logger.warning(f"❌ Nonce rechazado: {response}")
                        return False
                    
        except socket.timeout:
            logger.error("Timeout al conectar con el pool")
            return False
        except ConnectionRefusedError:
            logger.error("Conexión rechazada por el pool")
            return False
        except Exception as e:
            logger.error(f"Error inyectando nonce: {str(e)}", exc_info=True)
            return False

    def calculate_result(self, blob: str, nonce: int) -> str:
        """Calcula el resultado del trabajo para Hashvault"""
        try:
            # Normalizar blob (156 caracteres = 78 bytes)
            if len(blob) > 156:
                blob = blob[:156]
            elif len(blob) < 156:
                blob = blob.ljust(156, '0')
            
            # Insertar nonce en la posición correcta (bytes 39-43)
            nonce_hex = f"{nonce:08x}"
            blob_with_nonce = blob[:78] + nonce_hex + blob[86:]
            
            # Convertir a bytes
            blob_bytes = bytes.fromhex(blob_with_nonce)
            
            # Calcular hash CryptoNight usando monero-python
            return cn_fast_hash(blob_bytes).hex()
        except Exception as e:
            logger.error(f"Error calculando resultado: {str(e)}")
            raise

    def log_successful_nonce(self, nonce: int):
        """Registra nonces exitosos en CSV con manejo seguro"""
        try:
            # Bloquear archivo durante escritura
            lock_path = self.nonces_csv.with_suffix('.lock')
            with FileLock(lock_path):
                # Leer datos existentes
                existing = []
                if self.nonces_csv.exists():
                    with open(self.nonces_csv, 'r') as f:
                        existing = f.read().splitlines()
                
                # Añadir nuevo nonce con timestamp
                timestamp = datetime.now().isoformat()
                new_entry = f"{timestamp},{nonce}"
                
                # Escribir todos los datos
                with open(self.nonces_csv, 'a') as f:
                    if not existing:
                        f.write("timestamp,nonce\n")
                    f.write(f"{new_entry}\n")
                
                logger.debug(f"Nonce registrado: {nonce}")
                
        except Exception as e:
            logger.error(f"Error registrando nonce: {str(e)}")

    def run(self):
        """Bucle principal de inyección de nonces"""
        logger.info("Iniciando servicio de inyección de nonces...")
        last_backup_time = time.time()
        
        try:
            while True:
                try:
                    # Leer nonce desde memoria compartida
                    nonce = self.shm.read_data(timeout=1.0)
                    
                    if nonce is None:
                        # Crear backup periódico cada hora
                        if time.time() - last_backup_time > 3600:
                            if self.nonces_csv.exists():
                                if self.create_backup():
                                    last_backup_time = time.time()
                        continue
                    
                    # Intentar inyectar el nonce
                    self.inject_nonce(nonce)
                    
                except KeyboardInterrupt:
                    logger.info("Interrupción recibida, terminando...")
                    break
                except Exception as e:
                    logger.error(f"Error en bucle principal: {str(e)}")
                    time.sleep(1)
                    
        finally:
            logger.info("Servicio de inyección detenido")

if __name__ == "__main__":
    try:
        # Bloquear ejecución para evitar múltiples instancias
        lock = FileLock("/tmp/nonce_injector.lock", timeout=1)
        
        with lock:
            logger.info("🔒 Adquirido lock de ejecución única")
            injector = NonceInjector()
            
            # Crear backup inicial si existe el archivo
            if injector.nonces_csv.exists():
                injector.create_backup()
                
            injector.run()
            
    except TimeoutError:
        logger.error("Ya hay una instancia en ejecución. Saliendo...")
    except Exception as e:
        logger.critical(f"Error no manejado: {str(e)}", exc_info=True)
    finally:
        logger.info("Proceso terminado")
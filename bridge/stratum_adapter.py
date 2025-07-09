import socket
import ssl
import json
import threading
import time
import logging
import os
from datetime import datetime
from iazar.utils.hex_validator import is_valid_hex
from iazar.utils.config_manager import ConfigManager

# Configuración avanzada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("stratum_adapter.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StratumAdapter")

class StratumClient:
    def __init__(self, pools, config=None):
        self.pools = pools
        self.config = config or ConfigManager().get_config('ia_config')
        self.current_pool_index = 0
        self.socket = None
        self.ssl_context = None
        self.session_id = None
        self.worker_name = None
        self.current_job = None
        self.lock = threading.Lock()
        self.running = False
        self.reconnect_thread = None
        self.last_connection_time = 0
        self.connection_timeout = 30
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0
        self.cert_dir = os.path.join(
            self.config.get('paths', {}).get('cert_dir', 'certs')
        )
        os.makedirs(self.cert_dir, exist_ok=True)
        
        self._init_ssl_context()

    def _init_ssl_context(self):
        """Inicializa contexto SSL con validación robusta de certificados"""
        try:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            self.ssl_context.check_hostname = True
            self.ssl_context.verify_mode = ssl.CERT_REQUIRED
            
            # Cargar certificados del sistema
            self.ssl_context.load_default_certs()
            
            # Cargar certificados personalizados si existen
            custom_ca_path = os.path.join(self.cert_dir, 'custom_ca_bundle.pem')
            if os.path.exists(custom_ca_path):
                self.ssl_context.load_verify_locations(custom_ca_path)
                logger.info(f"Certificados personalizados cargados desde: {custom_ca_path}")
        except Exception as e:
            logger.exception(f"Error inicializando contexto SSL: {str(e)}")
            self.ssl_context = None

    def connect(self):
        """Establece conexión segura con el pool"""
        pool = self.pools[self.current_pool_index]
        host = pool['host']
        port = pool['port']
        use_tls = pool.get('tls', False)
        
        try:
            # Crear conexión base
            base_socket = socket.create_connection(
                (host, port), timeout=self.connection_timeout)
            
            if use_tls:
                if not self.ssl_context:
                    raise RuntimeError("Contexto SSL no disponible para conexión TLS")
                
                # Envolver en TLS con validación de certificado
                self.socket = self.ssl_context.wrap_socket(
                    base_socket,
                    server_hostname=host
                )
                
                # Verificación adicional del certificado
                cert = self.socket.getpeercert()
                self._validate_certificate(cert, host)
                logger.info(f"Conexión TLS segura establecida con {host}:{port}")
            else:
                self.socket = base_socket
                logger.info(f"Conexión no cifrada establecida con {host}:{port}")
            
            self.running = True
            self.last_connection_time = time.time()
            self.reconnect_attempts = 0
            
            # Iniciar hilo de monitorización
            self.reconnect_thread = threading.Thread(target=self.monitor_connection)
            self.reconnect_thread.daemon = True
            self.reconnect_thread.start()
            
            # Autenticación inicial
            self.subscribe(pool['wallet'])
            return True
            
        except Exception as e:
            logger.exception(f"Error de conexión con {host}:{port}: {str(e)}")
            self._handle_connection_error()
            return False

    def _validate_certificate(self, cert, host):
        """Validación avanzada del certificado del servidor"""
        if not cert:
            raise ssl.SSLError("El servidor no proporcionó certificado")
        
        # Verificar fecha de expiración
        not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
        if datetime.now() > not_after:
            raise ssl.SSLError(f"Certificado expirado: {not_after}")
        
        # Verificar nombres alternativos
        san = cert.get('subjectAltName', [])
        dns_names = [name[1] for name in san if name[0] == 'DNS']
        
        if host not in dns_names:
            raise ssl.SSLError(f"Nombre de host {host} no coincide con certificado")
        
        logger.info(f"Certificado válido para: {', '.join(dns_names)}")

    def disconnect(self):
        """Cierra la conexión de manera segura"""
        self.running = False
        try:
            if self.socket:
                # Enviar mensaje de cierre cortés
                try:
                    self.socket.sendall(b'{"id": 999, "method": "mining.close"}\n')
                except:
                    pass
                
                # Cerrar conexión
                self.socket.close()
                self.socket = None
                logger.info("Conexión cerrada correctamente")
        except Exception as e:
            logger.warning(f"Error al cerrar conexión: {str(e)}")
        
        if self.reconnect_thread:
            self.reconnect_thread.join(timeout=5)

    def monitor_connection(self):
        """Monitoriza la conexión y maneja reconexiones automáticas"""
        buffer = b''
        
        while self.running:
            try:
                # Verificar timeout
                if time.time() - self.last_connection_time > self.connection_timeout * 2:
                    raise socket.timeout("Timeout de inactividad excedido")
                
                # Recibir datos
                data = self.socket.recv(4096)
                if not data:
                    raise ConnectionError("Conexión cerrada por el servidor")
                
                self.last_connection_time = time.time()
                buffer += data
                
                # Procesar mensajes completos
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        self.handle_message(line)
                
            except (socket.timeout, ConnectionError) as e:
                logger.warning(f"Error de conexión: {str(e)}")
                self.reconnect()
            except Exception as e:
                logger.exception(f"Error inesperado en monitor_connection: {str(e)}")
                self.reconnect()

    def reconnect(self):
        """Maneja la reconexión con backoff exponencial"""
        if not self.running:
            return
            
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.error("Máximo de intentos de reconexión alcanzado. Abortando.")
            self.running = False
            return
            
        # Calcular retraso exponencial
        delay = min(self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)), 300)
        logger.info(f"Reconectando en {delay} segundos (intento {self.reconnect_attempts}/{self.max_reconnect_attempts})")
        
        time.sleep(delay)
        
        # Rotar al siguiente pool
        self.current_pool_index = (self.current_pool_index + 1) % len(self.pools)
        
        try:
            self.disconnect()
            self.connect()
        except Exception as e:
            logger.error(f"Error en reconexión: {str(e)}")

    def subscribe(self, wallet_address):
        """Envía solicitud de suscripción al pool"""
        message = {
            "id": 1,
            "method": "mining.subscribe",
            "params": ["ZarMiner/2.0.0"]
        }
        self._send_message(message)
        response = self._receive_response()
        if response and 'result' in response:
            self.session_id = response['result'][0]
            self.worker_name = wallet_address
            self.authorize(wallet_address)

    def authorize(self, wallet_address):
        """Autentica al minero en el pool"""
        message = {
            "id": 2,
            "method": "mining.authorize",
            "params": [wallet_address, "x"]
        }
        self._send_message(message)
        self._receive_response()

    def handle_message(self, data):
        """Procesa un mensaje recibido"""
        try:
            message = json.loads(data.decode().strip())
            self.process_message(message)
        except json.JSONDecodeError:
            logger.warning(f"Mensaje JSON inválido recibido: {data.decode()}")
        except Exception as e:
            logger.exception(f"Error procesando mensaje: {str(e)}")

    def process_message(self, message):
        """Distribuye mensajes según su tipo"""
        try:
            method = message.get('method')
            if method == 'mining.notify':
                self.handle_job(message['params'])
            elif method == 'mining.set_difficulty':
                self.handle_difficulty(message['params'][0])
            elif method == 'mining.set_version_mask':
                self.handle_version_mask(message['params'][0])
            elif message.get('result') is not None:
                self.handle_result(message)
            elif message.get('error') is not None:
                self.handle_error(message)
        except KeyError as e:
            logger.warning(f"Falta clave en mensaje: {e}")
        except Exception as e:
            logger.exception(f"Error en process_message: {str(e)}")

    def handle_job(self, params):
        """Actualiza el trabajo actual"""
        with self.lock:
            try:
                self.current_job = {
                    'id': params[0],
                    'prev_hash': params[1],
                    'coinb1': params[2],
                    'coinb2': params[3],
                    'extra_nonce': params[4],
                    'version': params[5],
                    'nbits': params[6],
                    'ntime': params[7],
                    'clean_jobs': params[8],
                    'target': int(params[9], 16) if len(params) > 9 else None
                }
                logger.info(f"Nuevo trabajo recibido: ID={self.current_job['id']}")
            except (IndexError, ValueError) as e:
                logger.error(f"Parámetros de trabajo inválidos: {e}")

    def handle_difficulty(self, difficulty):
        """Actualiza la dificultad actual"""
        with self.lock:
            if self.current_job:
                self.current_job['difficulty'] = difficulty
                logger.info(f"Dificultad actualizada: {difficulty}")

    def handle_version_mask(self, version_mask):
        """Actualiza la máscara de versión"""
        with self.lock:
            if self.current_job:
                self.current_job['version_mask'] = version_mask
                logger.info(f"Máscara de versión actualizada: {version_mask}")

    def handle_result(self, message):
        """Procesa resultados exitosos"""
        logger.info(f"Respuesta exitosa del servidor: {message.get('result')}")

    def handle_error(self, message):
        """Procesa mensajes de error"""
        error = message.get('error')
        logger.error(f"Error del servidor: {error}")

    def get_current_job(self):
        """Obtiene el trabajo actual de manera segura"""
        with self.lock:
            return self.current_job.copy() if self.current_job else None

    def submit_share(self, job_id, nonce, hash_result):
        """Envía una solución al pool con validación robusta"""
        if not is_valid_hex(nonce) or not is_valid_hex(hash_result):
            logger.error(f"Nonce o hash inválido: nonce={nonce}, hash={hash_result}")
            return False
        
        if not self.socket or not self.running:
            logger.warning("Intento de envío sin conexión activa")
            return False
        
        message = {
            "id": 3,
            "method": "mining.submit",
            "params": [
                self.worker_name,
                job_id,
                nonce,
                hash_result
            ]
        }
        
        try:
            self._send_message(message)
            response = self._receive_response(timeout=10)
            
            if response and response.get('result'):
                logger.info("Share aceptada por el pool")
                return True
            else:
                error = response.get('error', 'Respuesta inválida') if response else 'Sin respuesta'
                logger.warning(f"Share rechazada: {error}")
                return False
        except Exception as e:
            logger.exception(f"Error enviando share: {str(e)}")
            return False

    def _send_message(self, message):
        """Envía un mensaje de manera segura"""
        if not self.socket:
            raise ConnectionError("Socket no disponible para enviar")
        
        try:
            payload = json.dumps(message) + '\n'
            self.socket.sendall(payload.encode())
            logger.debug(f"Mensaje enviado: {message}")
        except (BrokenPipeError, ConnectionResetError):
            logger.warning("Conexión perdida durante envío")
            self.reconnect()
            raise
        except Exception as e:
            logger.exception(f"Error enviando mensaje: {str(e)}")
            raise

    def _receive_response(self, timeout=5):
        """Recibe una respuesta con timeout controlado"""
        if not self.socket:
            return None
        
        original_timeout = self.socket.gettimeout()
        self.socket.settimeout(timeout)
        
        try:
            data = self.socket.recv(4096)
            if data:
                response = json.loads(data.decode().strip())
                logger.debug(f"Respuesta recibida: {response}")
                return response
        except socket.timeout:
            logger.warning(f"Timeout esperando respuesta ({timeout}s)")
        except json.JSONDecodeError:
            logger.warning(f"Respuesta JSON inválida: {data.decode()}")
        except Exception as e:
            logger.exception(f"Error recibiendo respuesta: {str(e)}")
        finally:
            self.socket.settimeout(original_timeout)
        
        return None
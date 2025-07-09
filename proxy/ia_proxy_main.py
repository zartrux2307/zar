import sys
import os
import ssl
import json
import time
import socket
import logging
import threading
import traceback
import random
import hashlib
import struct
import multiprocessing.shared_memory as shm
from collections import deque
from typing import Dict, Optional, List

# --- Logger ---
logger = logging.getLogger("IA-Zar-Proxy")

# Configurar handlers con codificación UTF-8
handlers = [
    logging.StreamHandler(),
    logging.FileHandler(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'proxy.log'),
        encoding='utf-8'
    )
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)

# ==== RUTAS ====
PROXY_DIR = os.path.dirname(os.path.abspath(__file__))
IAZAR_DIR = os.path.dirname(PROXY_DIR)
SRC_DIR = os.path.dirname(IAZAR_DIR)
BASE_DIR = SRC_DIR
for path in [SRC_DIR, IAZAR_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Definir COLUMNS (debe coincidir con el módulo de evaluación)
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

# Tamaños de estructuras binarias
JOB_STRUCT_SIZE = 176  # 84 + 8 + 32 + 32 + 4 + 16
SOLUTION_STRUCT_SIZE = 5 + (len(COLUMNS) * 8)  # 4 (nonce) + 1 (is_valid) + (n_features * 8)
SHM_JOB_SIZE = JOB_STRUCT_SIZE + 1  # +1 byte para bandera
SHM_SOLUTION_SIZE = SOLUTION_STRUCT_SIZE + 1  # +1 byte para bandera

class BinSharedMemoryManager:
    """Gestión eficiente de memoria compartida con protocolo binario"""
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.job_shm = None
        self.solution_shm = None
        self._initialize_shm()

    def _initialize_shm(self):
        """Crea o conecta a la memoria compartida con nombres únicos"""
        job_shm_name = f"{self.prefix}_job"
        solution_shm_name = f"{self.prefix}_solution"
        
        try:
            self.job_shm = shm.SharedMemory(name=job_shm_name, create=False)
        except FileNotFoundError:
            self.job_shm = shm.SharedMemory(
                name=job_shm_name, 
                create=True, 
                size=SHM_JOB_SIZE
            )
            self.job_shm.buf[SHM_JOB_SIZE-1] = 0  # Inicializar bandera
        
        try:
            self.solution_shm = shm.SharedMemory(name=solution_shm_name, create=False)
        except FileNotFoundError:
            self.solution_shm = shm.SharedMemory(
                name=solution_shm_name, 
                create=True, 
                size=SHM_SOLUTION_SIZE
            )
            self.solution_shm.buf[SHM_SOLUTION_SIZE-1] = 0  # Inicializar bandera

    @staticmethod
    def serialize_job(job: Dict) -> bytes:
        """Serializa un trabajo a formato binario"""
        try:
            # Convertir campos a formatos binarios
            blob_bytes = bytes.fromhex(job['blob'])
            target_bytes = struct.pack('>Q', int(job['target'], 16))
            seed_hash_bytes = bytes.fromhex(job['seed_hash'])
            job_id_bytes = job['job_id'].encode('utf-8').ljust(32, b'\0')
            height_bytes = struct.pack('>I', job.get('height', 0))
            algo_bytes = job.get('algo', 'rx/0').encode('utf-8').ljust(16, b'\0')
            
            return blob_bytes + target_bytes + seed_hash_bytes + job_id_bytes + height_bytes + algo_bytes
        except Exception as e:
            logger.error(f"Error serializando job: {str(e)}")
            return b''

    @staticmethod
    def deserialize_job(data: bytes) -> Dict:
        """Deserializa datos binarios a un diccionario de trabajo"""
        try:
            return {
                'blob': data[0:84].hex(),
                'target': hex(struct.unpack('>Q', data[84:92])[0]),
                'seed_hash': data[92:124].hex(),
                'job_id': data[124:156].decode('utf-8').rstrip('\0'),
                'height': struct.unpack('>I', data[156:160])[0],
                'algo': data[160:176].decode('utf-8').rstrip('\0')
            }
        except Exception as e:
            logger.error(f"Error deserializando job: {str(e)}")
            return {}

    @staticmethod
    def serialize_solution(solution: Dict) -> bytes:
        """Serializa una solución a formato binario"""
        try:
            nonce_bytes = struct.pack('>I', solution['nonce'])
            is_valid_bytes = bytes([solution['is_valid']])
            features_bytes = b''.join(
                struct.pack('>d', solution.get(col, 0.0)) for col in COLUMNS
            )
            return nonce_bytes + is_valid_bytes + features_bytes
        except Exception as e:
            logger.error(f"Error serializando solución: {str(e)}")
            return b''

    @staticmethod
    def deserialize_solution(data: bytes) -> Dict:
        """Deserializa datos binarios a un diccionario de solución"""
        try:
            solution = {
                'nonce': struct.unpack('>I', data[0:4])[0],
                'is_valid': bool(data[4])
            }
            # Extraer características
            for i, col in enumerate(COLUMNS):
                start = 5 + i*8
                solution[col] = struct.unpack('>d', data[start:start+8])[0]
            return solution
        except Exception as e:
            logger.error(f"Error deserializando solución: {str(e)}")
            return {}

    def set_job(self, job: Dict):
        """Envía un trabajo a la IA a través de memoria compartida"""
        if not self.job_shm:
            return
            
        # Esperar hasta que la IA haya procesado el trabajo anterior
        while self.job_shm.buf[SHM_JOB_SIZE-1] == 1:
            time.sleep(0.001)
        
        # Serializar y escribir en memoria compartida
        job_data = self.serialize_job(job)
        if job_data:
            self.job_shm.buf[:JOB_STRUCT_SIZE] = job_data
            self.job_shm.buf[SHM_JOB_SIZE-1] = 1  # Bandera de nuevo trabajo

    def get_solution(self, timeout: float) -> Optional[Dict]:
        """Obtiene solución de la IA con timeout"""
        if not self.solution_shm:
            return None
            
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if self.solution_shm.buf[SHM_SOLUTION_SIZE-1] == 1:
                # Leer datos binarios
                solution_data = bytes(self.solution_shm.buf[:SOLUTION_STRUCT_SIZE])
                # Resetear bandera
                self.solution_shm.buf[SHM_SOLUTION_SIZE-1] = 0
                return self.deserialize_solution(solution_data)
            time.sleep(0.001)
        return None

    def close(self):
        """Libera recursos de memoria compartida"""
        if self.job_shm:
            self.job_shm.close()
        if self.solution_shm:
            self.solution_shm.close()

class MinerConnection:
    def __init__(self, sock, addr, connection_id):
        self.sock = sock
        self.addr = addr
        self.id = connection_id
        self.worker_name = None
        self.subscribed = False
        self.authorized = False
        self.buffer = b""
        self.last_job_id = None

    def send(self, message):
        try:
            if not isinstance(message, bytes):
                message = message.encode()
            self.sock.send(message + b"\n")
            return True
        except Exception as e:
            logger.error(f"Error enviando a minero {self.addr}: {e}")
            return False

class IAZarProxy:
    def __init__(self, wallet, pool_host="pool.hashvault.pro", pool_port=443, pool_tls=True, 
                 listen_port=3333, listen_tls_port=3334, miner_password="x", shm_prefix="zartrux_shared"):
        self.wallet = wallet
        self.pool_host = pool_host
        self.pool_port = pool_port
        self.pool_tls = pool_tls
        self.listen_port = listen_port
        self.listen_tls_port = listen_tls_port
        self.miner_password = miner_password
        self.conn = None
        self.last_job = None
        self.last_job_notify = None
        self.miner_connections = {}
        self.miner_connection_counter = 0
        self.message_id_counter = 100
        self.reconnect_attempts = 0
        self.lock = threading.Lock()
        self.session_id = None

        # Configuración de memoria compartida binaria
        self.shm_manager = BinSharedMemoryManager(prefix=shm_prefix)
        logger.info("Memoria compartida binaria inicializada para comunicacion IA-Proxy")
        
        self.connect_to_pool()
        logger.info(f"Servidor proxy STRATUM escuchando en {self.listen_port} (plain) y {self.listen_tls_port} (TLS)")
        self.start_miners_listener()

    def next_msg_id(self):
        self.message_id_counter += 1
        return self.message_id_counter

    def _send_json(self, data):
        """Envía datos JSON con codificación UTF-8"""
        try:
            payload = (json.dumps(data) + "\n").encode('utf-8')
            self.conn.sendall(payload)
            return True
        except Exception as e:
            logger.error(f"Error enviando datos: {e}")
            return False

    def _recv_line(self, timeout=30):
        """Recibe una línea completa hasta encontrar un newline"""
        start_time = time.time()
        buffer = b""
        self.conn.settimeout(0.5)
        while time.time() - start_time < timeout:
            try:
                chunk = self.conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    return line.decode('utf-8', errors="ignore").strip()
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error recibiendo línea: {e}")
                break
        # Devolver datos aunque no tengan newline
        if buffer:
            return buffer.decode('utf-8', errors="ignore").strip()
        return None

    def connect_to_pool(self):
        max_retries = 5
        retry_delay = 2
        for attempt in range(max_retries):
            try:
                # Crear conexión con timeout
                connect_timeout = min(15 + attempt * 5, 60)
                sock = socket.create_connection(
                    (self.pool_host, int(self.pool_port)), 
                    timeout=connect_timeout
                )
                
                # Configuración TLS específica para Hashvault
                if self.pool_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    # Conexión segura con SNI
                    self.conn = context.wrap_socket(
                        sock,
                        server_hostname=self.pool_host,
                        server_side=False
                    )
                    
                    # Validar TLS fingerprint
                    cert = self.conn.getpeercert(binary_form=True)
                    fingerprint = hashlib.sha256(cert).hexdigest()
                    expected = "420c7850e09b7c0bdcf748a7da9eb3647daf8515718f36d9ccfdd6b9ff834b14"
                    if fingerprint != expected:
                        raise ssl.SSLError(f"Invalid TLS fingerprint: {fingerprint}")
                else:
                    self.conn = sock
                
                self.conn.settimeout(30)
                
                logger.info(f"Conexion establecida: {self.pool_host}:{self.pool_port} {'(TLS)' if self.pool_tls else ''}")
                
                # 1. Enviar mining.subscribe con formato CORREGIDO para Hashvault
                # Usando el formato correcto para la suscripción
                subscribe_msg = json.dumps({
                    "id": None,
                    "method": "mining.subscribe",
                    "params": ["IA-ZarProxy/6.22.2", None]
                }) + "\n"
                
                self.conn.sendall(subscribe_msg.encode("utf-8"))
                logger.info(f"mining.subscribe enviado: {subscribe_msg.strip()}")
                
                # Intentar recibir respuesta inmediatamente
                try:
                    response = self.conn.recv(4096).decode("utf-8", errors="replace")
                    logger.info(f"🧪 Respuesta del pool:\n{response}")
                    
                    if '"result"' in response or '"status"' in response:
                        logger.info("✅ Respuesta válida recibida del pool")
                        # Intentar extraer session ID
                        try:
                            response_data = json.loads(response)
                            if "result" in response_data:
                                if isinstance(response_data["result"], list) and len(response_data["result"]) > 0:
                                    self.session_id = response_data["result"][0]
                            logger.info(f"Session ID obtenido: {self.session_id}")
                        except:
                            logger.warning("No se pudo extraer session ID de la respuesta")
                    else:
                        logger.warning("⚠️ Respuesta inesperada del pool")
                except socket.timeout:
                    logger.error("⏱️ Timeout esperando respuesta del pool")
                except Exception as e:
                    logger.exception(f"❌ Error leyendo respuesta del pool: {e}")
                
                # 2. Enviar mining.authorize
                msg_id = self.next_msg_id()
                authorize_msg = {
                    "id": msg_id,
                    "method": "mining.authorize",
                    "params": [self.wallet, "x"]
                }
                self._send_json(authorize_msg)
                logger.info("mining.authorize enviado a la pool")
                
                # 3. Esperar respuesta de autorización
                auth_response = self._recv_line(timeout=15)
                if not auth_response:
                    raise ConnectionError("No se recibió respuesta a mining.authorize")
                
                logger.info(f"Respuesta authorize: {auth_response}")
                
                # Resetear contador de reintentos
                self.reconnect_attempts = 0
                return True
                
            except Exception as e:
                logger.error(f"Error conectando a pool (intento {attempt+1}/{max_retries}): {str(e)}")
                if "Respuesta inválida" in str(e) or "No se encontró session ID" in str(e):
                    if 'response' in locals():
                        logger.error(f"Respuesta completa del pool: {response}")
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.critical(f"No se pudo conectar al pool después de {max_retries} intentos")
                    sys.exit(1)
        return False

    def start_miners_listener(self):
        threading.Thread(target=self.listen_plain, daemon=True).start()
        threading.Thread(target=self.listen_tls, daemon=True).start()

    def listen_plain(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.listen_port))
            s.listen(100)
            logger.info(f"Listener plain abierto en puerto {self.listen_port}")
            while True:
                client_sock, addr = s.accept()
                with self.lock:
                    self.miner_connection_counter += 1
                    miner_conn = MinerConnection(client_sock, addr, self.miner_connection_counter)
                    self.miner_connections[miner_conn.id] = miner_conn
                threading.Thread(target=self.handle_miner, args=(miner_conn,), daemon=True).start()
        except Exception as e:
            logger.error(f"Listener plain error: {e}")

    def listen_tls(self):
        crt_path = os.path.join(BASE_DIR, "certs", "iazar_proxy.crt")
        key_path = os.path.join(BASE_DIR, "certs", "iazar_proxy.key")
        try:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.load_cert_chain(certfile=crt_path, keyfile=key_path)
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.listen_tls_port))
            s.listen(100)
            logger.info(f"Listener TLS abierto en puerto {self.listen_tls_port}")
            
            while True:
                raw_sock, addr = s.accept()
                try:
                    client_sock = context.wrap_socket(raw_sock, server_side=True)
                    with self.lock:
                        self.miner_connection_counter += 1
                        miner_conn = MinerConnection(client_sock, addr, self.miner_connection_counter)
                        self.miner_connections[miner_conn.id] = miner_conn
                    threading.Thread(target=self.handle_miner, args=(miner_conn,), daemon=True).start()
                except Exception as e:
                    logger.warning(f"Fallo handshake TLS con minero {addr}: {e}")
        except Exception as e:
            logger.error(f"Listener TLS error: {e}")

    def handle_miner(self, miner_conn):
        try:
            logger.info(f"Nuevo minero conectado: {miner_conn.addr}")
            while True:
                data = miner_conn.sock.recv(4096)
                if not data:
                    break
                
                miner_conn.buffer += data
                while b"\n" in miner_conn.buffer:
                    msg, miner_conn.buffer = miner_conn.buffer.split(b"\n", 1)
                    try:
                        message = json.loads(msg)
                        self.process_miner_message(miner_conn, message)
                    except json.JSONDecodeError:
                        logger.warning(f"Mensaje invalido de {miner_conn.addr}: {msg[:100]}...")
                    except Exception as e:
                        logger.error(f"Error procesando mensaje minero: {e}")
                        traceback.print_exc()
        except Exception as e:
            logger.warning(f"Minero {miner_conn.addr} desconectado: {e}")
        finally:
            miner_conn.sock.close()
            with self.lock:
                if miner_conn.id in self.miner_connections:
                    del self.miner_connections[miner_conn.id]
                    logger.info(f"Minero desconectado: {miner_conn.addr}")

    def process_miner_message(self, miner_conn, message):
        method = message.get("method")
        params = message.get("params")
        msg_id = message.get("id")
        
        logger.info(f"[{miner_conn.addr}] Metodo: {method}, ID: {msg_id}")

        if method == "mining.subscribe":
            response = {
                "id": msg_id,
                "result": [
                    [["mining.notify", f"{random.randint(10000000, 99999999)}"], "08000002", 4],
                    "08000002"
                ],
                "error": None
            }
            miner_conn.send(json.dumps(response))
            miner_conn.subscribed = True
            logger.info(f"[{miner_conn.addr}] Suscrito")
            
            if self.last_job_notify:
                miner_conn.send(json.dumps(self.last_job_notify))

        elif method == "mining.authorize":
            if params and len(params) >= 1:
                login = params[0]
                password = params[1] if len(params) > 1 else "x"
                
                if not login:
                    response = {"id": msg_id, "error": ["-1", "Login requerido", ""]}
                elif password != self.miner_password:
                    response = {"id": msg_id, "error": ["-1", "Password incorrecto", ""]}
                else:
                    miner_conn.worker_name = login
                    miner_conn.authorized = True
                    response = {"id": msg_id, "result": True, "error": None}
                    logger.info(f"[{miner_conn.addr}] Autorizado como {login}")
            else:
                response = {"id": msg_id, "error": ["-1", "Parametros invalidos", ""]}
            
            miner_conn.send(json.dumps(response))

        elif method == "mining.submit":
            if not miner_conn.authorized:
                logger.warning(f"Submit de minero no autorizado: {miner_conn.addr}")
                response = {"id": msg_id, "error": ["-1", "No autorizado", ""]}
                miner_conn.send(json.dumps(response))
                return

            if params and len(params) >= 4:
                worker_name = params[0]
                job_id = params[1]
                nonce = params[2]
                hash_result = params[3]
                
                submit_msg = {
                    "id": self.next_msg_id(),
                    "jsonrpc": "2.0",
                    "method": "submit",
                    "params": {
                        "id": job_id,
                        "job_id": job_id,
                        "nonce": nonce,
                        "result": hash_result,
                        "algo": "rx/0",
                        "worker": worker_name
                    }
                }
                try:
                    self._send_json(submit_msg)
                    logger.info(f"Share minero enviado a pool: {worker_name} job={job_id}")
                    miner_conn.send(json.dumps({"id": msg_id, "result": True, "error": None}))
                except Exception as e:
                    logger.error(f"Error enviando share a pool: {e}")
                    miner_conn.send(json.dumps({"id": msg_id, "error": ["-1", "Error de proxy", str(e)]}))
            else:
                logger.warning(f"Submit invalido de {miner_conn.addr}: {params}")
                miner_conn.send(json.dumps({"id": msg_id, "error": ["-1", "Parametros invalidos", ""]}))

        elif method == "mining.configure":
            response = {
                "id": msg_id,
                "result": {
                    "version-rolling": True,
                    "version-rolling.mask": "1fffe000",
                    "version-rolling.min-bit-count": 16
                },
                "error": None
            }
            miner_conn.send(json.dumps(response))
            logger.info(f"[{miner_conn.addr}] Configuracion aceptada")

        else:
            logger.info(f"Metodo no reconocido de {miner_conn.addr}: {method}")
            miner_conn.send(json.dumps({
                "id": msg_id,
                "error": ["-1", "Metodo no soportado", ""]
            }))

    def parse_job_message(self, params):
        try:
            if isinstance(params, list):
                job = {
                    "id": params[0],
                    "blob": params[1],
                    "seed_hash": params[2],
                    "target": params[3],
                    "height": params[4] if len(params) > 4 else 0,
                    "difficulty": self.hex_to_difficulty(params[3]) if len(params) > 3 else 0.0
                }
            elif isinstance(params, dict):
                job = {
                    "id": params.get("job_id"),
                    "blob": params.get("blob"),
                    "seed_hash": params.get("seed_hash"),
                    "target": params.get("target"),
                    "height": params.get("height", 0),
                    "difficulty": float(params.get("difficulty", 0.0))
                }
            else:
                logger.error(f"mining.notify tipo inesperado: {type(params)}")
                return None
            return job
        except Exception as e:
            logger.error(f"Error parseando trabajo: {e}")
            traceback.print_exc()
            return None

    def hex_to_difficulty(self, target_hex):
        """Convierte target hexadecimal a dificultad"""
        try:
            target = int(target_hex, 16)
            return (2**256 - 1) / target if target > 0 else 0
        except:
            return 0.0

    def get_next_job(self):
        try:
            data = self._recv_line(timeout=1)
            if not data:
                return None
                
            try:
                message = json.loads(data)
                method = message.get("method")
                
                if method in ["job", "mining.job", "mining.notify"]:
                    job = self.parse_job_message(message.get("params", []))
                    if job:
                        logger.info(f"Nuevo trabajo recibido: {job['id']}")
                        return job
                else:
                    logger.info(f"Mensaje del pool: {data[:200]}...")
            except json.JSONDecodeError:
                logger.warning(f"Mensaje JSON invalido: {data[:100]}...")
            
            return None
        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Error socket pool: {e}")
            self.reconnect_to_pool()
            return None

    def reconnect_to_pool(self):
        logger.warning("Reconectando con el pool...")
        self.reconnect_attempts += 1
        reconnect_delay = min(2 ** self.reconnect_attempts, 60)
        
        time.sleep(reconnect_delay)
        try:
            if self.conn:
                self.conn.close()
            self.connect_to_pool()
        except Exception as e:
            logger.error(f"Error en reconexion: {e}")

    def broadcast_new_job(self, job):
        if not job:
            return
            
        notify_msg = {
            "id": None,
            "method": "mining.notify",
            "params": [
                job['id'],
                job['blob'],
                job['seed_hash'],
                job['target'],
                True
            ]
        }
        self.last_job_notify = notify_msg
        msg_str = json.dumps(notify_msg)
        
        logger.info(f"Broadcast trabajo {job['id']} a {len(self.miner_connections)} mineros")
        
        with self.lock:
            to_remove = []
            for conn_id, miner_conn in self.miner_connections.items():
                if miner_conn.subscribed:
                    if not miner_conn.send(msg_str):
                        to_remove.append(conn_id)
            
            for conn_id in to_remove:
                del self.miner_connections[conn_id]

    def submit_ia_solution(self, solution):
        try:
            submit_msg = {
                "id": self.next_msg_id(),
                "jsonrpc": "2.0",
                "method": "submit",
                "params": {
                    "id": solution["job_id"],
                    "job_id": solution["job_id"],
                    "nonce": format(solution["nonce"], "08x"),
                    "result": solution["hash"],
                    "algo": "rx/0",
                    "worker": "IA-Zar"
                }
            }
            self._send_json(submit_msg)
            logger.info(f"Share IA enviado a pool: nonce={solution['nonce']} job={solution['job_id']}")
            return True
        except Exception as e:
            logger.error(f"Error enviando solucion IA: {e}")
            self.reconnect_to_pool()
            return False

    def run(self):
        polling_interval = 0.1  # Intervalo aumentado
        logger.info("Iniciando bucle principal del proxy")
        
        while True:
            try:
                # 1. Obtener nuevo trabajo del pool
                job = self.get_next_job()
                if job:
                    self.last_job = job
                    logger.info(f"Nuevo trabajo recibido: {job['id']} (Diff: {job.get('difficulty', '?')}")
                    
                    # 2. Enviar a mineros
                    self.broadcast_new_job(job)
                    
                    # 3. Enviar a IA mediante memoria compartida binaria
                    self.shm_manager.set_job({
                        "blob": job['blob'],
                        "target": job['target'],
                        "seed_hash": job['seed_hash'],
                        "job_id": job['id'],
                        "height": job.get('height', 0)
                    })
                    logger.debug(f"Trabajo enviado a IA: {job['id']}")

                # 4. Verificar si hay solución de IA
                solution = self.shm_manager.get_solution(0.5)  # Timeout aumentado
                if solution:
                    logger.info(f"Solucion IA recibida: job={solution['job_id']} nonce={solution['nonce']}")
                    self.submit_ia_solution({
                        "job_id": solution["job_id"],
                        "nonce": solution["nonce"],
                        "hash": ""  # El pool calculará el hash
                    })

                time.sleep(polling_interval)
                
            except Exception as e:
                logger.error(f"Error en bucle principal: {e}")
                traceback.print_exc()
                time.sleep(1)

    def __del__(self):
        self.shm_manager.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ia_proxy_main.py <wallet_address> [pool_host] [pool_port]")
        sys.exit(1)
    
    wallet = sys.argv[1]
    pool_host = sys.argv[2] if len(sys.argv) > 2 else "pool.hashvault.pro"
    pool_port = int(sys.argv[3]) if len(sys.argv) > 3 else 443
    shm_prefix = sys.argv[4] if len(sys.argv) > 4 else "zartrux_shared"

    logger.info(f"""
    ======================================
    Iniciando IA-Zar Proxy v4.0
    Wallet: {wallet}
    Pool: {pool_host}:{pool_port}
    SHM Prefix: {shm_prefix}
    ======================================
    """)

    proxy = IAZarProxy(
        wallet, 
        pool_host=pool_host, 
        pool_port=pool_port,
        pool_tls=True,
        listen_port=3333,
        listen_tls_port=3334,
        shm_prefix=shm_prefix
    )
    
    try:
        proxy.run()
    except KeyboardInterrupt:
        logger.info("Proxy detenido por usuario")
        sys.exit(0)
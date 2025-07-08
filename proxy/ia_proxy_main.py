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
import hashlib  # Added for TLS fingerprint validation
from collections import deque
from iazar.bridge.shared_memory_manager import SharedMemoryManager
from iazar.utils.config_manager import get_shm_config

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
                 listen_port=3333, listen_tls_port=3334, miner_password="x"):
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

        # Configuración de memoria compartida
        self.config = get_shm_config()
        self.shm_manager = SharedMemoryManager(
            prefix=self.config.get("name", "zartrux_shared")
        )
        logger.info("Memoria compartida inicializada para comunicacion IA-Proxy")
        
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
                
                # 1. Enviar mining.subscribe con formato específico para Hashvault
                msg_id = self.next_msg_id()
                subscribe_msg = {
                    "id": msg_id,
                    "jsonrpc": "2.0",  # REQUIRED by Hashvault
                    "method": "mining.subscribe",
                    "params": ["IA-ZarProxy/6.22.2", None]  # Correct Hashvault format
                }
                self._send_json(subscribe_msg)
                logger.info("mining.subscribe enviado a la pool")
                
                # Recibir respuesta
                response = self._recv_line(timeout=15)
                if not response:
                    raise ConnectionError("No se recibió respuesta a mining.subscribe")
                
                logger.info(f"Respuesta subscribe: {response[:200]}")
                
                # Extraer session ID
                try:
                    response_data = json.loads(response)
                    if "result" in response_data:
                        self.session_id = response_data["result"][0]  # Formato esperado
                    else:
                        raise ConnectionError("Respuesta sin 'result' en mining.subscribe")
                except (KeyError, IndexError) as e:
                    raise ConnectionError(f"Error parseando respuesta: {str(e)}")
                
                # 2. Enviar mining.authorize
                msg_id = self.next_msg_id()
                authorize_msg = {
                    "id": msg_id,
                    "jsonrpc": "2.0",  # REQUIRED by Hashvault
                    "method": "mining.authorize",
                    "params": [self.wallet, "x"]
                }
                self._send_json(authorize_msg)
                logger.info("mining.authorize enviado a la pool")
                
                # 3. Esperar respuesta de autorización
                auth_response = self._recv_line(timeout=15)
                if not auth_response:
                    raise ConnectionError("No se recibió respuesta a mining.authorize")
                
                logger.info(f"Respuesta authorize: {auth_response[:200]}")
                
                # Resetear contador de reintentos
                self.reconnect_attempts = 0
                return True
                
            except Exception as e:
                logger.error(f"Error conectando a pool (intento {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.critical(f"No se pudo conectar al pool despues de {max_retries} intentos")
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
                    "jsonrpc": "2.0",  # Added for Hashvault compatibility
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
                    "difficulty": float(params[5]) if len(params) > 5 and params[5] else 0.0
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
                "jsonrpc": "2.0",  # Added for Hashvault compatibility
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
        polling_interval = self.config.get("polling_interval", 0.001)
        logger.info("Iniciando bucle principal del proxy")
        
        while True:
            try:
                job = self.get_next_job()
                if job:
                    self.last_job = job
                    logger.info(f"Nuevo trabajo recibido: {job['id']} (Diff: {job.get('difficulty', '?')}")
                    
                    self.broadcast_new_job(job)
                    
                    self.shm_manager.set_job({
                        "blob": job['blob'],
                        "target": job['target'],
                        "seed_hash": job['seed_hash'],
                        "job_id": job['id'],
                        "height": job.get('height', 0)
                    })

                if self.shm_manager.is_solution_ready():
                    solution = self.shm_manager.get_solution()
                    if solution:
                        logger.info(f"Solucion IA recibida: job={solution['job_id']} nonce={solution['nonce']}")
                        self.submit_ia_solution(solution)
                    self.shm_manager.reset()

                time.sleep(polling_interval)
                
            except Exception as e:
                logger.error(f"Error en bucle principal: {e}")
                traceback.print_exc()
                time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ia_proxy_main.py <wallet_address> [pool_host] [pool_port]")
        sys.exit(1)
    
    wallet = sys.argv[1]
    pool_host = sys.argv[2] if len(sys.argv) > 2 else "pool.hashvault.pro"
    pool_port = int(sys.argv[3]) if len(sys.argv) > 3 else 443

    logger.info(f"""
    ======================================
    Iniciando IA-Zar Proxy
    Wallet: {wallet}
    Pool: {pool_host}:{pool_port}
    ======================================
    """)

    proxy = IAZarProxy(
        wallet, 
        pool_host=pool_host, 
        pool_port=pool_port,
        pool_tls=True,
        listen_port=3333,
        listen_tls_port=3334
    )
    
    try:
        proxy.run()
    except KeyboardInterrupt:
        logger.info("Proxy detenido por usuario")
        sys.exit(0)
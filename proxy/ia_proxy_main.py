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
from typing import Dict, Optional

# Corregir comentarios y carga de configuración
try:
    base_dir = os.path.dirname(__file__)
    config_path = os.path.join(base_dir, '..', 'config', 'shared_memory.json')
    with open(config_path) as f:
        shm_config = json.load(f)
    PREFIX = shm_config["prefix"]
    BUFFER_SIZE = shm_config["solution_buffer_size"]  # Usa el buffer de soluciones
except Exception as e:
    print(f"Error loading shared memory config: {str(e)}")  # Usar print ya que logger aún no está inicializado
    PREFIX = "zartrux_shared"  # Fallback
    BUFFER_SIZE = 2097152       # Fallback

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# --- Logger Configuration ---
logger = logging.getLogger("IA-Zar-Proxy")
logger.setLevel(logging.INFO)

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure handlers
handlers = [
    logging.StreamHandler(),
    logging.FileHandler(
        os.path.join(log_dir, 'proxy.log'),
        encoding='utf-8'
    )
]

for handler in handlers:
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# ==== Constants ====
PROXY_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROXY_DIR)
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Shared memory structure sizes
JOB_STRUCT_SIZE = 180  # Fixed size for job data
SOLUTION_STRUCT_SIZE = 73  # Fixed size for solution data
SHM_JOB_SIZE = JOB_STRUCT_SIZE + 1  # +1 byte for flag
SHM_SOLUTION_SIZE = SOLUTION_STRUCT_SIZE + 1  # +1 byte for flag


class BinSharedMemoryManager:
    """Efficient binary shared memory management for proxy-AI communication"""
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.job_shm = None
        self.solution_shm = None
        self._initialize_shm()

    def _initialize_shm(self):
        """Create or connect to shared memory with unique names"""
        job_shm_name = f"{self.prefix}_job"
        solution_shm_name = f"{self.prefix}_solution"
        
        logger.info(f"Initializing shared memory: job='{job_shm_name}', solution='{solution_shm_name}'")
        
        # Job memory initialization
        try:
            self.job_shm = shm.SharedMemory(name=job_shm_name, create=True, size=SHM_JOB_SIZE)
            self.job_shm.buf[SHM_JOB_SIZE-1] = 0  # Initialize flag
            logger.info(f"Created job shared memory: {job_shm_name} ({SHM_JOB_SIZE} bytes)")
        except FileExistsError:
            self.job_shm = shm.SharedMemory(name=job_shm_name)
            logger.info(f"Connected to existing job shared memory: {job_shm_name}")
        
        # Solution memory initialization
        try:
            self.solution_shm = shm.SharedMemory(name=solution_shm_name, create=True, size=SHM_SOLUTION_SIZE)
            self.solution_shm.buf[SHM_SOLUTION_SIZE-1] = 0  # Initialize flag
            logger.info(f"Created solution shared memory: {solution_shm_name} ({SHM_SOLUTION_SIZE} bytes)")
        except FileExistsError:
            self.solution_shm = shm.SharedMemory(name=solution_shm_name)
            logger.info(f"Connected to existing solution shared memory: {solution_shm_name}")

    @staticmethod
    def serialize_job(job: Dict) -> bytes:
        """Serialize job to fixed-size binary format"""
        try:
            # Blob: 84 bytes
            blob_bytes = bytes.fromhex(job['blob'])[:84]
            blob_bytes = blob_bytes.ljust(84, b'\0')
            
            # Target: 8 bytes (big-endian)
            target_bytes = struct.pack('>Q', int(job['target'], 16))
            
            # Seed hash: 32 bytes
            seed_bytes = bytes.fromhex(job['seed_hash'])[:32]
            seed_bytes = seed_bytes.ljust(32, b'\0')
            
            # Job ID: 36 bytes (UTF-8)
            job_id_bytes = job['job_id'].encode('utf-8')[:36]
            job_id_bytes = job_id_bytes.ljust(36, b'\0')
            
            # Height: 4 bytes (big-endian)
            height_bytes = struct.pack('>I', job.get('height', 0))
            
            # Algorithm: 16 bytes (UTF-8)
            algo_bytes = job.get('algo', 'rx/0').encode('utf-8')[:16]
            algo_bytes = algo_bytes.ljust(16, b'\0')
            
            return blob_bytes + target_bytes + seed_bytes + job_id_bytes + height_bytes + algo_bytes
        except Exception as e:
            logger.error(f"Job serialization error: {str(e)}")
            return b''

    @staticmethod
    def deserialize_solution(data: bytes) -> Dict:
        """Deserialize binary solution data to dictionary"""
        try:
            return {
                'job_id': data[0:36].decode('utf-8').rstrip('\0'),
                'nonce': struct.unpack('>I', data[36:40])[0],
                'hash': data[40:72].hex(),
                'is_valid': bool(data[72])
            }
        except Exception as e:
            logger.error(f"Solution deserialization error: {str(e)}")
            return {}

    def set_job(self, job: Dict):
        """Send job to AI via shared memory"""
        if not self.job_shm:
            return
            
        # Wait for AI to process previous job
        while self.job_shm.buf[SHM_JOB_SIZE-1] == 1:
            time.sleep(0.001)
        
        # Serialize and write to shared memory
        job_data = self.serialize_job(job)
        if len(job_data) != JOB_STRUCT_SIZE:
            logger.error(f"Invalid job size: {len(job_data)} != {JOB_STRUCT_SIZE}")
            return
            
        self.job_shm.buf[:JOB_STRUCT_SIZE] = job_data
        self.job_shm.buf[SHM_JOB_SIZE-1] = 1  # Set new job flag
        logger.debug(f"Job sent to AI: {job['job_id']}")

    def get_solution(self, timeout: float = 3.0) -> Optional[Dict]:
        """Get solution from AI with timeout"""
        if not self.solution_shm:
            return None
            
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if self.solution_shm.buf[SHM_SOLUTION_SIZE-1] == 1:
                solution_data = bytes(self.solution_shm.buf[:SOLUTION_STRUCT_SIZE])
                self.solution_shm.buf[SHM_SOLUTION_SIZE-1] = 0  # Reset flag
                solution = self.deserialize_solution(solution_data)
                if solution:
                    logger.info(f"AI solution received: job_id={solution['job_id']}")
                return solution
            time.sleep(0.001)
        return None

    def close(self):
        """Release shared memory resources"""
        if self.job_shm:
            self.job_shm.close()
        if self.solution_shm:
            self.solution_shm.close()


class MinerConnection:
    """Represents a connection to a miner"""
    def __init__(self, sock, addr, connection_id):
        self.sock = sock
        self.addr = addr
        self.id = connection_id
        self.worker_name = None
        self.subscribed = False
        self.authorized = False
        self.buffer = b""
        self.last_job_id = None
        self.sock.settimeout(5.0)  # Set socket timeout

    def send(self, message):
        """Send message to miner with error handling"""
        try:
            if not isinstance(message, bytes):
                message = message.encode()
            self.sock.sendall(message + b"\n")
            return True
        except Exception as e:
            logger.error(f"Send error to {self.addr}: {e}")
            return False


class IAZarProxy:
    """Main proxy class for handling pool-miner-AI communication"""
    def __init__(self, wallet, pool_host="pool.hashvault.pro", pool_port=443, 
                 listen_port=3333, miner_password="x", shm_prefix="zartrux_shared"):
        self.wallet = wallet
        self.pool_host = pool_host
        self.pool_port = pool_port
        self.listen_port = listen_port
        self.miner_password = miner_password
        self.conn = None
        self.last_job = None
        self.miner_connections = {}
        self.miner_connection_counter = 0
        self.message_id_counter = 0
        self.lock = threading.Lock()
        self.session_id = None
        self.pool_buffer = b""
        self.is_connected = False
        self.expected_fingerprint = "420c7850e09b7c0bdcf748a7da9eb3647daf8515718f36d9ccfdd6b9ff834b14"

        # Shared memory for AI communication
        self.shm_manager = BinSharedMemoryManager(prefix=shm_prefix)
        
        # Connect to pool and start listeners
        self.connect_to_pool()
        self.start_miners_listener()
        logger.info(f"Proxy started on port {listen_port}")

    def next_msg_id(self):
        """Generate next message ID"""
        self.message_id_counter += 1
        return self.message_id_counter

    def _send_json(self, data):
        """Send JSON data with UTF-8 encoding"""
        try:
            payload = (json.dumps(data) + "\n").encode('utf-8')
            self.conn.sendall(payload)
            logger.debug(f"Sent: {data}")
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            self.reconnect_to_pool()
            return False

    def _recv_line(self, timeout=10) -> Optional[str]:
        """Receive a complete line with robust handling of non-JSON messages"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check buffer for complete line
            if b"\n" in self.pool_buffer:
                line, self.pool_buffer = self.pool_buffer.split(b"\n", 1)
                try:
                    return line.decode('utf-8').strip()
                except UnicodeDecodeError:
                    # Handle non-UTF8
                    logger.warning("Non-UTF8 message received, trying latin-1")
                    try:
                        return line.decode('latin-1').strip()
                    except Exception:
                        logger.error("Error decoding message, using raw representation")
                        return str(line)
            
            try:
                chunk = self.conn.recv(4096)
                if not chunk:
                    logger.warning("Connection closed by pool")
                    self.reconnect_to_pool()
                    return None
                    
                self.pool_buffer += chunk
            except socket.timeout:
                continue
            except ssl.SSLWantReadError:
                # SSL specific error, retry
                time.sleep(0.1)
                continue
            except Exception as e:
                logger.error(f"Receive error: {e}")
                self.reconnect_to_pool()
                return None
        
        return None

    def get_next_job(self):
        """Get jobs with handling of invalid messages"""
        try:
            data = self._recv_line(timeout=1)
            if not data:
                return None
                
            # Check if it's a JSON message
            if data.startswith("{"):
                try:
                    message = json.loads(data)
                    method = message.get("method")
                    
                    if method == "job":  # Standard job message
                        job = self.parse_job(message)
                        if job:
                            logger.info(f"Job received: {job['job_id']}")
                            return job
                    else:
                        # Log other JSON messages for debugging
                        logger.debug(f"Received non-job JSON message: {message}")
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON: {data[:100]}...")
            else:
                # Non-JSON message
                if "job" in data.lower() or "blob" in data.lower():
                    logger.warning(f"Suspicious message received: {data[:200]}")
                else:
                    logger.info(f"Non-JSON message: {data[:200]}...")
            
            return None
        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Socket error: {e}")
            self.reconnect_to_pool()
            return None

    def connect_to_pool(self):
        """Establish connection to mining pool"""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Reset buffer
                self.pool_buffer = b""
                
                # Create TCP connection
                sock = socket.create_connection(
                    (self.pool_host, self.pool_port), 
                    timeout=10
                )
                
                # Wrap with TLS
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.conn = context.wrap_socket(
                    sock,
                    server_hostname=self.pool_host,
                    server_side=False
                )
                self.conn.settimeout(10)
                
                # Validate TLS fingerprint
                cert = self.conn.getpeercert(binary_form=True)
                fingerprint = hashlib.sha256(cert).hexdigest()
                if fingerprint != self.expected_fingerprint:
                    logger.warning(f"Unexpected TLS fingerprint: {fingerprint}")
                
                # Send login
                login_msg = {
                    "id": self.next_msg_id(),
                    "jsonrpc": "2.0",
                    "method": "login",
                    "params": {
                        "login": self.wallet,
                        "pass": "x",
                        "agent": "IA-ZarProxy/1.0"
                    }
                }
                self._send_json(login_msg)
                
                # Get login response
                response = self._recv_line(15)
                if not response:
                    raise ConnectionError("No login response")
                
                response_data = json.loads(response)
                if "result" in response_data:
                    self.session_id = response_data["result"].get("id")
                    logger.info(f"Connected to pool, session ID: {self.session_id}")
                    self.is_connected = True
                    return True
                else:
                    error = response_data.get('error', {}).get('message', 'Unknown error')
                    raise ConnectionError(f"Login failed: {error}")
                    
            except Exception as e:
                logger.error(f"Connection attempt {attempt+1}/{max_retries} failed: {e}")
                time.sleep(min(2 ** attempt, 30))
        
        logger.critical("Failed to connect to pool")
        self.is_connected = False
        return False

    def start_miners_listener(self):
        """Start listening for miner connections"""
        def listener():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', self.listen_port))
            sock.listen(100)
            logger.info(f"Miner listener started on port {self.listen_port}")
            
            while True:
                client_sock, addr = sock.accept()
                with self.lock:
                    self.miner_connection_counter += 1
                    miner_conn = MinerConnection(client_sock, addr, self.miner_connection_counter)
                    self.miner_connections[miner_conn.id] = miner_conn
                threading.Thread(target=self.handle_miner, args=(miner_conn,), daemon=True).start()
        
        threading.Thread(target=listener, daemon=True).start()

    def handle_miner(self, miner_conn):
        """Handle communication with a miner"""
        logger.info(f"New miner connected: {miner_conn.addr}")
        try:
            while True:
                try:
                    data = miner_conn.sock.recv(4096)
                    if not data:
                        break
                    
                    miner_conn.buffer += data
                    while b"\n" in miner_conn.buffer:
                        msg, miner_conn.buffer = miner_conn.buffer.split(b"\n", 1)
                        self.process_miner_message(miner_conn, msg)
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Handle miner error: {e}")
                    break
        finally:
            miner_conn.sock.close()
            with self.lock:
                if miner_conn.id in self.miner_connections:
                    del self.miner_connections[miner_conn.id]
                    logger.info(f"Miner disconnected: {miner_conn.addr}")

    def process_miner_message(self, miner_conn, msg_bytes):
        """Process a message from a miner"""
        try:
            msg = json.loads(msg_bytes.decode('utf-8', errors='replace'))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {miner_conn.addr}: {msg_bytes[:100]}")
            return

        method = msg.get("method")
        params = msg.get("params")
        msg_id = msg.get("id")
        
        logger.debug(f"[{miner_conn.addr}] Method: {method}, ID: {msg_id}")

        if method == "mining.subscribe":
            # Standard subscription response
            response = {
                "id": msg_id,
                "result": [
                    [["mining.notify", random.randint(10000000, 99999999)], "08000002", 4],
                    "08000002"
                ],
                "error": None
            }
            miner_conn.send(json.dumps(response))
            miner_conn.subscribed = True
            logger.info(f"[{miner_conn.addr}] Subscribed")

        elif method == "mining.authorize":
            # Validate miner credentials
            if not params or len(params) < 1:
                response = {"id": msg_id, "error": ["-1", "Invalid parameters", ""]}
            else:
                login = params[0]
                password = params[1] if len(params) > 1 else "x"
                
                if password != self.miner_password:
                    response = {"id": msg_id, "error": ["-1", "Invalid password", ""]}
                else:
                    miner_conn.worker_name = login
                    miner_conn.authorized = True
                    response = {"id": msg_id, "result": True, "error": None}
                    logger.info(f"[{miner_conn.addr}] Authorized as {login}")
            
            miner_conn.send(json.dumps(response))

        elif method == "mining.submit":
            # Forward valid submits to pool
            if not miner_conn.authorized:
                response = {"id": msg_id, "error": ["-1", "Unauthorized", ""]}
                miner_conn.send(json.dumps(response))
                return

            if not params or len(params) < 4:
                response = {"id": msg_id, "error": ["-1", "Invalid parameters", ""]}
                miner_conn.send(json.dumps(response))
                return

            submit_msg = {
                "id": self.next_msg_id(),
                "jsonrpc": "2.0",
                "method": "submit",
                "params": {
                    "id": params[1],
                    "job_id": params[1],
                    "nonce": params[2],
                    "result": params[3],
                    "worker": params[0]
                }
            }
            
            if self._send_json(submit_msg):
                miner_conn.send(json.dumps({"id": msg_id, "result": True, "error": None}))
                logger.info(f"Share submitted: {params[0]} job={params[1]}")
            else:
                miner_conn.send(json.dumps({"id": msg_id, "error": ["-1", "Proxy error", ""]}))

        elif method == "mining.configure":
            # Standard configuration response
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
            logger.debug(f"[{miner_conn.addr}] Configured")

        else:
            logger.warning(f"Unsupported method from {miner_conn.addr}: {method}")
            miner_conn.send(json.dumps({
                "id": msg_id,
                "error": ["-1", "Unsupported method", ""]
            }))

    def broadcast_job(self, job):
        """Broadcast new job to all miners"""
        if not job:
            return
            
        notify_msg = {
            "id": None,
            "method": "mining.notify",
            "params": [
                job['job_id'],
                job['blob'],
                job['seed_hash'],
                job['target'],
                True  # Clean jobs flag
            ]
        }
        msg_str = json.dumps(notify_msg)
        
        with self.lock:
            for conn_id, miner_conn in list(self.miner_connections.items()):
                if miner_conn.subscribed:
                    if not miner_conn.send(msg_str):
                        del self.miner_connections[conn_id]

    def submit_ai_solution(self, solution):
        """Submit AI solution to pool"""
        submit_msg = {
            "id": self.next_msg_id(),
            "jsonrpc": "2.0",
            "method": "submit",
            "params": {
                "id": solution["job_id"],
                "job_id": solution["job_id"],
                "nonce": format(solution["nonce"], "08x"),
                "result": solution["hash"],
                "worker": "IA-Zar"
            }
        }
        return self._send_json(submit_msg)

    def parse_job(self, message):
        """Parse job message from pool"""
        try:
            params = message.get("params", {})
            return {
                "job_id": params["job_id"],
                "blob": params["blob"],
                "seed_hash": params["seed_hash"],
                "target": params["target"],
                "height": params.get("height", 0),
                "algo": params.get("algo", "rx/0")
            }
        except Exception as e:
            logger.error(f"Job parsing error: {e}")
            return None

    def reconnect_to_pool(self):
        """Robust reconnection with error handling"""
        logger.warning("Reconnecting to pool...")
        self.is_connected = False
        attempts = 0
        max_attempts = 5
        
        while attempts < max_attempts:
            try:
                if self.conn:
                    try:
                        self.conn.close()
                    except Exception:
                        pass
                
                # Reset buffer
                self.pool_buffer = b""
                
                if self.connect_to_pool():
                    logger.info("Reconnected successfully")
                    return True
                    
            except Exception as e:
                logger.error(f"Reconnection error (attempt {attempts+1}): {e}")
                traceback.print_exc()
            
            wait_time = min(2 ** attempts, 30)  # Exponential backoff
            logger.info(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            attempts += 1
        
        logger.critical("Failed to reconnect after multiple attempts")
        return False

    def run(self):
        """Main proxy loop with heartbeat and job timeout"""
        logger.info("Starting proxy main loop")
        last_heartbeat = time.time()
        last_job_time = time.time()
        JOB_TIMEOUT = 120  # seconds

        while True:
            try:
                if not self.is_connected:
                    if not self.reconnect_to_pool():
                        time.sleep(5)
                        continue
                    else:
                        last_job_time = time.time()  # reset on reconnect

                # Send heartbeat every 30 seconds
                current_time = time.time()
                if current_time - last_heartbeat > 30:
                    try:
                        self._send_json({"id": self.next_msg_id(), "method": "keepalive"})
                        last_heartbeat = current_time
                        logger.debug("Heartbeat sent")
                    except Exception as e:
                        logger.error(f"Heartbeat failed: {e}")
                        self.is_connected = False
                        continue

                # Check for jobs
                job = self.get_next_job()
                if job:
                    last_job_time = current_time
                    self.last_job = job
                    logger.info(f"New job: {job['job_id']}")
                    # Broadcast to miners
                    self.broadcast_job(job)
                    # Send to AI
                    self.shm_manager.set_job(job)

                # Check for AI solutions
                solution = self.shm_manager.get_solution()
                if solution and solution.get('is_valid'):
                    logger.info(f"Valid AI solution: job={solution['job_id']}")
                    self.submit_ai_solution(solution)

                # Check for job timeout
                if current_time - last_job_time > JOB_TIMEOUT:
                    logger.warning(f"No job received in {JOB_TIMEOUT} seconds, reconnecting...")
                    self.is_connected = False
                    last_job_time = current_time  # avoid immediate retrigger
                    continue

                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Main loop error: {e}")
                traceback.print_exc()
                time.sleep(1)

    def __del__(self):
        self.shm_manager.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ia_proxy_main.py <wallet_address> [pool_host] [pool_port] [shm_prefix]")
        sys.exit(1)
    
    wallet = sys.argv[1]
    pool_host = sys.argv[2] if len(sys.argv) > 2 else "pool.hashvault.pro"
    pool_port = int(sys.argv[3]) if len(sys.argv) > 3 else 443
    shm_prefix = sys.argv[4] if len(sys.argv) > 4 else "zartrux_shared"

    logger.info(f"""
    ======================================
    Starting IA-Zar Proxy
    Wallet: {wallet}
    Pool: {pool_host}:{pool_port}
    SHM Prefix: {shm_prefix}
    ======================================
    """)

    proxy = IAZarProxy(
        wallet, 
        pool_host=pool_host, 
        pool_port=pool_port,
        listen_port=3333,
        shm_prefix=shm_prefix
    )
    
    try:
        proxy.run()
    except KeyboardInterrupt:
        logger.info("Proxy stopped by user")
        sys.exit(0)
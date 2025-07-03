import sys
import os
import ssl
import zmq
import json
import time
import socket
import logging
import threading
import traceback

# --- Logger ---
logger = logging.getLogger("IA-Zar-Proxy")
logging.basicConfig(level=logging.INFO)

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

# ==== CLASE PRINCIPAL ====
class IAZarProxy:
    def __init__(self, wallet, pool_host="127.0.0.1", pool_port=3333, pool_tls=True, listen_port=3333, listen_tls_port=3334):
        self.wallet = wallet
        self.pool_host = pool_host
        self.pool_port = pool_port
        self.pool_tls = pool_tls
        self.listen_port = listen_port
        self.listen_tls_port = listen_tls_port

        self.conn = None
        self.job_cache = {}
        self.last_job = None
        self.last_job_notify = None

        # ZMQ para IA
        zmq_context = zmq.Context()
        self.proxy_sender = zmq_context.socket(zmq.PUSH)
        self.proxy_sender.bind("tcp://127.0.0.1:5555")
        self.proxy_receiver = zmq_context.socket(zmq.PULL)
        self.proxy_receiver.bind("tcp://127.0.0.1:5556")

        logger.info("🧠 Modelos IA cargados")
        logger.info("🔌 Sockets ZMQ configurados")
        self.connect_to_pool()
        logger.info(f"🔒 Servidor proxy STRATUM escuchando en {self.listen_port} (plain) y {self.listen_tls_port} (TLS)")
        # Lanzar listeners para mineros
        self.start_miners_listener()

    # ----------- POOL UPSTREAM -----------
    def connect_to_pool(self):
        try:
            raw_sock = socket.create_connection((self.pool_host, int(self.pool_port)), timeout=10)
            if self.pool_tls:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.conn = context.wrap_socket(raw_sock, server_hostname=self.pool_host)
            else:
                self.conn = raw_sock
            logger.info(f"🔌 Conexión TCP TLS establecida: {self.pool_host}:{self.pool_port}")

            # --- HANDSHAKE STRATUM MONERO ---
            # 1. mining.subscribe
            subscribe_msg = {
                "id": 1,
                "method": "mining.subscribe",
                "params": ["IA-ZarProxy/6.22.2"]  # user agent típico de XMRig
            }
            self.conn.send((json.dumps(subscribe_msg) + "\n").encode())
            logger.info("📡 mining.subscribe enviado a la pool")

            # 2. login para pools Monero (HashVault, SupportXMR, etc)
            login_msg = {
                "id": 2,
                "method": "login",
                "params": {
                    "login": self.wallet,
                    "pass": "x",
                    "agent": "IA-ZarProxy"
                }
            }
            self.conn.send((json.dumps(login_msg) + "\n").encode())
            logger.info("🔑 login enviado a la pool")
        except Exception as e:
            logger.error(f"❌ Error conectando a pool: {e}")
            sys.exit(1)

    # ----------- LISTENER PARA MINEROS (XMRig) -----------
    def start_miners_listener(self):
        threading.Thread(target=self.listen_plain, daemon=True).start()
        threading.Thread(target=self.listen_tls, daemon=True).start()

    def listen_plain(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.listen_port))
            s.listen(100)
            logger.info(f"🖥️ Listener plain abierto en puerto {self.listen_port}")
            while True:
                client_sock, addr = s.accept()
                logger.info(f"🖥️ Nuevo minero (plain) desde {addr}")
                threading.Thread(target=self.handle_miner, args=(client_sock, addr), daemon=True).start()
        except Exception as e:
            logger.error(f"❌ Listener plain error: {e}")

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
            logger.info(f"🖥️ Listener TLS abierto en puerto {self.listen_tls_port}")
            while True:
                raw_sock, addr = s.accept()
                try:
                    client_sock = context.wrap_socket(raw_sock, server_side=True)
                    logger.info(f"🖥️ Nuevo minero (TLS) desde {addr}")
                    threading.Thread(target=self.handle_miner, args=(client_sock, addr), daemon=True).start()
                except Exception as e:
                    logger.warning(f"⚠️ Fallo handshake TLS con minero {addr}: {e}")
        except Exception as e:
            logger.error(f"❌ Listener TLS error: {e}")

    # ------------- GESTIÓN DE MINEROS -------------
    def handle_miner(self, sock, addr):
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                logger.info(f"⛏️ [{addr}] Recibido: {data[:100]}...")
                if self.last_job_notify:
                    sock.send(json.dumps(self.last_job_notify).encode())
        except Exception as e:
            logger.warning(f"❌ Minero {addr} desconectado: {e}")
        finally:
            sock.close()

    # ------------- POOL (UPSTREAM) -------------
    def parse_job_message(self, params):
        try:
            logger.info(f"🔎 mining.notify params: {params}")
            if isinstance(params, list):
                job = {
                    "id": params[0] if len(params) > 0 else None,
                    "blob": params[1] if len(params) > 1 else None,
                    "seed_hash": params[2] if len(params) > 2 else None,
                    "target": params[3] if len(params) > 3 else None,
                    "height": params[4] if len(params) > 4 else None,
                    "difficulty": float(params[5]) if len(params) > 5 and params[5] is not None else 0.0
                }
            elif isinstance(params, dict):
                job = {
                    "id": params.get("job_id"),
                    "blob": params.get("blob"),
                    "seed_hash": params.get("seed_hash"),
                    "target": params.get("target"),
                    "height": params.get("height"),
                    "difficulty": float(params.get("difficulty", 0.0))
                }
            else:
                logger.error(f"❌ mining.notify tipo inesperado: {type(params)}")
                return None
            logger.info(f"✅ Job parseado: {job}")
            return job
        except Exception as e:
            logger.error(f"❌ Error parseando trabajo: {e}")
            logger.error(f"Params recibidos: {params}")
            return None

    def handle_ping(self, message):
        try:
            pong = {"id": message.get("id"), "method": "mining.pong", "params": []}
            self.conn.send(json.dumps(pong).encode())
            logger.info("🏓 Pong enviado a pool")
        except Exception as e:
            logger.error(f"❌ Error manejando ping: {e}")

    # ---- RUN CON INTEGRACIÓN DE SHARES IA ----
    def run(self):
        logger.info("🏁 Bucle principal proxy activo")
        while True:
            try:
                job = self.get_next_job()
                if job:
                    self.last_job = job
                    self.last_job_notify = {
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
                    logger.info(f"📥 Trabajo recibido de pool | Altura: {job.get('height', 'N/A')} Dif: {job.get('difficulty')}")

                # <--- NUEVO: Recibe soluciones de la IA
                try:
                    solution_msg = self.proxy_receiver.recv_json(flags=zmq.NOBLOCK)
                except zmq.Again:
                    solution_msg = None
                if solution_msg and solution_msg.get("type") == "solution":
                    sol = solution_msg["data"]
                    logger.info(f"🧠 Solución IA recibida: {sol}")
                    # REENVÍO DEL SHARE a la POOL
                    submit_msg = {
                        "id": 3,
                        "method": "submit",
                        "params": {
                            "id": self.last_job.get("id"),
                            "job_id": sol["job_id"],
                            "nonce": format(sol["nonce"], "08x"),
                            "result": sol["hash"],
                            "algo": "rx/0"
                        }
                    }
                    self.conn.send((json.dumps(submit_msg) + "\n").encode())
                    logger.info(f"🚀 Share enviado a pool: {submit_msg['params']}")

                time.sleep(0.1)
            except Exception as e:
                logger.error(f"⚠️ Error en bucle principal: {e}")
                traceback.print_exc()

    def get_next_job(self):
        try:
            data = self.conn.recv(4096).decode()
            if not data:
                return None
            for msg in data.strip().split('\n'):
                if not msg:
                    continue
                try:
                    logger.info(f"🔷 Respuesta pool: {msg}")  # <--- LOGUEA TODAS LAS RESPUESTAS CRUDAS DE LA POOL
                    message = json.loads(msg)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Pool mensaje no JSON: {msg}")
                    continue

                if message.get("method") in ["set_difficulty", "mining.set_difficulty"]:
                    logger.info(f"📏 mining.set_difficulty recibido: {message.get('params')}")
                if message.get("method") in ["job", "mining.job", "mining.notify"]:
                    logger.info(f"🚀 Nuevo trabajo pool: {message.get('params')}")
                    params = message.get("params", [])
                    return self.parse_job_message(params)
                if message.get("result") is not None and message.get("id") is not None:
                    logger.info(f"🟢 Respuesta pool (id={message['id']}): {message['result']}")
                if message.get("error") is not None:
                    logger.warning(f"🔴 Error pool: {message['error']}")
            return None
        except socket.timeout:
            logger.warning("⌛ Timeout pool, reconectando...")
            self.connect_to_pool()
            return None
        except Exception as e:
            logger.error(f"🔌 Error socket pool: {e}")
            self.connect_to_pool()
            return None

# --- MAIN ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ia_proxy_main.py <wallet_address> [pool_host] [pool_port]")
        sys.exit(1)
    wallet = sys.argv[1]
    pool_host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    pool_port = int(sys.argv[3]) if len(sys.argv) > 3 else 3333

    proxy = IAZarProxy(wallet, pool_host=pool_host, pool_port=pool_port, pool_tls=True, listen_port=3333, listen_tls_port=3334)
    proxy.run()

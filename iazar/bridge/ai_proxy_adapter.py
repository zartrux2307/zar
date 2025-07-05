# iazar/bridge/ai_proxy_adapter.py
import socket
import ssl
import json
import time
import threading
import logging
import select
import zmq

from iazar.core.randomx_handler import RandomXHandler
from iazar.core.hash_validator import HashValidator
from iazar.utils.config_manager import get_ia_config

class AIProxyAdapter:
    def __init__(self, wallet_address, pool_host, pool_port, ai_server_url, password="x", tls=True):
        self.wallet_address = wallet_address
        self.pool_host = pool_host
        self.pool_port = int(pool_port)
        self.pool_password = password
        self.ai_server_url = ai_server_url
        self.tls = tls
        self.logger = logging.getLogger("IA-Zar-Proxy")
        self.randomx = RandomXHandler()
        self.hash_validator = HashValidator()
        self.config = get_ia_config()
        self.sock = None
        self.ctx = None
        self.session_id = None
        self.job = None
        self.is_running = True

        # ZMQ contexto para comunicación con IA
        self.zmq_ctx = zmq.Context()
        self.zmq_socket = self.zmq_ctx.socket(zmq.REQ)
        self.zmq_socket.connect(self.ai_server_url)  # Ejemplo: "tcp://127.0.0.1:5555"

    def connect_to_pool(self):
        self.logger.info(f"Conectando a pool (TLS={self.tls}) {self.pool_host}:{self.pool_port}...")
        raw_sock = socket.create_connection((self.pool_host, self.pool_port), timeout=10)
        if self.tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE  # Para producción, cambia esto
            self.sock = context.wrap_socket(raw_sock, server_hostname=self.pool_host)
        else:
            self.sock = raw_sock
        self.sock.settimeout(30)
        self.logger.info("Conexión establecida. Enviando subscribe...")

        # Enviar mining.subscribe
        subscribe_msg = {
            "id": 1, "method": "mining.subscribe", "params": []
        }
        self._send_json(subscribe_msg)
        sub_resp = self._recv_json()
        if "result" not in sub_resp:
            raise Exception(f"Respuesta subscribe inválida: {sub_resp}")
        self.session_id = sub_resp["result"].get("id") or sub_resp["result"][0]
        self.logger.info(f"Subscripción OK, session_id={self.session_id}")

        # Enviar mining.authorize o mining.login (según pool, para XMR suele ser login)
        login_msg = {
            "id": 2,
            "method": "mining.login",
            "params": {
                "login": self.wallet_address,
                "pass": self.pool_password,
                "agent": "IA-Zar-Proxy"
            }
        }
        self._send_json(login_msg)
        login_resp = self._recv_json()
        if "result" not in login_resp:
            raise Exception(f"Login fallido: {login_resp}")
        self.logger.info("Login exitoso.")
        return True

    def fetch_job(self):
        """
        Espera y parsea un trabajo real mining.job de la pool.
        """
        while True:
            resp = self._recv_json()
            if resp.get("method") == "mining.job":
                params = resp["params"]
                job = {
                    "job_id": params["job_id"],
                    "blob": params["blob"],
                    "target": params["target"],
                    "seed_hash": params.get("seed_hash", ""),
                    "height": params.get("height"),
                    "algo": params.get("algo", "rx/0")
                }
                self.job = job
                self.logger.info(f"Nuevo trabajo recibido: {job['job_id']}")
                return job
            # Opcional: manejo de 'mining.set_difficulty', 'mining.set_target', etc.

    def request_nonce_from_ai(self, job_data):
        """
        Solicita un nonce válido a la IA vía ZMQ. El job_data se pasa como JSON.
        """
        try:
            # Enviar trabajo como JSON a IA
            self.zmq_socket.send_json(job_data)
            result = self.zmq_socket.recv_json()
            nonce = result.get("nonce")
            if not nonce:
                raise Exception(f"IA devolvió resultado vacío: {result}")
            return nonce
        except Exception as ex:
            self.logger.error(f"Error comunicando con IA: {ex}")
            raise

    def submit_share(self, job_id, nonce, extra_data=None):
        """
        Enviar resultado a la pool con el formato mining.submit.
        """
        submit_msg = {
            "id": 3,
            "method": "mining.submit",
            "params": {
                "id": self.session_id,
                "job_id": job_id,
                "nonce": nonce,
                "result": "",  # Deja vacío, el pool calculará el resultado real.
                "extra": extra_data or {}
            }
        }
        self._send_json(submit_msg)
        resp = self._recv_json()
        if resp.get("result") == "OK":
            self.logger.info(f"Share enviado y aceptado: nonce={nonce}")
        else:
            self.logger.warning(f"Share no aceptado: respuesta pool={resp}")

    def _send_json(self, data):
        data_raw = (json.dumps(data) + "\n").encode()
        self.sock.sendall(data_raw)

    def _recv_json(self):
        buff = b""
        while b"\n" not in buff:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Desconectado de pool.")
            buff += chunk
        raw_line, buff = buff.split(b"\n", 1)
        return json.loads(raw_line.decode())

    def mining_loop(self):
        self.logger.info("Iniciando bucle minería real IA ↔ Pool")
        while self.is_running:
            try:
                job = self.fetch_job()
                if not job:
                    continue
                # Solicita a la IA el mejor nonce para el blob recibido
                nonce = self.request_nonce_from_ai(job)
                if not self.hash_validator.is_valid(nonce):
                    self.logger.error(f"Nonce inválido recibido de IA: {nonce}")
                    continue
                self.logger.info(f"Nonce válido: {nonce}")
                self.submit_share(job["job_id"], nonce)
            except Exception as ex:
                self.logger.error(f"Error crítico en loop minería: {ex}")
                time.sleep(2)

    def start(self):
        if self.connect_to_pool():
            self.is_running = True
            t = threading.Thread(target=self.mining_loop, daemon=True)
            t.start()
            self.logger.info("Proxy IA iniciado y minando con la pool.")
        else:
            self.logger.error("No se pudo conectar a la pool de minería")

    def stop(self):
        self.is_running = False
        if self.sock:
            self.sock.close()
        self.logger.info("Proxy de IA detenido.")

# Función auxiliar para arrancar el proxy en producción
def start_proxy(wallet_address, pool_host, pool_port, ai_server_url):
    proxy = AIProxyAdapter(wallet_address, pool_host, pool_port, ai_server_url)
    try:
        proxy.start()
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        proxy.stop()
        print("\nProxy detenido")

__all__ = ["AIProxyAdapter", "start_proxy"]

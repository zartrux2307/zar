import json
import threading
import time
import socket
import ssl
from iazar.core.hash_validator import HashValidator
from iazar.core.block_builder import MoneroBlockBuilder
from iazar.bridge.job_sync import JobDistributor

class StratumClientHandler(threading.Thread):
    def __init__(self, conn, addr, job_distributor: JobDistributor):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.job_distributor = job_distributor
        self.job_id = None
        self.extra_nonce = "00000000"
        self.subscription_id = "0000000000000000"
        self.authorized = False
        self.running = True

    def send_json(self, data):
        try:
            message = json.dumps(data) + "\n"
            self.conn.sendall(message.encode())
        except Exception as e:
            print(f"[ERROR] Error enviando JSON a {self.addr}: {e}")
            self.running = False

    def handle_subscribe(self, req_id):
        self.job_id = self.job_distributor.get_current_job_id()
        result = [["mining.set_difficulty", self.subscription_id], self.extra_nonce]
        self.send_json({"id": req_id, "result": result, "error": None})

    def handle_authorize(self, req_id):
        self.authorized = True
        self.send_json({"id": req_id, "result": True, "error": None})
        job = self.job_distributor.get_current_job()
        if job:
            self.send_job(job)

    def handle_submit(self, req_id, params):
        job_id, nonce, result_hash = params[1:4]
        print(f"[INFO] Share recibido: nonce={nonce}, hash={result_hash}")
        if HashValidator().is_valid(result_hash):
            print(f"[OK] Share válido de {self.addr}")
            self.send_json({"id": req_id, "result": True, "error": None})
        else:
            print(f"[WARN] Share inválido de {self.addr}")
            self.send_json({"id": req_id, "result": False, "error": "Invalid share"})

    def send_job(self, job):
        self.job_id = job.get("job_id", "1")
        blob = job.get("blob")
        target = job.get("target")
        if blob and target:
            notify = {
                "id": None,
                "method": "mining.notify",
                "params": [
                    self.job_id,
                    blob,
                    target,
                    False
                ]
            }
            self.send_json(notify)

    def run(self):
        buffer = ""
        self.job_distributor.subscribe(self)
        while self.running:
            try:
                data = self.conn.recv(4096)
                if not data:
                    break
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    message = json.loads(line)
                    method = message.get("method")
                    req_id = message.get("id")
                    params = message.get("params", [])

                    if method == "mining.subscribe":
                        self.handle_subscribe(req_id)
                    elif method == "mining.authorize":
                        self.handle_authorize(req_id)
                    elif method == "mining.submit":
                        self.handle_submit(req_id, params)
            except Exception as e:
                print(f"[ERROR] Conexión cerrada con {self.addr}: {e}")
                break
        self.conn.close()
        self.job_distributor.unsubscribe(self)

class StratumServer:
    def __init__(self, host, port, job_distributor: JobDistributor, use_tls=False, certfile=None, keyfile=None):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.certfile = certfile
        self.keyfile = keyfile
        self.job_distributor = job_distributor
        self.running = True

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)
        print(f"[INFO] Stratum {'TLS' if self.use_tls else 'plain'} en {self.host}:{self.port}")

        if self.use_tls:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)

        while self.running:
            conn, addr = sock.accept()
            if self.use_tls:
                conn = context.wrap_socket(conn, server_side=True)
            print(f"[INFO] Cliente conectado desde {addr}")
            handler = StratumClientHandler(conn, addr, self.job_distributor)
            handler.start()

    def stop(self):
        self.running = False

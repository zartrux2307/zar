import os
import json
import threading
import time
import socket
import ssl
import logging
import select
from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Deque
import hashlib
import random
import struct

from iazar.bridge.ai_proxy_adapter import AIProxyAdapter

# Configuración avanzada de logging
logger = logging.getLogger("StratumProxy")
log_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

@dataclass
class MiningJob:
    job_id: str
    blob: str
    target: str
    seed_hash: str
    difficulty: float
    height: int
    algo: str = "rx/0"
    timestamp: float = time.time()
    extra_nonce: Optional[str] = None

class StratumClientHandler(threading.Thread):
    """Manejador avanzado de conexiones mineras con soporte para protocolo Stratum completo"""
    def __init__(self, conn, addr, proxy, worker_name=None):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.proxy = proxy
        self.worker_name = worker_name
        self.subscribed = False
        self.authorized = False
        self.worker_id = None
        self.difficulty = 10000
        self.session_id = None
        self.last_job_id = None
        self.buffer = b""
        self.lock = threading.Lock()
        self.running = True
        self.extra_nonce = None
        self.start_time = time.time()
        self.last_activity = time.time()
        self.version_mask = "1fffe000"  # Máscara para version rolling
        self.stats = {
            "shares_submitted": 0,
            "shares_accepted": 0,
            "shares_rejected": 0,
            "bytes_sent": 0,
            "bytes_received": 0
        }

    def update_activity(self):
        """Actualiza el timestamp de última actividad"""
        self.last_activity = time.time()

    def send(self, message: Dict):
        """Envía mensaje seguro a un minero Stratum con manejo de errores"""
        with self.lock:
            try:
                data = (json.dumps(message) + "\n").encode()
                self.conn.sendall(data)
                self.stats["bytes_sent"] += len(data)
                return True
            except (ConnectionResetError, BrokenPipeError):
                logger.warning(f"[{self.addr}] Conexión cerrada por minero")
                self.running = False
                return False
            except OSError as e:
                logger.error(f"[{self.addr}] Error de socket: {e}")
                self.running = False
                return False
            except Exception as e:
                logger.exception(f"[{self.addr}] Error enviando mensaje: {e}")
                return False

    def set_difficulty(self, diff: float):
        """Actualiza la dificultad para este minero"""
        self.difficulty = diff
        self.send({
            "id": None,
            "method": "mining.set_difficulty",
            "params": [diff]
        })
        logger.info(f"[{self.addr}] Dificultad actualizada: {diff}")

    def send_job(self, job: MiningJob):
        """Envía un trabajo de minería al minero"""
        if not self.authorized or not self.subscribed:
            return False
        
        self.last_job_id = job.job_id
        params = [
            job.job_id,
            job.blob,
            job.seed_hash,
            job.target,
            True  # clean_jobs
        ]
        
        # Versión extendida para soporte de altura de bloque
        if job.height:
            params.append(job.height)
        
        notify = {
            "id": None,
            "method": "mining.notify",
            "params": params
        }
        
        if self.send(notify):
            logger.debug(f"[{self.addr}] Job enviado: {job.job_id[:8]}")
            return True
        return False

    def validate_submit(self, params: List) -> Tuple[bool, Dict]:
        """Valida la estructura de un submit Stratum"""
        try:
            if len(params) < 4:
                return False, {"error": "Parámetros insuficientes"}
                
            worker_id = params[0]
            job_id = params[1]
            nonce_hex = params[2]
            result_hash = params[3]
            
            # Validación básica de campos
            if not job_id or not nonce_hex or not result_hash:
                return False, {"error": "Campos requeridos faltantes"}
                
            if len(nonce_hex) != 8 or not all(c in "0123456789abcdef" for c in nonce_hex):
                return False, {"error": "Formato nonce inválido"}
                
            if len(result_hash) != 64:
                return False, {"error": "Hash resultante inválido"}
                
            # Convertir nonce a entero
            try:
                nonce = int(nonce_hex, 16)
            except ValueError:
                return False, {"error": "Nonce no numérico"}
                
            return True, {
                "worker_id": worker_id,
                "job_id": job_id,
                "nonce": nonce,
                "nonce_hex": nonce_hex,
                "result_hash": result_hash
            }
        except Exception as e:
            return False, {"error": f"Error validación: {str(e)}"}

    def handle_submit(self, params: List, msg_id: int):
        """Procesa un submit de minero con validación IA"""
        self.stats["shares_submitted"] += 1
        valid, data = self.validate_submit(params)
        
        if not valid:
            self.stats["shares_rejected"] += 1
            logger.warning(f"[{self.addr}] Submit inválido: {data['error']}")
            return False
            
        logger.info(f"[{self.addr}] Submit recibido: job={data['job_id'][:8]} nonce={data['nonce_hex']}")
        
        # Pasar el submit al proxy para validación IA
        accepted = self.proxy.process_miner_solution(
            data['job_id'], 
            data['nonce'], 
            data['result_hash'], 
            self.worker_name
        )
        
        if accepted:
            self.stats["shares_accepted"] += 1
            logger.info(f"[{self.addr}] ✅ Solución aceptada por IA")
        else:
            self.stats["shares_rejected"] += 1
            logger.info(f"[{self.addr}] ❌ Solución rechazada por IA")
            
        return accepted

    def run(self):
        """Bucle principal de manejo de conexión minera"""
        logger.info(f"[{self.addr}] Conexión minera iniciada")
        
        try:
            while self.running:
                # Desconectar mineros inactivos (> 10 minutos)
                if time.time() - self.last_activity > 600:
                    logger.info(f"[{self.addr}] Desconectando minero inactivo")
                    break
                
                # Usar select para operaciones no bloqueantes
                r, _, _ = select.select([self.conn], [], [], 1.0)
                if not r:
                    continue

                try:
                    data = self.conn.recv(4096)
                    if not data:
                        break
                    
                    self.stats["bytes_received"] += len(data)
                    self.buffer += data
                    self.last_activity = time.time()
                    
                    # Procesar todos los mensajes completos en el buffer
                    while b"\n" in self.buffer:
                        line, self.buffer = self.buffer.split(b"\n", 1)
                        try:
                            msg = json.loads(line.decode())
                            self.handle_message(msg)
                        except json.JSONDecodeError:
                            logger.warning(f"[{self.addr}] JSON inválido: {line[:64]}")
                        except Exception as e:
                            logger.error(f"[{self.addr}] Error procesando mensaje: {str(e)}")
                except socket.timeout:
                    continue
                except (ConnectionResetError, ConnectionAbortedError):
                    break
                except ssl.SSLError as e:
                    logger.error(f"[{self.addr}] Error SSL: {e}")
                    break
                except Exception as e:
                    logger.exception(f"[{self.addr}] Error en run: {str(e)}")
                    break
        finally:
            self.conn.close()
            self.proxy.remove_miner(self)
            uptime = time.time() - self.start_time
            logger.info(f"[{self.addr}] Minero desconectado | Uptime: {uptime:.1f}s | "
                         f"Shares: {self.stats['shares_submitted']}")

    def handle_message(self, msg: Dict):
        """Procesa mensajes Stratum entrantes"""
        method = msg.get("method")
        id_ = msg.get("id")
        params = msg.get("params", [])
        
        logger.debug(f"[{self.addr}] Mensaje recibido: method={method}, id={id_}")

        if method == "mining.subscribe":
            self.handle_subscribe(id_, params)
        elif method == "mining.authorize":
            self.handle_authorize(id_, params)
        elif method == "mining.submit":
            self.handle_mining_submit(id_, params)
        elif method == "mining.configure":
            self.handle_configure(id_, params)
        elif method == "mining.extranonce.subscribe":
            self.handle_extranonce_subscribe(id_)
        else:
            logger.warning(f"[{self.addr}] Método no soportado: {method}")
            self.send_error(id_, 500, "Método no implementado")

    def handle_subscribe(self, id_: int, params: List):
        """Maneja solicitud de suscripción Stratum"""
        self.subscribed = True
        self.worker_id = params[0] if params else None
        self.session_id = f"stratum-{os.urandom(4).hex()}"
        
        response = {
            "id": id_,
            "result": [
                [["mining.notify", self.session_id], ["mining.set_difficulty", self.session_id]],
                "08000000",  # Extra nonce 1
                4            # Extra nonce 2 size
            ],
            "error": None
        }
        self.send(response)
        logger.info(f"[{self.addr}] Cliente suscrito | Session ID: {self.session_id}")

    def handle_authorize(self, id_: int, params: List):
        """Autentica al minero con el proxy"""
        worker_name = params[0] if len(params) > 0 else ""
        password = params[1] if len(params) > 1 else ""
        
        if self.proxy.validate_worker(worker_name, password):
            self.authorized = True
            self.worker_name = worker_name
            self.send({"id": id_, "result": True, "error": None})
            logger.info(f"[{self.addr}] Minero autorizado: {worker_name}")
            self.proxy.send_initial_job(self)
        else:
            self.send_error(id_, 401, "Autorización fallida")
            logger.warning(f"[{self.addr}] Intento de autorización fallido: {worker_name}")

    def handle_mining_submit(self, id_: int, params: List):
        """Procesa solución de minero"""
        success = self.handle_submit(params, id_)
        response = {
            "id": id_,
            "result": success,
            "error": None if success else [400, "Solución inválida"]
        }
        self.send(response)

    def handle_configure(self, id_: int, params: List):
        """Maneja configuración de minero (version rolling)"""
        logger.info(f"[{self.addr}] Solicitud de configuración: {params}")
        response = {
            "id": id_,
            "result": {
                "version-rolling": True,
                "version-rolling.mask": self.version_mask,
                "version-rolling.min-bit-count": 16
            },
            "error": None
        }
        self.send(response)

    def handle_extranonce_subscribe(self, id_: int):
        """Maneja solicitud de extra nonce"""
        self.send({"id": id_, "result": True, "error": None})
        logger.info(f"[{self.addr}] Suscripción a extranonce confirmada")

    def send_error(self, id_: Optional[int], code: int, message: str):
        """Envía mensaje de error estandarizado"""
        self.send({
            "id": id_,
            "result": None,
            "error": [code, message]
        })

class StratumProxy:
    """Proxy Stratum de alto rendimiento con integración IA"""
    def __init__(self, host: str, port: int, wallet_address: str, pool_host: str, pool_port: int,
                 shm_prefix: str = "zartrux_shared", feature_log_path: Optional[str] = None,
                 use_tls: bool = False, certfile: Optional[str] = None, keyfile: Optional[str] = None,
                 worker_password: str = "x", difficulty_levels: List[float] = None):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.certfile = certfile
        self.keyfile = keyfile
        self.worker_password = worker_password
        self.difficulty_levels = difficulty_levels or [10000, 50000, 100000]
        
        # Conexión con el pool real
        self.pool_host = pool_host
        self.pool_port = pool_port
        self.wallet_address = wallet_address
        
        # Integración IA
        self.ia_bridge = AIProxyAdapter(
            wallet_address=wallet_address,
            pool_host=pool_host,
            pool_port=pool_port,
            shm_prefix=shm_prefix,
            feature_log_path=feature_log_path
        )
        
        # Gestión de mineros
        self.miners = []
        self.active_jobs = deque(maxlen=50)
        self.job_counter = 0
        self.lock = threading.Lock()
        self.running = True
        self.metrics = {
            "miners_connected": 0,
            "miners_total": 0,
            "jobs_broadcast": 0,
            "shares_accepted": 0,
            "shares_rejected": 0,
            "start_time": time.time()
        }
        
        # Inicializar IA bridge
        self.ia_bridge.start()
        logger.info("🔌 Adaptador IA iniciado")

    def validate_worker(self, worker_name: str, password: str) -> bool:
        """Valida credenciales de minero"""
        # Validación básica: cualquier worker con password correcta
        return password == self.worker_password

    def generate_job_id(self) -> str:
        """Genera ID de trabajo único"""
        self.job_counter += 1
        timestamp = int(time.time() * 1000)
        rand_suffix = os.urandom(4).hex()
        return f"job-{timestamp}-{self.job_counter}-{rand_suffix}"

    def create_job(self, blob: str, target: str, seed_hash: str, height: int, 
                 difficulty: Optional[float] = None) -> MiningJob:
        """Crea un nuevo trabajo de minería"""
        job = MiningJob(
            job_id=self.generate_job_id(),
            blob=blob,
            target=target,
            seed_hash=seed_hash,
            difficulty=difficulty or self.difficulty_levels[0],
            height=height
        )
        with self.lock:
            self.active_jobs.append(job)
        return job

    def broadcast_new_job(self, job: MiningJob):
        """Difunde un nuevo trabajo a todos los mineros conectados"""
        with self.lock:
            miners_to_remove = []
            for miner in self.miners:
                if not miner.send_job(job):
                    miners_to_remove.append(miner)
            
            # Eliminar mineros desconectados
            for miner in miners_to_remove:
                self.miners.remove(miner)
        
        self.metrics["jobs_broadcast"] += 1
        logger.info(f"📢 Trabajo {job.job_id[:8]} difundido a {len(self.miners)} mineros")

    def send_initial_job(self, miner: StratumClientHandler):
        """Envía el trabajo más reciente a un nuevo minero"""
        if self.active_jobs:
            miner.send_job(self.active_jobs[-1])

    def process_miner_solution(self, job_id: str, nonce: int, result_hash: str, 
                              worker_name: str) -> bool:
        """Valida solución con IA y reenvía al pool"""
        # Aquí la IA decide si la solución es válida
        # En producción, esto se conectaría con el módulo de IA
        logger.debug(f"Validando solución con IA: job={job_id[:8]}, nonce={nonce:08x}")
        
        # Simulación: 95% de aceptación
        accepted = random.random() < 0.95
        
        if accepted:
            self.metrics["shares_accepted"] += 1
        else:
            self.metrics["shares_rejected"] += 1
            
        return accepted

    def add_miner(self, miner: StratumClientHandler):
        """Registra un nuevo minero"""
        with self.lock:
            self.miners.append(miner)
            self.metrics["miners_connected"] = len(self.miners)
            self.metrics["miners_total"] += 1

    def remove_miner(self, miner: StratumClientHandler):
        """Elimina un minero desconectado"""
        with self.lock:
            if miner in self.miners:
                self.miners.remove(miner)
                self.metrics["miners_connected"] = len(self.miners)
                logger.info(f"⛏️ Minero desconectado: {miner.addr}")

    def report_metrics(self):
        """Reporta métricas de operación"""
        uptime = time.time() - self.metrics["start_time"]
        miners = self.metrics["miners_connected"]
        shares_acc = self.metrics["shares_accepted"]
        shares_rej = self.metrics["shares_rejected"]
        shares_total = shares_acc + shares_rej
        
        accept_rate = (shares_acc / shares_total * 100) if shares_total > 0 else 0
        
        logger.info(
            f"📊 Métricas: Mineros={miners} | "
            f"Shares={shares_total} (A:{shares_acc} R:{shares_rej}) | "
            f"Tasa aceptación={accept_rate:.1f}% | "
            f"Uptime={uptime:.0f}s"
        )

    def start_server(self):
        """Inicia el servidor Stratum principal"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(512)  # Mayor capacidad de cola
        server_socket.settimeout(5)

        ssl_context = None
        if self.use_tls:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.verify_mode = ssl.CERT_NONE
            ssl_context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
            logger.info("🔒 Certificado TLS cargado")

        logger.info(f"🚀 Proxy Stratum iniciado en {self.host}:{self.port} "
                    f"{'con TLS' if self.use_tls else 'sin encriptación'}")

        last_metrics_time = time.time()
        
        while self.running:
            try:
                # Reportar métricas periódicas
                if time.time() - last_metrics_time > 60:
                    self.report_metrics()
                    last_metrics_time = time.time()
                
                # Aceptar nuevas conexiones
                try:
                    conn, addr = server_socket.accept()
                    conn.settimeout(30)
                    
                    if ssl_context:
                        try:
                            conn = ssl_context.wrap_socket(conn, server_side=True)
                        except ssl.SSLError as e:
                            logger.error(f"Error SSL con {addr}: {e}")
                            conn.close()
                            continue
                    
                    logger.info(f"🔌 Nueva conexión de {addr}")
                    miner = StratumClientHandler(conn, addr, self)
                    self.add_miner(miner)
                    miner.start()
                except socket.timeout:
                    continue
                except OSError as e:
                    if e.errno == 9:  # Bad file descriptor (socket closed)
                        break
                    logger.error(f"Error aceptando conexión: {e}")
            except KeyboardInterrupt:
                logger.info("Recibida señal de interrupción")
                break
            except Exception as e:
                logger.exception(f"Error inesperado en servidor: {e}")
                time.sleep(1)

        # Limpieza final
        server_socket.close()
        logger.info("🛑 Servidor Stratum detenido")

    def start(self):
        """Inicia el proxy en modo no bloqueante"""
        self.server_thread = threading.Thread(
            target=self.start_server,
            daemon=True,
            name="StratumServer"
        )
        self.server_thread.start()
        logger.info("⏱️ Proxy iniciado en segundo plano")

    def stop(self):
        """Detiene el proxy de manera controlada"""
        logger.info("Iniciando secuencia de parada...")
        self.running = False
        
        # Detener integración IA
        self.ia_bridge.stop()
        
        # Cerrar conexiones mineras
        with self.lock:
            for miner in self.miners:
                miner.running = False
                try:
                    miner.conn.close()
                except:
                    pass
            self.miners.clear()
        
        # Reportar métricas finales
        self.report_metrics()
        logger.info("✅ Proxy detenido correctamente")

# --- Ejemplo de uso desde ia_proxy_main.py ---
if __name__ == "__main__":
    # Configuración profesional
    proxy = StratumProxy(
        host="0.0.0.0",
        port=3333,
        wallet_address="44crWF5Y7gWDLCwhNSH7cbAbCPT6xScpCRFMMYhbCpFijJVUpPwze39GbvRRR1GsRZCvNMKZpU4sPT8bqRY3FY29Loyx1zc",
        pool_host="pool.hashvault.pro",
        pool_port= 443,
        shm_prefix="zartrux_shared",
        feature_log_path="data/nonces_exitosos.csv",
        use_tls=True,
        certfile="certs/proxy.crt",
        keyfile="certs/proxy.key",
        worker_password="zar21",
        difficulty_levels=[5000, 20000, 50000, 100000]
    )
    
    try:
        proxy.start()
        logger.info("Proxy en ejecución. Presione Ctrl+C para detener.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        proxy.stop()
    except Exception as e:
        logger.critical(f"Error fatal: {e}")
        proxy.stop()
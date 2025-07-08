import logging
import time
import struct
import socket
import ssl
import os
import json
import threading
from enum import IntEnum
from typing import Optional, Dict, Any, Tuple, List
from collections import deque
import random
import concurrent.futures
import hashlib  # Added for TLS fingerprint validation

from iazar.core.randomx_handler import RandomXHandler
from iazar.core.hash_validator import HashValidator
from iazar.utils.config_manager import get_ia_config
from iazar.utils.feature_utils import COLUMNS
from iazar.bridge.shared_memory_manager import SharedMemoryManager

# Configuración avanzada de logging
logger = logging.getLogger("IA-Zar-Proxy")
log_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

class ConnectionState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3
    SHUTTING_DOWN = 4

class AIProxyAdapter:
    """
    Adaptador profesional para integración IA ↔ Proxy ↔ Pool de minería
    con manejo avanzado de conexiones, métricas y optimización de recursos.
    """
    def __init__(self, wallet_address: str, pool_host: str, pool_port: int, 
                 shm_prefix: str = "zartrux_shared", feature_log_path: Optional[str] = None, 
                 password: str = "x", tls: bool = True, ai_timeout: float = 3.0):
        self.wallet_address = wallet_address
        self.pool_host = pool_host
        self.pool_port = int(pool_port)
        self.pool_password = password
        self.tls = tls
        self.ai_timeout = ai_timeout
        self.randomx = RandomXHandler()
        self.hash_validator = HashValidator()
        self.config = get_ia_config()
        self.feature_log_path = feature_log_path or os.path.join(
            self.config["data_paths"]["successful_nonces"], 
            f"nonces_{int(time.time())}.csv"
        )
        self.connection_state = ConnectionState.DISCONNECTED
        self.sock = None
        self.session_id = None
        self.job = None
        self.is_running = True
        self.recv_buffer = b""
        self.lock = threading.Lock()
        self.backoff_factor = 1
        self.max_backoff = 60
        
        # Estadísticas avanzadas
        self.metrics = {
            "shares_submitted": 0,
            "shares_accepted": 0,
            "shares_rejected": 0,
            "ai_response_time": deque(maxlen=100),
            "connection_errors": 0,
            "ai_timeouts": 0,
            "last_block_height": 0,
            "start_time": time.monotonic()
        }

        # Memoria compartida con gestión de conexión segura
        self.shm = SharedMemoryManager(prefix=shm_prefix)
        self.shutdown_event = threading.Event()

        # Thread pool para operaciones concurrentes
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="ProxyWorker"
        )

        # Configuración de TLS
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def safe_connect(self) -> bool:
        """Establece conexión con backoff exponencial y manejo robusto de errores"""
        self.connection_state = ConnectionState.CONNECTING
        attempt = 0
        
        while not self.shutdown_event.is_set():
            try:
                logger.info(f"Conectando (intento {attempt+1}) a {self.pool_host}:{self.pool_port} {'(TLS)' if self.tls else ''}")
                
                # Crear conexión base
                sock = socket.create_connection(
                    (self.pool_host, self.pool_port), 
                    timeout=min(10 + attempt * 2, 30)
                )
                
                # Aplicar TLS si es necesario
                if self.tls:
                    self.sock = self.ssl_context.wrap_socket(
                        sock, 
                        server_hostname=self.pool_host
                    )
                else:
                    self.sock = sock
                
                self.sock.settimeout(15)
                self.recv_buffer = b""
                
                if self._perform_handshake():
                    self.connection_state = ConnectionState.CONNECTED
                    self.backoff_factor = 1
                    return True
            
            except (socket.timeout, ConnectionRefusedError) as e:
                logger.warning(f"Error de conexión temporal: {str(e)}")
            except (ssl.SSLError, OSError) as e:
                logger.error(f"Error crítico de conexión: {str(e)}")
                self.metrics["connection_errors"] += 1
            except Exception as e:
                logger.exception(f"Error inesperado en conexión: {str(e)}")
            
            # Backoff exponencial con jitter
            sleep_time = min(self.backoff_factor + random.uniform(0, 1), self.max_backoff)
            logger.info(f"Reintentando en {sleep_time:.1f} segundos...")
            self.shutdown_event.wait(sleep_time)
            
            self.backoff_factor *= 2
            attempt += 1
        
        return False

    def _perform_handshake(self) -> bool:
        """Handshake Stratum completo con validación de respuestas y TLS fingerprint"""
        try:
            # Validación de fingerprint TLS
            if self.tls:
                expected_fingerprint = "420c7850e09b7c0bdcf748a7da9eb3647daf8515718f36d9ccfdd6b9ff834b14"
                cert = self.sock.getpeercert(binary_form=True)
                actual_fingerprint = hashlib.sha256(cert).hexdigest()
                
                if actual_fingerprint != expected_fingerprint:
                    raise ssl.SSLError(f"Invalid TLS fingerprint: {actual_fingerprint}")

            # Fase de suscripción con formato actualizado
            subscribe_msg = {
                "id": 1,
                "jsonrpc": "2.0",  # Especificación JSON-RPC
                "method": "mining.subscribe",
                "params": ["IA-Zar-Proxy/v2.0", None]  # Agente de usuario
            }
            self._send_json(subscribe_msg)
            sub_resp = self._recv_json(timeout=15)  # Timeout aumentado
            
            if not sub_resp or "result" not in sub_resp:
                raise ConnectionError(f"Respuesta subscribe inválida: {sub_resp}")
            
            # Extracción mejorada de session ID (compatible con Hashvault)
            if isinstance(sub_resp["result"], list):
                # Nuevo formato: [subscription_info, extranonce1, extranonce2_size]
                if len(sub_resp["result"]) > 1 and isinstance(sub_resp["result"][1], str):
                    self.session_id = sub_resp["result"][1]  # extranonce1 como session ID
                elif len(sub_resp["result"]) > 0:
                    # Formato tradicional
                    self.session_id = sub_resp["result"][0][0] if isinstance(sub_resp["result"][0], list) else sub_resp["result"][0]
            elif isinstance(sub_resp["result"], dict):
                self.session_id = sub_resp["result"].get("id")
            else:
                self.session_id = str(sub_resp["id"])
            
            logger.info(f"Subscripción exitosa | Session ID: {self.session_id}")
            
            # Fase de autenticación
            login_msg = {
                "id": 2,
                "jsonrpc": "2.0",
                "method": "mining.login",
                "params": {
                    "login": self.wallet_address,
                    "pass": self.pool_password,
                    "agent": "IA-Zar-Proxy/v2.0"
                }
            }
            self._send_json(login_msg)
            login_resp = self._recv_json(timeout=10)
            
            if not login_resp:
                raise ConnectionError("No se recibió respuesta de login")
            
            # Validar diferentes formatos de respuesta exitosa
            login_ok = (
                (isinstance(login_resp.get("result"), dict) and login_resp["result"].get("status") == "OK") or
                (login_resp.get("result") is True) or
                (isinstance(login_resp.get("result"), str) and "OK" in login_resp["result"])
            )
            
            if not login_ok:
                error_msg = login_resp.get("error", [None, "Error desconocido"])[1]
                raise ConnectionError(f"Login fallido: {error_msg}")
            
            logger.info("Autenticación exitosa con el pool")
            return True
        
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando respuesta: {str(e)}")
            return False
        except ConnectionError as e:
            logger.error(str(e))
            return False

    # ... (rest of the methods remain unchanged) ...

    def _send_json(self, data: Dict):
        """Envía datos JSON con manejo robusto de errores de conexión"""
        try:
            payload = (json.dumps(data) + "\n").encode()
            with self.lock:
                self.sock.sendall(payload)
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning(f"Error de conexión al enviar: {str(e)}")
            self.connection_state = ConnectionState.ERROR
        except OSError as e:
            logger.error(f"Error crítico de socket: {str(e)}")
            self.connection_state = ConnectionState.ERROR
        except Exception as e:
            logger.exception(f"Error inesperado al enviar: {str(e)}")
            self.connection_state = ConnectionState.ERROR

    def _recv_json(self, timeout: float = 30) -> Optional[Dict]:
        """Recibe datos JSON con manejo de fragmentación y timeout"""
        start_time = time.monotonic()
        
        try:
            self.sock.settimeout(timeout)
            
            while time.monotonic() - start_time < timeout:
                # Buscar mensaje completo en buffer
                if b"\n" in self.recv_buffer:
                    line, self.recv_buffer = self.recv_buffer.split(b"\n", 1)
                    return json.loads(line.decode(errors="ignore"))
                
                # Recibir más datos
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("Conexión cerrada por el pool")
                    self.recv_buffer += chunk
                except socket.timeout:
                    continue
            
            logger.warning(f"Timeout recibiendo datos después de {timeout} segundos")
            return None
        
        except (ConnectionError, json.JSONDecodeError) as e:
            logger.warning(f"Error recibiendo JSON: {str(e)}")
            return None
        except ssl.SSLError as e:
            logger.error(f"Error SSL: {str(e)}")
            self.connection_state = ConnectionState.ERROR
            return None
        except Exception as e:
            logger.exception(f"Error inesperado recibiendo datos: {str(e)}")
            return None

    def fetch_job(self, timeout: float = 60) -> Optional[Dict[str, Any]]:
        """Obtiene trabajo del pool con manejo de múltiples mensajes"""
        start_time = time.monotonic()
        
        while time.monotonic() - start_time < timeout:
            resp = self._recv_json(timeout=1)
            if not resp:
                continue
                 
            # Manejar diferentes tipos de mensajes
            if resp.get("method") == "mining.job":
                return self._parse_job(resp["params"])
            elif resp.get("method") == "mining.set_difficulty":
                logger.info(f"Nueva dificultad: {resp['params'][0]}")
            elif resp.get("method") == "mining.notify":
                return self._parse_job(resp["params"])
            elif resp.get("result"):
                logger.debug(f"Mensaje del pool: {resp['result']}")
        
        logger.warning("Timeout esperando trabajo del pool")
        return None

    def _parse_job(self, params: Any) -> Dict[str, Any]:
        """Parsea diferentes formatos de trabajos Stratum"""
        try:
            # Formato de lista (Stratum tradicional)
            if isinstance(params, list) and len(params) >= 4:
                return {
                    "job_id": params[0],
                    "blob": params[1],
                    "target": params[3],
                    "seed_hash": params[2] if len(params) > 2 else "",
                    "height": params[4] if len(params) > 4 else 0,
                    "algo": "rx/0"
                }
            # Formato de objeto (Stratum extendido)
            elif isinstance(params, dict):
                return {
                    "job_id": params.get("job_id"),
                    "blob": params.get("blob"),
                    "target": params.get("target"),
                    "seed_hash": params.get("seed_hash", ""),
                    "height": params.get("height", 0),
                    "algo": params.get("algo", "rx/0")
                }
            else:
                raise ValueError(f"Formato de trabajo no reconocido: {type(params)}")
        except Exception as e:
            logger.exception(f"Error parseando trabajo: {str(e)}")
            return None

    def request_nonce_from_ai(self, job_data: Dict) -> Optional[Dict]:
        """Solicita nonce a IA con timeout configurable y validación"""
        t0 = time.monotonic()
        
        try:
            # Enviar trabajo a la IA
            self.shm.set_job(job_data)
            
            # Esperar solución con timeout
            while time.monotonic() - t0 < self.ai_timeout:
                if self.shm.is_solution_ready():
                    solution = self.shm.get_solution()
                    if self._validate_solution(solution):
                        latency = time.monotonic() - t0
                        self.metrics["ai_response_time"].append(latency)
                        logger.info(f"Nonce IA recibido en {latency:.3f}s: {solution['nonce']}")
                        return solution
                time.sleep(0.01)
            
            # Timeout
            self.metrics["ai_timeouts"] += 1
            logger.warning(f"Timeout esperando solución de IA ({self.ai_timeout}s)")
            return None
            
        except Exception as e:
            logger.exception(f"Error solicitando nonce a IA: {str(e)}")
            return None

    def _validate_solution(self, solution: Dict) -> bool:
        """Validación avanzada de solución de IA"""
        try:
            # Validación básica de estructura
            if not all(key in solution for key in ["nonce", "is_valid"] + COLUMNS):
                logger.warning("Solución de IA incompleta")
                return False
                
            # Validación de tipos
            if not isinstance(solution["nonce"], int) or solution["nonce"] < 0 or solution["nonce"] > 0xFFFFFFFF:
                logger.warning(f"Nonce inválido: {solution['nonce']}")
                return False
                
            # Validación de bandera
            if not isinstance(solution["is_valid"], int) or solution["is_valid"] not in (0, 1):
                logger.warning(f"Bandera is_valid inválida: {solution['is_valid']}")
                return False
                
            return True
        except Exception:
            return False

    def submit_share(self, job_id: str, solution: Dict):
        """Envía share al pool con manejo de errores y registro de features"""
        try:
            self.metrics["shares_submitted"] += 1
            
            # Construir mensaje de submit
            submit_msg = {
                "id": 3,
                "method": "mining.submit",
                "params": {
                    "id": self.session_id,
                    "job_id": job_id,
                    "nonce": f"{solution['nonce']:08x}",
                    "result": "",  # Pool calculará el hash
                    "extra": {col: solution[col] for col in COLUMNS}
                }
            }
            
            # Enviar y esperar respuesta
            self._send_json(submit_msg)
            resp = self._recv_json(timeout=10)
            
            # Registrar features independientemente del resultado
            guardar_nonces_csv([solution], self.feature_log_path)
            
            # Interpretar respuesta
            if resp and resp.get("result") == "OK":
                self.metrics["shares_accepted"] += 1
                logger.info(f" Share aceptado: job={job_id}, nonce=0x{solution['nonce']:08x}")
            else:
                self.metrics["shares_rejected"] += 1
                error = resp.get('error', ['-1', 'Error desconocido'])[1] if resp else "Sin respuesta"
                logger.warning(f" Share rechazado: {error}")
        
        except Exception as e:
            logger.exception(f"Error crítico enviando share: {str(e)}")

    def mining_loop(self):
        """Bucle principal de minería con gestión avanzada de errores"""
        logger.info("Iniciando bucle de minería IA-Pool")
        
        while not self.shutdown_event.is_set():
            try:
                # Reconectar si es necesario
                if self.connection_state != ConnectionState.CONNECTED:
                    if not self.safe_connect():
                        time.sleep(5)
                        continue
                
                # Obtener trabajo
                job = self.fetch_job()
                if not job:
                    time.sleep(1)
                    continue
                
                # Actualizar métricas
                if job.get("height") and job["height"] > self.metrics["last_block_height"]:
                    self.metrics["last_block_height"] = job["height"]
                    logger.info(f"🔨 Nuevo bloque: {job['height']}")
                
                # Solicitar nonce a IA
                solution = self.request_nonce_from_ai(job)
                
                # Fallback a nonce aleatorio si IA no responde
                if not solution:
                    solution = {
                        "nonce": random.randint(0, 0xFFFFFFFF),
                        "is_valid": 0,
                        **{col: 0.0 for col in COLUMNS}
                    }
                    logger.info("Usando nonce aleatorio como fallback")
                
                # Enviar share
                self.executor.submit(self.submit_share, job["job_id"], solution)
                
                # Reportar métricas periódicamente
                if self.metrics["shares_submitted"] % 10 == 0:
                    self.report_metrics()
            
            except Exception as e:
                logger.exception(f"Error en bucle de minería: {str(e)}")
                time.sleep(5)

    def report_metrics(self):
        """Reporta métricas avanzadas con análisis de rendimiento"""
        elapsed = time.monotonic() - self.metrics["start_time"]
        shares = self.metrics["shares_submitted"]
        accepted = self.metrics["shares_accepted"]
        rejected = self.metrics["shares_rejected"]
        
        # Calcular tasas
        accept_rate = (accepted / shares) * 100 if shares > 0 else 0
        reject_rate = (rejected / shares) * 100 if shares > 0 else 0
        
        # Calcular latencia IA
        ai_times = list(self.metrics["ai_response_time"])
        avg_latency = sum(ai_times) / len(ai_times) if ai_times else 0
        max_latency = max(ai_times) if ai_times else 0
        
        # Reporte completo
        logger.info(
            f"\n{'='*50}\n"
            f" Reporte de Métricas\n"
            f"{'-'*50}\n"
            f"• Shares enviados: {shares}\n"
            f"• Aceptados: {accepted} ({accept_rate:.1f}%)\n"
            f"• Rechazados: {rejected} ({reject_rate:.1f}%)\n"
            f"• Latencia IA: {avg_latency:.3f}s (avg) | {max_latency:.3f}s (max)\n"
            f"• Timeouts IA: {self.metrics['ai_timeouts']}\n"
            f"• Errores conexión: {self.metrics['connection_errors']}\n"
            f"• Altura bloque: {self.metrics['last_block_height']}\n"
            f"• Uptime: {elapsed:.1f}s\n"
            f"{'='*50}"
        )

    def start(self):
        """Inicia el proxy en modo no bloqueante"""
        if self.connection_state == ConnectionState.CONNECTED:
            logger.warning("Proxy ya está en ejecución")
            return False
            
        # Iniciar conexión
        if self.safe_connect():
            # Iniciar bucle de minería en hilo separado
            self.mining_thread = threading.Thread(
                target=self.mining_loop, 
                daemon=True,
                name="MiningLoop"
            )
            self.mining_thread.start()
            logger.info("Proxy IA iniciado correctamente")
            return True
        return False

    def stop(self):
        """Detiene el proxy de manera controlada"""
        logger.info("Iniciando secuencia de parada...")
        self.is_running = False
        self.shutdown_event.set()
        self.connection_state = ConnectionState.SHUTTING_DOWN
        
        # Cerrar conexiones
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        
        # Esperar a que los hilos terminen
        self.executor.shutdown(wait=True)
        
        # Reportar métricas finales
        self.report_metrics()
        logger.info("Proxy detenido correctamente")

def start_proxy(wallet_address: str, pool_host: str, pool_port: int, shm_prefix: str = "zartrux_shared"):
    """Función de inicio con manejo profesional de excepciones"""
    proxy = None
    try:
        logger.info(f"""
        {'='*50}
         Iniciando IA-Zar Proxy (v2.0)
         Wallet: {wallet_address}
         Pool: {pool_host}:{pool_port}
         SHM Prefix: {shm_prefix}
        {'='*50}
        """)
        
        proxy = AIProxyAdapter(wallet_address, pool_host, pool_port, shm_prefix)
        proxy.start()
        
        # Mantener el hilo principal activo
        while not proxy.shutdown_event.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Recibida señal de interrupción")
    except Exception as e:
        logger.critical(f"Error fatal: {str(e)}")
    finally:
        if proxy:
            proxy.stop()

__all__ = ("AIProxyAdapter", "start_proxy")
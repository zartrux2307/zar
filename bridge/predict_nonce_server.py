import logging
import time
import socket
import ssl
import os
import json
import threading
import struct
import random
import concurrent.futures
from enum import IntEnum
from typing import Optional, Dict, Any, List, Tuple
from collections import deque
import multiprocessing.shared_memory as shm

from iazar.core.randomx_handler import RandomXHandler
from iazar.core.hash_validator import HashValidator
from iazar.utils.config_manager import get_ia_config
from iazar.utils.feature_utils import COLUMNS, guardar_nonces_csv

# Configuración avanzada de logging
logger = logging.getLogger("IA-Zar-Proxy")
log_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

# Tamaños de estructuras binarias
JOB_STRUCT_SIZE = 176  # 84 + 8 + 32 + 32 + 4 + 16
SOLUTION_STRUCT_SIZE = 69  # 4 + 1 + (8*8)
SHM_JOB_SIZE = JOB_STRUCT_SIZE + 1  # +1 byte para bandera
SHM_SOLUTION_SIZE = SOLUTION_STRUCT_SIZE + 1  # +1 byte para bandera

class ConnectionState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3
    SHUTTING_DOWN = 4

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
                struct.pack('>d', solution[col]) for col in COLUMNS
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
                'is_valid': data[4]
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

class AIProxyAdapter:
    """
    Adaptador profesional para integración IA ↔ Proxy ↔ Pool de minería
    con protocolo binario de memoria compartida
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

        # Memoria compartida con protocolo binario
        self.shm = BinSharedMemoryManager(prefix=shm_prefix)
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
                logger.info("Conectando (intento %d) a %s:%d %s", 
                           attempt+1, self.pool_host, self.pool_port, 
                           "(TLS)" if self.tls else "")
                
                # Crear conexión base con timeout dinámico
                connect_timeout = min(10 + attempt * 2, 30)
                sock = socket.create_connection(
                    (self.pool_host, self.pool_port), 
                    timeout=connect_timeout
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
                logger.warning("Error de conexión temporal: %s", str(e))
            except (ssl.SSLError, OSError) as e:
                logger.error("Error crítico de conexión: %s", str(e))
                self.metrics["connection_errors"] += 1
            except Exception as e:
                logger.exception("Error inesperado en conexión: %s", str(e))
            
            # Backoff exponencial con jitter
            sleep_time = min(self.backoff_factor + random.uniform(0, 1), self.max_backoff)
            logger.info("Reintentando en %.1f segundos...", sleep_time)
            self.shutdown_event.wait(sleep_time)
            
            self.backoff_factor *= 2
            attempt += 1
        
        return False

    def _perform_handshake(self) -> bool:
        """Handshake Stratum completo con validación de respuestas"""
        try:
            # Fase de suscripción
            subscribe_msg = {"id": 1, "method": "mining.subscribe", "params": []}
            self._send_json(subscribe_msg)
            sub_resp = self._recv_json(timeout=10)
            
            if not sub_resp or "result" not in sub_resp:
                raise ConnectionError(f"Respuesta subscribe inválida: {sub_resp}")
            
            # Extraer session ID de diferentes formatos de respuesta
            result = sub_resp["result"]
            if isinstance(result, list) and len(result) > 0:
                self.session_id = result[0][0] if isinstance(result[0], list) else result[0]
            elif isinstance(result, dict):
                self.session_id = result.get("id")
            else:
                self.session_id = str(sub_resp.get("id", "unknown"))
            
            logger.info("Subscripción exitosa | Session ID: %s", self.session_id)
            
            # Fase de autenticación
            login_msg = {
                "id": 2,
                "method": "mining.login",
                "params": {
                    "login": self.wallet_address,
                    "pass": self.pool_password,
                    "agent": "IA-Zar-Proxy/v3.0"
                }
            }
            self._send_json(login_msg)
            login_resp = self._recv_json(timeout=10)
            
            if not login_resp:
                raise ConnectionError("No se recibió respuesta de login")
            
            # Validar diferentes formatos de respuesta exitosa
            result = login_resp.get("result")
            login_ok = (
                (isinstance(result, dict) and result.get("status") == "OK") or
                (result is True) or
                (isinstance(result, str) and "OK" in result)
            )
            
            if not login_ok:
                error = login_resp.get("error", [None, "Error desconocido"])
                error_msg = error[1] if isinstance(error, list) and len(error) > 1 else str(error)
                raise ConnectionError(f"Login fallido: {error_msg}")
            
            logger.info("Autenticación exitosa con el pool")
            return True
        
        except json.JSONDecodeError as e:
            logger.error("Error decodificando respuesta: %s", str(e))
            return False
        except ConnectionError as e:
            logger.error(str(e))
            return False

    def _send_json(self, data: Dict):
        """Envía datos JSON con manejo robusto de errores de conexión"""
        try:
            payload = (json.dumps(data) + "\n").encode()
            with self.lock:
                self.sock.sendall(payload)
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning("Error de conexión al enviar: %s", str(e))
            self.connection_state = ConnectionState.ERROR
        except OSError as e:
            logger.error("Error crítico de socket: %s", str(e))
            self.connection_state = ConnectionState.ERROR
        except Exception as e:
            logger.exception("Error inesperado al enviar: %s", str(e))
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
                    try:
                        return json.loads(line.decode(errors="ignore"))
                    except json.JSONDecodeError:
                        continue
                
                # Recibir más datos
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("Conexión cerrada por el pool")
                    self.recv_buffer += chunk
                except socket.timeout:
                    continue
            
            logger.warning("Timeout recibiendo datos después de %d segundos", timeout)
            return None
        
        except (ConnectionError, json.JSONDecodeError) as e:
            logger.warning("Error recibiendo JSON: %s", str(e))
            return None
        except ssl.SSLError as e:
            logger.error("Error SSL: %s", str(e))
            self.connection_state = ConnectionState.ERROR
            return None
        except Exception as e:
            logger.exception("Error inesperado recibiendo datos: %s", str(e))
            return None

    def fetch_job(self, timeout: float = 60) -> Optional[Dict[str, Any]]:
        """Obtiene trabajo del pool con manejo de múltiples mensajes"""
        start_time = time.monotonic()
        
        while time.monotonic() - start_time < timeout:
            resp = self._recv_json(timeout=1)
            if not resp:
                continue
                 
            # Manejar diferentes tipos de mensajes
            method = resp.get("method")
            if method == "mining.job":
                return self._parse_job(resp["params"])
            elif method == "mining.set_difficulty":
                logger.info("Nueva dificultad: %s", resp['params'][0])
            elif method == "mining.notify":
                return self._parse_job(resp["params"])
            elif resp.get("result"):
                logger.debug("Mensaje del pool: %s", resp['result'])
        
        logger.warning("Timeout esperando trabajo del pool")
        return None

    def _parse_job(self, params: Any) -> Optional[Dict[str, Any]]:
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
            logger.exception("Error parseando trabajo: %s", str(e))
            return None

    def request_nonce_from_ai(self, job_data: Dict) -> Optional[Dict]:
        """Solicita nonce a IA con protocolo binario de memoria compartida"""
        t0 = time.monotonic()
        
        try:
            # Enviar trabajo a la IA
            self.shm.set_job(job_data)
            
            # Esperar solución con timeout
            solution = self.shm.get_solution(self.ai_timeout)
            if solution:
                if self._validate_solution(solution):
                    latency = time.monotonic() - t0
                    self.metrics["ai_response_time"].append(latency)
                    logger.info("Nonce IA recibido en %.3fs: %d", latency, solution['nonce'])
                    return solution
            else:
                # Timeout
                self.metrics["ai_timeouts"] += 1
                logger.warning("Timeout esperando solución de IA (%.1fs)", self.ai_timeout)
            
            return None
            
        except Exception as e:
            logger.exception("Error solicitando nonce a IA: %s", str(e))
            return None

    def _validate_solution(self, solution: Dict) -> bool:
        """Validación avanzada de solución de IA"""
        try:
            # Validación básica de estructura
            required_keys = ["nonce", "is_valid"] + COLUMNS
            if not all(key in solution for key in required_keys):
                missing = [key for key in required_keys if key not in solution]
                logger.warning("Solución de IA incompleta. Faltan: %s", missing)
                return False
                
            # Validación de tipos
            nonce = solution["nonce"]
            if not isinstance(nonce, int) or nonce < 0 or nonce > 0xFFFFFFFF:
                logger.warning("Nonce inválido: %d (0x%x)", nonce, nonce)
                return False
                
            # Validación de bandera
            is_valid = solution["is_valid"]
            if not isinstance(is_valid, int) or is_valid not in (0, 1):
                logger.warning("Bandera is_valid inválida: %s", is_valid)
                return False
                
            return True
        except Exception as e:
            logger.exception("Error en validación de solución: %s", str(e))
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
            try:
                guardar_nonces_csv([solution], self.feature_log_path)
            except Exception as e:
                logger.error("Error guardando features: %s", str(e))
            
            # Interpretar respuesta
            if resp and resp.get("result") == "OK":
                self.metrics["shares_accepted"] += 1
                logger.info("✅ Share aceptado: job=%s, nonce=0x%08x", job_id, solution['nonce'])
            else:
                self.metrics["shares_rejected"] += 1
                error = resp.get('error', ['-1', 'Error desconocido'])
                error_msg = error[1] if isinstance(error, list) and len(error) > 1 else str(error)
                logger.warning(" Share rechazado: %s", error_msg)
        
        except Exception as e:
            logger.exception("Error crítico enviando share: %s", str(e))

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
                    logger.info("Nuevo bloque: %d", job["height"])
                
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
                logger.exception("Error en bucle de minería: %s", str(e))
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
            "\n%s\n📊 Reporte de Métricas\n%s\n"
            "• Shares enviados: %d\n"
            "• Aceptados: %d (%.1f%%)\n"
            "• Rechazados: %d (%.1f%%)\n"
            "• Latencia IA: %.3fs (avg) | %.3fs (max)\n"
            "• Timeouts IA: %d\n"
            "• Errores conexión: %d\n"
            "• Altura bloque: %d\n"
            "• Uptime: %.1f segundos\n%s",
            "=" * 50, "-" * 50,
            shares, accepted, accept_rate, rejected, reject_rate,
            avg_latency, max_latency,
            self.metrics['ai_timeouts'], self.metrics['connection_errors'],
            self.metrics['last_block_height'], elapsed,
            "=" * 50
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
        self.shm.close()
        
        # Reportar métricas finales
        self.report_metrics()
        logger.info("Proxy detenido correctamente")

def start_proxy(wallet_address: str, pool_host: str, pool_port: int, shm_prefix: str = "zartrux_shared"):
    """Función de inicio con manejo profesional de excepciones"""
    proxy = None
    try:
        logger.info(
            "\n%s\n🚀 Iniciando IA-Zar Proxy (v3.0)\n"
            " Wallet: %s\n"
            " Pool: %s:%d\n"
            " SHM Prefix: %s\n%s",
            "=" * 50, wallet_address, pool_host, pool_port, shm_prefix, "=" * 50
        )
        
        proxy = AIProxyAdapter(wallet_address, pool_host, pool_port, shm_prefix)
        proxy.start()
        
        # Mantener el hilo principal activo
        while not proxy.shutdown_event.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Recibida señal de interrupción")
    except Exception as e:
        logger.critical("Error fatal: %s", str(e))
    finally:
        if proxy:
            proxy.stop()

__all__ = ("AIProxyAdapter", "start_proxy")
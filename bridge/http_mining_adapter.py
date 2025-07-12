# bridge/http_mining_adapter.py
import json
import logging
import ssl
import socket
from typing import Tuple, Optional
from monero import crypto # Importación clave para CryptoNight

logger = logging.getLogger(__name__)

class HttpMiningAdapter:
    def __init__(self, endpoint: str = "https://pool.hashvault.pro:443",
                 user: str = "", password: str = "x", 
                 worker_id: str = "default_worker"):
        """
        Adapter para conectar con pools de minería HTTP/HTTPS
        
        Args:
            endpoint: URL completa del endpoint del pool
            user: Nombre de usuario para autenticación
            password: Contraseña para autenticación
            worker_id: ID del trabajador para reportar
        """
        self.endpoint = endpoint
        self.user = user
        self.password = password
        self.worker_id = worker_id
        self.session_id = None
        self.current_job = None
        self.timeout = 15
        
        # Extraer host y puerto del endpoint
        if self.endpoint.startswith("https://"):
            self.host = self.endpoint[8:].split(':')[0]
            self.port = 443
        elif self.endpoint.startswith("http://"):
            self.host = self.endpoint[7:].split(':')[0]
            self.port = 80
        else:
            self.host = self.endpoint.split(':')[0]
            self.port = 443 if "https" in self.endpoint else 80

    def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """
        Envía una solicitud JSON-RPC al pool
        
        Args:
            method: Método JSON-RPC a llamar
            params: Parámetros para el método
            
        Returns:
            Respuesta del servidor o None en caso de error
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        
        try:
            # Usar SSL si es necesario
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                
                # Conexión segura para HTTPS
                if self.port == 443:
                    with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                        ssock.connect((self.host, self.port))
                        ssock.sendall(json.dumps(payload).encode() + b"\n")
                        response = ssock.recv(4096).decode()
                else:
                    # Conexión no segura para HTTP
                    sock.connect((self.host, self.port))
                    sock.sendall(json.dumps(payload).encode() + b"\n")
                    response = sock.recv(4096).decode()
                
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    logger.error("Respuesta JSON inválida del pool")
                    return None
                    
        except socket.timeout:
            logger.error("Timeout al conectar con el pool")
            return None
        except ConnectionRefusedError:
            logger.error("Conexión rechazada por el pool")
            return None
        except Exception as e:
            logger.error(f"Error de conexión: {str(e)}")
            return None

    def login(self) -> bool:
        """
        Autentica con el pool y obtiene el primer trabajo
        
        Returns:
            True si el login fue exitoso, False en caso contrario
        """
        login_params = {
            "login": self.user,
            "pass": self.password,
            "agent": f"HttpMiningAdapter/1.0 ({self.worker_id})"
        }
        
        response = self._send_request("login", login_params)
        
        if not response or "error" in response:
            error_msg = response.get('error', {}).get('message', '') if response else 'Sin respuesta'
            logger.error(f"Error de autenticación: {error_msg}")
            return False
            
        try:
            self.session_id = response["result"]["id"]
            self.current_job = response["result"]["job"]
            logger.info(f"✅ Autenticado exitosamente. Job ID: {self.current_job['id']}")
            return True
        except KeyError:
            logger.error("Respuesta de login inválida")
            return False

    def get_job(self) -> Optional[dict]:
        """
        Obtiene un nuevo trabajo del pool
        
        Returns:
            Diccionario con datos del trabajo o None en caso de error
        """
        if not self.session_id:
            if not self.login():
                return None
                
        response = self._send_request("getjob", {"id": self.session_id})
        
        if not response or "error" in response:
            error_msg = response.get('error', {}).get('message', '') if response else 'Sin respuesta'
            logger.error(f"Error obteniendo trabajo: {error_msg}")
            return None
            
        try:
            self.current_job = response["result"]
            logger.debug(f"Nuevo trabajo recibido: {self.current_job['id']}")
            return self.current_job
        except KeyError:
            logger.error("Respuesta de trabajo inválida")
            return None

    def submit_nonce(self, nonce: str) -> Tuple[bool, str]:
        """
        Envía un nonce al pool para validación
        
        Args:
            nonce: Nonce en formato hexadecimal (8 caracteres)
            
        Returns:
            Tupla (success, message) indicando el resultado
        """
        if not self.current_job:
            logger.warning("No hay trabajo actual. Obteniendo nuevo trabajo...")
            if not self.get_job():
                return False, "No se pudo obtener trabajo"
                
        job_id = self.current_job["id"]
        
        submit_params = {
            "id": self.session_id,
            "job_id": job_id,
            "nonce": nonce,
            "result": self.calculate_result(self.current_job["blob"], nonce)
        }
        
        response = self._send_request("submit", submit_params)
        
        if not response:
            return False, "Sin respuesta del servidor"
            
        if "error" in response:
            error_msg = response["error"].get("message", "Error desconocido")
            logger.warning(f"❌ Nonce rechazado: {error_msg}")
            return False, error_msg
            
        if response.get("result", {}).get("status") == "OK":
            logger.info(f"✅ Nonce aceptado: {nonce}")
            return True, "Nonce aceptado"
            
        return False, "Respuesta inesperada del servidor"

    def calculate_result(self, blob: str, nonce: str) -> str:
        """
        Calcula el resultado del trabajo para Hashvault usando CryptoNight
        
        Args:
            blob: Blob del trabajo en hexadecimal
            nonce: Nonce en formato hexadecimal (8 caracteres)
            
        Returns:
            Hash resultante en hexadecimal
        """
        try:
            # Normalizar blob (156 caracteres = 78 bytes)
            if len(blob) > 156:
                blob = blob[:156]
            elif len(blob) < 156:
                blob = blob.ljust(156, '0')
            
            # Insertar nonce en la posición correcta (caracteres 78 a 86)
            blob_with_nonce = blob[:78] + nonce + blob[86:]
            
            # Convertir a bytes
            blob_bytes = bytes.fromhex(blob_with_nonce)
            
            # Calcular hash CryptoNight usando la implementación real
            hash_bytes = cn_fast_hash(blob_bytes)
            return hash_bytes.hex()
        except Exception as e:
            logger.error(f"Error calculando resultado: {str(e)}")
            return "0000000000000000000000000000000000000000000000000000000000000000"


if __name__ == "__main__":
    # Configuración básica de logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Ejemplo de uso
    adapter = HttpMiningAdapter(
        endpoint="https://pool.hashvault.pro:443",
        user="tu_usuario",
        password="x",
        worker_id="worker1"
    )
    
    # Autenticar
    if adapter.login():
        # Obtener trabajo
        job = adapter.get_job()
        if job:
            print(f"Trabajo recibido: {job['id']}")
            print(f"Blob: {job['blob']}")
            print(f"Target: {job['target']}")
            
            # Enviar nonce de prueba
            success, message = adapter.submit_nonce("abcdef12")
            print(f"Resultado: {success} - {message}")
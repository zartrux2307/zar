# Adaptador TLS/SSL para conexiones seguras a pools
import socket
import ssl
from OpenSSL import crypto

class TLSStratumAdapter:
    def __init__(self, pool_host, pool_port, tls_version=ssl.PROTOCOL_TLSv1_2):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = True
        self.ctx.verify_mode = ssl.CERT_REQUIRED
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.wrapped_sock = self.ctx.wrap_socket(
            self.sock, 
            server_hostname=pool_host
        )
        self.wrapped_sock.connect((pool_host, pool_port))
    
    def enable_self_signed_cert(self, cert_path="proxy_cert.pem", key_path="proxy_key.pem"):
        """Genera certificado autofirmado para conexiones salientes"""
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 4096)
        
        cert = crypto.X509()
        cert.get_subject().CN = "Zar-IA-Proxy"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365*24*60*60)  # 1 año
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha512')
        
        with open(cert_path, "wb") as cert_file:
            cert_file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        with open(key_path, "wb") as key_file:
            key_file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
        
        self.ctx.load_cert_chain(cert_path, key_path)
    
    def send(self, data):
        return self.wrapped_sock.write(data.encode())
    
    def receive(self, buffer_size=4096):
        return self.wrapped_sock.read(buffer_size).decode()
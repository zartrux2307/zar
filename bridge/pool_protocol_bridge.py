
# Soporte para múltiples protocolos de pool
import socket
from iazar.core.tls_stratum_adapter import TLSStratumAdapter
import os
import sys
from iazar.bridge.http_mining_adapter import HttpMiningAdapter
from monero.crypto import cn_fast_hash


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
PROTOCOL_MAP = {
    "stratum+tcp": socket.socket,
    "stratum+tls": TLSStratumAdapter,
    "stratum2": TLSStratumAdapter,  # Stratum V2
    "http": HttpMiningAdapter,
    "https": HttpsMiningAdapter
}

class ProtocolBridge:
    def __init__(self, connection_string):
        protocol, _, address = connection_string.partition("://")
        self.adapter = PROTOCOL_MAP[protocol](*address.split(":"))
    
    def submit_share(self, nonce):
        return self.adapter.send(f"SUBMIT|{nonce}")
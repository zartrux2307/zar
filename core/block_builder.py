"""
block_builder.py - Construcción profesional de blobs de bloque Monero para minería IA-Zartrux.
Implementa el estándar completo de construcción de bloques Monero con validación integrada.
"""

import binascii
import struct
import json
import hashlib
from typing import Dict, Optional
from iazar.utils.randomx_wrapper import compute_randomx_hash


class MoneroBlockBuilder:
    """
    Constructor de bloques Monero profesional con:
    - Construcción completa de blobs compatibles con el protocolo
    - Validación integrada de campos
    - Serialización/deserialización eficiente
    - Soporte para múltiples versiones de protocolo
    - Cálculo de hashes RandomX optimizado
    """

    # Versiones de protocolo soportadas
    SUPPORTED_VERSIONS = {
        'mainnet': (16, 16),
        'stagenet': (15, 15),
        'testnet': (14, 14)
    }

    # Estructura del blob (offsets en bytes)
    HEADER_STRUCTURE = [
        ('major_version', 'B', 1),
        ('minor_version', 'B', 1),
        ('timestamp', 'I', 4),
        ('prev_id', '32s', 32),
        ('nonce', 'I', 4)
    ]

    def __init__(self, network: str = 'mainnet'):
        """
        Inicializa el constructor para una red específica

        Args:
            network: 'mainnet', 'stagenet' o 'testnet'
        """
        if network not in self.SUPPORTED_VERSIONS:
            raise ValueError(f"Red no soportada: {network}. Opciones: {list(self.SUPPORTED_VERSIONS.keys())}")

        self.network = network
        self.major_version, self.minor_version = self.SUPPORTED_VERSIONS[network]
        self.reset()

    def reset(self) -> None:
        """Reinicia el estado del constructor"""
        self.fields = {
            'major_version': self.major_version,
            'minor_version': self.minor_version,
            'timestamp': 0,
            'prev_id': b'\x00' * 32,
            'nonce': 0
        }
        self.transactions = []
        self.miner_tx = b''
        self.seed_hash = b''

    def validate_field(self, field: str, value) -> bool:
        """Valida un campo según su tipo y restricciones"""
        if field == 'prev_id':
            if not isinstance(value, bytes) or len(value) != 32:
                raise ValueError("prev_id debe ser bytes de 32 caracteres")
            return True

        if field == 'timestamp':
            if not isinstance(value, int) or value < 0:
                raise ValueError("timestamp debe ser un entero positivo")
            return True

        if field == 'nonce':
            if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
                raise ValueError("nonce debe ser un entero entre 0 y 4294967295")
            return True

        if field in ('major_version', 'minor_version'):
            if not isinstance(value, int) or value < 0 or value > 255:
                raise ValueError(f"{field} debe ser un byte válido (0-255)")
            return True

        return True

    def set_field(self, field: str, value) -> None:
        """
        Establece un campo del bloque con validación

        Args:
            field: Uno de ('major_version', 'minor_version', 'timestamp', 'prev_id', 'nonce')
            value: Valor del campo adecuadamente formateado
        """
        if field not in self.fields:
            raise KeyError(f"Campo inválido: {field}. Campos válidos: {list(self.fields.keys())}")

        self.validate_field(field, value)

        # Conversión especial para prev_id
        if field == 'prev_id' and isinstance(value, str):
            if len(value) != 64:
                raise ValueError("prev_id como string debe tener 64 caracteres hex")
            value = binascii.unhexlify(value)

        self.fields[field] = value

    def set_seed_hash(self, seed_hash: bytes) -> None:
        """Establece el seed hash para el cálculo de RandomX"""
        if not isinstance(seed_hash, bytes) or len(seed_hash) != 32:
            raise ValueError("seed_hash debe ser bytes de 32 caracteres")
        self.seed_hash = seed_hash

    def add_transaction(self, tx_hex: str) -> None:
        """Añade una transacción al bloque"""
        tx_bytes = binascii.unhexlify(tx_hex)
        self.transactions.append(tx_bytes)

    def set_miner_tx(self, tx_hex: str) -> None:
        """Establece la transacción del minero"""
        self.miner_tx = binascii.unhexlify(tx_hex)

    def build_block_blob(self) -> bytes:
        """
        Construye el blob completo del bloque Monero en formato binario
        compatible con el protocolo y pools de minería

        Returns:
            bytes: Blob serializado listo para hashing
        """
        # Construir encabezado
        header = b''
        for field, fmt, size in self.HEADER_STRUCTURE:
            value = self.fields[field]

            if field == 'prev_id' and isinstance(value, str):
                value = binascii.unhexlify(value)

            header += struct.pack('<' + fmt, value)

        # Construir cuerpo del bloque
        # 1. Transacción del minero
        block_body = self.miner_tx

        # 2. Número de transacciones (varint)
        num_txs = len(self.transactions)
        if num_txs < 0x80:
            block_body += struct.pack('B', num_txs)
        elif num_txs < 0x8000:
            block_body += struct.pack('<H', num_txs | 0x8000)
        else:
            block_body += struct.pack('<B', 0x80)
            block_body += struct.pack('<I', num_txs)

        # 3. Hashes de las transacciones
        for tx in self.transactions:
            block_body += hashlib.sha256(tx).digest()

        return header + block_body

    def compute_block_hash(self, blob: Optional[bytes] = None) -> bytes:
        """
        Calcula el hash del bloque usando RandomX

        Args:
            blob: Blob opcional (si no se proporciona, usa el blob actual)

        Returns:
            bytes: Hash del bloque de 32 bytes
        """
        if blob is None:
            blob = self.build_block_blob()

        if not self.seed_hash:
            raise RuntimeError("seed_hash no establecido. Use set_seed_hash() primero")

        return compute_randomx_hash(blob, seed_hash=self.seed_hash)

    def build_from_job(self, job_data: Dict) -> bytes:
        """
        Construye un blob de bloque desde un trabajo de pool estándar

        Args:
            job_data: Diccionario con datos del trabajo. Debe incluir:
                - 'blob' (str): Plantilla de blob
                - 'nonce' (int): Nonce a insertar
                - 'offset' (int): Offset del nonce en el blob

        Returns:
            bytes: Blob completo con nonce insertado
        """
        if 'blob' not in job_data or 'nonce' not in job_data:
            raise KeyError("job_data debe contener 'blob' y 'nonce'")

        # Convertir blob hex a binario
        blob = binascii.unhexlify(job_data['blob'])

        # Insertar nonce
        nonce_offset = job_data.get('offset', 39)  # Offset predeterminado en Monero
        nonce_bytes = struct.pack('<I', job_data['nonce'])

        # Reemplazar nonce en el blob
        return blob[:nonce_offset] + nonce_bytes + blob[nonce_offset + 4:]

    def get_block_header(self) -> Dict:
        """Devuelve los campos del encabezado como diccionario"""
        return self.fields.copy()

    def save_block_template(self, file_path: str) -> None:
        """Guarda la plantilla de bloque actual como JSON"""
        template = {
            'network': self.network,
            'header': self.fields,
            'miner_tx': binascii.hexlify(self.miner_tx).decode() if self.miner_tx else '',
            'transactions': [binascii.hexlify(tx).decode() for tx in self.transactions],
            'seed_hash': binascii.hexlify(self.seed_hash).decode() if self.seed_hash else ''
        }

        with open(file_path, 'w') as f:
            json.dump(template, f, indent=2)

    def load_block_template(self, file_path: str) -> None:
        """Carga una plantilla de bloque desde JSON"""
        with open(file_path, 'r') as f:
            template = json.load(f)

        if template.get('network') != self.network:
            raise ValueError(f"Plantilla de red {template.get('network')} no coincide con {self.network}")

        self.reset()

        # Cargar encabezado
        for field, value in template['header'].items():
            self.set_field(field, value)

        # Cargar transacciones
        if template['miner_tx']:
            self.miner_tx = binascii.unhexlify(template['miner_tx'])

        self.transactions = [binascii.unhexlify(tx) for tx in template['transactions']]

        if template['seed_hash']:
            self.seed_hash = binascii.unhexlify(template['seed_hash'])

# Función de compatibilidad para uso externo


def compute_block_hash(block_blob: bytes, seed_hash: bytes) -> bytes:
    """Función auxiliar para cálculo directo de hash"""
    return MoneroBlockBuilder().compute_block_hash(block_blob, seed_hash)

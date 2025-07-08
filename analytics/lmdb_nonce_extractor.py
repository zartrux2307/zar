import lmdb
import struct
import csv
import os
import time
import signal
import hashlib
import sys
from typing import Dict, Optional, Set
from tqdm.auto import tqdm
from datetime import datetime
from collections import deque
from iazar.utils.feature_utils import calc_nonce_features, guardar_nonces_csv, COLUMNS

# ======== CONFIGURACIÓN MEJORADA ========
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Raíz del proyecto

CONFIG = {
    'lmdb_path': r"E:/monero-blockchain/lmdb",
    'csv_output': os.path.join(PROJECT_ROOT, "iazar/data/nonce_training_data.csv"),  # Ruta absoluta estandarizada
    'max_blocks': 32720,
    'update_interval': 3600,
    'max_retries': 5,
    'nonce_offsets': {
        1: 43, 2: 47, 3: 51, 4: 55, 'default': 43
    },
    'hash_window': 1000
}

# ==== Cabecera estándar global para TODOS los CSV de nonces ====
NONCE_COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

class NonceExtractor:
    def __init__(self):
        self.processed_hashes = deque(maxlen=CONFIG['hash_window'])
        self.running = True
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)

    def write_csv(self, entries: list):
        """Escribe en CSV creando directorios automáticamente, usando la cabecera estándar"""
        try:
            output_dir = os.path.dirname(CONFIG['csv_output'])
            os.makedirs(output_dir, exist_ok=True)  # Crear directorios si no existen
            
            file_exists = os.path.exists(CONFIG['csv_output'])
            mode = 'a' if file_exists else 'w'
            
            # Si el archivo ya existe, no duplicar nonces
            existing_nonces = set()
            if file_exists:
                with open(CONFIG['csv_output'], 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing_nonces.add(row.get("nonce"))

            with open(CONFIG['csv_output'], mode, newline='') as f:
                writer = csv.DictWriter(f, fieldnames=NONCE_COLUMNS)
                if not file_exists:
                    writer.writeheader()
                # Escribir solo si la fila tiene la cabecera correcta y no es duplicada
                for e in entries:
                    if all(k in e for k in NONCE_COLUMNS) and str(e["nonce"]) not in existing_nonces:
                        writer.writerow({k: e[k] for k in NONCE_COLUMNS})

            print(f"[Éxito] {len(entries)} nuevos registros añadidos en: {CONFIG['csv_output']}")

        except Exception as e:
            print(f"[Error CSV] {str(e)}")
            self.create_backup()

    def create_backup(self):
        """Manejo robusto de respaldos"""
        try:
            backup_dir = os.path.dirname(CONFIG['csv_output'])
            os.makedirs(backup_dir, exist_ok=True)  # Asegurar directorio para respaldo
            backup_file = os.path.join(
                backup_dir,
                f"nonce_training_data.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            if os.path.exists(CONFIG['csv_output']):
                os.rename(CONFIG['csv_output'], backup_file)
                print(f"[Respaldo] Backup creado: {backup_file}")
            else:
                print("[Advertencia] No hay archivo original para respaldar")
        except Exception as e:
            print(f"[Error Backup] {str(e)}")

    def graceful_shutdown(self, signum, frame):
        print(f"\n[Info] Recibida señal {signum}. Cerrando limpiamente...")
        self.running = False

    def _block_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def parse_block(self, data: bytes) -> Optional[Dict]:
        try:
            major_version = struct.unpack('<B', data[0:1])[0]
            offset = CONFIG['nonce_offsets'].get(major_version, CONFIG['nonce_offsets']['default'])
            nonce_value = struct.unpack('<I', data[offset:offset+4])[0]
            # Aquí puedes calcular/estimar las features del nonce si las tienes,
            # por defecto se ponen como 0.0 o 0/1.
            return {
                "nonce": nonce_value,
                "entropy": 0.0,
                "uniqueness": 0.0,
                "zero_density": 0.0,
                "pattern_score": 0.0,
                "is_valid": 1  # O ajusta según tu lógica
            }
        except (struct.error, IndexError) as e:
            print(f"[Error] Bloque corrupto: {str(e)}")
            return None

    def process_blocks(self, cursor) -> list:
        new_entries = []
        cursor.last()
        block_count = 0
        retries = 0
        with tqdm(total=CONFIG['max_blocks'], desc="Procesando bloques") as pbar:
            while self.running and block_count < CONFIG['max_blocks'] and retries < 3:
                try:
                    data = cursor.value()
                    block_hash = self._block_hash(data)
                    if block_hash in self.processed_hashes:
                        retries += 1
                        continue
                    parsed = self.parse_block(data)
                    if parsed:
                        new_entries.append(parsed)
                        self.processed_hashes.append(block_hash)
                        block_count += 1
                        pbar.update(1)
                        retries = 0
                    if not cursor.prev():
                        break
                except lmdb.Error as e:
                    print(f"[Error LMDB] {str(e)}")
                    retries += 1
                    time.sleep(2 ** retries)
        return new_entries

    def run_extraction(self):
        try:
            env = lmdb.open(
                CONFIG['lmdb_path'],
                max_dbs=1,
                readonly=True,
                lock=False,
                metasync=False,
                readahead=False
            )
            with env.begin(db=env.open_db(b'blocks'), buffers=True) as txn:
                new_entries = self.process_blocks(txn.cursor())
                if new_entries:
                    self.write_csv(new_entries)
        except lmdb.Error as e:
            print(f"[Error LMDB] {str(e)}")
        except Exception as e:
            print(f"[Error] {str(e)}")
        finally:
            if 'env' in locals():
                env.close()

    def main_loop(self):
        while self.running:
            start_time = time.time()
            try:
                print(f"\n[{datetime.now()}] Iniciando extracción...")
                self.run_extraction()
                print(f"Tiempo ejecución: {time.time() - start_time:.2f}s")
                print(f"Esperando próxima ejecución ({CONFIG['update_interval']}s)...")
                time.sleep(CONFIG['update_interval'])
            except Exception as e:
                print(f"[Error Crítico] {str(e)}")
                time.sleep(60)

if __name__ == "__main__":
    NonceExtractor().main_loop()

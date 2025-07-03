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

# ======== CONFIGURACIÓN MEJORADA ========
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Raíz del proyecto

CONFIG = {
    'lmdb_path': r"E:/monero-blockchain/lmdb",
    'csv_output': os.path.join(PROJECT_ROOT, "C:/zarturxia/src/iazar/data/datanonce_training_data.csv"),  # Ruta absoluta
    'max_blocks': 40000,
    'update_interval': 3600,
    'max_retries': 5,
    'nonce_offsets': {
        1: 43, 2: 47, 3: 51, 4: 55, 'default': 43
    },
    'hash_window': 1000
}

class NonceExtractor:
    def __init__(self):
        self.processed_hashes = deque(maxlen=CONFIG['hash_window'])
        self.running = True
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)

    # ======== MÉTODOS CLAVE CORREGIDOS ========
    def write_csv(self, entries: list):
        """Escribe en CSV creando directorios automáticamente"""
        try:
            output_dir = os.path.dirname(CONFIG['csv_output'])
            os.makedirs(output_dir, exist_ok=True)  # Crear directorios si no existen
            
            file_exists = os.path.exists(CONFIG['csv_output'])
            mode = 'a' if file_exists else 'w'
            
            with open(CONFIG['csv_output'], mode, newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'nonce', 'nonce_hex', 'major_ver', 'minor_ver',
                    'block_timestamp', 'block_size', 'block_hash', 
                    'accepted', 'predicted_by_ia'
                ])
                
                if not file_exists:
                    writer.writeheader()
                writer.writerows(entries)
            
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

    # ======== RESTANTES MÉTODOS (SIN CAMBIOS) ========
    def graceful_shutdown(self, signum, frame):
        print(f"\n[Info] Recibida señal {signum}. Cerrando limpiamente...")
        self.running = False

    def _block_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def parse_block(self, data: bytes) -> Optional[Dict]:
        try:
            major_version = struct.unpack('<B', data[0:1])[0]
            offset = CONFIG['nonce_offsets'].get(major_version, CONFIG['nonce_offsets']['default'])
            return {
                'nonce': struct.unpack('<I', data[offset:offset+4])[0],
                'major_version': major_version,
                'minor_version': struct.unpack('<B', data[1:2])[0],
                'timestamp': struct.unpack('<I', data[2:6])[0],
                'size': len(data)
            }
        except (struct.error, IndexError) as e:
            print(f"[Error] Bloque corrupto: {str(e)}")
            return None

    def load_existing_nonces(self) -> Set[int]:
        existing = set()
        if not os.path.exists(CONFIG['csv_output']):
            return existing
        try:
            with open(CONFIG['csv_output'], 'r') as f:
                reader = csv.DictReader(f)
                if not {'nonce', 'block_hash'}.issubset(reader.fieldnames):
                    raise ValueError("Formato CSV inválido")
                existing = {int(row['nonce']) for row in reader if row['nonce'].isdigit()}
        except Exception as e:
            print(f"[Error] Fallo al cargar CSV: {str(e)}")
        return existing

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
                    
                    if parsed := self.parse_block(data):
                        new_entries.append({
                            'timestamp': datetime.now().isoformat(),
                            'nonce': parsed['nonce'],
                            'nonce_hex': hex(parsed['nonce']),
                            'major_ver': parsed['major_version'],
                            'minor_ver': parsed['minor_version'],
                            'block_timestamp': parsed['timestamp'],
                            'block_size': parsed['size'],
                            'block_hash': block_hash,
                            'accepted': 0,
                            'predicted_by_ia': 0
                        })
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
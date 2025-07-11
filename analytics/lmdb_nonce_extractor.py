import lmdb
import struct
import csv
import os
import sys

import time
import signal
import hashlib
from typing import Dict, Optional, List, Tuple
from tqdm.auto import tqdm
from datetime import datetime
from collections import deque
import concurrent.futures
from iazar.utils.feature_utils import calc_nonce_features  # Importamos la función de características

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
# ======== CONFIGURACIÓN MEJORADA ========
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Raíz del proyecto

CONFIG = {
    'lmdb_path': r"E:/monero-blockchain/lmdb",
    'csv_output': os.path.join(PROJECT_ROOT, "iazar/data/nonce_training_data.csv"),  # Ruta absoluta estandarizada
    'max_blocks': 250000,
    'update_interval': 3600,
    'max_retries': 5,
    'nonce_offsets': {
        1: 43, 2: 47, 3: 51, 4: 55, 'default': 43
    },
    'hash_window': 1000,
    'batch_size': 1000  # Nuevo: tamaño del lote para procesamiento paralelo
}

# ==== Cabecera estándar global para TODOS los CSV de nonces ====
NONCE_COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]


class NonceExtractor:
    def __init__(self):
        self.processed_hashes = deque(maxlen=CONFIG['hash_window'])
        self.running = True
        self.processed_nonces = set()  # Conjunto para evitar duplicados entre ejecuciones
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)
        self._load_existing_nonces()  # Cargar nonces existentes al iniciar

    def _load_existing_nonces(self):
        """Cargar nonces existentes del CSV para evitar duplicados"""
        if os.path.exists(CONFIG['csv_output']):
            try:
                with open(CONFIG['csv_output'], 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.processed_nonces.add(row.get("nonce"))
                print(f"[Info] Cargados {len(self.processed_nonces)} nonces existentes")
            except Exception as e:
                print(f"[Error] No se pudieron cargar nonces existentes: {str(e)}")

    def write_csv(self, entries: list):
        """Escribe en CSV creando directorios automáticamente, usando la cabecera estándar"""
        try:
            output_dir = os.path.dirname(CONFIG['csv_output'])
            os.makedirs(output_dir, exist_ok=True)  # Crear directorios si no existen

            file_exists = os.path.exists(CONFIG['csv_output'])
            mode = 'a' if file_exists else 'w'

            # Filtrar entradas ya existentes
            new_entries = []
            for e in entries:
                nonce_str = str(e.get("nonce", ""))
                if nonce_str and nonce_str not in self.processed_nonces:
                    new_entries.append(e)
                    self.processed_nonces.add(nonce_str)  # Añadir a procesados

            if not new_entries:
                print("[Info] No hay nuevos registros para añadir")
                return

            with open(CONFIG['csv_output'], mode, newline='') as f:
                writer = csv.DictWriter(f, fieldnames=NONCE_COLUMNS)
                if not file_exists:
                    writer.writeheader()
                
                for e in new_entries:
                    writer.writerow({k: e[k] for k in NONCE_COLUMNS})

            print(f"[Éxito] {len(new_entries)} nuevos registros añadidos en: {CONFIG['csv_output']}")

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

    def parse_block(self, data: bytes) -> Optional[int]:
        try:
            major_version = struct.unpack('<B', data[0:1])[0]
            offset = CONFIG['nonce_offsets'].get(major_version, CONFIG['nonce_offsets']['default'])
            nonce_value = struct.unpack('<I', data[offset:offset + 4])[0]
            return nonce_value
        except (struct.error, IndexError) as e:
            print(f"[Error] Bloque corrupto: {str(e)}")
            return None

    def process_block_batch(self, blocks: List[Tuple[bytes, str]]) -> List[Dict]:
        """Procesa un lote de bloques en paralelo"""
        batch_entries = []
        for data, block_hash in blocks:
            if block_hash in self.processed_hashes:
                continue
                
            nonce_value = self.parse_block(data)
            if nonce_value is None:
                continue
                
            # Calcular características usando la función importada
            features = calc_nonce_features(nonce_value)
            batch_entries.append(features)
            self.processed_hashes.append(block_hash)
            
        return batch_entries

    def process_blocks(self, cursor) -> list:
        new_entries = []
        cursor.last()
        block_count = 0
        retries = 0
        
        # Leer todos los bloques primero
        blocks_to_process = []
        with tqdm(total=CONFIG['max_blocks'], desc="Recolectando bloques") as pbar:
            while self.running and block_count < CONFIG['max_blocks'] and retries < CONFIG['max_retries']:
                try:
                    data = cursor.value()
                    block_hash = self._block_hash(data)
                    
                    # Solo procesar si no hemos visto este bloque
                    if block_hash not in self.processed_hashes:
                        blocks_to_process.append((data, block_hash))
                        block_count += 1
                        pbar.update(1)
                    
                    if not cursor.prev():
                        break
                except lmdb.Error as e:
                    print(f"[Error LMDB] {str(e)}")
                    retries += 1
                    time.sleep(2 ** retries)
                except Exception as e:
                    print(f"[Error inesperado] {str(e)}")
                    retries += 1
                    time.sleep(2 ** retries)
        
        # Procesar en lotes paralelos
        batch_size = CONFIG['batch_size']
        total_batches = (len(blocks_to_process) + batch_size - 1) // batch_size
        
        with tqdm(total=len(blocks_to_process), desc="Procesando bloques") as pbar:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = []
                
                # Dividir en lotes
                for i in range(0, len(blocks_to_process), batch_size):
                    batch_end = min(i + batch_size, len(blocks_to_process))
                    batch = blocks_to_process[i:batch_end]
                    futures.append(executor.submit(self.process_block_batch, batch))
                
                # Recolectar resultados
                for future in concurrent.futures.as_completed(futures):
                    try:
                        batch_entries = future.result()
                        new_entries.extend(batch_entries)
                        pbar.update(len(batch_entries))
                    except Exception as e:
                        print(f"[Error en lote] {str(e)}")
        
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
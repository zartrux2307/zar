import os
import csv
import pandas as pd
import json
from iazar.utils.feature_utils import COLUMNS
# Columnas estándar globales
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

def leer_nonces_csv(path):
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
    if not os.path.exists(path):
        pd.DataFrame(columns=COLUMNS).to_csv(path, index=False)
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    missing = [col for col in COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = 0
    df = df[COLUMNS]
    df = df.dropna()  # Opcional, borra filas incompletas
    return df

def guardar_nonces_csv(df, path):
    """Guarda un DataFrame de nonces con la cabecera y orden estándar."""
    if not set(COLUMNS).issubset(df.columns):
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
    df = df[COLUMNS]
    df.to_csv(path, index=False)

def leer_nonces_json(path):
    """Lee un JSON de nonces como lista de dicts."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
        return []
    with open(path, 'r') as f:
        data = json.load(f)
    # Completa campos faltantes
    for item in data:
        for col in COLUMNS:
            if col not in item:
                item[col] = 0
    return data

def guardar_nonces_json(lista, path):
    """Guarda una lista de dicts como JSON de nonces."""
    with open(path, 'w') as f:
        json.dump(lista, f, indent=2)

# Utilidades para blobs binarios
def hexstr_to_bytes(blob_hex):
    return bytes.fromhex(blob_hex) if isinstance(blob_hex, str) else blob_hex

def bytes_to_hexstr(blob_bytes):
    return blob_bytes.hex() if isinstance(blob_bytes, (bytes, bytearray)) else blob_bytes

# === CONFIGURACIÓN ===
# Usar rutas absolutas corregidas
CSV_PATH = os.path.abspath("src/iazar/data/nonce_training_data.csv")
BACKUP_PATH = os.path.abspath("src/iazar/data/nonce_training_data.backup.csv")

# === CAMPOS REQUERIDOS ACTUALIZADOS ===
CSV_FIELDS = [
    'timestamp', 'nonce', 'nonce_hex', 'major_ver', 'minor_ver',
    'block_timestamp', 'block_size', 'block_hash',
    'accepted', 'predicted_by_ia',
    'entropy', 'uniqueness', 'zero_density', 'pattern_score', 'is_valid'
]

def clean_duplicates():
    # Crear directorios si no existen
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] Archivo no encontrado: {CSV_PATH}")
        return

    seen_nonces = set()
    cleaned_rows = []

    with open(CSV_PATH, 'r', newline='') as infile:
        reader = csv.DictReader(infile)
        # Obtener todos los campos existentes en el archivo
        all_fields = reader.fieldnames
        
        for row in reader:
            nonce = row.get('nonce')
            if nonce and nonce not in seen_nonces:
                seen_nonces.add(nonce)
                
                # Crear nueva fila solo con campos válidos
                valid_row = {field: row.get(field, '') for field in CSV_FIELDS}
                cleaned_rows.append(valid_row)

    # Crear respaldo antes de sobrescribir
    if os.path.exists(CSV_PATH):
        os.rename(CSV_PATH, BACKUP_PATH)
        print(f"[BACKUP] Respaldo guardado en: {BACKUP_PATH}")

    # Reescribir archivo limpio
    with open(CSV_PATH, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    print(f"[OK] Duplicados eliminados. Total final: {len(cleaned_rows)} registros.")

if __name__ == "__main__":
    clean_duplicates()
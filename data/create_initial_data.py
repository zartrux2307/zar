import os
import pandas as pd
import numpy as np
import json
from iazar.utils.feature_utils import calc_nonce_features, guardar_nonces_csv, COLUMNS

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

# Ejemplo de uso:
# df = leer_nonces_csv("ruta.csv")
# guardar_nonces_csv(df, "nueva_ruta.csv")
# nonces = leer_nonces_json("ruta.json")
# guardar_nonces_json(nonces, "nueva_ruta.json")

DATA_DIR = "src/iazar/data/"
os.makedirs(DATA_DIR, exist_ok=True)

# Crear datos de ejemplo con tipo correcto
data = {
    "nonce": np.random.randint(0, 2**32, 1000, dtype=np.uint32),  # Corregido
    "entropy": np.random.uniform(2.5, 4.0, 1000),
    "uniqueness": np.random.uniform(0.7, 0.95, 1000),
    "zero_density": np.random.uniform(0.03, 0.07, 1000),
    "pattern_score": np.random.uniform(0.6, 0.9, 1000),
    "is_valid": np.random.choice([0, 1], 1000)
}

df = pd.DataFrame(data)
df.to_csv(os.path.join(DATA_DIR, "nonce_training_data.csv"), index=False)
print("✅ Datos iniciales creados en:", os.path.join(DATA_DIR, "nonce_training_data.csv"))
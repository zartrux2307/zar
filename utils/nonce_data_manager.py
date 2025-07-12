import os
import pandas as pd
from datetime import datetime
from shutil import copyfile
import threading

# Ruta central configurable
CENTRAL_CSV = os.environ.get("NONCE_TRAINING_CSV", "C:/zarturxia/data/nonce_training_data.csv")
BACKUP_DIR = "C:/zarturxia/data/backups"
_LOCK = threading.Lock()

def get_nonce_data(columns=None, csv_path=None):
    """Lee el CSV central y retorna un DataFrame limpio."""
    path = csv_path or CENTRAL_CSV
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró el archivo central de nonces: {path}")
    df = pd.read_csv(path)
    if columns:
        for col in columns:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[columns]
    return df

def append_nonces(nonces, extra_cols=None, csv_path=None, backup=True):
    """
    Añade una lista de nonces (y columnas extra) de forma thread-safe, sin duplicados.
    nonces: lista de ints o dicts ({"nonce": int, ...})
    extra_cols: dict con columnas adicionales (ej: {"is_valid": 1})
    """
    path = csv_path or CENTRAL_CSV
    with _LOCK:
        # Backup antes de escribir
        if backup:
            make_backup(path)
        if not os.path.exists(path):
            df = pd.DataFrame(columns=["nonce"])
        else:
            df = pd.read_csv(path)
        # Normaliza input
        if isinstance(nonces[0], dict):
            nuevos = pd.DataFrame(nonces)
        else:
            data = {"nonce": nonces}
            if extra_cols:
                for k, v in extra_cols.items():
                    data[k] = v
            nuevos = pd.DataFrame(data)
        # Evita duplicados
        df = pd.concat([df, nuevos], ignore_index=True)
        df = df.drop_duplicates(subset=["nonce"])
        df.to_csv(path, index=False)
    print(f"[APPEND] {len(nuevos)} nuevos nonces añadidos a {os.path.basename(path)}")

def update_nonce_column(nonce, column, value, csv_path=None, backup=True):
    """Actualiza una columna para un nonce concreto, thread-safe."""
    path = csv_path or CENTRAL_CSV
    with _LOCK:
        if backup:
            make_backup(path)
        df = pd.read_csv(path)
        df.loc[df["nonce"] == nonce, column] = value
        df.to_csv(path, index=False)
    print(f"[UPDATE] Nonce {nonce} actualizado: {column}={value}")

def make_backup(csv_path):
    """Backup automático antes de sobrescribir el CSV."""
    if not os.path.exists(csv_path):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"nonce_training_data_{ts}.csv")
    copyfile(csv_path, backup_path)
    print(f"[BACKUP] Backup creado en {backup_path}")

# --- Ejemplo de uso directo ---
if __name__ == "__main__":
    # Leer nonces
    df = get_nonce_data()
    print(df.head())

    # Añadir nonces
    append_nonces([1234567, 2222222, 3333333], extra_cols={"is_valid": 1})

    # Actualizar columna
    update_nonce_column(1234567, "is_accepted", 1)

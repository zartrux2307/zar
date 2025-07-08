import pandas as pd
import numpy as np
import os

try:
    import seaborn as sns
    import matplotlib.pyplot as plt
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

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

class CorrelationAnalyzer:
    """
    Analizador avanzado de correlaciones para datos mineros y de IA.

    Calcula y guarda la matriz de correlación en un CSV compartido,
    facilitando el acceso a otros módulos del sistema.
    """

    def __init__(self, df: pd.DataFrame, log_dir: str = '../../logs/reports/', filename: str = 'correlation_matrix.csv'):
        self.df = df
        self.corr_matrix = None
        self.method = None
        self.log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), log_dir))
        self.filename = filename

    def compute(self, method: str = 'pearson', columns: list = None) -> pd.DataFrame:
        """
        Calcula la matriz de correlación y la guarda como CSV.
        """
        self.method = method
        if columns is None:
            columns = self.df.select_dtypes(include=[np.number]).columns
        if len(columns) < 2:
            raise ValueError("Se necesitan al menos dos columnas numéricas para correlacionar.")

        self.corr_matrix = self.df[columns].corr(method=method)
        self._save_to_csv()
        return self.corr_matrix

    def _save_to_csv(self):
        os.makedirs(self.log_dir, exist_ok=True)
        csv_path = os.path.join(self.log_dir, self.filename)
        self.corr_matrix.to_csv(csv_path)
        print(f"[CorrelationAnalyzer] Matriz de correlación guardada en: {csv_path}")

    def report_top_correlations(self, n: int = 5, threshold: float = 0.8):
        """
        Imprime las correlaciones más altas (positivas o negativas) excluyendo la diagonal.
        """
        if self.corr_matrix is None:
            raise RuntimeError("Primero ejecuta compute()")
        corr = self.corr_matrix.copy()
        np.fill_diagonal(corr.values, 0)
        stacked = corr.abs().unstack().sort_values(ascending=False)
        seen = set()
        count = 0
        print(f"\nTop-{n} correlaciones (umbral |r| > {threshold}):")
        for (col1, col2), val in stacked.iteritems():
            if col1 == col2 or (col2, col1) in seen:
                continue
            if abs(val) < threshold:
                break
            print(f"{col1} <-> {col2}: {self.corr_matrix.loc[col1, col2]:.3f}")
            seen.add((col1, col2))
            count += 1
            if count >= n:
                break
        if count == 0:
            print("No se encontraron correlaciones significativas.")

    def outlier_pairs(self, threshold: float = 0.9) -> list:
        """
        Devuelve pares de columnas con correlación fuerte (outliers).
        """
        if self.corr_matrix is None:
            raise RuntimeError("Primero ejecuta compute()")
        pairs = []
        corr = self.corr_matrix.copy()
        np.fill_diagonal(corr.values, 0)
        for col1 in corr.columns:
            for col2 in corr.columns:
                if col1 >= col2:
                    continue
                val = corr.loc[col1, col2]
                if abs(val) >= threshold:
                    pairs.append((col1, col2, val))
        return pairs

    def plot(self, figsize=(8, 6), annot=True, cmap='coolwarm'):
        """
        Visualiza la matriz de correlación como heatmap.
        """
        if not HAS_PLOTTING:
            print("Instala seaborn y matplotlib para visualizar la matriz.")
            return
        if self.corr_matrix is None:
            raise RuntimeError("Primero ejecuta compute()")
        plt.figure(figsize=figsize)
        sns.heatmap(self.corr_matrix, annot=annot, cmap=cmap, center=0, fmt=".2f")
        plt.title(f"Matriz de correlación ({self.method})")
        plt.tight_layout()
        plt.show()

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq
from typing import Tuple
import logging  # Se añade para registrar errores
import os
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

# Configuración básica de logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

class FourierAnalyzer:
    def __init__(self, sampling_rate: float = 1.0):
        """
        Inicializa el analizador de Fourier.

        Args:
            sampling_rate (float): Tasa de muestreo de los datos.
        """
        self.sampling_rate = sampling_rate

    def apply_fft(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Aplica la Transformada Rápida de Fourier (FFT) a los datos.

        Args:
            data (np.ndarray): Datos de entrada.

        Returns:
            Tuple[np.ndarray, np.ndarray]: Frecuencias y amplitudes correspondientes.
        """
        n = len(data)
        yf = fft(data)
        xf = fftfreq(n, 1 / self.sampling_rate)
        return xf[:n // 2], 2.0 / n * np.abs(yf[0:n // 2])

    def plot_spectrum(self, data: np.ndarray, title: str = "Espectro de Frecuencias"):
        """
        Grafica el espectro de frecuencias de los datos.

        Args:
            data (np.ndarray): Datos de entrada.
            title (str): Título del gráfico.
        """
        xf, yf = self.apply_fft(data)
        plt.figure(figsize=(10, 6))
        plt.plot(xf, yf)
        plt.title(title)
        plt.xlabel("Frecuencia [Hz]")
        plt.ylabel("Amplitud")
        plt.grid()
        plt.show()

    def extract_features(self, data: np.ndarray, num_features: int = 5) -> np.ndarray:
        """
        Extrae las frecuencias y amplitudes dominantes de los datos.

        Args:
            data (np.ndarray): Datos de entrada.
            num_features (int): Número de características a extraer.

        Returns:
            np.ndarray: Características extraídas.
        """
        xf, yf = self.apply_fft(data)
        sorted_indices = np.argsort(yf)[::-1]
        top_indices = sorted_indices[:num_features]
        top_frequencies = xf[top_indices]
        top_amplitudes = yf[top_indices]
        return np.concatenate((top_frequencies, top_amplitudes))

# Ejemplo de uso de la clase FourierAnalyzer
if __name__ == "__main__":
    # Cargar datos de nonces desde el archivo CSV
    data_path = 'C:/zarturxia/src/iazar/data/nonce_training_data.csv'
    
    try:
        # Intento principal con manejo de líneas problemáticas
        df = pd.read_csv(data_path, on_bad_lines='skip', encoding='utf-8')
    except pd.errors.ParserError as e:
        # Recuperación usando modo flexible si falla el parser estándar
        logger.error(f"Error leyendo CSV: {e}, usando modo flexible")
        df = pd.read_csv(data_path, sep=None, engine='python', encoding='utf-8')

    # Seleccionar una columna específica para el análisis de Fourier
    column_name = 'nonce'  # Cambiar según la columna de interés
    data = df[column_name].values

    # Inicializar el analizador de Fourier
    fourier_analyzer = FourierAnalyzer(sampling_rate=1.0)

    # Aplicar FFT y graficar el espectro de frecuencias
    fourier_analyzer.plot_spectrum(data, title="Espectro de Frecuencias del Columna 'nonce'")

    # Extraer características dominantes
    features = fourier_analyzer.extract_features(data, num_features=5)
    print(f"Características Dominantes: {features}")
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq
from typing import Tuple

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
    df = pd.read_csv(data_path)

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

import numpy as np
import pandas as pd

class NonceStats:
    """
    Clase para análisis estadístico de nonces.
    """
    @staticmethod
    def analisis_completo(values):
        """
        Realiza un análisis estadístico completo sobre una lista/array de nonces.
        Retorna un diccionario con métricas útiles.
        """
        values = np.array(values)
        stats = {
            "count": len(values),
            "mean": np.mean(values) if len(values) > 0 else None,
            "std": np.std(values) if len(values) > 0 else None,
            "min": np.min(values) if len(values) > 0 else None,
            "max": np.max(values) if len(values) > 0 else None,
            "median": np.median(values) if len(values) > 0 else None,
            "25%": np.percentile(values, 25) if len(values) > 0 else None,
            "75%": np.percentile(values, 75) if len(values) > 0 else None,
            "skew": pd.Series(values).skew() if len(values) > 1 else None,
            "kurtosis": pd.Series(values).kurtosis() if len(values) > 1 else None,
        }
        return stats

    @staticmethod
    def exportar_csv(values, path):
        """
        Exporta el análisis estadístico de los nonces a un archivo CSV.
        """
        stats = NonceStats.analisis_completo(values)
        df = pd.DataFrame([stats])
        df.to_csv(path, index=False)
        return path

    @staticmethod
    def resumen_simple(values):
        """
        Devuelve solo el promedio y la desviación estándar.
        """
        values = np.array(values)
        return {
            "mean": np.mean(values) if len(values) > 0 else None,
            "std": np.std(values) if len(values) > 0 else None
        }

# ---- FIX PARA LEGACY ----
def calculate_nonce_stats(values):
    """
    Función global para análisis estadístico de nonces.
    Compatible con imports legacy: NonceStats.analisis_completo().
    """
    return NonceStats.analisis_completo(values)

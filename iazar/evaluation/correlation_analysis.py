import pandas as pd
import numpy as np
import os

try:
    import seaborn as sns
    import matplotlib.pyplot as plt
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

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

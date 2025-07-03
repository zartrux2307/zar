import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr, kendalltau
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
from ..utils.nonce_loader import NonceLoader
from ..utils.data_preprocessing import NonceDataPreprocessor
import joblib

class DistributionAnalyzer:
    """
    Analizador avanzado de correlaciones y distribución para minería de datos.
    """

    def __init__(self, config_path: str = "config/miner_config.json"):
        self.loader = NonceLoader()
        self.preprocessor = NonceDataPreprocessor()
        self.logger = logging.getLogger(__name__)
        self._load_models()

    def _load_models(self):
        """Carga modelos necesarios para análisis combinado"""
        try:
            self.models = {
                'ethical': joblib.load(Path("models") / "ethical_nonce_model.joblib"),
                'classifier': joblib.load(Path("models") / "hash_classifier_model.joblib")
            }
        except Exception as e:
            self.logger.error(f"Error cargando modelos: {str(e)}")
            self.models = None

    def autocorrelation_analysis(
        self,
        series: np.ndarray,
        max_lags: int = 20
    ) -> Dict[int, float]:
        """Calcula la autocorrelación para múltiples lags con validación estadística."""
        if len(series) < max_lags * 2:
            self.logger.warning("Serie demasiado corta para el número de lags solicitado")
            max_lags = len(series) // 2

        results = {}
        for lag in range(1, max_lags + 1):
            try:
                if len(series) <= lag:
                    continue
                corr = pearsonr(series[:-lag], series[lag:])[0]
                results[lag] = corr if not np.isnan(corr) else 0
            except Exception as e:
                self.logger.error(f"Error en lag {lag}: {str(e)}")
                continue

        return results

    def cross_correlation_matrix(
        self,
        df: Optional[pd.DataFrame] = None,
        method: str = 'pearson'
    ) -> pd.DataFrame:
        """Calcula matriz de correlación con múltiples métodos y optimización de memoria."""
        if df is None:
            df = self.loader.load_training_data()

        df = self.preprocessor.reduce_memory_usage(df)

        methods = {
            'pearson': pearsonr,
            'spearman': spearmanr,
            'kendall': kendalltau
        }

        if method not in methods:
            raise ValueError(f"Método {method} no soportado")

        cols = df.select_dtypes(include=np.number).columns.tolist()
        matrix = pd.DataFrame(index=cols, columns=cols)

        for i in cols:
            for j in cols:
                if i == j:
                    matrix.loc[i, j] = 1.0
                else:
                    try:
                        matrix.loc[i, j] = methods[method](df[i], df[j])[0]
                    except Exception as e:
                        self.logger.warning(f"Error calculando {i}-{j}: {str(e)}")
                        matrix.loc[i, j] = np.nan

        return matrix.astype(float)

    def detect_significant_patterns(
        self,
        threshold: float = 0.7,
        p_value: float = 0.05
    ) -> Dict[str, Dict[str, float]]:
        """Detecta patrones significativos con validación estadística."""
        df = self.loader.load_all()['training']
        patterns = {}

        numeric_cols = df.select_dtypes(include=np.number).columns
        for i in numeric_cols:
            for j in numeric_cols:
                if i >= j:
                    continue
                try:
                    corr, p = pearsonr(df[i], df[j])
                    if abs(corr) >= threshold and p <= p_value:
                        patterns[f"{i}_{j}"] = {
                            'correlation': corr,
                            'p_value': p,
                            'method': 'pearson'
                        }
                except Exception as e:
                    continue

        return patterns

    def plot_correlogram(
        self,
        save_path: Optional[str] = None,
        figsize: Tuple[int, int] = (14, 10),
        dpi: int = 300
    ):
        """Genera y guarda correlogramas profesionales."""
        df = self.loader.load_hash_data()
        plt.figure(figsize=figsize, facecolor='white')

        sns.set_theme(style="whitegrid", palette="muted")
        corr_matrix = self.cross_correlation_matrix(df)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool))

        heatmap = sns.heatmap(
            corr_matrix,
            mask=mask,
            annot=True,
            fmt=".2f",
            cmap="vlag",
            center=0,
            linewidths=0.5,
            annot_kws={"size": 8}
        )

        plt.title("Análisis de Correlación de Nonces", pad=20, fontsize=14)
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)

        if save_path:
            Path(save_path).parent.mkdir(exist_ok=True)
            plt.savefig(save_path, bbox_inches='tight', dpi=dpi)
            plt.close()
        else:
            plt.show()

    def analyze_and_report(self) -> Dict:
        """Ejecuta análisis completo y genera reporte estructurado."""
        report = {
            'autocorrelation': {},
            'cross_correlations': {},
            'significant_patterns': {},
            'model_insights': {}
        }

        try:
            # Análisis de datos principales
            hash_data = self.loader.load_hash_data()
            report['autocorrelation'] = self.autocorrelation_analysis(
                hash_data['nonce'].values
            )

            # Correlaciones cruzadas
            report['cross_correlations'] = self.cross_correlation_matrix()

            # Patrones significativos
            report['significant_patterns'] = self.detect_significant_patterns()

            # Integración con modelos IA
            if self.models:
                report['model_insights'] = self._generate_model_insights(hash_data)

            # Generación de gráficos
            self.plot_correlogram(save_path="reports/correlogram.png")

        except Exception as e:
            self.logger.error(f"Error en análisis completo: {str(e)}")
            report['error'] = str(e)

        return report

    def _generate_model_insights(self, data: pd.DataFrame) -> Dict:
        """Genera insights integrando modelos de IA"""
        insights = {}

        try:
            # Predicciones con modelo ético
            ethical_preds = self.models['ethical'].predict_proba(data[['nonce']])[:,1]
            insights['ethical_correlation'] = pearsonr(data['hash_score'], ethical_preds)[0]

            # Clasificación de hashes
            hash_classes = self.models['classifier'].predict(data[['nonce']])
            insights['class_distribution'] = pd.Series(hash_classes).value_counts().to_dict()

        except Exception as e:
            self.logger.error(f"Error generando insights de modelos: {str(e)}")

        return insights

if __name__ == "__main__":
    analyzer = DistributionAnalyzer()

    # Análisis completo con reporte
    report = analyzer.analyze_and_report()
    print("Resumen del análisis:")
    print(f"- Autocorrelaciones calculadas: {len(report['autocorrelation'])} lags")
    print(f"- Patrones significativos encontrados: {len(report['significant_patterns'])}")
    print(f"- Insights de modelos: {report['model_insights'].keys()}")

    # Generación de gráfico profesional
    analyzer.plot_correlogram(save_path="reports/correlogram.png")

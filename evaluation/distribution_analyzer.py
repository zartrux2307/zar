import os
import sys
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr, kendalltau
from typing import Dict, Optional, Tuple
import logging
from pathlib import Path
import joblib
import json
from datetime import datetime
from iazar.utils.nonce_loader import NonceLoader
from iazar.utils.data_preprocessing import NonceDataPreprocessor

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Configuración avanzada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("distribution_analyzer.log")
    ]
)
logger = logging.getLogger("DistributionAnalyzer")


class DistributionAnalyzer:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = self._resolve_base_dir(base_dir)
        logger.info(f"Inicializando DistributionAnalyzer en directorio: {self.base_dir}")

        try:
            self.loader = NonceLoader(base_dir=self.base_dir)
            self.preprocessor = NonceDataPreprocessor()
        except Exception as e:
            logger.error(f"Error inicializando componentes: {str(e)}")
            raise

        self._load_models()
        self.report_dir = Path(self.base_dir) / "reports" / "distribution_analysis"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_base_dir(self, base_dir: Optional[str]) -> str:
        if base_dir and os.path.isabs(base_dir) and os.path.exists(base_dir):
            return base_dir
        candidate_paths = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
            os.getcwd(),
            os.path.abspath(".")
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                return path
        default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        os.makedirs(default_path, exist_ok=True)
        return default_path

    def _load_models(self):
        model_dir = Path(self.base_dir) / "iazar" / "models"
        self.models = {}
        model_files = {
            'ethical': "ethical_nonce_model.joblib",
            'classifier': "hash_classifier_model.joblib"
        }
        for model_name, filename in model_files.items():
            model_path = model_dir / filename
            try:
                if model_path.exists():
                    self.models[model_name] = joblib.load(model_path)
                    logger.info(f"Modelo cargado: {model_name} desde {model_path}")
                else:
                    logger.warning(f"Archivo de modelo no encontrado: {model_path}")
            except Exception as e:
                logger.error(f"Error cargando modelo {model_name}: {str(e)}")

        if not self.models:
            logger.warning("No se cargaron modelos - Algunas funciones estarán limitadas")

    def autocorrelation_analysis(self, series: np.ndarray, max_lags: int = 20) -> Dict[int, float]:
        if not isinstance(series, np.ndarray):
            logger.error("La serie debe ser un array de numpy")
            return {}
        if len(series) < 10:
            logger.warning("Serie demasiado corta para análisis de autocorrelación")
            return {}
        max_lags = min(max_lags, len(series) // 2)
        if max_lags < 1:
            return {}
        results = {}
        for lag in range(1, max_lags + 1):
            try:
                if len(series) <= lag:
                    continue
                clean_series1 = series[:-lag]
                clean_series2 = series[lag:]
                mask = np.isfinite(clean_series1) & np.isfinite(clean_series2)
                if np.sum(mask) < 2:
                    continue
                corr = pearsonr(clean_series1[mask], clean_series2[mask])[0]
                results[lag] = corr if not np.isnan(corr) else 0
            except Exception as e:
                logger.error(f"Error en lag {lag}: {str(e)}")
        return results

    def _safe_correlation(self, func, x, y):
        try:
            mask = np.isfinite(x) & np.isfinite(y)
            x_clean = x[mask]
            y_clean = y[mask]
            if len(x_clean) < 2:
                return np.nan
            return func(x_clean, y_clean)[0]
        except Exception as e:
            logger.error(f"Error calculando correlación: {str(e)}")
            return np.nan

    def cross_correlation_matrix(self, df: Optional[pd.DataFrame] = None, method: str = 'pearson') -> pd.DataFrame:
        methods = {
            'pearson': pearsonr,
            'spearman': spearmanr,
            'kendall': kendalltau
        }
        if method not in methods:
            raise ValueError(f"Método {method} no soportado. Opciones: {list(methods.keys())}")
        if df is None:
            try:
                df = self.loader.load_training_data()
                df = self.preprocessor.reduce_memory_usage(df)
            except Exception as e:
                logger.error(f"Error cargando datos: {str(e)}")
                return pd.DataFrame()
        numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
        if not numeric_cols:
            logger.warning("No se encontraron columnas numéricas para análisis de correlación")
            return pd.DataFrame()
        matrix = pd.DataFrame(index=numeric_cols, columns=numeric_cols)
        for i, col1 in enumerate(numeric_cols):
            matrix.loc[col1, col1] = 1.0
            for col2 in numeric_cols[i + 1:]:
                corr = self._safe_correlation(methods[method], df[col1], df[col2])
                matrix.loc[col1, col2] = corr
                matrix.loc[col2, col1] = corr
        return matrix

    def detect_significant_patterns(self, df: pd.DataFrame = None, threshold: float = 0.7, p_value: float = 0.05) -> Dict[str, Dict[str, float]]:
        if df is None:
            try:
                df = self.loader.load_all().get('training', pd.DataFrame())
            except Exception as e:
                logger.error(f"Error cargando datos: {str(e)}")
                return {}
        if df.empty:
            logger.warning("DataFrame vacío - No se pueden detectar patrones")
            return {}
        numeric_cols = df.select_dtypes(include=np.number).columns
        patterns = {}
        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i + 1:]:
                try:
                    mask = np.isfinite(df[col1]) & np.isfinite(df[col2])
                    if np.sum(mask) < 10:
                        continue
                    corr, p_val = pearsonr(df[col1][mask], df[col2][mask])
                    if abs(corr) >= threshold and p_val <= p_value:
                        patterns[f"{col1} vs {col2}"] = {
                            'correlation': corr,
                            'p_value': p_val,
                            'method': 'pearson'
                        }
                except Exception as e:
                    logger.error(f"Error analizando {col1} vs {col2}: {str(e)}")
        return patterns

    def plot_correlogram(self, save_path: Optional[str] = None, figsize: Tuple[int, int] = (14, 10), dpi: int = 300):
        try:
            df = self.loader.load_hash_data()
            if df.empty:
                logger.warning("No hay datos para generar correlograma")
                return
            corr_matrix = self.cross_correlation_matrix(df)
            if corr_matrix.empty:
                logger.warning("Matriz de correlación vacía")
                return
            plt.figure(figsize=figsize, facecolor='white')
            sns.set_theme(style="whitegrid", palette="muted")
            mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
            sns.heatmap(
                corr_matrix.astype(float),
                mask=mask,
                annot=True,
                fmt=".2f",
                cmap="vlag",
                center=0,
                linewidths=0.5,
                annot_kws={"size": 8},
                cbar_kws={"shrink": 0.8}
            )
            plt.title("Análisis de Correlación de Nonces", pad=20, fontsize=14)
            plt.xticks(rotation=45, ha='right')
            plt.yticks(rotation=0)
            if not save_path:
                save_path = self.report_dir / "correlogram.png"
            elif not os.path.isabs(str(save_path)):
                save_path = self.report_dir / save_path
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, bbox_inches='tight', dpi=dpi)
            plt.close()
            logger.info(f"Correlograma guardado en: {save_path}")
        except Exception as e:
            logger.error(f"Error generando correlograma: {str(e)}")

    def analyze_and_report(self) -> Dict:
        report = {
            'metadata': {
                'execution_time': datetime.now().isoformat(),
                'base_dir': self.base_dir,
                'status': 'success'
            },
            'autocorrelation': {},
            'cross_correlations': {},
            'significant_patterns': {},
            'model_insights': {}
        }
        try:
            logger.info("Iniciando análisis completo de distribución")
            try:
                hash_data = self.loader.load_hash_data()
                if hash_data.empty:
                    raise ValueError("Datos de hash vacíos")
                logger.info(f"Datos cargados: {hash_data.shape[0]} muestras, {hash_data.shape[1]} características")
            except Exception as e:
                report['metadata']['status'] = 'data_load_error'
                report['metadata']['error'] = str(e)
                logger.error(f"Error cargando datos: {str(e)}")
                return report
            try:
                report['autocorrelation'] = self.autocorrelation_analysis(hash_data['nonce'].values)
                logger.info(f"Autocorrelación calculada para {len(report['autocorrelation'])} lags")
            except Exception as e:
                report['metadata']['status'] = 'autocorrelation_error'
                report['metadata']['error'] = str(e)
                logger.error(f"Error en autocorrelación: {str(e)}")
            try:
                report['cross_correlations'] = self.cross_correlation_matrix(hash_data)
                logger.info("Matriz de correlación cruzada calculada")
            except Exception as e:
                report['metadata']['status'] = 'correlation_error'
                report['metadata']['error'] = str(e)
                logger.error(f"Error en correlaciones cruzadas: {str(e)}")
            try:
                report['significant_patterns'] = self.detect_significant_patterns(hash_data)
                logger.info(f"{len(report['significant_patterns'])} patrones significativos detectados")
            except Exception as e:
                report['metadata']['status'] = 'pattern_error'
                report['metadata']['error'] = str(e)
                logger.error(f"Error detectando patrones: {str(e)}")
            try:
                self.plot_correlogram(save_path="correlogram.png")
                report['metadata']['correlogram_path'] = str(self.report_dir / "correlogram.png")
            except Exception as e:
                report['metadata']['status'] = 'plot_error'
                report['metadata']['error'] = str(e)
                logger.error(f"Error generando correlograma: {str(e)}")
            if self.models:
                try:
                    report['model_insights'] = self._generate_model_insights(hash_data)
                    logger.info("Insights de modelos generados")
                except Exception as e:
                    logger.error(f"Error generando insights de modelos: {str(e)}")
            report_path = self.report_dir / f"distribution_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            report['metadata']['report_path'] = str(report_path)
            logger.info(f"Reporte completo guardado en: {report_path}")
        except Exception as e:
            report['metadata']['status'] = 'critical_error'
            report['metadata']['error'] = str(e)
            logger.exception("Error crítico en análisis completo")
        return report

    def _generate_model_insights(self, data: pd.DataFrame) -> Dict:
        insights = {}
        if 'nonce' not in data.columns:
            logger.warning("Columna 'nonce' no encontrada para insights de modelos")
            return insights
        if 'hash_score' not in data.columns:
            logger.warning("Columna 'hash_score' no encontrada para insights de modelos")
        if 'ethical' in self.models:
            try:
                if hasattr(self.models['ethical'], 'predict_proba'):
                    ethical_preds = self.models['ethical'].predict_proba(data[['nonce']])[:, 1]
                    if 'hash_score' in data.columns:
                        insights['ethical_correlation'] = pearsonr(
                            data['hash_score'].values,
                            ethical_preds
                        )[0]
                    insights['ethical_predictions'] = {
                        'mean': float(np.mean(ethical_preds)),
                        'std': float(np.std(ethical_preds)),
                        'min': float(np.min(ethical_preds)),
                        'max': float(np.max(ethical_preds))
                    }
            except Exception as e:
                logger.error(f"Error generando insights para modelo ético: {str(e)}")
        if 'classifier' in self.models:
            try:
                if hasattr(self.models['classifier'], 'predict'):
                    hash_classes = self.models['classifier'].predict(data[['nonce']])
                    class_dist = pd.Series(hash_classes).value_counts(normalize=True)
                    insights['class_distribution'] = class_dist.to_dict()
                    if 'hash_score' in data.columns:
                        class_scores = data.groupby(hash_classes)['hash_score'].agg(['mean', 'std'])
                        insights['class_scores'] = class_scores.to_dict()
            except Exception as e:
                logger.error(f"Error generando insights para clasificador: {str(e)}")
        return insights


if __name__ == "__main__":
    try:
        logger.info("Iniciando análisis de distribución")
        analyzer = DistributionAnalyzer()
        report = analyzer.analyze_and_report()
        print("\nResumen del análisis:")
        print(f"- Estado: {report['metadata']['status']}")
        print(f"- Autocorrelaciones calculadas: {len(report.get('autocorrelation', {}))}")
        print(f"- Patrones significativos detectados: {len(report.get('significant_patterns', {}))}")
        print(f"- Insights IA: {len(report.get('model_insights', {}))}")
        if 'report_path' in report['metadata']:
            print(f"\nReporte completo guardado en: {report['metadata']['report_path']}")
        if 'correlogram_path' in report['metadata']:
            print(f"Correlograma guardado en: {report['metadata']['correlogram_path']}")
    except Exception as e:
        logger.exception("Error crítico en la ejecución principal")
        print(f"Error: {str(e)} - Ver logs para detalles")

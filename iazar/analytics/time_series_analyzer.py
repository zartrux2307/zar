import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, Optional, Union
from ..utils.nonce_loader import NonceLoader
from ..utils.config_manager import ConfigManager
from ..utils.data_preprocessing import NonceDataPreprocessor
import logging
import mlflow

class TimeSeriesAnalyzer:
    """Analizador avanzado de series temporales para datos de minería."""

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self.loader = NonceLoader(self.config)
        self.preprocessor = NonceDataPreprocessor()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialize_parameters()

    def _initialize_parameters(self):
        """Carga parámetros de configuración"""
        self.window_sizes = self.config.get('ts_windows', [10, 50, 100])
        self.metrics = self.config.get('ts_metrics', ['ma', 'ema', 'std'])
        self.report_path = Path(self.config.get('reports_path', 'iazar/logs/reports/timeseries'))

    def load_and_prepare_data(self) -> pd.DataFrame:
        """Carga y prepara datos temporales de minería"""
        df = self.loader.load_hash_data()
        df = df.set_index('timestamp').sort_index()
        return self.preprocessor.preprocess(df)

    def calculate_moving_average(self, data: pd.Series, window: int) -> pd.Series:
        """Calcula media móvil con validación de ventana"""
        if len(data) < window:
            self.logger.warning(f"Ventana demasiado grande ({window}) para datos de longitud {len(data)}")
            window = max(1, len(data)//2)
        return data.rolling(window=window, min_periods=1).mean()

    def calculate_ema(self, data: pd.Series, span: int) -> pd.Series:
        """Calcula media móvil exponencial"""
        return data.ewm(span=span, adjust=False).mean()

    def calculate_volatility(self, data: pd.Series, window: int) -> pd.Series:
        """Calcula volatilidad (desviación estándar móvil)"""
        return data.rolling(window=window).std()

    def analyze(self, feature: str = 'hash_score') -> Dict[str, Union[pd.Series, dict]]:
        """Ejecuta análisis completo de series temporales"""
        try:
            df = self.load_and_prepare_data()
            results = {}

            for window in self.window_sizes:
                if 'ma' in self.metrics:
                    results[f'ma_{window}'] = self.calculate_moving_average(df[feature], window)
                if 'ema' in self.metrics:
                    results[f'ema_{window}'] = self.calculate_ema(df[feature], window)
                if 'std' in self.metrics:
                    results[f'std_{window}'] = self.calculate_volatility(df[feature], window)

            self._generate_visualizations(results, feature)
            self._log_metrics(results)

            return {
                'series': results,
                'cross_correlation': self._calculate_cross_correlation(results),
                'stationarity_test': self._check_stationarity(df[feature])
            }

        except Exception as e:
            self.logger.error(f"Error en análisis de series temporales: {str(e)}")
            raise

    def _generate_visualizations(self, data: dict, feature: str):
        """Genera y guarda visualizaciones profesionales"""
        plt.figure(figsize=(12, 6))

        for key, series in data.items():
            plt.plot(series, label=key.replace('_', ' ').upper())

        plt.title(f"Análisis Temporal de {feature}", pad=15)
        plt.xlabel("Timestamp")
        plt.ylabel("Valor")
        plt.legend()
        plt.grid(True)

        self.report_path.mkdir(exist_ok=True, parents=True)
        plot_file = self.report_path / f"ts_analysis_{feature}.png"
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        plt.close()

        if mlflow.active_run():
            mlflow.log_artifact(str(plot_file))

    def _log_metrics(self, data: dict):
        """Registra métricas clave en MLflow"""
        metrics = {
            f"{key}_final": values[-1] 
            for key, values in data.items() 
            if len(values) > 0
        }

        if mlflow.active_run():
            mlflow.log_metrics(metrics)

    def _calculate_cross_correlation(self, data: dict) -> pd.DataFrame:
        """Calcula correlación cruzada entre las diferentes métricas"""
        return pd.DataFrame(data).corr()

    def _check_stationarity(self, series: pd.Series, test: str = 'adfuller') -> Dict:
        """Realiza test de estacionalidad"""
        from statsmodels.tsa.stattools import adfuller

        result = adfuller(series.dropna())
        return {
            'test': test,
            'statistic': result[0],
            'p_value': result[1],
            'is_stationary': result[1] < 0.05
        }

    def generate_features(self, target: str = 'hash_score') -> pd.DataFrame:
        """Genera características para modelos de forecasting"""
        df = self.load_and_prepare_data()
        features = pd.DataFrame(index=df.index)

        for window in self.window_sizes:
            features[f'ma_{window}'] = self.calculate_moving_average(df[target], window)
            features[f'ema_{window}'] = self.calculate_ema(df[target], window)
            features[f'std_{window}'] = self.calculate_volatility(df[target], window)

        features['hour'] = df.index.hour
        features['day_of_week'] = df.index.dayofweek
        features['target'] = df[target]

        return features.dropna()

    @classmethod
    def example_usage(cls):
        """Ejemplo de integración con el proyecto"""
        config = ConfigManager(config_path="iazar/config/ia_config.json")
        analyzer = cls(config)

        try:
            analysis_results = analyzer.analyze('nonce')
            print("Análisis completado. Métricas calculadas:")
            print(list(analysis_results['series'].keys()))

            features = analyzer.generate_features()
            print("\nCaracterísticas generadas para forecasting:")
            print(features.head())

            return features

        except Exception as e:
            print(f"Error en análisis: {str(e)}")
            return None

if __name__ == "__main__":
    TimeSeriesAnalyzer.example_usage()

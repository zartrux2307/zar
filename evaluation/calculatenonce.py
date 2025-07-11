import argparse
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from datetime import datetime
from typing import Dict
import os
import sys
from iazar.utils.nonce_loader import NonceLoader


# Establecer el directorio del proyecto
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
# Configuración profesional de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nonce_analysis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NonceAnalyzer")


class DataLoader:
    """Carga y prepara datos desde archivos CSV locales"""
    REQUIRED_COLUMNS = ['nonce', 'timestamp']

    def __init__(self, config=None):
        self.loader = NonceLoader(config=config)
        self.data_path = os.path.join(self.loader.training_dir, "nonce_training_data.csv")
        self.results_dir = os.path.join(self.loader.data_dir, "analysis_results")
        os.makedirs(self.results_dir, exist_ok=True)
        self.df = None

    def load_and_prepare(self) -> pd.DataFrame:
        """Carga datos y realiza limpieza básica con verificación de existencia"""
        logger.info(f"Intentando cargar datos desde: {self.data_path}")

        if not os.path.exists(self.data_path):
            logger.error(f"Archivo de datos no encontrado: {self.data_path}")
            raise FileNotFoundError(f"Archivo de datos no encontrado: {self.data_path}")

        try:
            # Detectar tamaño para estrategia de lectura
            file_size = os.path.getsize(self.data_path)
            logger.info(f"Tamaño del archivo: {file_size / (1024 * 1024):.2f} MB")

            if file_size > 50 * 1024 * 1024:  # > 50 MB
                logger.info("Archivo grande, usando lectura por chunks")
                chunks = []
                for chunk in pd.read_csv(self.data_path, chunksize=10000,
                                         on_bad_lines='warn', encoding='utf-8'):
                    chunks.append(chunk)
                self.df = pd.concat(chunks, ignore_index=True)
            else:
                self.df = pd.read_csv(self.data_path, on_bad_lines='warn', encoding='utf-8')

            # Validar estructura
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in self.df.columns]
            if missing_cols:
                raise ValueError(f"Columnas requeridas faltantes: {', '.join(missing_cols)}")

            # Convertir tipos de datos
            self.df['nonce'] = self.df['nonce'].astype(np.uint32)

            # Convertir timestamp si es necesario
            if not pd.api.types.is_datetime64_any_dtype(self.df['timestamp']):
                try:
                    self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], unit='s')
                except BaseException:
                    try:
                        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
                    except Exception as e:
                        logger.warning(f"No se pudo convertir timestamp: {str(e)}")
                        self.df['timestamp'] = datetime.now()

            # Limpieza básica
            initial_count = len(self.df)
            self.df = self.df.dropna(subset=['nonce', 'timestamp'])
            self.df = self.df[self.df['nonce'] <= 2**32]
            cleaned_count = initial_count - len(self.df)

            if cleaned_count > 0:
                logger.info(f"Limpieza: eliminados {cleaned_count} registros inválidos")

            logger.info(f"Datos cargados exitosamente: {self.df.shape[0]} registros válidos")
            return self.df.copy()

        except Exception as e:
            logger.exception(f"Error crítico cargando datos: {str(e)}")
            raise


class NonceAnalyzer:
    """Analizador estadístico avanzado de nonces"""
    MAX_NONCE = 2**32  # 4,294,967,295
    STRATEGY_THRESHOLDS = {
        'low_range': (0, 100_000),
        'mid_range': (2.1e9, 2.2e9),
        'high_range': (4_294_000_000, MAX_NONCE)
    }

    def __init__(self, df: pd.DataFrame, results_dir: str):
        self.df = df
        self.results_dir = results_dir
        self.validate_data()

    def validate_data(self):
        """Valida la integridad de los datos"""
        if self.df.empty:
            raise ValueError("El DataFrame de entrada está vacío")

        if 'nonce' not in self.df.columns:
            raise ValueError("Columna 'nonce' no encontrada en los datos")

        logger.info(f"Datos validados. Rango temporal: {self.df['timestamp'].min()} - {self.df['timestamp'].max()}")

    def calculate_distribution(self) -> Dict[str, float]:
        """Calcula distribución con estadísticas avanzadas"""
        total_blocks = len(self.df)
        results = {}

        # Calcular métricas básicas
        results['global_mean'] = self.df['nonce'].mean()
        results['global_median'] = self.df['nonce'].median()
        results['global_std'] = self.df['nonce'].std()

        for strategy, (low, high) in self.STRATEGY_THRESHOLDS.items():
            mask = (self.df['nonce'] >= low) & (self.df['nonce'] <= high)
            count = len(self.df[mask])
            pct = (count / total_blocks) * 100 if total_blocks > 0 else 0
            results[f'pct_{strategy}'] = pct

            # Estadísticas por rango
            subset = self.df[mask]['nonce']
            if not subset.empty:
                results[f'{strategy}_mean'] = subset.mean()
                results[f'{strategy}_std'] = subset.std()
                results[f'{strategy}_min'] = subset.min()
                results[f'{strategy}_max'] = subset.max()
            else:
                logger.warning(f"No se encontraron datos en el rango: {strategy}")
                results[f'{strategy}_mean'] = 0
                results[f'{strategy}_std'] = 0
                results[f'{strategy}_min'] = 0
                results[f'{strategy}_max'] = 0

        # Análisis de densidad avanzado
        results['kurtosis'] = stats.kurtosis(self.df['nonce']) if len(self.df) > 3 else 0
        results['skew'] = stats.skew(self.df['nonce']) if len(self.df) > 3 else 0
        results['entropy'] = self.calculate_entropy() if len(self.df) > 1 else 0

        logger.info(f"Distribución calculada con {len(self.df)} bloques")
        return results

    def calculate_entropy(self) -> float:
        """Calcula la entropía de la distribución de nonces"""
        hist, _ = np.histogram(self.df['nonce'], bins=min(1000, len(self.df)))
        prob = hist / hist.sum()
        return -np.sum(prob * np.log2(prob + 1e-10))

    def detect_clusters(self) -> Dict:
        """Detección avanzada de clusters usando KDE"""
        from sklearn.neighbors import KernelDensity
        from sklearn.cluster import DBSCAN

        if len(self.df) < 100:
            logger.warning("Insuficientes datos para detección de clusters")
            return {
                'cluster_labels': [],
                'n_clusters': 0,
                'kde_score': 0,
                'sample_size': 0
            }

        # Usar una muestra si el dataset es muy grande
        sample_size = min(10000, len(self.df))
        sample = self.df['nonce'].sample(sample_size, random_state=42).values

        # Transformación logarítmica para mejor distribución
        log_nonces = np.log1p(sample).reshape(-1, 1)

        # Estimación de densidad de kernel
        kde = KernelDensity(bandwidth=0.05, kernel='gaussian')
        kde.fit(log_nonces)

        # Identificación de clusters
        clustering = DBSCAN(eps=0.3, min_samples=min(10, sample_size // 100)).fit(log_nonces)
        labels = clustering.labels_
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        return {
            'cluster_labels': labels,
            'n_clusters': n_clusters,
            'kde_score': kde.score(log_nonces),
            'sample_size': sample_size
        }

    def plot_distribution(self, output_file: str = "nonce_distribution.png"):
        """Visualización profesional con múltiples vistas"""
        if self.df.empty:
            logger.error("No hay datos para generar gráficos")
            return

        plt.figure(figsize=(15, 10))

        # Histograma principal
        plt.subplot(2, 2, 1)
        plt.hist(self.df['nonce'], bins=min(1000, len(self.df)), alpha=0.7, color='royalblue', log=True)
        plt.axvline(x=2.15e9, color='red', linestyle='--', label='Punto medio (2.15e9)')
        plt.axvline(x=4.294e9, color='green', linestyle='--', label='Máximo (4.294e9)')
        plt.title('Distribución de Nonces', fontsize=14)
        plt.xlabel('Valor del Nonce', fontsize=12)
        plt.ylabel('Frecuencia (log)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)

        # Gráfico de densidad KDE
        plt.subplot(2, 2, 2)
        if len(self.df) > 100:
            from sklearn.neighbors import KernelDensity
            sample = self.df['nonce'].sample(min(5000, len(self.df)), random_state=42)
            kde = KernelDensity(bandwidth=0.01, kernel='gaussian')
            kde.fit(np.log1p(sample.values).reshape(-1, 1))

            x = np.linspace(0, self.MAX_NONCE, 1000)
            log_dens = kde.score_samples(np.log1p(x).reshape(-1, 1))

            plt.fill_between(x, np.exp(log_dens), alpha=0.5)
            plt.title('Densidad de Probabilidad (KDE)', fontsize=14)
            plt.xlabel('Nonce')
            plt.ylabel('Densidad')
        else:
            plt.text(0.5, 0.5, "Insuficientes datos para KDE",
                     ha='center', va='center', fontsize=12)
            plt.title('Densidad de Probabilidad (KDE)', fontsize=14)

        # Boxplot por estrategia
        plt.subplot(2, 2, 3)
        strategies = []
        values = []
        for strategy, (low, high) in self.STRATEGY_THRESHOLDS.items():
            subset = self.df[(self.df['nonce'] >= low) & (self.df['nonce'] <= high)]['nonce']
            if len(subset) > 0:
                strategies.append(strategy)
                values.append(subset)

        if values:
            plt.boxplot(values, labels=strategies, showfliers=False)
            plt.title('Distribución por Estrategia', fontsize=14)
            plt.ylabel('Valor Nonce')
            plt.yscale('log')
        else:
            plt.text(0.5, 0.5, "No hay datos para estrategias",
                     ha='center', va='center', fontsize=12)
            plt.title('Distribución por Estrategia', fontsize=14)

        # Serie temporal (si hay suficientes datos)
        plt.subplot(2, 2, 4)
        if len(self.df) > 100:
            time_df = self.df.set_index('timestamp').resample('W').size()
            time_df.plot(kind='line', ax=plt.gca())
            plt.title('Frecuencia Temporal de Nonces', fontsize=14)
            plt.xlabel('Fecha')
            plt.ylabel('Nonces por semana')
        else:
            plt.scatter(self.df['timestamp'], self.df['nonce'], alpha=0.5, s=10)
            plt.title('Distribución Temporal', fontsize=14)
            plt.xlabel('Fecha')
            plt.ylabel('Nonce')

        plt.tight_layout()

        output_path = os.path.join(self.results_dir, output_file)
        plt.savefig(output_path, dpi=300)
        plt.close()
        logger.info(f"Gráfico guardado en {output_path}")

        # Guardar datos procesados
        self.save_processed_data(output_path.replace('.png', '_data.csv'))

    def save_processed_data(self, output_path: str):
        """Guarda datos procesados para análisis posterior"""
        processed_df = self.df.copy()
        for strategy, (low, high) in self.STRATEGY_THRESHOLDS.items():
            processed_df[strategy] = ((processed_df['nonce'] >= low) &
                                      (processed_df['nonce'] <= high)).astype(int)

        processed_df.to_csv(output_path, index=False)
        logger.info(f"Datos procesados guardados en {output_path}")

    def run_analysis(self):
        """Ejecuta el análisis completo"""
        logger.info(f"Iniciando análisis con {len(self.df)} bloques")

        try:
            # Paso 1: Calcular estadísticas
            stats = self.calculate_distribution()

            # Paso 2: Detectar clusters
            cluster_info = self.detect_clusters()

            # Paso 3: Visualización
            self.plot_distribution()

            # Paso 4: Generar reporte
            report = self.generate_report(stats, cluster_info)

            # Guardar reporte en archivo
            report_path = os.path.join(self.results_dir, "nonce_analysis_report.txt")
            with open(report_path, "w") as f:
                f.write(report)

            logger.info(f"Reporte guardado en {report_path}")
            return stats

        except Exception as e:
            logger.exception(f"Error durante el análisis: {str(e)}")
            return None

    def generate_report(self, stats: Dict, cluster_info: Dict) -> str:
        """Genera un reporte detallado de análisis"""
        return f"""
        ===== ANÁLISIS PROFESIONAL DE NONCES =====
        Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Bloques analizados: {len(self.df)}
        Rango temporal: {self.df['timestamp'].min().date()} - {self.df['timestamp'].max().date()}

        DISTRIBUCIÓN DE ESTRATEGIAS:
        - Búsqueda lineal desde 0: {stats['pct_low_range']:.2f}%
          (μ={stats.get('low_range_mean', 0):.2e}, σ={stats.get('low_range_std', 0):.2e})
        - Búsqueda desde punto medio: {stats['pct_mid_range']:.2f}%
          (μ={stats.get('mid_range_mean', 0):.2e}, σ={stats.get('mid_range_std', 0):.2e})
        - Búsqueda desde máximo: {stats['pct_high_range']:.2f}%
          (μ={stats.get('high_range_mean', 0):.2e}, σ={stats.get('high_range_std', 0):.2e})

        ESTADÍSTICAS GLOBALES:
        - Media: {stats['global_mean']:.2e}
        - Mediana: {stats['global_median']:.2e}
        - Desviación estándar: {stats['global_std']:.2e}
        - Curtosis: {stats['kurtosis']:.2f} ({"leptocúrtica" if stats['kurtosis'] > 3 else "platicúrtica"})
        - Asimetría: {stats['skew']:.2f}
        - Entropía: {stats['entropy']:.4f}
        - Clusters detectados: {cluster_info['n_clusters']} (muestra={cluster_info['sample_size']})

        CONCLUSIONES:
        La distribución muestra patrones claros de estrategias de minería según el estudio "Utter Noncesense".
        La entropía de {stats['entropy']:.4f} sugiere 
        {'baja aleatoriedad' if stats['entropy'] < 8.0 else 'alta aleatoriedad'} en la distribución.
        """


def main():
    parser = argparse.ArgumentParser(description='Análisis profesional de distribución de nonces en Monero')
    parser.add_argument('--config', type=str, default='ia_config',
                        help='Nombre de la configuración a usar')
    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("INICIANDO ANÁLISIS DE DISTRIBUCIÓN DE NONCES")
        logger.info("=" * 60)

        # Inicializar cargador de datos
        data_loader = DataLoader(config=args.config)

        # Cargar datos
        logger.info("Cargando datos de entrenamiento...")
        df = data_loader.load_and_prepare()

        # Analizar datos
        logger.info("Iniciando análisis estadístico...")
        analyzer = NonceAnalyzer(df, data_loader.results_dir)
        results = analyzer.run_analysis()

        if results:
            logger.info("Análisis completado exitosamente")
            logger.info(f"Resultados guardados en: {data_loader.results_dir}")
        else:
            logger.error("El análisis no pudo completarse correctamente")

        logger.info("=" * 60)
        logger.info("PROCESO FINALIZADO")
        logger.info("=" * 60)

        return 0 if results else 1

    except Exception as e:
        logger.exception(f"Error fatal en el proceso principal: {str(e)}")
        return 2


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

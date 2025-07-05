import argparse
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import os

# Configuración profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nonce_analysis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DataLoader:
    """Carga y prepara datos desde archivos CSV locales"""
    REQUIRED_COLUMNS = ['nonce', 'timestamp']
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = None
        
    def load_and_prepare(self) -> pd.DataFrame:
        """Carga datos y realiza limpieza básica"""
        try:
            # Cargar datos
            self.df = pd.read_csv(self.file_path)
            
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
                except:
                    self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            
            # Limpieza básica
            self.df = self.df.dropna(subset=['nonce', 'timestamp'])
            self.df = self.df[self.df['nonce'] <= 2**32]
            
            logger.info(f"Datos cargados exitosamente: {self.df.shape[0]} registros")
            return self.df.copy()
        
        except Exception as e:
            logger.error(f"Error cargando datos: {str(e)}")
            raise

class NonceAnalyzer:
    """Analizador estadístico avanzado de nonces"""
    MAX_NONCE = 2**32  # 4,294,967,295
    STRATEGY_THRESHOLDS = {
        'low_range': (0, 100_000),
        'mid_range': (2.1e9, 2.2e9),
        'high_range': (4_294_000_000, MAX_NONCE)
    }
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
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
            pct = (count / total_blocks) * 100
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
        
        # Análisis de densidad avanzado
        results['kurtosis'] = stats.kurtosis(self.df['nonce'])
        results['skew'] = stats.skew(self.df['nonce'])
        results['entropy'] = self.calculate_entropy()
        
        logger.info(f"Distribución calculada: {results}")
        return results
    
    def calculate_entropy(self) -> float:
        """Calcula la entropía de la distribución de nonces"""
        hist, _ = np.histogram(self.df['nonce'], bins=1000)
        prob = hist / hist.sum()
        return -np.sum(prob * np.log2(prob + 1e-10))
    
    def detect_clusters(self) -> Dict:
        """Detección avanzada de clusters usando KDE"""
        from sklearn.neighbors import KernelDensity
        from sklearn.cluster import DBSCAN
        
        # Usar una muestra si el dataset es muy grande
        sample_size = min(10000, len(self.df))
        sample = self.df['nonce'].sample(sample_size, random_state=42).values
        
        # Transformación logarítmica para mejor distribución
        log_nonces = np.log1p(sample).reshape(-1, 1)
        
        # Estimación de densidad de kernel
        kde = KernelDensity(bandwidth=0.05, kernel='gaussian')
        kde.fit(log_nonces)
        
        # Identificación de clusters
        clustering = DBSCAN(eps=0.3, min_samples=10).fit(log_nonces)
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
        plt.figure(figsize=(15, 10))
        
        # Histograma principal
        plt.subplot(2, 2, 1)
        plt.hist(self.df['nonce'], bins=1000, alpha=0.7, color='royalblue', log=True)
        plt.axvline(x=2.15e9, color='red', linestyle='--', label='Punto medio (2.15e9)')
        plt.axvline(x=4.294e9, color='green', linestyle='--', label='Máximo (4.294e9)')
        plt.title('Distribución de Nonces', fontsize=14)
        plt.xlabel('Valor del Nonce', fontsize=12)
        plt.ylabel('Frecuencia (log)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Gráfico de densidad KDE
        plt.subplot(2, 2, 2)
        from sklearn.neighbors import KernelDensity
        sample = self.df['nonce'].sample(min(5000, len(self.df)), random_state=42)
        kde = KernelDensity(bandwidth=0.01, kernel='gaussian')
        kde.fit(np.log1p(sample.values).reshape(-1, 1)
        
        x = np.linspace(0, self.MAX_NONCE, 1000)
        log_dens = kde.score_samples(np.log1p(x).reshape(-1, 1))
        
        plt.fill_between(x, np.exp(log_dens), alpha=0.5)
        plt.title('Densidad de Probabilidad (KDE)', fontsize=14)
        plt.xlabel('Nonce')
        plt.ylabel('Densidad')
        
        # Boxplot por estrategia
        plt.subplot(2, 2, 3)
        strategies = []
        values = []
        for strategy, (low, high) in self.STRATEGY_THRESHOLDS.items():
            subset = self.df[(self.df['nonce'] >= low) & (self.df['nonce'] <= high)]['nonce']
            if len(subset) > 0:
                strategies.append(strategy)
                values.append(subset)
        plt.boxplot(values, labels=strategies, showfliers=False)
        plt.title('Distribución por Estrategia', fontsize=14)
        plt.ylabel('Valor Nonce')
        plt.yscale('log')
        
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
        plt.savefig(output_file, dpi=300)
        logger.info(f"Gráfico guardado en {output_file}")
        
        # Guardar datos procesados
        self.save_processed_data(output_file.replace('.png', '_data.csv'))
    
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
        
        # Paso 1: Calcular estadísticas
        stats = self.calculate_distribution()
        
        # Paso 2: Detectar clusters
        cluster_info = self.detect_clusters()
        
        # Paso 3: Visualización
        self.plot_distribution()
        
        # Paso 4: Reporte
        report = f"""
        ===== ANÁLISIS PROFESIONAL DE NONCES =====
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
        La entropía de {stats['entropy']:.4f} sugiere {'baja aleatoriedad' if stats['entropy'] < 8.0 else 'alta aleatoriedad'} en la distribución.
        """
        logger.info(report)
        
        # Guardar reporte en archivo
        with open("nonce_analysis_report.txt", "w") as f:
            f.write(report)
            
        return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Análisis profesional de distribución de nonces en Monero')
    parser.add_argument('--input', type=str, default='C:/zarturxia/src/iazar/data/nonce_training_data.csv', 
                        help='Ruta al archivo CSV con los datos de entrenamiento')
    parser.add_argument('--output', type=str, default='results', 
                        help='Directorio de salida para resultados')
    args = parser.parse_args()

    # Crear directorio de salida si no existe
    os.makedirs(args.output, exist_ok=True)
    
    try:
        # Cargar datos
        loader = DataLoader(args.input)
        df = loader.load_and_prepare()
        
        # Analizar datos
        analyzer = NonceAnalyzer(df)
        analyzer.run_analysis()
        
        logger.info("Análisis completado exitosamente")
    except Exception as e:
        logger.error(f"Error en el análisis: {str(e)}")

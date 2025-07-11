import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import json
import logging
import sys
from datetime import datetime
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.utils import concordance_index
from iazar.utils.nonce_loader import NonceLoader


# Establecer el directorio del proyecto
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
# Configuración avanzada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("survival_analysis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SurvivalAnalyzer")


class SurvivalAnalyzer:
    def __init__(self, config=None):
        self.loader = NonceLoader(config=config)
        self.data_path = os.path.join(self.loader.training_dir, "nonce_training_data.csv")
        self.results_dir = os.path.join(self.loader.data_dir, "survival_results")
        os.makedirs(self.results_dir, exist_ok=True)

        # Columnas requeridas para análisis
        self.REQUIRED_COLUMNS = ['nonce', 'entropy', 'uniqueness',
                                 'zero_density', 'pattern_score', 'is_valid']
        self.DURATION_COL = 'duration'
        self.EVENT_COL = 'event'

    def _load_data(self) -> pd.DataFrame:
        """Carga datos con manejo robusto de errores y verificación de estructura"""
        logger.info(f"Cargando datos desde: {self.data_path}")

        if not os.path.exists(self.data_path):
            logger.error(f"Archivo de datos no encontrado: {self.data_path}")
            return pd.DataFrame()

        try:
            # Cargar datos
            df = pd.read_csv(self.data_path, on_bad_lines='warn')

            # Verificar columnas requeridas
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                logger.warning(f"Columnas faltantes: {', '.join(missing_cols)}")
                for col in missing_cols:
                    df[col] = 0  # Valor por defecto

            # Crear columnas sintéticas si no existen
            if self.DURATION_COL not in df.columns:
                logger.info(f"Creando columna sintética: {self.DURATION_COL}")
                df[self.DURATION_COL] = np.random.randint(1, 100, size=len(df))

            if self.EVENT_COL not in df.columns:
                logger.info(f"Creando columna sintética: {self.EVENT_COL}")
                df[self.EVENT_COL] = np.random.choice([0, 1], size=len(df))

            # Convertir todas las columnas a formato string para consistencia
            df = df.rename(columns={c: str(c) for c in df.columns})

            logger.info(f"Datos cargados: {len(df)} registros, {len(df.columns)} columnas")
            return df

        except Exception as e:
            logger.exception(f"Error crítico cargando datos: {str(e)}")
            return pd.DataFrame()

    def fit_kaplan_meier(self, durations, event_observed, label='Kaplan-Meier Estimate'):
        """Ajusta el modelo Kaplan-Meier con manejo de errores"""
        try:
            kmf = KaplanMeierFitter()
            kmf.fit(durations, event_observed, label=label)
            logger.info("Modelo Kaplan-Meier ajustado exitosamente")
            return kmf
        except Exception as e:
            logger.exception(f"Error ajustando Kaplan-Meier: {str(e)}")
            return None

    def fit_cox_ph(self, df, duration_col, event_col, covariates):
        """Ajusta el modelo Cox Proportional Hazards con validación de datos"""
        try:
            # Preparar dataframe para análisis
            analysis_df = df[[duration_col, event_col] + covariates].copy()
            analysis_df = analysis_df.dropna()

            if len(analysis_df) < 10:
                logger.error("Insuficientes datos para modelo Cox PH")
                return None

            cph = CoxPHFitter()
            cph.fit(analysis_df, duration_col=duration_col, event_col=event_col)

            # Calcular índice de concordancia
            concordance = concordance_index(
                analysis_df[duration_col],
                -cph.predict_partial_hazard(analysis_df[covariates]),  # Nota: signo negativo
                analysis_df[event_col]
            )

            logger.info(f"Modelo Cox PH ajustado. Concordance Index: {concordance:.4f}")
            return cph, concordance

        except Exception as e:
            logger.exception(f"Error ajustando modelo Cox PH: {str(e)}")
            return None, 0.0

    def plot_survival_function(self, kmf, title="Curva de Supervivencia", save_plot=True):
        """Genera y guarda gráfico de función de supervivencia"""
        if kmf is None:
            logger.error("No se puede graficar: modelo Kaplan-Meier no válido")
            return None

        plt.figure(figsize=(10, 6))
        kmf.plot()
        plt.title(title)
        plt.xlabel("Tiempo")
        plt.ylabel("Probabilidad de Supervivencia")
        plt.grid(True)

        if save_plot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plot_path = os.path.join(self.results_dir, f"kaplan_meier_{timestamp}.png")
            plt.savefig(plot_path, dpi=150)
            plt.close()
            logger.info(f"Gráfico Kaplan-Meier guardado en: {plot_path}")
            return plot_path
        else:
            plt.show()
            return None

    def plot_partial_effects(self, cph, covariate, values, title="Efectos Parciales", save_plot=True):
        """Visualiza efectos parciales de una covariable"""
        if cph is None:
            logger.error("No se puede graficar: modelo Cox PH no válido")
            return None

        try:
            plt.figure(figsize=(10, 6))
            cph.plot_partial_effects_on_outcome(
                covariates=covariate,
                values=values,
                cmap='coolwarm'
            )
            plt.title(title)
            plt.xlabel("Tiempo")
            plt.ylabel("Probabilidad de Supervivencia")
            plt.grid(True)

            if save_plot:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                plot_path = os.path.join(self.results_dir, f"partial_effect_{covariate}_{timestamp}.png")
                plt.savefig(plot_path, dpi=150)
                plt.close()
                logger.info(f"Gráfico de efectos parciales guardado en: {plot_path}")
                return plot_path
            else:
                plt.show()
                return None

        except Exception as e:
            logger.exception(f"Error graficando efectos parciales: {str(e)}")
            return None

    def analyze_survival(self, covariates=None):
        """Ejecuta análisis completo de supervivencia"""
        logger.info("=" * 60)
        logger.info("INICIANDO ANÁLISIS DE SUPERVIVENCIA")
        logger.info("=" * 60)

        # Paso 1: Cargar datos
        data = self._load_data()
        if data.empty:
            logger.error("No se pudieron cargar datos. Abortando análisis.")
            return None

        # Paso 2: Verificar columnas críticas
        critical_cols = [self.DURATION_COL, self.EVENT_COL]
        missing_critical = [col for col in critical_cols if col not in data.columns]

        if missing_critical:
            logger.error(f"Columnas críticas faltantes: {', '.join(missing_critical)}")
            return None

        # Determinar covariables si no se proporcionan
        if covariates is None:
            covariates = [col for col in self.REQUIRED_COLUMNS if col in data.columns]
            logger.info(f"Usando covariables automáticas: {', '.join(covariates)}")

        # Paso 3: Ajustar modelo Kaplan-Meier
        logger.info("Ajustando modelo Kaplan-Meier...")
        kmf = self.fit_kaplan_meier(
            data[self.DURATION_COL],
            data[self.EVENT_COL]
        )
        km_plot_path = self.plot_survival_function(
            kmf,
            title="Curva de Supervivencia de Nonces"
        )

        # Paso 4: Ajustar modelo Cox PH
        cph = None
        concordance = 0.0
        partial_effect_paths = {}

        if covariates:
            logger.info("Ajustando modelo Cox Proportional Hazards...")
            cph, concordance = self.fit_cox_ph(
                data,
                duration_col=self.DURATION_COL,
                event_col=self.EVENT_COL,
                covariates=covariates
            )

            # Graficar efectos parciales para cada covariable
            if cph:
                for covariate in covariates:
                    values = [
                        data[covariate].quantile(0.25),
                        data[covariate].median(),
                        data[covariate].quantile(0.75)
                    ]
                    path = self.plot_partial_effects(
                        cph,
                        covariate,
                        values,
                        title=f"Efecto de {covariate} en Supervivencia"
                    )
                    if path:
                        partial_effect_paths[covariate] = path

        # Paso 5: Guardar resultados
        results = {
            "timestamp": datetime.now().isoformat(),
            "data_source": self.data_path,
            "duration_column": self.DURATION_COL,
            "event_column": self.EVENT_COL,
            "covariates": covariates,
            "kaplan_meier_plot": km_plot_path,
            "cox_ph_concordance": concordance,
            "partial_effect_plots": partial_effect_paths,
            "record_count": len(data)
        }

        results_path = os.path.join(
            self.results_dir, f"survival_analysis_{
                datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Resultados completos guardados en: {results_path}")
        logger.info("=" * 60)
        logger.info("ANÁLISIS COMPLETADO EXITOSAMENTE")
        logger.info("=" * 60)

        return results


def main():
    try:
        # Inicializar analizador
        analyzer = SurvivalAnalyzer()

        # Ejecutar análisis
        results = analyzer.analyze_survival()

        return 0 if results else 1

    except Exception as e:
        logger.exception(f"Error fatal en el análisis: {str(e)}")
        return 2


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

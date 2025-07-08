import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import json
import seaborn as sns
import logging
import socket
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.utils import concordance_index
from iazar.utils.feature_utils import COLUMNS
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Columnas estándar globales
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]

def leer_nonces_csv(path):
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
    try:
        logger.info(f"Intentando leer: {os.path.abspath(path)}")
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
    except Exception as e:
        logger.exception(f"Error al leer CSV: {e}")
        raise

# Similar error handling for other functions (guardar_nonces_csv, leer_nonces_json, etc.)

class SurvivalAnalyzer:
    def __init__(self):
        pass

    def fit_kaplan_meier(self, durations, event_observed):
        kmf = KaplanMeierFitter()
        kmf.fit(durations, event_observed, label='Kaplan-Meier Estimate')
        return kmf

    def fit_cox_ph(self, durations, event_observed, covariates):
        # Ensure covariate columns are strings
        covariates = covariates.rename(columns=str)
        
        df = pd.DataFrame({'duration': durations, 'event': event_observed})
        df = df.join(covariates)
        
        cph = CoxPHFitter()
        cph.fit(df, duration_col='duration', event_col='event')
        return cph

    def plot_survival_function(self, kmf, title="Curva de Supervivencia"):
        kmf.plot(figsize=(10, 6))
        plt.title(title)
        plt.xlabel("Tiempo")
        plt.ylabel("Probabilidad de Supervivencia")
        plt.grid(True)
        plt.show()

    def plot_partial_effects_on_outcome(self, cph, covariate, values, baseline_covariates=None, title="Efectos Parciales sobre el Outcome"):
        covariate = str(covariate)  # Ensure string type
        
        # Convert values to list if needed
        if not isinstance(values, list):
            values = values.tolist() if hasattr(values, 'tolist') else list(values)
            
        ax = cph.plot_partial_effects_on_outcome(
            covariates=covariate,
            values=values,
            cmap='coolwarm'
        )
        plt.title(title)
        plt.xlabel("Tiempo")
        plt.ylabel("Probabilidad de Supervivencia")
        plt.grid(True)
        plt.show()

    def analyze_survival(self, data, duration_col, event_col, covariates=None):
        try:
            durations = data[duration_col]
            event_observed = data[event_col]

            kmf = self.fit_kaplan_meier(durations, event_observed)
            self.plot_survival_function(kmf, title=f"Curva de Supervivencia de {duration_col}")

            results = {
                'kaplan_meier_model': kmf,
                'kaplan_meier_summary': kmf.survival_function_
            }

            if covariates is not None:
                cph = self.fit_cox_ph(durations, event_observed, data[covariates])
                
                # Compute baseline covariates (mean values)
                baseline_covariates = data[covariates].mean().to_dict()
                
                for covariate in covariates:
                    # Convert covariate to string explicitly
                    covariate_str = str(covariate)
                    
                    self.plot_partial_effects_on_outcome(
                        cph,
                        covariate=covariate_str,
                        values=[
                            data[covariate_str].quantile(0.25),
                            data[covariate_str].median(),
                            data[covariate_str].quantile(0.75)
                        ],
                        baseline_covariates=baseline_covariates,
                        title=f"Efectos Parciales de {covariate_str}"
                    )
                    
                concordance_idx = concordance_index(
                    durations, 
                    cph.predict_partial_hazard(data[covariates]), 
                    event_observed
                )
                
                results.update({
                    'cox_ph_model': cph,
                    'cox_ph_summary': cph.summary,
                    'concordance_index': concordance_idx
                })

            return results
            
        except Exception as e:
            logger.exception(f"Error en análisis de supervivencia: {e}")
            raise

# Network connection helper (example)
def safe_connect(host, port):
    try:
        # Increased timeout to 30 seconds
        sock = socket.create_connection((host, port), timeout=30)
        logger.info(f"Conexión exitosa a {host}:{port}")
        return sock
    except socket.error as e:
        logger.exception(f"Error de conexión: {e}")
        raise

if __name__ == "__main__":
    try:
        # Debug current working directory
        logger.info(f"Directorio actual: {os.path.abspath('.')}")
        
        data_path = 'C:/zarturxia/src/iazar/data/nonce_training_data.csv'
        logger.info(f"Intentando cargar datos de: {os.path.abspath(data_path)}")
        
        df = pd.read_csv(data_path)
        df['duration'] = np.random.randint(1, 100, size=len(df))
        df['event'] = np.random.choice([0, 1], size=len(df))

        covariates = ['nonce', 'entropy', 'uniqueness', 'zero_density', 'pattern_score', 'is_valid']
        
        # Convert all covariate columns to string type
        df = df.rename(columns={c: str(c) for c in covariates})
        covariates = [str(c) for c in covariates]

        survival_analyzer = SurvivalAnalyzer()
        results = survival_analyzer.analyze_survival(
            df, 
            duration_col='duration', 
            event_col='event', 
            covariates=covariates
        )
        
        logger.info(f"Análisis completado: Concordance Index={results.get('concordance_index', 'N/A')}")
        
    except Exception as e:
        logger.exception(f"Error en ejecución principal: {e}")
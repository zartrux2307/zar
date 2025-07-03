import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.utils import concordance_index

class SurvivalAnalyzer:
    def __init__(self):
        """
        Inicializa el analizador de supervivencia.
        """
        pass

    def fit_kaplan_meier(self, durations, event_observed):
        """
        Ajusta el modelo Kaplan-Meier a los datos.

        Args:
            durations (pd.Series or np.ndarray): Duraciones observadas.
            event_observed (pd.Series or np.ndarray): Indicador de eventos observados (1 si ocurrió, 0 si no).

        Returns:
            KaplanMeierFitter: Modelo ajustado.
        """
        kmf = KaplanMeierFitter()
        kmf.fit(durations, event_observed, label='Kaplan-Meier Estimate')
        return kmf

    def fit_cox_ph(self, durations, event_observed, covariates):
        """
        Ajusta el modelo Cox Proportional Hazards a los datos.

        Args:
            durations (pd.Series or np.ndarray): Duraciones observadas.
            event_observed (pd.Series or np.ndarray): Indicador de eventos observados (1 si ocurrió, 0 si no).
            covariates (pd.DataFrame): Covariables para el modelo.

        Returns:
            CoxPHFitter: Modelo ajustado.
        """
        cph = CoxPHFitter()
        cph.fit(pd.DataFrame({'duration': durations, 'event': event_observed}).join(covariates), duration_col='duration', event_col='event')
        return cph

    def plot_survival_function(self, kmf, title="Curva de Supervivencia"):
        """
        Grafica la curva de supervivencia.

        Args:
            kmf (KaplanMeierFitter): Modelo Kaplan-Meier ajustado.
            title (str): Título del gráfico.
        """
        kmf.plot(figsize=(10, 6))
        plt.title(title)
        plt.xlabel("Tiempo")
        plt.ylabel("Probabilidad de Supervivencia")
        plt.grid(True)
        plt.show()

    def plot_partial_effects_on_outcome(self, cph, covariate, values, covariates=None, title="Efectos Parciales sobre el Outcome"):
        """
        Grafica los efectos parciales sobre el outcome.

        Args:
            cph (CoxPHFitter): Modelo Cox Proportional Hazards ajustado.
            covariate (str): Nombre de la covariable.
            values (list): Valores de la covariable para los cuales se desea graficar.
            covariates (pd.DataFrame): Otras covariables fijas. Si None, se usan los promedios.
            title (str): Título del gráfico.
        """
        if covariates is None:
            covariates = cph.summary.index.to_series().map(lambda x: cph.params_.loc[x] if x != covariate else values[0])
        cph.plot_partial_effects_on_outcome(covariate=covariate, values=values, covariates=covariates)
        plt.title(title)
        plt.xlabel("Tiempo")
        plt.ylabel("Log Hazard Ratio")
        plt.grid(True)
        plt.show()

    def analyze_survival(self, data, duration_col, event_col, covariates=None):
        """
        Analiza la supervivencia calculando la curva de supervivencia y ajustando modelos.

        Args:
            data (pd.DataFrame): Datos de entrada.
            duration_col (str): Nombre de la columna de duraciones.
            event_col (str): Nombre de la columna de eventos observados.
            covariates (list): Lista de nombres de columnas de covariables. Si None, no se ajusta el modelo Cox.

        Returns:
            dict: Diccionario con los resultados del análisis.
        """
        durations = data[duration_col]
        event_observed = data[event_col]

        # Ajustar el modelo Kaplan-Meier
        kmf = self.fit_kaplan_meier(durations, event_observed)

        # Graficar la curva de supervivencia
        self.plot_survival_function(kmf, title=f"Curva de Supervivencia de {duration_col}")

        results = {
            'kaplan_meier_model': kmf,
            'kaplan_meier_summary': kmf.summary
        }

        if covariates is not None:
            # Ajustar el modelo Cox Proportional Hazards
            cph = self.fit_cox_ph(durations, event_observed, data[covariates])

            # Graficar los efectos parciales sobre el outcome
            for covariate in covariates:
                self.plot_partial_effects_on_outcome(cph, covariate, values=[data[covariate].mean() - 1, data[covariate].mean(), data[covariate].mean() + 1], title=f"Efectos Parciales de {covariate}")

            # Calcular el índice de concordancia
            concordance_idx = concordance_index(durations, cph.predict_partial_hazard(data[covariates]), event_observed)
            results.update({
                'cox_ph_model': cph,
                'cox_ph_summary': cph.summary,
                'concordance_index': concordance_idx
            })

        return results

# Ejemplo de uso de la clase SurvivalAnalyzer
if __name__ == "__main__":
    # Cargar datos de nonces desde el archivo CSV
    data_path = '../data/nonce_training_data.csv'
    df = pd.read_csv(data_path)

    # Asumir que tenemos columnas 'duration' y 'event' en el DataFrame
    # Si no existen, debes crearlas según tu dataset
    # Por ejemplo, 'duration' podría ser el tiempo que el nonce fue válido y 'event' si el nonce fue utilizado o no
    # Aquí creamos columnas ficticias para el ejemplo
    df['duration'] = np.random.randint(1, 100, size=len(df))
    df['event'] = np.random.choice([0, 1], size=len(df))

    # Seleccionar covariables para el modelo Cox
    covariates = ['feature1', 'feature2']  # Cambiar según las columnas de tu dataset

    # Inicializar el analizador de supervivencia
    survival_analyzer = SurvivalAnalyzer()

    # Analizar la supervivencia
    results = survival_analyzer.analyze_survival(df, duration_col='duration', event_col='event', covariates=covariates)
    print(f"Análisis de Supervivencia: {results}")

import pandas as pd

def load_nonce_csv_dataset(path: str) -> pd.DataFrame:
    """
    Carga un dataset de nonces desde un archivo CSV plano.

    Args:
        path (str): Ruta al archivo CSV.

    Returns:
        pd.DataFrame: DataFrame con los datos cargados.
    """
    try:
        df = pd.read_csv(path)
        if 'nonce' not in df.columns:
            raise ValueError("El archivo CSV debe contener una columna 'nonce'")
        return df
    except Exception as e:
        raise RuntimeError(f"Error al cargar el dataset de nonces desde {path}: {e}")

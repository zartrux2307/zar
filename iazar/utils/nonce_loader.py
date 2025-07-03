import os
import pandas as pd
import json
import gzip
import bz2
import datetime
from typing import Union

class NonceLoader:
    def __init__(self, config: Union[dict, 'ConfigManager', str] = None):
        """
        Inicializa el cargador de nonces.
        Args:
            config (ConfigManager, dict o str): Instancia de configuración, diccionario, o ruta al archivo.
        """
        if config is None:
            # Valor por defecto si no se pasa nada
            config_path = 'config/config_manager.json'
            self.config = self.load_config(config_path)
        elif isinstance(config, str):
            self.config = self.load_config(config)
        elif hasattr(config, 'get_config'):
            # ConfigManager: usa el método para obtener la config de nonces o ruta de datos
            # Aquí puedes cambiar el nombre 'miner_config' según tu uso real
            self.config = config.get_config('miner_config')
        elif isinstance(config, dict):
            self.config = config
        else:
            raise ValueError("Config debe ser ruta, dict, o instancia de ConfigManager")

    def load_config(self, config_path):
        """Carga la configuración desde un archivo JSON."""
        with open(config_path, 'r') as file:
            config = json.load(file)
        return config

    def load_csv(self, file_path, compression=None, **kwargs):
        return pd.read_csv(file_path, compression=compression, **kwargs) if compression else pd.read_csv(file_path, **kwargs)

    def load_json(self, file_path, **kwargs):
        return pd.read_json(file_path, **kwargs)

    def load_jsonl(self, file_path, **kwargs):
        return pd.read_json(file_path, lines=True, **kwargs)

    def load_parquet(self, file_path, **kwargs):
        return pd.read_parquet(file_path, **kwargs)

    def load_log_files(self, log_dir, file_extension='*.csv', compression=None, **kwargs):
        import glob
        file_paths = glob.glob(os.path.join(log_dir, file_extension))
        dfs = []
        for file_path in file_paths:
            if file_path.endswith('.csv'):
                df = self.load_csv(file_path, compression=compression, **kwargs)
            elif file_path.endswith('.json'):
                df = self.load_json(file_path, **kwargs)
            elif file_path.endswith('.jsonl'):
                df = self.load_jsonl(file_path, **kwargs)
            elif file_path.endswith('.parquet'):
                df = self.load_parquet(file_path, **kwargs)
            else:
                raise ValueError(f"Archivo no soportado: {file_path}")
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True)

    def load_data(self, data_path, data_format='csv', compression=None, **kwargs):
        """
        Carga datos desde una ruta especificada.
        Args:
            data_path (str): Ruta al archivo o directorio de datos.
            data_format (str): Formato de los datos ('csv', 'json', 'jsonl', 'parquet').
            compression (str): Tipo de compresión ('gzip', 'bz2', None).
            **kwargs: Argumentos adicionales para el método de carga.
        Returns:
            pd.DataFrame: Datos cargados.
        """
        if os.path.isfile(data_path):
            if data_format == 'csv':
                return self.load_csv(data_path, compression=compression, **kwargs)
            elif data_format == 'json':
                return self.load_json(data_path, **kwargs)
            elif data_format == 'jsonl':
                return self.load_jsonl(data_path, **kwargs)
            elif data_format == 'parquet':
                return self.load_parquet(data_path, **kwargs)
            else:
                raise ValueError(f"Formato de datos no soportado: {data_format}")
        elif os.path.isdir(data_path):
            return self.load_log_files(data_path, file_extension=f'*.{data_format}', compression=compression, **kwargs)
        else:
            raise FileNotFoundError(f"No se encontró el archivo o directorio: {data_path}")

# === Funciones auxiliares globales ===

def load_nonce_data(filepath: str):
    """Carga nonces desde un archivo de texto plano"""
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def log_injection(nonce, status="INJECTED"):
    print(f"[{datetime.datetime.now()}] {status}: {nonce}")

def log_successful_nonce(nonce, confidence):
    print(f"[{datetime.datetime.now()}] SUCCESS: {nonce} (confidence: {confidence:.2f})")

if __name__ == "__main__":
    from iazar.utils.config_manager import ConfigManager
    config = ConfigManager()
    nonce_loader = NonceLoader(config)
    data_path = 'data/nonce_training_data.csv'
    df = nonce_loader.load_data(data_path, data_format='csv')
    print(df.head())

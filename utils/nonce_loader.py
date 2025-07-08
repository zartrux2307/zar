# iazar/utils/nonce_loader.py
"""
NonceLoader: Cargador flexible de nonces y datasets para IA Zartrux.
- Compatible con CSV, JSON, Parquet, logs de minería.
- Integrado con ConfigManager y rutas absolutas del sistema.
- Robusto para ejecución en Windows/Linux (uso real, no ejemplo).
"""

import os
import pandas as pd
import json
import datetime
from typing import Union
from iazar.utils.config_manager import ConfigManager

class NonceLoader:
    def __init__(self, config: Union[dict, ConfigManager, str] = None, base_dir: str = None):
        """
        Inicializa el cargador de nonces.
        Args:
            config: dict, ConfigManager o ruta a config. Si None, usa ia_config.
            base_dir: Ruta raíz del proyecto (para resolver archivos relativos).
        """
        self.base_dir = base_dir or os.getcwd()
        if isinstance(config, ConfigManager):
            self.config = config.get_config('ia_config')
        elif isinstance(config, dict):
            self.config = config
        elif isinstance(config, str):
            self.config = ConfigManager().get_config(config)
        else:
            self.config = ConfigManager().get_config('ia_config')
        self.data_dir = self.config.get('paths', {}).get('data_dir', 'C:/zarturxia/src/iazar/data')

    def _abs(self, path: str) -> str:
        """Convierte rutas relativas a absolutas respecto al proyecto."""
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.base_dir, path))

    def load_csv(self, file_path, **kwargs):
        return pd.read_csv(self._abs(file_path), **kwargs)

    def load_json(self, file_path, **kwargs):
        return pd.read_json(self._abs(file_path), **kwargs)

    def load_jsonl(self, file_path, **kwargs):
        return pd.read_json(self._abs(file_path), lines=True, **kwargs)

    def load_parquet(self, file_path, **kwargs):
        return pd.read_parquet(self._abs(file_path), **kwargs)

    def load_log_files(self, log_dir, file_extension='*.csv', **kwargs):
        import glob
        full_dir = self._abs(log_dir)
        file_paths = glob.glob(os.path.join(full_dir, file_extension))
        dfs = []
        for file_path in file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.csv':
                df = self.load_csv(file_path, **kwargs)
            elif ext == '.json':
                df = self.load_json(file_path, **kwargs)
            elif ext == '.jsonl':
                df = self.load_jsonl(file_path, **kwargs)
            elif ext == '.parquet':
                df = self.load_parquet(file_path, **kwargs)
            else:
                raise ValueError(f"Archivo no soportado: {file_path}")
            dfs.append(df)
        if not dfs:
            raise FileNotFoundError(f"No se encontraron archivos {file_extension} en {log_dir}")
        return pd.concat(dfs, ignore_index=True)

    def load_data(self, data_path, data_format='csv', **kwargs):
        """
        Carga datos desde una ruta especificada.
        Args:
            data_path: Ruta archivo/directorio (relativa o absoluta).
            data_format: csv, json, jsonl, parquet.
        Returns:
            pd.DataFrame
        """
        abs_path = self._abs(data_path)
        if os.path.isfile(abs_path):
            if data_format == 'csv':
                return self.load_csv(abs_path, **kwargs)
            elif data_format == 'json':
                return self.load_json(abs_path, **kwargs)
            elif data_format == 'jsonl':
                return self.load_jsonl(abs_path, **kwargs)
            elif data_format == 'parquet':
                return self.load_parquet(abs_path, **kwargs)
            else:
                raise ValueError(f"Formato no soportado: {data_format}")
        elif os.path.isdir(abs_path):
            return self.load_log_files(abs_path, file_extension=f'*.{data_format}', **kwargs)
        else:
            raise FileNotFoundError(f"No se encontró archivo/directorio: {abs_path}")

# === Funciones auxiliares ===

def load_nonce_data(filepath: str):
    """Carga nonces desde un archivo de texto plano."""
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def log_injection(nonce, status="INJECTED"):
    print(f"[{datetime.datetime.now()}] {status}: {nonce}")

def log_successful_nonce(nonce, confidence):
    print(f"[{datetime.datetime.now()}] SUCCESS: {nonce} (confidence: {confidence:.2f})")

if __name__ == "__main__":
    # Test real: carga desde la carpeta oficial de datos definida en config
    cm = ConfigManager()
    loader = NonceLoader(config=cm, base_dir=os.getcwd())
    try:
        path = os.path.join(loader.data_dir, "C:/zarturxia/src/iazar/data/nonce_training_data.csv")
        df = loader.load_data(path, data_format="csv")
        print(df.head())
    except Exception as ex:
        print("ERROR cargando datos:", ex)

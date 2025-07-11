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
import logging
from typing import Union
from iazar.utils.config_manager import ConfigManager
from iazar.utils.feature_utils import guardar_nonces_csv, COLUMNS


# Columnas estándar globales
COLUMNS = ["nonce", "entropy", "uniqueness", "zero_density", "pattern_score", "is_valid"]


def leer_nonces_csv(path):
    """Lee un CSV de nonces y garantiza estructura/cabecera estándar."""
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


def guardar_nonces_csv(df, path):
    """Guarda un DataFrame de nonces con la cabecera y orden estándar."""
    if not set(COLUMNS).issubset(df.columns):
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
    df = df[COLUMNS]
    df.to_csv(path, index=False)


def leer_nonces_json(path):
    """Lee un JSON de nonces como lista de dicts."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
        return []
    with open(path, 'r') as f:
        data = json.load(f)
    # Completa campos faltantes
    for item in data:
        for col in COLUMNS:
            if col not in item:
                item[col] = 0
    return data


def guardar_nonces_json(lista, path):
    """Guarda una lista de dicts como JSON de nonces."""
    with open(path, 'w') as f:
        json.dump(lista, f, indent=2)

# Utilidades para blobs binarios


def hexstr_to_bytes(blob_hex):
    return bytes.fromhex(blob_hex) if isinstance(blob_hex, str) else blob_hex


def bytes_to_hexstr(blob_bytes):
    return blob_bytes.hex() if isinstance(blob_bytes, (bytes, bytearray)) else blob_bytes

# Ejemplo de uso:
# df = leer_nonces_csv("ruta.csv")
# guardar_nonces_csv(df, "nueva_ruta.csv")
# nonces = leer_nonces_json("ruta.json")
# guardar_nonces_json(nonces, "nueva_ruta.json")


# Configurar logger
logger = logging.getLogger('NonceLoader')
logger.setLevel(logging.WARNING)  # Solo mostrar warnings y errores


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

        # Manejo robusto de rutas de datos
        self.data_dir = self.config.get('paths', {}).get('data_dir', 'C:/zarturxia/src/iazar/data')
        if not os.path.exists(self.data_dir):
            logger.warning(f"Directorio de datos no encontrado: {self.data_dir}")
            self.data_dir = os.path.join(self.base_dir, 'data')  # Fallback
            os.makedirs(self.data_dir, exist_ok=True)

    def _abs(self, path: str) -> str:
        """Convierte rutas relativas a absolutas respecto al proyecto."""
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.base_dir, path))

    def load_csv(self, file_path, **kwargs):
        abs_path = self._abs(file_path)
        if not os.path.exists(abs_path):
            logger.warning(f"Archivo CSV no encontrado: {abs_path}")
            return pd.DataFrame()  # Retornar dataframe vacío
        return pd.read_csv(abs_path, **kwargs)

    def load_json(self, file_path, **kwargs):
        abs_path = self._abs(file_path)
        if not os.path.exists(abs_path):
            logger.warning(f"Archivo JSON no encontrado: {abs_path}")
            return pd.DataFrame()  # Retornar dataframe vacío
        return pd.read_json(abs_path, **kwargs)

    def load_jsonl(self, file_path, **kwargs):
        abs_path = self._abs(file_path)
        if not os.path.exists(abs_path):
            logger.warning(f"Archivo JSONL no encontrado: {abs_path}")
            return pd.DataFrame()  # Retornar dataframe vacío
        return pd.read_json(abs_path, lines=True, **kwargs)

    def load_parquet(self, file_path, **kwargs):
        abs_path = self._abs(file_path)
        if not os.path.exists(abs_path):
            logger.warning(f"Archivo Parquet no encontrado: {abs_path}")
            return pd.DataFrame()  # Retornar dataframe vacío
        return pd.read_parquet(abs_path, **kwargs)

    def load_log_files(self, log_dir, file_extension='*.csv', **kwargs):
        import glob
        full_dir = self._abs(log_dir)
        if not os.path.exists(full_dir):
            logger.warning(f"Directorio de logs no encontrado: {full_dir}")
            return pd.DataFrame()  # Retornar dataframe vacío

        file_paths = glob.glob(os.path.join(full_dir, file_extension))
        if not file_paths:
            logger.warning(f"No se encontraron archivos {file_extension} en {log_dir}")
            return pd.DataFrame()  # Retornar dataframe vacío

        dfs = []
        for file_path in file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == '.csv':
                    df = self.load_csv(file_path, **kwargs)
                elif ext == '.json':
                    df = self.load_json(file_path, **kwargs)
                elif ext == '.jsonl':
                    df = self.load_jsonl(file_path, **kwargs)
                elif ext == '.parquet':
                    df = self.load_parquet(file_path, **kwargs)
                else:
                    logger.warning(f"Formato de archivo no soportado: {file_path}")
                    continue

                if not df.empty:
                    dfs.append(df)
            except Exception as e:
                logger.error(f"Error procesando archivo {file_path}: {str(e)}")

        if not dfs:
            return pd.DataFrame()  # Retornar dataframe vacío

        return pd.concat(dfs, ignore_index=True)

    def load_data(self, data_path, data_format='csv', **kwargs):
        """
        Carga datos desde una ruta especificada.
        Args:
            data_path: Ruta archivo/directorio (relativa o absoluta).
            data_format: csv, json, jsonl, parquet.
        Returns:
            pd.DataFrame (vacío si no se encuentra)
        """
        abs_path = self._abs(data_path)
        if not os.path.exists(abs_path):
            logger.warning(f"Archivo/directorio no encontrado: {abs_path}")
            return pd.DataFrame()  # Retornar dataframe vacío

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
                logger.error(f"Formato no soportado: {data_format}")
                return pd.DataFrame()
        elif os.path.isdir(abs_path):
            return self.load_log_files(abs_path, file_extension=f'*.{data_format}', **kwargs)
        else:
            logger.error(f"Ruta inválida: {abs_path}")
            return pd.DataFrame()

# === Funciones auxiliares ===


def load_nonce_data(filepath: str):
    """Carga nonces desde un archivo de texto plano."""
    if not os.path.exists(filepath):
        logger.warning(f"Archivo de nonces no encontrado: {filepath}")
        return []

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
        path = os.path.join(loader.data_dir, "nonce_training_data.csv")
        df = loader.load_data(path, data_format="csv")
        print("Datos cargados:")
        print(df.head() if not df.empty else "DataFrame vacío")
    except Exception as ex:
        print("ERROR cargando datos:", ex)

# iazar/utils/nonce_loader.py
"""
NonceLoader: Cargador flexible de nonces y datasets para IA Zartrux.
- Compatible con CSV, JSON, Parquet, logs de minería
- Sistema de rutas relativas jerárquico
- Generación automática de timestamp si falta
- Manejo de configuraciones flexible
- Carga robusta de datos de hash
"""

import os
import pandas as pd
import json
import datetime
import time
from typing import Union, List, Dict, Any
from iazar.utils.config_manager import ConfigManager

class NonceLoader:
    def __init__(self, config: Union[dict, ConfigManager, str] = None, base_dir: str = None):
        """
        Inicializa el cargador de nonces con sistema jerárquico de rutas.
        Args:
            config: dict, ConfigManager o ruta a config. Si None, usa ia_config.
            base_dir: Ruta raíz del proyecto (para resolver rutas relativas).
        """
        self.base_dir = base_dir or os.getcwd()
        self._init_config(config)
        self._init_paths()
        
    def _init_config(self, config: Union[dict, ConfigManager, str]):
        """Manejo flexible de diferentes tipos de configuración"""
        if isinstance(config, ConfigManager):
            self.config = config.get_config('ia_config')
        elif isinstance(config, dict):
            self.config = config
        elif isinstance(config, str):
            self.config = ConfigManager().get_config(config)
        else:
            self.config = ConfigManager().get_config('ia_config')
            
        # Configuración por defecto si falta
        self.config.setdefault('paths', {})
        self.config['paths'].setdefault('data_dir', 'data')
        self.config['paths'].setdefault('hash_dir', 'hash_data')
        self.config['paths'].setdefault('log_dir', 'logs')

    def _init_paths(self):
        """Inicializa rutas jerárquicas con creación automática de directorios"""
        # Rutas principales
        self.data_dir = self._abs(self.config['paths']['data_dir'])
        self.hash_dir = self._abs(self.config['paths']['hash_dir'])
        self.log_dir = self._abs(self.config['paths']['log_dir'])
        
        # Crear directorios si no existen
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.hash_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Subdirectorios específicos
        self.training_dir = self._abs(os.path.join(self.data_dir, 'training'))
        self.results_dir = self._abs(os.path.join(self.data_dir, 'results'))
        os.makedirs(self.training_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

    def _abs(self, path: str) -> str:
        """Convierte rutas relativas a absolutas respecto al proyecto."""
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(self.base_dir, path))

    def _ensure_timestamp(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Añade timestamp si falta en los datos"""
        if 'timestamp' not in data:
            data['timestamp'] = time.time()
        return data

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
        os.makedirs(full_dir, exist_ok=True)  # Crear si no existe
        
        file_paths = glob.glob(os.path.join(full_dir, file_extension))
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
                    continue  # Saltar archivos no soportados
                
                # Asegurar timestamp si falta
                if 'timestamp' not in df.columns:
                    df['timestamp'] = time.time()
                dfs.append(df)
                
            except Exception as e:
                print(f"Error cargando {file_path}: {str(e)}")
                continue
        
        if not dfs:
            raise FileNotFoundError(f"No se encontraron archivos {file_extension} en {log_dir}")
        return pd.concat(dfs, ignore_index=True)

    def load_data(self, data_path, data_format='csv', **kwargs):
        """
        Carga datos desde una ruta especificada.
        Args:
            data_path: Ruta archivo/directorio (relativa o absoluta)
            data_format: csv, json, jsonl, parquet
        Returns:
            pd.DataFrame con timestamp garantizado
        """
        abs_path = self._abs(data_path)
        if os.path.isfile(abs_path):
            if data_format == 'csv':
                df = self.load_csv(abs_path, **kwargs)
            elif data_format == 'json':
                df = self.load_json(abs_path, **kwargs)
            elif data_format == 'jsonl':
                df = self.load_jsonl(abs_path, **kwargs)
            elif data_format == 'parquet':
                df = self.load_parquet(abs_path, **kwargs)
            else:
                raise ValueError(f"Formato no soportado: {data_format}")
        elif os.path.isdir(abs_path):
            df = self.load_log_files(abs_path, file_extension=f'*.{data_format}', **kwargs)
        else:
            raise FileNotFoundError(f"No se encontró archivo/directorio: {abs_path}")
        
        # Asegurar timestamp
        if 'timestamp' not in df.columns:
            df['timestamp'] = time.time()
            
        return df

    def load_hash_data(self, file_path: str) -> List[str]:
        """
        Carga robusta de datos de hash desde archivo de texto.
        Maneja diferentes formatos y añade timestamp si es necesario.
        """
        abs_path = self._abs(file_path)
        hashes = []
        try:
            with open(abs_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        # Manejar diferentes formatos de hash
                        if len(line) == 64:  # SHA-256
                            hashes.append(line)
                        elif ':' in line:  # Formato hash:valor
                            parts = line.split(':', 1)
                            hashes.append(parts[0].strip())
                        else:  # Hash simple
                            hashes.append(line)
        except Exception as e:
            print(f"Error cargando hashes desde {abs_path}: {str(e)}")
            raise
        
        return hashes

# === Funciones auxiliares mejoradas ===

def load_nonce_data(filepath: str) -> List[str]:
    """Carga nonces desde archivo con manejo de errores robusto"""
    nonces = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    nonces.append(line)
    except Exception as e:
        print(f"Error cargando nonces: {str(e)}")
    return nonces

def log_injection(nonce: str, status: str = "INJECTED", log_dir: str = None):
    """Registra inyección con timestamp automático"""
    timestamp = datetime.datetime.now()
    msg = f"[{timestamp}] {status}: {nonce}"
    print(msg)
    
    # Guardar en log si se especifica directorio
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"injection_{timestamp.date()}.log")
        with open(log_file, 'a') as f:
            f.write(msg + '\n')

def log_successful_nonce(nonce: str, confidence: float, log_dir: str = None):
    """Registra nonce exitoso con timestamp automático"""
    timestamp = datetime.datetime.now()
    msg = f"[{timestamp}] SUCCESS: {nonce} (confidence: {confidence:.2f})"
    print(msg)
    
    # Guardar en log si se especifica directorio
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"success_{timestamp.date()}.log")
        with open(log_file, 'a') as f:
            f.write(msg + '\n')

if __name__ == "__main__":
    # Test completo del sistema
    cm = ConfigManager()
    loader = NonceLoader(config=cm, base_dir=os.getcwd())
    
    print("\n=== Directorios configurados ===")
    print(f"Base:     {loader.base_dir}")
    print(f"Datos:    {loader.data_dir}")
    print(f"Hash:     {loader.hash_dir}")
    print(f"Logs:     {loader.log_dir}")
    print(f"Training: {loader.training_dir}")
    print(f"Results:  {loader.results_dir}")
    
    print("\n=== Probando carga de datos ===")
    try:
        # Usando ruta relativa dentro del directorio de datos
        test_file = os.path.join("training", "nonce_training_data.csv")
        df = loader.load_data(
            os.path.join(loader.data_dir, test_file),
            data_format="csv"
        )
        print(f"Datos cargados correctamente. Filas: {len(df)}")
        print("Columnas:", df.columns.tolist())
        print("Primeras filas:")
        print(df.head(2))
    except Exception as ex:
        print("ERROR cargando datos de entrenamiento:", ex)
    
    print("\n=== Probando carga de hashes ===")
    try:
        hash_file = os.path.join(loader.hash_dir, "block_hashes.txt")
        # Crear archivo de prueba si no existe
        if not os.path.exists(hash_file):
            with open(hash_file, 'w') as f:
                f.write("0000000000000000000aef3b4d7b3683e1e7c42d8b5f8f1d7d6b5c5a\n")
                f.write("0000000000000000000d2b1e9f5b8d1e6f3c4a5b7e8d9f0a1b2c3d4\n")
                f.write("sha256:5a86b1c4d7e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3\n")
        
        hashes = loader.load_hash_data(hash_file)
        print(f"Se cargaron {len(hashes)} hashes:")
        for h in hashes[:3]:
            print(f"- {h[:12]}...{h[-12:]}")
    except Exception as ex:
        print("ERROR cargando hashes:", ex)
    
    print("\n=== Probando funciones de log ===")
    log_injection("nonce_12345", log_dir=loader.log_dir)
    log_successful_nonce("nonce_abcde", 0.92, log_dir=loader.log_dir)
    print("Logs guardados en:", loader.log_dir)
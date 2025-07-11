import os
import pandas as pd
import numpy as np
import sklearn
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from typing import Optional, Dict, Any

from iazar.utils.config_manager import get_ia_config
from iazar.utils.nonce_loader import NonceLoader

from packaging import version

if version.parse(sklearn.__version__) >= version.parse("1.2"):
    categorical_transformer = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
else:
    categorical_transformer = OneHotEncoder(handle_unknown='ignore', sparse=False)


class NonceDataPreprocessor:
    """
    Preprocesador de datos de nonces para el sistema Zartrux IA Mining.
    Soporta: carga, limpieza, cálculo de features, encoding y pipeline de sklearn.
    """

    def __init__(self):
        self.config = get_ia_config()
        self.data_paths = self.config.get('data_paths', {})
        self.processing_params = self.config.get('processing_params', {})
        self.feature_pipeline = None
        self.data = None
        self.metadata = {}
        self.loader = NonceLoader()  # Usamos el cargador de nonces

    def _load_and_merge_data(self) -> pd.DataFrame:
        """Carga y fusiona los datos de nonces desde rutas configuradas"""
        dfs = []
        # Lista priorizada de archivos con rutas relativas
        files_to_try = [
            ('successful_nonces', 'nonces_exitosos.csv'),
            ('training_data', 'nonce_training_data.csv'),
            ('preprocessed', 'nonce_preprocessed.csv')
        ]

        for key, default_filename in files_to_try:
            # Primero intenta con la ruta configurada
            config_path = self.data_paths.get(key)
            if config_path:
                try:
                    df = self.loader.load_data(config_path, data_format='csv')
                    dfs.append(df)
                    print(f"[Zartrux][data_preprocessing] Cargado {key} desde: {config_path}")
                    continue  # Si se carga, pasamos al siguiente
                except Exception as e:
                    print(f"[Zartrux][data_preprocessing] Error cargando {key} ({config_path}): {e}")

            # Fallback: intenta en el directorio de datos por defecto
            try:
                fallback_path = os.path.join(self.loader.data_dir, default_filename)
                df = self.loader.load_data(fallback_path, data_format='csv')
                dfs.append(df)
                print(f"[Zartrux][data_preprocessing] Cargado {key} desde fallback: {fallback_path}")
            except Exception as e:
                print(f"[Zartrux][data_preprocessing] Error cargando fallback para {key} ({fallback_path}): {e}")

        if dfs:
            df_nonces = pd.concat(dfs, ignore_index=True)
        else:
            print("[Zartrux][data_preprocessing]No se encontró ningún archivo de nonces, devolviendo DataFrame vacío.")
            df_nonces = pd.DataFrame()
        return df_nonces

    def _calculate_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula características adicionales (ejemplo simple)"""
        if df.empty:
            return df
        if 'nonce' in df.columns:
            df['zero_density'] = df['nonce'].astype(str).apply(lambda x: x.count('0') / len(x) if len(x) > 0 else 0)
        return df

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpieza básica de datos"""
        return df.dropna()

    def _encode_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Codifica variables categóricas:
        - Convierte columnas 'object' que sean verdaderamente categóricas en categoría.
        - Deja el resto intacto para el pipeline.
        """
        cat_cols = df.select_dtypes(include=['object']).columns
        for col in cat_cols:
            unique_ratio = df[col].nunique() / len(df) if len(df) > 0 else 0
            # Sólo convierte en 'category' si tiene pocos valores únicos
            if unique_ratio < 0.2 or df[col].nunique() < 30:
                df[col] = df[col].astype('category')
        return df

    def _generate_metadata(self, df: pd.DataFrame):
        """Genera y almacena metadatos útiles del preprocesamiento"""
        self.metadata['num_rows'] = len(df)
        self.metadata['columns'] = list(df.columns)

    def build_feature_pipeline(self, df: pd.DataFrame) -> Pipeline:
        """Construye y guarda el pipeline de sklearn para features"""
        numeric_features = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = df.select_dtypes(include=['object', 'category']).columns.tolist()
        numeric_transformer = StandardScaler()
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, numeric_features),
                ('cat', categorical_transformer, categorical_features)
            ],
            remainder='passthrough'
        )
        pipeline = Pipeline(steps=[('preprocessor', preprocessor)])
        self.feature_pipeline = pipeline
        return pipeline

    def preprocess(self, data: Optional[pd.DataFrame] = None) -> np.ndarray:
        """Ejecuta el pipeline completo de preprocesamiento
        Si data=None, carga automáticamente según rutas config.
        """
        print("Cargando y fusionando datos...")
        raw_data = data if data is not None else self._load_and_merge_data()

        print("Calculando características derivadas...")
        processed_data = self._calculate_derived_features(raw_data)

        print("Limpiando datos...")
        cleaned_data = self._clean_data(processed_data)

        print("Codificando variables...")
        encoded_data = self._encode_categoricals(cleaned_data)

        print("Construyendo pipeline de features...")
        if self.feature_pipeline is None:
            self.build_feature_pipeline(encoded_data)

        print("Aplicando transformaciones...")
        final_data = self.feature_pipeline.fit_transform(encoded_data)

        print("Generando metadatos...")
        self._generate_metadata(encoded_data)

        # Liberar memoria
        import gc
        del raw_data, processed_data, cleaned_data, encoded_data
        gc.collect()

        self.data = final_data
        return self.data

    def get_metadata(self) -> Dict[str, Any]:
        return self.metadata

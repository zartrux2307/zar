# iazar/training/train_model_randomforest.py
import joblib
import logging
import pandas as pd
import numpy as np
import os
import sys

import json
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
from iazar.utils.config_manager import get_ia_config
from iazar.utils.data_preprocessing import NonceDataPreprocessor
from iazar.utils.feature_utils import COLUMNS


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
        logging.StreamHandler(),
        logging.FileHandler("train_model_randomforest.log")
    ]
)
logger = logging.getLogger("ModelTraining")

def load_real_winner_data(data_path: Path) -> pd.DataFrame:
    """Carga datos reales de bloques ganadores con validación estricta"""
    logger.info(f"Cargando datos reales de bloques ganadores: {data_path}")
    
    if not data_path.exists():
        raise FileNotFoundError(f"Archivo de datos no encontrado: {data_path}")
    
    try:
        # Cargar datos
        df = pd.read_csv(data_path)
        
        # Validación crítica de datos
        required_cols = set(COLUMNS + ['nonce'])
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            raise ValueError(f"Columnas requeridas faltantes: {missing_cols}")
        
        # Verificar que hay suficientes datos
        if len(df) < 1000:
            raise ValueError(f"Datos insuficientes: solo {len(df)} registros")
        
        # Verificar distribución de nonces
        nonce_stats = df['nonce'].describe()
        logger.info(f"Estadísticas de nonces: {nonce_stats.to_dict()}")
        
        # Verificar que no sean todos cero o constantes
        if nonce_stats['std'] < 1:
            raise ValueError("Nonces constantes o casi constantes")
            
        return df
        
    except Exception as e:
        logger.exception("Error cargando datos reales")
        raise

def train_real_model(X, y, config: dict):
    """Entrena modelo con datos reales y validación rigurosa"""
    logger.info("Entrenando modelo con datos reales...")
    
    try:
        # Dividir datos (80/20)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=42
        )

        # Configurar modelo
        model_params = {
            "n_estimators": config.get("n_estimators", 200),
            "max_depth": config.get("max_depth", 20),
            "min_samples_split": config.get("min_samples_split", 5),
            "min_samples_leaf": config.get("min_samples_leaf", 2),
            "max_features": config.get("max_features", 0.8),
            "bootstrap": True,
            "n_jobs": -1,
            "random_state": 42,
            "verbose": 1
        }

        model = RandomForestRegressor(**model_params)
        model.fit(X_train, y_train)
        logger.info("Entrenamiento completado")

        # Validación de rendimiento
        train_preds = model.predict(X_train)
        test_preds = model.predict(X_test)

        train_mse = mean_squared_error(y_train, train_preds)
        test_mse = mean_squared_error(y_test, test_preds)
        r2 = r2_score(y_test, test_preds)

        logger.info(f"MSE - Entrenamiento: {train_mse:.4f}, Prueba: {test_mse:.4f}")
        logger.info(f"R² Score: {r2:.4f}")

        # Validación de importancia de características
        importances = model.feature_importances_
        if np.max(importances) < 0.1:
            logger.warning("Importancia máxima de características muy baja")
            
        # Validación de árboles
        if len(model.estimators_) < model_params["n_estimators"]:
            raise RuntimeError(f"Faltan estimadores: {len(model.estimators_)}/{model_params['n_estimators']}")

        return model
        
    except Exception as e:
        logger.exception("Error entrenando modelo real")
        raise

def main():
    try:
        logger.info("=== ENTRENAMIENTO DE MODELO REAL CON DATOS DE BLOQUES GANADORES ===")

        # 1. Obtener configuración
        config = get_ia_config()
        model_config = config.get("model", {})
        data_config = config.get("data_paths", {})

        # 2. Preparar rutas
        model_output_path = Path(model_config.get("path", "src/iazar/models/rf_nonce_model.joblib"))
        real_data_path = Path(data_config.get("winner_blocks", "src/iazar/data/winner_blocks.csv"))

        model_output_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Cargar datos reales
        df = load_real_winner_data(real_data_path)
        
        # 4. Preprocesar datos
        preprocessor = NonceDataPreprocessor()
        X = preprocessor.preprocess(df)
        y = df['nonce'].values

        # 5. Entrenar modelo con validación
        model = train_real_model(X, y, model_config)

        # 6. Guardar modelo
        joblib.dump(model, model_output_path)
        logger.info(f"Modelo guardado en {model_output_path}")

        # 7. Guardar metadatos de validación
        metadata = {
            "training_date": pd.Timestamp.now().isoformat(),
            "data_source": str(real_data_path),
            "data_samples": len(df),
            "features": list(X.columns),
            "feature_importances": dict(zip(X.columns, model.feature_importances_)),
            "performance": {
                "r2_score": r2_score(y, model.predict(X)),
                "mse": mean_squared_error(y, model.predict(X))
            }
        }

        metadata_path = model_output_path.with_suffix(".metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Metadatos guardados en {metadata_path}")
        logger.info("✅ Entrenamiento completado con éxito!")

    except Exception:
        logger.exception("❌ Error crítico en el entrenamiento")
        sys.exit(1)

if __name__ == "__main__":
    main()
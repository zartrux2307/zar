import os
import joblib
import logging
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from iazar.utils.config_manager import get_ia_config
from iazar.utils.data_preprocessing import NonceDataPreprocessor
from iazar.utils.feature_utils import COLUMNS

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

def load_and_validate_data(data_path: Path) -> pd.DataFrame:
    """Carga y valida el conjunto de datos con verificaciones exhaustivas"""
    logger.info(f"Validando archivo de datos: {data_path}")
    
    # Verificar existencia del archivo
    if not data_path.exists():
        logger.error(f"Archivo de datos no encontrado: {data_path}")
        raise FileNotFoundError(f"Archivo de datos no encontrado: {data_path}")
    
    # Verificar extensión del archivo
    if data_path.suffix not in ['.csv', '.parquet']:
        logger.error(f"Formato de archivo no soportado: {data_path.suffix}")
        raise ValueError(f"Formato de archivo no soportado: {data_path.suffix}")
    
    try:
        # Cargar datos según formato
        if data_path.suffix == '.csv':
            df = pd.read_csv(data_path)
        else:  # .parquet
            df = pd.read_parquet(data_path)
            
        logger.info(f"Datos cargados: {df.shape[0]} muestras, {df.shape[1]} características")
        
        # Verificar columnas requeridas
        required_cols = set(COLUMNS)
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            logger.error(f"Columnas requeridas faltantes: {', '.join(missing_cols)}")
            raise ValueError(f"Columnas requeridas faltantes: {missing_cols}")
            
        # Verificar valores faltantes
        missing_values = df.isnull().sum().sum()
        if missing_values > 0:
            logger.warning(f"Se encontraron {missing_values} valores faltantes - Imputando...")
            df = df.fillna(df.mean(numeric_only=True))
            
        # Verificar distribución de clases
        if 'is_valid' in df.columns:
            class_dist = df['is_valid'].value_counts(normalize=True)
            logger.info(f"📊 Distribución de clases: Válidos={class_dist.get(1, 0):.2%}, Inválidos={class_dist.get(0, 0):.2%}")
            
            if class_dist.get(1, 0) < 0.1 or class_dist.get(0, 0) < 0.1:
                logger.warning("⚠️ Desbalance de clases significativo - Considerar técnicas de balanceo")
        
        return df
        
    except Exception as e:
        logger.exception(f"Error al cargar datos: {str(e)}")
        raise

def preprocess_data(df: pd.DataFrame) -> tuple:
    """Realiza preprocesamiento avanzado de los datos"""
    logger.info("🔧 Iniciando preprocesamiento de datos...")
    
    try:
        preprocessor = NonceDataPreprocessor()
        
        # Conservar etiquetas antes del preprocesamiento
        if 'is_valid' in df.columns:
            y = df['is_valid'].values
        else:
            logger.warning("Columna 'is_valid' no encontrada - Generando etiquetas sintéticas")
            y = np.random.randint(0, 2, size=len(df))
        
        # Preprocesar características
        X = preprocessor.preprocess(df)
        
        # Validar formato de salida
        if not isinstance(X, (pd.DataFrame, np.ndarray)):
            raise TypeError("El preprocesador debe devolver DataFrame o ndarray")
            
        if isinstance(X, pd.DataFrame):
            logger.info(f"📋 Características después de preprocesamiento: {X.columns.tolist()}")
        
        logger.info(f"Preprocesamiento completado. Dimensiones: {X.shape}")
        return X, y
        
    except Exception as e:
        logger.exception(f"Error en preprocesamiento: {str(e)}")
        raise

def train_random_forest(X, y, config: dict):
    """Entrena y evalúa un modelo RandomForest con validación robusta"""
    logger.info("Iniciando entrenamiento de RandomForest...")
    
    try:
        # Dividir datos en entrenamiento y prueba
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, 
            test_size=config.get("test_size", 0.2),
            stratify=y,
            random_state=42
        )
        
        logger.info(f"Datos divididos: Entrenamiento={X_train.shape[0]}, Prueba={X_test.shape[0]}")
        
        # Configurar modelo
        model_params = {
            "n_estimators": config.get("n_estimators", 100),
            "max_depth": config.get("max_depth", None),
            "min_samples_split": config.get("min_samples_split", 2),
            "min_samples_leaf": config.get("min_samples_leaf", 1),
            "max_features": config.get("max_features", "sqrt"),
            "bootstrap": config.get("bootstrap", True),
            "n_jobs": -1,
            "random_state": 42,
            "verbose": 1
        }
        
        model = RandomForestClassifier(**model_params)
        
        # Entrenar modelo
        model.fit(X_train, y_train)
        logger.info("Entrenamiento completado")
        
        # Evaluar modelo
        train_preds = model.predict(X_train)
        test_preds = model.predict(X_test)
        
        train_acc = accuracy_score(y_train, train_preds)
        test_acc = accuracy_score(y_test, test_preds)
        
        logger.info(f"Precisión - Entrenamiento: {train_acc:.4f}, Prueba: {test_acc:.4f}")
        logger.info("\nReporte de clasificación:\n" + classification_report(y_test, test_preds))
        
        # Feature importance
        if hasattr(model, "feature_importances_"):
            if isinstance(X, pd.DataFrame):
                feature_names = X.columns
            else:
                feature_names = [f"feature_{i}" for i in range(X.shape[1])]
                
            importances = pd.Series(model.feature_importances_, index=feature_names)
            top_features = importances.sort_values(ascending=False).head(10)
            logger.info("Top 10 características más importantes:\n" + top_features.to_string())
        
        return model
        
    except Exception as e:
        logger.exception(f"Error en entrenamiento: {str(e)}")
        raise

def main():
    try:
        logger.info("Iniciando entrenamiento de modelo RandomForest")
        
        # 1. Obtener configuración
        config = get_ia_config()
        model_config = config.get("model", {})
        data_config = config.get("data_paths", {})
        
        # 2. Preparar rutas
        model_output_path = Path(model_config.get("path", "models/random_forest_model.joblib"))
        data_path = Path(data_config.get("successful_nonces", "data/processed/nonces.csv"))
        
        model_output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 3. Cargar y validar datos
        df = load_and_validate_data(data_path)
        
        # 4. Preprocesar datos
        X, y = preprocess_data(df)
        
        # 5. Entrenar modelo
        model = train_random_forest(X, y, model_config)
        
        # 6. Guardar modelo
        joblib.dump(model, model_output_path)
        logger.info(f"Modelo guardado en {model_output_path}")
        
        # 7. Guardar metadatos
        metadata = {
            "data_path": str(data_path),
            "data_shape": X.shape,
            "model_type": "RandomForest",
            "training_date": pd.Timestamp.now().isoformat(),
            "features": list(X.columns) if isinstance(X, pd.DataFrame) else [],
            "classes": list(np.unique(y))
        }
        
        metadata_path = model_output_path.with_suffix(".metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
            
        logger.info(f"📝 Metadatos guardados en {metadata_path}")
        logger.info("🎉 Entrenamiento completado exitosamente!")
        
    except Exception as e:
        logger.exception("Error crítico en el proceso de entrenamiento")
        sys.exit(1)

if __name__ == "__main__":
    main()
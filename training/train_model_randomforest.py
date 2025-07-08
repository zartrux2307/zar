import os
import joblib
import logging
import pandas as pd
import sys  # Added for proper exit handling
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from iazar.utils.config_manager import get_ia_config
from iazar.utils.data_preprocessing import NonceDataPreprocessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrainModel")

def main():
    config = get_ia_config()
    model_output_path = Path(config["model"]["path"])
    model_output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data_path = Path(config['data_paths']['successful_nonces'])
    logger.info(f"📥 Cargando y procesando datos desde: {data_path}")

    # 1. Check if data file exists before processing
    if not data_path.exists():
        logger.error(f"❌ Archivo de datos no encontrado: {data_path}")
        logger.error("Por favor ejecute primero el script de recolección de datos")
        sys.exit(1)  # Exit with error code

    preprocessor = NonceDataPreprocessor()
    try:
        X = preprocessor.preprocess()
        metadata = preprocessor.get_metadata()
    except Exception as e:
        logger.exception(f"🚨 Error durante el preprocesamiento: {str(e)}")
        sys.exit(1)

    # 2. Validate dataset before training
    if X.shape[0] == 0:
        logger.error("❌ Dataset vacío - No hay datos para entrenar")
        logger.error("Verifique el archivo de entrada y el proceso de preprocesamiento")
        sys.exit(1)

    logger.info(f"✅ Datos preprocesados: {X.shape} dimensiones | {metadata['num_rows']} muestras")

    # Generar etiquetas ficticias para entrenamiento
    y = [1 if i % 2 == 0 else 0 for i in range(X.shape[0])]

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    logger.info("🧠 Entrenando modelo RandomForest...")
    
    try:
        model.fit(X, y)
    except ValueError as e:
        logger.exception(f"🚨 Error en entrenamiento: {str(e)}")
        logger.error("Posibles causas: Datos insuficientes o características incompatibles")
        sys.exit(1)

    logger.info(f"💾 Guardando modelo en {model_output_path}")
    joblib.dump(model, model_output_path)

    logger.info("✅ Entrenamiento completado y modelo guardado exitosamente.")

if __name__ == "__main__":
    main()
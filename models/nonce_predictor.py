import sys
import os
import logging
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from iazar.utils.config_manager import get_config
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)
# Configurar ruta del paquete
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PACKAGE_ROOT)

# Configurar logger
logger = logging.getLogger("NoncePredictor")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

class NoncePredictor:
    def __init__(self, model_path=None):
        if model_path:
            self.model_path = model_path
        else:
            config = get_config("ia_config") 
            self.model_path = config.get("model", {}).get("path", "default_model.pkl")
        
        self.model = None
        
        # Verificar si el modelo existe y es válido
        if not self._is_model_valid():
            logger.warning("Modelo inválido o no entrenado. Entrenando nuevo modelo...")
            self.train_dummy_model()
            if not self._is_model_valid():
                raise RuntimeError("Fallo al crear modelo válido")
        
        self.load_model(self.model_path)
        logger.info(f"Modelo cargado: {type(self.model).__name__}")

    def _is_model_valid(self) -> bool:
        """Verifica si el modelo es válido"""
        try:
            if not os.path.isfile(self.model_path):
                logger.error(f"Modelo no encontrado: {self.model_path}")
                return False
                
            file_size = os.path.getsize(self.model_path)
            if file_size < 1024:
                logger.warning(f"Modelo sospechosamente pequeño: {file_size} bytes")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validando modelo: {str(e)}")
            return False

    def train_dummy_model(self):
        """Entrena un modelo dummy con datos de ejemplo"""
        try:
            logger.info("Entrenando modelo dummy...")
            self.model = RandomForestRegressor(n_estimators=10, random_state=42)
            
            # Datos de ejemplo
            X = np.random.rand(100, 5)
            y = np.random.rand(100)
            
            self.model.fit(X, y)
            self.save_model(self.model_path)
            logger.info(f"Modelo dummy guardado en: {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error entrenando modelo dummy: {str(e)}")
            raise

    def train(self, X, y):
        """Entrena el modelo con datos reales"""
        try:
            logger.info("Entrenando modelo con datos reales...")
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.model.fit(X, y)
            self.save_model(self.model_path)
            logger.info(f"Modelo entrenado guardado en: {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error entrenando modelo: {str(e)}")
            raise

    def predict(self, X):
        """Realiza predicciones con el modelo"""
        if self.model is None:
            raise RuntimeError("Modelo no cargado")
            
        X = np.array(X)
        return self.model.predict(X)
    
    def save_model(self, path):
        """Guarda el modelo en disco"""
        joblib.dump(self.model, path)
        logger.info(f"Modelo guardado en: {path}")
    
    def load_model(self, path):
        """Carga el modelo desde disco"""
        self.model = joblib.load(path)
        logger.info(f"Modelo cargado desde: {path}")

if __name__ == "__main__":
    predictor = NoncePredictor()
    X_test = np.random.rand(5, 5)
    predictions = predictor.predict(X_test)
    print("Predicciones:", predictions)
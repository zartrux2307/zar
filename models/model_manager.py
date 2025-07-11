# iazar/models/model_manager.py
import joblib
from pathlib import Path

MODEL_DIR = Path("src/iazar/models")

class ModelManager:
    @staticmethod
    def get_model(model_name="rf_nonce_model"):
        """Carga el modelo principal o alternativos bajo demanda"""
        model_path = MODEL_DIR / f"{model_name}.joblib"
        
        if not model_path.exists():
            raise FileNotFoundError(f"Modelo {model_name} no encontrado")
            
        return joblib.load(model_path)

    @staticmethod
    def list_available_models():
        """Lista todos los modelos disponibles"""
        return [f.stem for f in MODEL_DIR.glob("*.joblib")]
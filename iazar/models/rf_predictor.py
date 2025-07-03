# iazar/models/rf_predictor.py
import os
import joblib
import numpy as np
from iazar.utils.config_manager import get_config

class RandomForestPredictor:
    def __init__(self):
        config = get_config()
        self.model_path = config["model"]["path"]
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Modelo RandomForest no encontrado en: {self.model_path}")
        self.model = joblib.load(self.model_path)

    def predict(self, X):
        X = np.array(X)
        return self.model.predict(X)

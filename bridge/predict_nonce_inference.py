import os
import joblib
import numpy as np
from pathlib import Path
from iazar.utils.feature_engineer import extract_features
from iazar.utils.config_manager import get_ia_config


class Config:
    MODEL_PATH = Path("iazar/models/rf_nonce_model.joblib")


class PredictNonceInference:
    def __init__(self):
        self.config = get_ia_config()
        self.model = self._load_model()

    def _load_model(self):
        if not Config.MODEL_PATH.exists():
            raise FileNotFoundError(f"Modelo no encontrado en: {Config.MODEL_PATH}")
        return joblib.load(Config.MODEL_PATH)

    def predict_batch(self, nonces: list[dict]) -> list[dict]:
        features = [extract_features(n["blob"], n["nonce"]) for n in nonces]
        X = np.array(features)
        raw_scores = self.model.predict(X)
        probabilities = np.clip(raw_scores, 0.0, 1.0)

        for i, nonce in enumerate(nonces):
            nonce["score"] = float(probabilities[i])

        return sorted(nonces, key=lambda x: x["score"], reverse=True)

    def predict_one(self, blob: str, nonce: str) -> float:
        features = extract_features(blob, nonce)
        X = np.array(features).reshape(1, -1)
        score = self.model.predict(X)[0]
        return float(np.clip(score, 0.0, 1.0))

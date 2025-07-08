import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler, StandardScaler

class featureEngineer:
    def __init__(self, df):
        self.df = df.copy()

    def add_entropy(self, column='nonce'):
        def entropy(s):
            probs = pd.Series(list(s)).value_counts(normalize=True)
            return -(probs * np.log2(probs)).sum()
        self.df[f'{column}_entropy'] = self.df[column].astype(str).apply(entropy)
        return self

    def scale_features(self, columns, method='standard'):
        scaler = StandardScaler() if method == 'standard' else MinMaxScaler()
        self.df[columns] = scaler.fit_transform(self.df[columns])
        return self

    def get_df(self):
        return self.df

# ✅ FUNCIÓN GLOBAL requerida por IA
def extract_features(blob: str, nonce: str) -> list[float]:
    """
    Extrae features simples: longitud, entropía, conteo de dígitos, letras hex, etc.
    """
    entropy = lambda s: -(pd.Series(list(s)).value_counts(normalize=True) * 
                          np.log2(pd.Series(list(s)).value_counts(normalize=True))).sum()

    def hex_ratio(s, chars):
        return sum(1 for c in s if c in chars) / len(s) if s else 0

    return [
        len(blob),
        len(nonce),
        entropy(blob),
        entropy(nonce),
        hex_ratio(blob, "abcdef"),
        hex_ratio(blob, "0123456789"),
        hex_ratio(nonce, "abcdef"),
        hex_ratio(nonce, "0123456789"),
    ]

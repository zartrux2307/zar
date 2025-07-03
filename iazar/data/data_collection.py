import os
import logging
import pandas as pd
from pathlib import Path
from iazar.utils.config_manager import get_ia_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataCollection")

def main():
    config = get_ia_config()
    data_path = Path(config['data_paths']['successful_nonces'])
    data_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📥 Generando datos de ejemplo en: {data_path}")
    
    # Datos de ejemplo - en una aplicación real aquí se recolectarían datos reales
    data = {
        'block_number': [1000000, 1000001, 1000002],
        'miner': ['miner1', 'miner2', 'miner3'],
        'nonce': [123456, 654321, 987654],
        'difficulty': [1000000, 1000001, 1000002],
        'timestamp': [1625097600, 1625097601, 1625097602]
    }
    
    df = pd.DataFrame(data)
    df.to_csv(data_path, index=False)
    logger.info(f"✅ Datos generados: {len(df)} registros guardados")

if __name__ == "__main__":
    main()
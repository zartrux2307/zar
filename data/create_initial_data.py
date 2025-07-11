import os
import pandas as pd
import logging
from datetime import datetime
from iazar.utils.config_manager import ConfigManager
from iazar.utils.logging_config import setup_logging

# Configuración inicial
setup_logging()
logger = logging.getLogger(__name__)
config_manager = ConfigManager()

def generate_core_datasets():
    """
    Genera datasets esenciales si no existen o están vacíos
    """
    try:
        # Obtener rutas de configuración
        data_dir = config_manager.get_path('data_dir')
        training_dir = config_manager.get_path('training_data_dir')
        os.makedirs(training_dir, exist_ok=True)
        
        # Archivos esenciales con sus estructuras
        REQUIRED_FILES = {
            'winner_blocks.csv': pd.DataFrame(columns=[
                'block_hash', 'nonce', 'timestamp', 'difficulty', 'miner_address'
            ]),
            'nonce_training_data.csv': pd.DataFrame(columns=[
                'nonce_hex', 'entropy', 'zero_density', 'pattern_score', 
                'timestamp', 'block_height', 'is_valid'
            ]),
            'nonces_exitosos.csv': pd.DataFrame(columns=[
                'nonce_hex', 'timestamp', 'block_hash', 'miner_id', 'difficulty'
            ])
        }
        
        generated_files = []
        
        for file_name, df_template in REQUIRED_FILES.items():
            file_path = os.path.join(training_dir, file_name)
            
            # Crear archivo si no existe o está vacío
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                # Añadir datos de ejemplo para evitar DataFrames vacíos
                sample_data = df_template.copy()
                if not sample_data.empty:
                    n_columns = len(sample_data.columns)
                    sample_data.loc[0] = ['0'*64] + [0.0] * (n_columns - 1)
                
                sample_data.to_csv(file_path, index=False)
                logger.info(f"✅ Archivo {file_name} generado: {file_path}")
                generated_files.append(file_path)
            else:
                logger.info(f"ℹ️ Archivo ya existe: {file_path}")
        
        return generated_files
    
    except Exception as e:
        logger.error(f"❌ Error generando datasets: {str(e)}", exc_info=True)
        return []

def generate_placeholder_data(file_path, columns):
    """Genera datos de placeholder para un archivo específico"""
    try:
        df = pd.DataFrame(columns=columns)
        df.loc[0] = ['0'*64 if 'hash' in col.lower() else 0.0 for col in columns]
        df.to_csv(file_path, index=False)
        return True
    except Exception as e:
        logger.error(f"Error generando placeholder: {str(e)}")
        return False

def main():
    """Función principal"""
    logger.info("="*50)
    logger.info(" INICIANDO GENERACIÓN DE DATOS INICIALES ")
    logger.info("="*50)
    
    # Generar datasets esenciales
    generated = generate_core_datasets()
    
    # Verificar archivos adicionales
    ESSENTIAL_FILES = [
        ('nonce_hashes.bin', None),  # Archivo binario, no manejado aquí
        ('lmdb_index.idx', None)
    ]
    
    for file_name, _ in ESSENTIAL_FILES:
        file_path = os.path.join(config_manager.get_path('data_dir'), file_name)
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ Archivo esencial no encontrado: {file_path}")
    
    logger.info(f"🚀 Proceso completado. Archivos generados: {len(generated)}")
    return generated

if __name__ == "__main__":
    main()
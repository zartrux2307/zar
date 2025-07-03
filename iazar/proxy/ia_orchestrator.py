import os
import sys
import json
import time
import logging
import csv
from pathlib import Path

# ZMQ & Tipado
import zmq
from typing import List, Dict, Any

# Importar módulos IA internos con manejo robusto de errores
try:
    from iazar.bridge.predict_nonce_inference import PredictNonceInference
    from iazar.bridge.ethical_nonce_adapter import EthicalNonceAdapter
    from iazar.bridge.inject_nonces_from_ia import send_nonces_to_proxy
except ImportError as e:
    logging.error(f"❌ Error crítico al importar módulos IA: {str(e)}")
    logging.error("Por favor verifique la estructura de paquetes y PYTHONPATH")
    sys.exit(1)

# Logger principal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("iazar_proxy_orchestrator.log")
    ]
)
logger = logging.getLogger("IA-Orchestrator")

def get_project_root() -> Path:
    """Obtiene la ruta raíz del proyecto de forma confiable"""
    current_path = Path(__file__).resolve()
    # Ajuste: Subir solo 2 niveles para llegar a src/iazar/proxy -> src/
    return current_path.parent.parent.parent

def load_nonces(path: Path) -> List[Dict[str, Any]]:
    """Carga nonces desde JSON o CSV con detección automática de formato"""
    if not path.exists():
        logger.error(f"❌ Archivo no encontrado: {path}")
        return []
    
    try:
        # Detectar formato por extensión
        if path.suffix.lower() == '.json':
            return load_json_nonces(path)
        elif path.suffix.lower() in ['.csv', '.txt']:
            return load_csv_nonces(path)
        else:
            logger.error(f"❌ Formato no soportado: {path.suffix}")
            return []
    except Exception as e:
        logger.error(f"❌ Error cargando nonces: {str(e)}")
        return []

def load_json_nonces(path: Path) -> List[Dict[str, Any]]:
    """Carga nonces desde archivo JSON"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                logger.warning("⚠️ Archivo JSON vacío")
                return []
            
            data = json.loads(content)
            
            # Verificar estructura básica
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                logger.error("❌ Formato JSON inválido: Se esperaba lista de diccionarios")
                return []
                
            return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error decodificando JSON: {str(e)}")
        return []

def load_csv_nonces(path: Path) -> List[Dict[str, Any]]:
    """Carga nonces desde archivo CSV"""
    nonces = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convertir valores numéricos
                processed_row = {}
                for key, value in row.items():
                    try:
                        # Intentar convertir a float o int
                        processed_row[key] = float(value) if '.' in value else int(value)
                    except (ValueError, TypeError):
                        processed_row[key] = value
                nonces.append(processed_row)
        
        if not nonces:
            logger.warning("⚠️ Archivo CSV vacío")
            
        return nonces
    except Exception as e:
        logger.error(f"❌ Error leyendo CSV: {str(e)}")
        return []

def save_ranked_nonces(nonces: List[Dict[str, Any]], path: Path):
    """Guarda nonces clasificados con manejo robusto de errores"""
    try:
        os.makedirs(path.parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(nonces, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Nonces clasificados guardados en: {path} ({len(nonces)})")
    except Exception as e:
        logger.error(f"❌ Error guardando resultados IA: {str(e)}")

def main():
    logger.info("🚀 Iniciando orquestador IA ↔ ZMQ")
    
    PROJECT_ROOT = get_project_root()
    logger.info(f"📁 Directorio raíz del proyecto: {PROJECT_ROOT}")

    # RUTAS CORRECTAS DEFINIDAS EXPLÍCITAMENTE
    BRIDGE_DIR = PROJECT_ROOT / "iazar" / "bridge"
    DATA_DIR = PROJECT_ROOT / "iazar" / "data"
    
    # Archivo de entrada principal
    NONCES_INPUT_PATH = BRIDGE_DIR / "nonces_ready.json"
    # Archivo de respaldo
    FALLBACK_INPUT_PATH = DATA_DIR / "nonce_training_data.csv"
    # Archivo de salida
    NONCES_OUTPUT_PATH = DATA_DIR / "nonces_clasificados.json"
    
    logger.info(f"🔍 Buscando nonces en: {NONCES_INPUT_PATH}")

    # Paso 1: Cargar datos IA con verificación mejorada
    raw_nonces = load_nonces(NONCES_INPUT_PATH)
    if not raw_nonces:
        logger.warning("⚠️ Archivo principal no encontrado o vacío, usando respaldo...")
        raw_nonces = load_nonces(FALLBACK_INPUT_PATH)
        
        if not raw_nonces:
            logger.error("❌ No se encontraron nonces para evaluar. Revisando en 10 segundos...")
            time.sleep(10)
            return

    logger.info(f"📥 {len(raw_nonces)} nonces cargados para procesamiento")

    # Paso 2: Predicción y puntuación con IA
    try:
        predictor = PredictNonceInference()
        logger.info("🧠 Iniciando predicción de batch de nonces...")
        scored_nonces = predictor.predict_batch(raw_nonces)
        save_ranked_nonces(scored_nonces, NONCES_OUTPUT_PATH)
    except Exception as e:
        logger.error(f"❌ Error durante la predicción: {str(e)}")
        logger.error("Reiniciando proceso en 15 segundos...")
        time.sleep(15)
        return

    # Paso 3: Filtrado ético
    try:
        ethical_processor = EthicalNonceAdapter()
        logger.info("⚖️ Aplicando filtros éticos a nonces...")
        ethical_processor.execute_pipeline()  # Crea nuevo nonces_ready.json ético
        final_path = BRIDGE_DIR / "nonces_ethical.json"
    except Exception as e:
        logger.error(f"❌ Error en filtrado ético: {str(e)}")
        logger.error("Usando nonces clasificados directamente...")
        final_path = NONCES_OUTPUT_PATH

    # Paso 4: Inyección final a ZMQ
    if not final_path.exists():
        logger.error("❌ No se encontró archivo final. Usando clasificados.")
        final_path = NONCES_OUTPUT_PATH

    try:
        nonces_to_send = load_nonces(final_path)
        if not nonces_to_send:
            logger.error("❌ No hay nonces para enviar")
            return
            
        logger.info(f"📤 Enviando {len(nonces_to_send)} nonces al proxy XMRig...")
        send_nonces_to_proxy(nonces_to_send)
        logger.info("✅ Nonces enviados exitosamente")
    except Exception as e:
        logger.error(f"❌ Error enviando nonces: {str(e)}")


if __name__ == "__main__":
    while True:
        try:
            main()
            # Esperar antes del próximo ciclo
            logger.info("🔄 Ciclo completado. Esperando 10 segundos...")
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Detenido por el usuario")
            break
        except Exception as e:
            logger.critical(f"🔥 Error crítico no manejado: {str(e)}")
            logger.info("♻️ Reiniciando en 20 segundos...")
            time.sleep(20)
# src/iazar/bridge/predict_nonce_server.py
import os
import sys
import time
import json
import pickle
import logging
import argparse
import threading
import multiprocessing as mp
from datetime import datetime
from multiprocessing.shared_memory import SharedMemory

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Importaciones necesarias
from iazar.models.nonce_predictor import NoncePredictor
from iazar.utils.logging_config import configurar_logger
from iazar.utils.config_manager import ConfigManager
from iazar.utils.feature_utils import calc_nonce_features

# Configurar logger
logger = configurar_logger(__name__)

class NoncePredictorServer:
    def __init__(self, model_path=None, config=None):
        self.config = config or {}
        
        # Cargar configuración de memoria compartida
        shm_config_path = os.path.join(PROJECT_DIR, 'src', 'iazar', 'config', 'shared_memory.json')
        if os.path.exists(shm_config_path):
            with open(shm_config_path) as f:
                self.shm_config = json.load(f)
            logger.info("Configuración de memoria compartida cargada")
        else:
            # Configuración por defecto si el archivo no existe
            self.shm_config = {
                "prefix": "zartrux_shared",
                "job_buffer_size": 1048576,   # 1MB
                "solution_buffer_size": 2097152  # 2MB
            }
            logger.warning("Usando configuración por defecto para memoria compartida")
        
        # Obtener ruta del modelo
        self.model_path = model_path or os.path.join(
            self.config.get('model_dir', 'models'),
            self.config.get('model_file', 'iazar_model.pkl')
        )
        
        # Crear directorio si no existe
        model_dir = os.path.dirname(self.model_path)
        if model_dir and not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)
            logger.info(f"Directorio de modelos creado: {model_dir}")
        
        # Verificar si el modelo existe
        if not os.path.isfile(self.model_path):
            logger.warning(f"Modelo no encontrado en {self.model_path}. Entrenando modelo dummy...")
            self.train_dummy_model()
            
        self.predictor = None
        self.shm_job = None
        self.shm_solution = None
        self.running = False
        self.lock_file = os.path.join(os.getcwd(), "iazar_predictor.lock")

    def train_dummy_model(self):
        """Entrenar un modelo dummy temporal"""
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        import joblib
        
        logger.info("Entrenando modelo dummy temporal...")
        try:
            model = RandomForestRegressor(n_estimators=10, random_state=42)
            
            # Datos de ejemplo
            X = np.random.rand(100, 5)
            y = np.random.rand(100)
            
            model.fit(X, y)
            joblib.dump(model, self.model_path)
            logger.info(f"Modelo dummy guardado en: {self.model_path}")
        except Exception as e:
            logger.error(f"Error creando modelo dummy: {str(e)}")
            raise

    def initialize(self):
        """Inicializar predictor y memoria compartida"""
        try:
            # Cargar predictor
            self.predictor = NoncePredictor(model_path=self.model_path)
            logger.info(f"Predictor inicializado con modelo en {self.model_path}")

            # Inicializar memoria compartida
            prefix = self.shm_config["prefix"]
            job_shm_name = f"{prefix}_job"
            solution_shm_name = f"{prefix}_solution"

            try:
                # Conectar sin crear, asumiendo que ya existe
                self.shm_job = SharedMemory(name=job_shm_name, create=False)
                self.shm_solution = SharedMemory(name=solution_shm_name, create=False)
                logger.info(f"Conectado a memoria compartida: {job_shm_name} ({self.shm_job.size} bytes), "
                            f"{solution_shm_name} ({self.shm_solution.size} bytes)")
                
                # Verificar tamaños
                job_struct_size = self.config.get('job_struct_size', 256)
                if job_struct_size > self.shm_job.size:
                    logger.error(f"Tamaño de estructura de trabajo ({job_struct_size}) "
                                f"mayor que buffer ({self.shm_job.size})")
                
                solution_struct_size = self.config.get('solution_struct_size', 128)
                if solution_struct_size > self.shm_solution.size:
                    logger.error(f"Tamaño de estructura de solución ({solution_struct_size}) "
                                f"mayor que buffer ({self.shm_solution.size})")
                
                return True
            except FileNotFoundError:
                logger.error("Memoria compartida no encontrada. Asegúrese de que el proxy está en ejecución.")
                return False
        except Exception as e:
            logger.exception(f"Error inicializando predictor: {str(e)}")
            return False

    def run(self):
        """Bucle principal del servidor de predicción"""
        if not self.initialize():
            logger.critical("No se pudo inicializar el predictor. Saliendo.")
            return

        logger.info("🚀 Servidor de predicción IA-Zar iniciado")
        self.running = True
        
        try:
            while self.running:
                # Verificar si hay nuevo trabajo
                if self.check_for_job():
                    self.process_job()
                
                time.sleep(0.001)  # Menor tiempo de espera para mayor capacidad de respuesta
        except KeyboardInterrupt:
            logger.info("Recibida señal de interrupción, deteniendo...")
        except Exception as e:
            logger.exception(f"Error en bucle principal: {str(e)}")
        finally:
            self.cleanup()
            logger.info("Servidor detenido")

    def check_for_job(self):
        """Verificar si hay un nuevo trabajo en memoria compartida"""
        try:
            # El último byte es la bandera de nuevo trabajo
            if self.shm_job.buf[-1] == 1:
                return True
        except Exception as e:
            logger.error(f"Error verificando trabajo: {str(e)}")
        return False

    def process_job(self):
        """Procesar un trabajo y enviar la solución"""
        try:
            # Leer datos binarios del trabajo
            job_struct_size = self.config.get('job_struct_size', 256)
            job_data = bytes(self.shm_job.buf[:job_struct_size])
            
            # Parsear trabajo (implementar según tu formato)
            job = self.parse_job(job_data)
            logger.debug(f"📦 Trabajo recibido: {job['job_id']}")
            
            # Predecir nonce
            nonce = self.predictor.predict(job)
            logger.info(f"🔮 Nonce predicho: {nonce}")
            
            # Calcular hash (implementar según tu algoritmo)
            solution_hash = self.calculate_solution_hash(job, nonce)
            
            # Preparar solución
            solution = {
                'job_id': job['job_id'],
                'nonce': nonce,
                'hash': solution_hash,
                'is_valid': 1  # Marcado como válido
            }
            
            # Serializar y enviar solución
            solution_data = self.serialize_solution(solution)
            solution_struct_size = self.config.get('solution_struct_size', 128)
            
            if len(solution_data) > solution_struct_size:
                logger.error(f"Solución demasiado grande ({len(solution_data)} > {solution_struct_size})")
            else:
                self.shm_solution.buf[:len(solution_data)] = solution_data
                self.shm_solution.buf[-1] = 1  # Bandera de nueva solución
                logger.debug(f"✅ Solución enviada para trabajo {job['job_id']}")
            
            # Resetear bandera de trabajo
            self.shm_job.buf[-1] = 0
            
        except Exception as e:
            logger.exception(f"Error procesando trabajo: {str(e)}")
            # Resetear bandera incluso en caso de error
            self.shm_job.buf[-1] = 0

    def parse_job(self, job_data):
        """Parsear datos binarios del trabajo (implementar según tu formato)"""
        # Implementación de ejemplo - reemplazar con tu lógica
        return {
            'job_id': 'ejemplo_id',
            'blob': 'a1b2c3d4',
            'target': '0000ffff',
            'height': 1000000
        }

    def serialize_solution(self, solution):
        """Serializar solución a binario (implementar según tu formato)"""
        # Implementación de ejemplo - reemplazar con tu lógica
        return f"{solution['job_id']}:{solution['nonce']}:{solution['hash']}".encode()

    def calculate_solution_hash(self, job, nonce):
        """Calcular hash de solución (implementar según tu algoritmo)"""
        # Implementación de ejemplo
        return "abcd1234hash"

    def cleanup(self):
        """Liberar recursos"""
        try:
            if self.shm_job:
                self.shm_job.close()
            if self.shm_solution:
                self.shm_solution.close()
        except Exception as e:
            logger.error(f"Error limpiando recursos: {str(e)}")

def acquire_lock():
    """Asegurar solo una instancia en ejecución (compatible con Windows)"""
    lock_file = os.path.join(os.getcwd(), "iazar_predictor.lock")
    try:
        # Verificar si el archivo de lock existe
        if os.path.exists(lock_file):
            # Intentar eliminar si es antiguo (>5 minutos)
            file_age = time.time() - os.path.getmtime(lock_file)
            if file_age > 300:  # 5 minutos
                os.remove(lock_file)
                logger.warning("Eliminado archivo de lock antiguo")
            else:
                logger.warning("Archivo de lock existente. Otra instancia puede estar en ejecución.")
                return False
        
        # Crear nuevo lock
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        logger.error(f"Error con archivo de lock: {str(e)}")
        return False

if __name__ == "__main__":
    # Parsear argumentos
    parser = argparse.ArgumentParser(description='Servidor de predicción de nonces IA-Zar')
    parser.add_argument('--model', type=str, help='Ruta al modelo entrenado')
    parser.add_argument('--debug', action='store_true', help='Habilitar modo debug')
    args = parser.parse_args()

    # Configurar nivel de logging
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Modo debug activado")

    # Adquirir lock (evitar múltiples instancias)
    if not acquire_lock():
        logger.error("No se pudo adquirir el lock. Saliendo.")
        sys.exit(1)

    # Cargar configuración
    try:
        config_manager = ConfigManager()
        config = config_manager.get_config('ia_config')
        logger.info("Configuración IA cargada correctamente")
    except Exception as e:
        logger.critical(f"Error cargando configuración: {str(e)}")
        # Limpiar archivo de lock
        lock_file = os.path.join(os.getcwd(), "iazar_predictor.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)
        sys.exit(1)

    # Crear y ejecutar servidor
    server = NoncePredictorServer(model_path=args.model, config=config)
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Servidor detenido por el usuario")
    finally:
        # Limpiar archivo de lock al salir
        lock_file = os.path.join(os.getcwd(), "iazar_predictor.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.info("Lock liberado")
            except Exception as e:
                logger.error(f"Error eliminando lock: {str(e)}")
        logger.info("Recursos liberados")
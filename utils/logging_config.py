# src/iazar/utils/logging_config.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def configurar_logger(nombre_modulo, directorio_logs="logs", nivel=logging.INFO):
    """Configuración centralizada de logging con soporte Unicode"""
    # Crear directorio de logs si es necesario
    os.makedirs(directorio_logs, exist_ok=True)
    
    # Crear logger específico del módulo
    logger = logging.getLogger(nombre_modulo)
    logger.setLevel(nivel)
    
    # Eliminar handlers existentes
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Handler de archivo con codificación UTF-8
    archivo_log = os.path.join(directorio_logs, f"{nombre_modulo}.log")
    file_handler = RotatingFileHandler(
        archivo_log, 
        maxBytes=5*1024*1024, 
        backupCount=3,
        encoding='utf-8'
    )
    
    # Handler de consola con soporte Unicode para Windows
    if sys.platform == 'win32':
        from logging import StreamHandler
        class WindowsSafeHandler(StreamHandler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    stream = self.stream
                    stream.write(msg + self.terminator)
                    self.flush()
                except UnicodeEncodeError:
                    # Intentar con UTF-8
                    try:
                        msg = msg.encode('utf-8').decode(sys.stdout.encoding, 'replace')
                        stream.write(msg + self.terminator)
                        self.flush()
                    except Exception:
                        self.handleError(record)
        console_handler = WindowsSafeHandler()
    else:
        console_handler = logging.StreamHandler()
    
    # Formateador común
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Agregar handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
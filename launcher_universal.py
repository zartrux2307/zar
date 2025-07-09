#!/usr/bin/env python3
"""
Launcher Universal Zartrux IA Mining System
Versión 2.4 - Correcciones Unicode y rutas críticas
"""

# Fix Unicode encoding for Windows
import sys
import io
if sys.stdout.encoding != 'UTF-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'UTF-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import time
import argparse
import signal
import subprocess
import logging
from datetime import datetime
import psutil
import yaml
import platform

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("launcher.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ZartruxLauncher")

# Estructura del proyecto basada en estructura2.txt
DEFAULT_FOLDERS = [
    "analytics",
    "bridge",
    "core",
    "evaluation",
    "models",
    "security",
    "training",
    "utils"
  
]

# Scripts críticos que deben iniciarse primero (CORREGIDOS)
CRITICAL_SCRIPTS = [
    "core/mining_core.py",
    "bridge/shared_memory_manager.py",  # Nombre real
    "analytics/entropy_tools.py"        # Nombre real
]

# Tiempo máximo de espera para que los procesos críticos se inicien (segundos)
CRITICAL_TIMEOUT = 15

def normalize_path(path):
    """Normaliza las rutas para comparación insensible a mayúsculas y separadores"""
    return path.replace('\\', '/').lower()

def load_config(config_path="launcher_config.yaml"):
    """Carga la configuración desde archivo YAML"""
    config = {
        "folders": DEFAULT_FOLDERS,
        "critical_scripts": CRITICAL_SCRIPTS,
        "start_delay": 0.5,
        "resource_monitor": True,
        "windows_compat": platform.system() == "Windows"
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
                config.update(user_config)
                logger.info(f"Configuración cargada desde {config_path}")
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
    
    return config

def find_scripts(base_dir, folders):
    """Busca todos los scripts en la estructura de carpetas"""
    scripts = []
    for folder in folders:
        # Resolver ruta relativa (especialmente importante para ../monitor)
        folder_path = os.path.normpath(os.path.join(base_dir, folder))
        
        if not os.path.exists(folder_path):
            logger.warning(f"Carpeta no encontrada: {folder_path}")
            continue
            
        for root, _, files in os.walk(folder_path):
            for file in files:
                if (file.endswith(".py") and 
                    not file.startswith("__init__") and
                    not file.startswith("test")):
                    full_path = os.path.join(root, file)
                    
                    # Conservar ruta relativa para identificación
                    rel_path = os.path.relpath(full_path, base_dir)
                    scripts.append((full_path, rel_path))
    
    # Ordenar por prioridad: críticos primero, luego por orden alfabético
    scripts.sort(key=lambda x: (
        0 if any(normalize_path(crit) in normalize_path(x[1]) for crit in config["critical_scripts"]) else 1,
        x[1]
    ))
    return scripts

def run_script(script_path, rel_path, delay=0.4, resource_monitor=False, windows_compat=False):
    """Ejecuta un script y devuelve el proceso con información adicional"""
    logger.info(f"🚀 Iniciando: {rel_path}")
    try:
        # Configurar entorno con variables críticas
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["ZARTRUX_LAUNCHER"] = "1"
        env["ZARTRUX_BASE_DIR"] = os.path.dirname(os.path.abspath(__file__))
        
        # Redirigir salida a archivo de log específico
        log_dir = os.path.join("logs", "scripts")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{os.path.basename(script_path)}.log")
        
        # Manejo especial para Windows
        if windows_compat:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            creationflags = 0
            
        with open(log_file, 'a', encoding='utf-8') as log_handle:
            p = subprocess.Popen(
                [sys.executable, script_path],
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags
            )
        
        process_info = {
            "process": p,
            "path": script_path,
            "rel_path": rel_path,
            "start_time": datetime.now(),
            "log_file": log_file
        }
        
        if resource_monitor:
            try:
                process_info["monitor"] = psutil.Process(p.pid)
            except psutil.NoSuchProcess:
                logger.warning(f"No se pudo monitorear PID {p.pid} para {rel_path}")
        
        time.sleep(delay)
        return process_info
    except Exception as e:
        logger.error(f"❌ Error iniciando {rel_path}: {str(e)}")
        return None

def check_critical_processes(running_procs, critical_scripts):
    """Verifica que los procesos críticos estén en ejecución (MEJORADO)"""
    # Normalizar rutas críticas
    normalized_critical = [normalize_path(script) for script in critical_scripts]
    
    critical_ok = True
    missing = []
    
    # Verificar existencia de procesos críticos
    for crit_script, norm_crit in zip(critical_scripts, normalized_critical):
        found = False
        for proc in running_procs:
            # Comparar rutas normalizadas
            if norm_crit == normalize_path(proc["rel_path"]):
                found = True
                if proc["process"].poll() is not None:
                    logger.critical(f"⚠️ Proceso crítico falló: {proc['rel_path']}")
                    logger.critical(f"   Consulte el log: {proc['log_file']}")
                    critical_ok = False
                break
        
        if not found:
            missing.append(crit_script)
    
    # Reportar procesos críticos faltantes
    if missing:
        for script in missing:
            logger.critical(f"⚠️ Proceso crítico no encontrado: {script}")
        critical_ok = False
    
    return critical_ok

def signal_handler(sig, frame):
    """Maneja señales de terminación"""
    print("\n" + "="*50)
    logger.info("🛑 Señal de terminación recibida. Finalizando procesos...")
    for proc in running_procs:
        try:
            process = proc["process"]
            rel_path = proc["rel_path"]
            
            if process.poll() is None:
                logger.info(f"   Deteniendo: {rel_path}")
                
                # Manejo especial para Windows
                if config["windows_compat"]:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                
                # Esperar terminación elegante
                try:
                    process.wait(timeout=5)
                except (subprocess.TimeoutExpired, psutil.TimeoutExpired):
                    logger.warning(f"   Forzando terminación: {rel_path}")
                    process.kill()
        except Exception as e:
            logger.error(f"   Error deteniendo proceso: {str(e)}")
    
    logger.info("✅ Todos los procesos finalizados. Adiós!")
    sys.exit(0)

def print_summary(running_procs, critical_scripts):
    """Imprime un resumen de los procesos en ejecución"""
    print("\n" + "="*50)
    logger.info("🔥 Sistema Zartrux IA Mining completamente operativo")
    logger.info(f"📊 Procesos activos: {len(running_procs)}")
    
    print("\nProcesos Críticos:")
    for crit_script in critical_scripts:
        status = "NO ENCONTRADO"
        for proc in running_procs:
            if normalize_path(crit_script) == normalize_path(proc["rel_path"]):
                status = "ACTIVO" if proc["process"].poll() is None else "FALLIDO"
                break
        print(f"  • {crit_script} [{status}]")
    
    print("\nProcesos Adicionales:")
    for proc in running_procs:
        if not any(normalize_path(crit) == normalize_path(proc["rel_path"]) for crit in critical_scripts):
            status = "ACTIVO" if proc["process"].poll() is None else "FALLIDO"
            print(f"  • {proc['rel_path']} [{status}]")
    
    print("\n" + "="*50)
    logger.info("Presione Ctrl+C para detener todos los procesos")
    print("="*50 + "\n")

def monitor_processes(running_procs):
    """Monitorea el estado de los procesos en ejecución"""
    logger.info("🔍 Iniciando monitoreo de procesos...")
    try:
        while running_procs:
            all_ok = True
            for proc in running_procs[:]:
                if proc["process"].poll() is not None:
                    logger.warning(f"⚠️ Proceso terminado: {proc['rel_path']}")
                    running_procs.remove(proc)
                    all_ok = False
            
            if not running_procs:
                logger.info("✅ Todos los procesos han terminado normalmente")
                break
                
            time.sleep(10)
            
            # Reporte periódico de estado
            if time.time() % 30 < 1:  # Cada ~30 segundos
                active_count = sum(1 for p in running_procs if p["process"].poll() is None)
                logger.info(f"📈 Procesos activos: {active_count}/{len(running_procs)}")
                
    except KeyboardInterrupt:
        logger.info("Monitoreo interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error en monitoreo: {str(e)}")

if __name__ == "__main__":
    print(f"""
    ███████ █████╗ ██████╗ ████████╗██████╗ ██╗   ██╗██╗  ██╗
    ██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██║   ██║╚██╗██╔╝
    █████╗  ███████║██████╔╝   ██║   ██████╔╝██║   ██║ ╚███╔╝ 
    ██╔══╝  ██╔══██║██╔══██╗   ██║   ██╔══██╗██║   ██║ ██╔██╗ 
    ███████╗██║  ██║██║  ██║   ██║   ██║  ██║╚██████╔╝██╔╝ ██╗
    ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
    IA Mining System Launcher v2.4 | {'Windows' if platform.system() == 'Windows' else 'Linux'}
    """)
    
    # Configuración de argumentos
    parser = argparse.ArgumentParser(description="Launcher Universal Zartrux IA Mining System")
    parser.add_argument("-d", "--delay", type=float, default=0.5, 
                        help="Delay entre inicio de scripts (segundos)")
    parser.add_argument("-m", "--manual", action="store_true", 
                        help="Modo manual (selección interactiva de scripts)")
    parser.add_argument("-c", "--config", default="launcher_config.yaml", 
                        help="Archivo de configuración YAML")
    parser.add_argument("-s", "--skip-critical-check", action="store_true",
                        help="Omitir verificación de procesos críticos")
    args = parser.parse_args()

    global running_procs, config
    running_procs = []

    # Cargar configuración
    config = load_config(args.config)
    
    # Obtener directorio base del launcher
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logger.info(f"Directorio base del launcher: {base_dir}")

    # Registrar configuración
    logger.info(f"Modo: {'MANUAL' if args.manual else 'AUTOMÁTICO'}")
    logger.info(f"Delay entre scripts: {args.delay} segundos")
    logger.info(f"Monitoreo de recursos: {'ACTIVADO' if config['resource_monitor'] else 'DESACTIVADO'}")
    logger.info(f"Modo Windows: {'SÍ' if config['windows_compat'] else 'NO'}")

    # Buscar scripts
    all_scripts = find_scripts(base_dir, config["folders"])
    
    if not all_scripts:
        logger.error("No se encontraron scripts para ejecutar. Verifique la estructura de carpetas.")
        sys.exit(1)

    # Modo manual: selección interactiva
    if args.manual:
        print("\n📋 Scripts disponibles:")
        for idx, (full_path, rel_path) in enumerate(all_scripts):
            prefix = "[CRÍTICO] " if any(normalize_path(crit) in normalize_path(rel_path) for crit in config["critical_scripts"]) else ""
            print(f"  [{idx}] {prefix}{rel_path}")
        
        selection = input("\nSeleccione scripts (ej: 1,3-5,7 o 'all' para todos): ")
        selected_indices = set()
        
        if selection.strip().lower() == "all":
            selected_indices = set(range(len(all_scripts)))
        else:
            # Procesar selección compleja (rangos y valores individuales)
            for part in selection.split(","):
                part = part.strip()
                if '-' in part:
                    start, end = part.split('-')
                    if start.isdigit() and end.isdigit():
                        selected_indices.update(range(int(start), int(end)+1))
                elif part.isdigit():
                    selected_indices.add(int(part))
        
        # Filtrar scripts seleccionados
        all_scripts = [all_scripts[i] for i in sorted(selected_indices) if i < len(all_scripts)]
    
    # Registrar secuencia de inicio
    logger.info("\n🔧 Secuencia de inicio:")
    critical_scripts = config["critical_scripts"]
    for full_path, rel_path in all_scripts:
        prefix = "🔥 " if any(normalize_path(crit) in normalize_path(rel_path) for crit in critical_scripts) else "   "
        logger.info(f"{prefix}{rel_path}")

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Ejecutar scripts
    logger.info("\n🚀 Iniciando procesos...")
    for full_path, rel_path in all_scripts:
        proc_info = run_script(
            full_path, 
            rel_path, 
            delay=args.delay,
            resource_monitor=config["resource_monitor"],
            windows_compat=config["windows_compat"]
        )
        if proc_info:
            running_procs.append(proc_info)

    # Verificación de procesos críticos
    if not args.skip_critical_check:
        logger.info("\n🔍 Verificando procesos críticos...")
        time.sleep(CRITICAL_TIMEOUT)
        
        if not check_critical_processes(running_procs, critical_scripts):
            logger.critical("🚨 Fallo en procesos críticos. Deteniendo sistema...")
            signal_handler(signal.SIGINT, None)
            sys.exit(1)

    # Mostrar resumen y monitorear
    print_summary(running_procs, critical_scripts)
    monitor_processes(running_procs)
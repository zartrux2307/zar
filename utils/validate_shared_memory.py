# validate_shared_memory.py
import os
import json
from multiprocessing import shared_memory

def check_shm_config():
    config_path = r"C:\zarturxia\src\iazar\config\shared_memory.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
        print("✅ Configuración de memoria compartida:")
        print(f"  Prefijo: {config['prefix']}")
        print(f"  Tamaño buffer trabajos: {config['job_buffer_size']/1024:.1f} KB")
        print(f"  Tamaño buffer soluciones: {config['solution_buffer_size']/1024:.1f} KB")
        
        # Verifica conexión real
        test_shm = shared_memory.SharedMemory(
            name=f"{config['prefix']}_job",
            create=False,
            size=1024
        )
        test_shm.close()
        print("✅ Conexión a SHM exitosa")
    except FileNotFoundError:
        print("❌ shared_memory.json no encontrado")
    except Exception as e:
        print(f"❌ Error en configuración: {str(e)}")

if __name__ == "__main__":
    check_shm_config()
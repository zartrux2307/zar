#!/usr/bin/env python3
"""
main_central.py - Orquesta el arranque de todos los módulos IA-Zar y del proxy.

Se inicia cada main.py en src/iazar/<modulo>/, además de iazar/proxy/ia_proxy_main.py como procesos independientes.
Cada proceso escribe su salida estándar en un archivo de log individual.
"""
import os
import sys
import subprocess

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Configurar directorio de logs relativos
    logs_dir = os.path.join(base_dir, "logs", "iazar_subprocess")
    os.makedirs(logs_dir, exist_ok=True)

    # Lista de módulos a iniciar: (nombre, ruta_script, ruta_log)
    processes = []

    # Subcarpetas con main.py
    modules = ["analytics", "bridge", "evaluation", "training", "utils", "models", "security"]
    for mod in modules:
        script_path = os.path.join(base_dir, "iazar", mod, "main.py")
        log_path = os.path.join(logs_dir, f"{mod}.log")
        processes.append((mod, script_path, log_path))

    # Proxy IA-Zar Stratum
    proxy_script = os.path.join(base_dir, "iazar", "proxy", "ia_proxy_main.py")
    if len(sys.argv) < 2:
        print("Uso: python main_central.py <wallet_address> [pool_host] [pool_port]")
        sys.exit(1)
    wallet = sys.argv[1]
    pool_host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    pool_port = sys.argv[3] if len(sys.argv) > 3 else "3333"
    proxy_log = os.path.join(logs_dir, "ia_proxy.log")
    processes.append(("ia_proxy", proxy_script, proxy_log))

    # Lanzar cada proceso
    for item in processes:
        name, path, log_file = item[0], item[1], item[2]
        try:
            log_fh = open(log_file, "w")
            cmd = [sys.executable, path]
            # Si es el proxy, añadir argumentos de conexión
            if name == "ia_proxy":
                cmd.extend([wallet, pool_host, pool_port])
            print(f"✨ Lanzando proceso '{name}' -> {path}")
            # Redirige stdout y stderr al archivo de log
            subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
        except Exception as e:
            print(f"❌ Error arrancando {name}: {e}")
            if 'log_fh' in locals():
                log_fh.write(f"❌ Excepción al iniciar {name}: {e}\n")
                log_fh.close()

if __name__ == "__main__":
    main()

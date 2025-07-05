import os
import subprocess
import sys
import time
import argparse
import signal

# CARPETAS (ajusta si tu estructura cambia)
FOLDERS = [
    "analytics",
            "utils",
            "training",
            "models",
            "core",
            "bridge",
            "evaluation",
            "security",
            "data",
            "logs"
            
]

def all_py_scripts(base_dir):
    scripts = []
    for folder in FOLDERS:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.exists(folder_path):
            continue
        for file in sorted(os.listdir(folder_path)):
            if file.endswith(".py") and not file.startswith("__init__"):
                scripts.append(os.path.join(folder_path, file))
    return scripts

def run_script(script_path, delay=0.4):
    print(f"▶️ Lanzando: {script_path}")
    try:
        p = subprocess.Popen([sys.executable, script_path])
        time.sleep(delay)
        return p
    except Exception as e:
        print(f"❌ Error lanzando {script_path}: {e}")
        return None

def signal_handler(sig, frame):
    print("\n🛑 Ctrl+C detectado. Finalizando todos los procesos...")
    for proc in running_procs:
        try:
            proc.terminate()
        except Exception:
            pass
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launcher universal Zarturxia")
    parser.add_argument("-d", "--delay", type=float, default=0.5, help="Delay entre scripts (s)")
    parser.add_argument("-m", "--manual", action="store_true", help="Modo manual (te deja elegir scripts)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    scripts = all_py_scripts(base_dir)
    running_procs = []

    if args.manual:
        print("Scripts detectados:")
        for idx, script in enumerate(scripts):
            print(f"  {idx}: {script}")
        seleccion = input("Introduce índices separados por coma: ")
        indices = [int(i) for i in seleccion.split(",") if i.strip().isdigit()]
        scripts = [scripts[i] for i in indices if i < len(scripts)]

    print("\n📋 Scripts a ejecutar:")
    for s in scripts:
        print(" •", s)

    signal.signal(signal.SIGINT, signal_handler)
    print(f"\n🚦 Iniciando {len(scripts)} procesos...\n")
    for s in scripts:
        p = run_script(s, delay=args.delay)
        if p:
            running_procs.append(p)

    print("\n✅ Todos los procesos iniciados. Ctrl+C para salir\n")
    # Esperar a que terminen (nunca, hasta Ctrl+C)
    for p in running_procs:
        p.wait()

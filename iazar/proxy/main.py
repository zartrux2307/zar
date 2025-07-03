#!/usr/bin/env python3
"""
main.py del módulo bridge de IA-Zar.
Ejecuta automáticamente todos los scripts .py en este directorio.
"""
import os
import runpy

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in sorted(os.listdir(current_dir)):
        if not filename.endswith(".py"):
            continue
        if filename in ("__init__.py", os.path.basename(__file__)):
            continue
        filepath = os.path.join(current_dir, filename)
        if os.path.isfile(filepath):
            print(f"➡️ Ejecutando módulo: {filename}")
            try:
                runpy.run_path(filepath, run_name="__main__")
            except Exception as e:
                print(f"❌ Error al ejecutar {filename}: {e}")

if __name__ == "__main__":
    main()

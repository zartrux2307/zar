import os
import re

PROYECTO_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(PROYECTO_DIR, 'iazar')

rel_imports = []
rutas_relativas = []
py_scripts = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    for fname in filenames:
        if fname.endswith('.py'):
            fullpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fullpath, PROYECTO_DIR)
            # Evitar __init__.py para el launcher
            if fname != '__init__.py':
                py_scripts.append(fullpath)
            # Analiza cada línea
            with open(fullpath, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    # Imports relativos
                    if re.search(r'^\s*from\s+\.+', line) or re.search(r'^\s*import\s+\.+', line):
                        rel_imports.append(f"{rel_path}:{i}: {line.strip()}")
                    # Rutas relativas peligrosas
                    if re.search(r"(['\"])(\.\.?/|data/|logs/)", line):
                        rutas_relativas.append(f"{rel_path}:{i}: {line.strip()}")

# Resultados
print("\n===== IMPORTS RELATIVOS DETECTADOS =====")
for x in rel_imports:
    print(x or "(ninguno)")

print("\n===== RUTAS RELATIVAS SOSPECHOSAS =====")
for x in rutas_relativas:
    print(x or "(ninguna)")

print("\n===== LISTA PARA LAUNCHER UNIVERSAL =====")
for script in py_scripts:
    print(script)

# Opcional: guardar la lista para el launcher
with open('scripts_launcher.txt', 'w', encoding='utf-8') as f:
    for script in py_scripts:
        f.write(f"{script}\n")
print("\n[OK] scripts_launcher.txt generado con todos los .py (menos __init__.py)")

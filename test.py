import os

# Carpeta raíz de los scripts python
ROOT = os.path.join("src", "iazar")
# Importación estándar
IMPORT_LINE = "from iazar.utils.feature_utils import calc_nonce_features, guardar_nonces_csv, COLUMNS\n"

# Extensiones y nombres candidatos
TARGETS = [
     ["data", "clean_nonce_training_data.py"],
    ["data", "create_initial_data.py"],
    ["data", "data_collection.py"],
    ["analytics", "lmdb_nonce_extractor.py"],
    ["bridge", "predict_nonce_inference.py"],
    ["bridge", "predict_nonce_server.py"],
    ["bridge", "inject_nonces_from_ia.py"],
    ["bridge", "ai_proxy_adapter.py"],
    ["bridge", "ethical_nonce_adapter.py"],
    ["bridge", "job_sync.py"],
    ["evaluation", "nonce_quality_filter.py"],
    # Puedes añadir más aquí si lo deseas
]

for rel_path in TARGETS:
    file_path = os.path.join(ROOT, rel_path)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.readlines()
        # No añadir si ya existe
        if any("feature_utils" in line for line in content):
            print(f"Ya tiene import en {file_path}")
            continue
        # Insertar después de comentarios/shebang/encoding o al inicio
        insert_idx = 0
        for idx, line in enumerate(content):
            if (line.strip().startswith("#!") or
                line.strip().startswith("# -*-") or
                line.strip().startswith("#") or
                line.strip() == ""):
                insert_idx = idx + 1
            else:
                break
        # Añadir la importación
        new_content = content[:insert_idx] + [IMPORT_LINE] + content[insert_idx:]
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_content)
        print(f"✔ Importación añadida en {file_path}")
    else:
        print(f"⚠ Archivo NO encontrado: {file_path}")

print("\nHecho. Revisa los archivos modificados.")

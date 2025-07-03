# ZARTRUX IA Mining System

Bienvenido al sistema de minería inteligente **ZARTRUX**, una arquitectura modular diseñada para optimizar la minería de Monero (XMR) mediante el uso de inteligencia artificial, análisis estadístico y aprendizaje automático. Esta plataforma combina un proxy IA con un sistema de validación multicapa, entrenamiento ético y análisis avanzado de datos mineros.

---

## 📌 Índice

1. [Visión general del sistema](#visión-general-del-sistema)
2. [Arquitectura general](#arquitectura-general)
3. [Diagrama de flujo IAProxy](#diagrama-de-flujo-iaproxy)
4. [Estructura de carpetas](#estructura-de-carpetas)
5. [Componentes clave](#componentes-clave)
6. [Modelos IA incluidos](#modelos-ia-incluidos)
7. [Entrenamiento y evaluación](#entrenamiento-y-evaluación)
8. [Requisitos y ejecución](#requisitos-y-ejecución)
9. [Contribuciones y licencia](#contribuciones-y-licencia)

---

## 🔍 Visión general del sistema

ZARTRUX IA Mining System está diseñado para:

* Predecir nonces efectivos en minería XMR.
* Filtrar resultados inválidos mediante validaciones estadísticas.
* Reentrenar automáticamente los modelos con datos reales.
* Mantener trazabilidad y rendimiento de cada componente IA.

El sistema se comunica con el proxy de minería XMRig a través de ZeroMQ y analiza en tiempo real los trabajos recibidos de la pool.

---

## 🧠 Arquitectura general

```plaintext
          ┌────────────┐
          │   Pool     │
          └────┬───────┘
               │ Trabajo
               ▼
        ┌──────────────┐
        │  IA Proxy    │◄──┐
        └────┬─────────┘   │
             │ Optimiza    │
             ▼            │
       ┌──────────────┐   │
       │ IA Módulos   │   │
       └────┬─────────┘   │
            │ Nonces      │
            ▼            │
     ┌───────────────┐   │
     │  XMRig Proxy  │───┘
     └────┬──────────┘
          │ Soluciones
          ▼
     ┌───────────────┐
     │   Pool (TLS)  │
     └───────────────┘
```

---

## ⚙️ Diagrama de flujo IAProxy

1. **Notificación de trabajo (Pool → IAProxy):**

   * El pool envía un nuevo trabajo de minería al proxy IA.

2. **Procesamiento IA:**

   * Análisis de patrones de nonces.
   * Optimización de parámetros de minería.
   * Selección de algoritmos más eficientes.

3. **Distribución a mineros:**

   * El trabajo optimizado se envía al proxy XMRig.
   * Distribución a los mineros conectados.

4. **Solución de mineros:**

   * Los mineros resuelven el trabajo con parámetros optimizados.
   * Envían la solución al proxy XMRig.

5. **Validación IA:**

   * Seis técnicas de validación en cascada.
   * Filtrado multicapa antes de enviar al pool.

6. **Envío al pool:**

   * Transmisión segura TLS.
   * Mantenimiento de conexión (ping/pong).

7. **Actualización de modelos:**

   * Reentrenamiento incremental con nuevos datos.
   * Ajuste de parámetros en tiempo real.
   * Optimización continua de los filtros IA.

---

## 📁 Estructura de carpetas

```plaintext
/ia-mining-system/
├── monitor/                 # Interfaz web de monitoreo
├── src/
│   ├── ia-modules/
│   │   ├── bridge/          # Adaptadores IA ↔ minería
│   │   ├── training/        # Entrenamiento y modelos ML
│   │   ├── analytics/       # Análisis de series temporales y minería
│   │   ├── evaluation/      # Validaciones estadísticas
│   │   ├── logs/            # Nonces, inyecciones y resultados
│   │   ├── data/            # Dataset de entrenamiento CSV
│   │   ├── models/          # Modelos entrenados (Joblib)
│   │   └── utils/           # Preprocesamiento, configuración
│   └── proxy/               # Módulo IA Proxy
├── xmrig-proxy/             # Proxy XMRig
```

---

## 🧩 Componentes clave

* **predict\_nonce\_server.py**: Servidor que analiza y responde con nonces IA.
* **inject\_nonces\_from\_ia.py**: Inserta los nonces filtrados dentro del flujo de minería.
* **auto\_trainer.py**: Automatiza el entrenamiento diario del modelo IA.
* **nonce\_quality\_filter.py**: Aplica 6 filtros estadísticos para validar nonces.
* **monitor/server.py**: Muestra en tiempo real métricas de IA, precisión y nonces exitosos.

---

## 🧠 Modelos IA incluidos

* `ethical_nonce_model.joblib`: modelo principal de clasificación de nonces.
* `hash_classifier_model.joblib`: estima dificultad futura con clasificación por hash.
* `cluster_model.joblib`: segmenta grupos de nonces por comportamiento similar.

---

## 🧪 Entrenamiento y evaluación

* Datos de entrenamiento: `data/nonce_training_data.csv`.
* Ingeniería de características: `Feature_Engineer.py`, `nonce_loader.py`.
* Evaluación cruzada: `pca_nonce_classifier.py`, `kl_divergence.py`, `entropy_analysis.py`.
* Métricas de rendimiento: `zar.py`, `monitor/server.py`.

---

## 🚀 Requisitos y ejecución

```bash
# Instalar requisitos
pip install -r requirements.txt

# Ejecutar el sistema completo (IA + Proxy + Monitor)
bash run_all.sh

# Entrenamiento manual
python3 train_model.py
```

### Requisitos clave

* Python 3.10+
* Flask, NumPy, Scikit-learn, pandas, joblib
* ZeroMQ (para comunicación IA ↔ Proxy)
* TLS/SSL certificados (seguridad pool)

---

## 🤝 Contribuciones y licencia

ZARTRUX es un proyecto ético y educativo que busca mejorar la minería responsable mediante inteligencia artificial y sistemas de validación. Está abierto a contribuciones.

> Licencia: MIT

> Autor: José Luis "zartrux"

---

¿Preguntas o sugerencias? Contacta a través de GitHub o el sistema de monitoreo IA.

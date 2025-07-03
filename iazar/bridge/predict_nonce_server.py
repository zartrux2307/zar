import zmq
import json
import logging
from iazar.bridge.predict_nonce_inference import PredictNonceInference
from iazar.utils.randomx_wrapper import compute_randomx_hash, hash_meets_target

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PredictNonceServer")

context = zmq.Context()
socket_in = context.socket(zmq.PULL)
socket_in.connect("tcp://127.0.0.1:5555")  # Trabajos desde el proxy

socket_out = context.socket(zmq.PUSH)
socket_out.connect("tcp://127.0.0.1:5556")  # Soluciones hacia el proxy

predictor = PredictNonceInference()
logger.info("📡 Servidor de predicción IA listo en 5555/5556")

while True:
    try:
        message = socket_in.recv_json()
        job = message.get("data")
        if not job:
            continue
        blob = job.get("blob")
        target = job.get("target")
        seed_hash = job.get("seed_hash")
        job_id = job.get("id")

        logger.info(f"🚀 Nuevo trabajo recibido: {job_id} Altura: {job.get('height')}")

        # Generar pool de nonces candidatos IA
        candidatos = []
        for i in range(10000):  # Puedes variar el número
            nonce = i  # O usa la IA para sugerir nonces
            score = predictor.predict_one(blob, nonce)
            candidatos.append({"nonce": nonce, "score": score})
        candidatos = sorted(candidatos, key=lambda x: x["score"], reverse=True)[:300]

        # Buscar un nonce válido real (cumpla el target)
        for cand in candidatos:
            hash_hex = compute_randomx_hash(blob, cand["nonce"], seed_hash)
            if hash_meets_target(hash_hex, target):
                logger.info(f"🟢 ¡Share encontrado por IA! Nonce={cand['nonce']} Hash={hash_hex}")
                socket_out.send_json({
                    "type": "solution",
                    "data": {
                        "job_id": job_id,
                        "nonce": cand["nonce"],
                        "hash": hash_hex,
                        "target": target
                    }
                })
                break
    except Exception as e:
        logger.error(f"❌ Error IA: {e}")

# C:\zarturxia\main_central.py
import os
import sys
import argparse
from iazar.bridge import ai_proxy_adapter

def main():
    parser = argparse.ArgumentParser(description='Proxy de IA para minería Monero')
    parser.add_argument('wallet', type=str, help='Dirección de billetera Monero')
    parser.add_argument('pool_host', type=str, help='Host de la pool de minería')
    parser.add_argument('pool_port', type=int, help='Puerto de la pool de minería')
    parser.add_argument('--threads', type=int, default=1, help='Número de hilos de minería')
    parser.add_argument('--ai-server', type=str, default='tcp://localhost:5555', help='URL del servidor de IA')
    
    args = parser.parse_args()
    
    print(f"⚙️ Configuración de minería:")
    print(f"  Billetera: {args.wallet}")
    print(f"  Pool: {args.pool_host}:{args.pool_port}")
    print(f"  Hilos: {args.threads}")
    print(f"  Servidor IA: {args.ai_server}")
    print("\n🚀 Iniciando proxy de IA...")
    
    # Iniciar el proxy de IA
    ai_proxy_adapter.start_proxy(
        wallet_address=args.wallet,
        pool_host=args.pool_host,
        pool_port=args.pool_port,
        num_threads=args.threads,
        ai_server_url=args.ai_server
    )

if __name__ == "__main__":
    main()
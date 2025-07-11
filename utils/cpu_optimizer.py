import psutil
import time
import os
from iazar.utils.avx_optimizer import enable_avx_optimizations


class CPUMonitor:
    def __init__(self):
        self.max_temperature = 85  # °C
        self.max_usage = 90  # %
        self.threads = psutil.cpu_count(logical=False)
        self.enable_avx = True
        self.last_adjustment = time.time()

    def get_cpu_temperature(self):
        try:
            if os.name == 'nt':
                # Windows
                import wmi
                w = wmi.WMI(namespace="root\\wmi")
                temperature = w.MSAcpi_ThermalZoneTemperature()[0].CurrentTemperature / 10 - 273.15
                return temperature
            else:
                # Linux
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp = int(f.read().strip()) / 1000
                return temp
        except Exception:
            return 60  # Valor por defecto

    def get_cpu_usage(self):
        return psutil.cpu_percent(interval=1)

    def get_optimal_thread_count(self):
        return max(1, self.threads)

    def adjust_performance(self):
        current_time = time.time()
        if current_time - self.last_adjustment < 30:  # Ajustar cada 30s
            return

        self.last_adjustment = current_time
        temp = self.get_cpu_temperature()
        usage = self.get_cpu_usage()

        if temp > self.max_temperature:
            self.threads = max(1, self.threads - 1)
            print(f"Thermal throttling! Reducing threads to {self.threads}")
        elif usage > self.max_usage:
            self.threads = max(1, self.threads - 1)
            print(f"High CPU usage! Reducing threads to {self.threads}")
        elif usage < 50 and self.threads < psutil.cpu_count(logical=False):
            self.threads += 1
            print(f"Low CPU usage. Increasing threads to {self.threads}")

        # Aplicar optimizaciones AVX si están disponibles
        if self.enable_avx:
            enable_avx_optimizations()

import cpuinfo
import os


def enable_avx_optimizations():
    cpu_info = cpuinfo.get_cpu_info()
    flags = cpu_info['flags']

    if 'avx2' in flags:
        os.environ['RANDOMX_FORCE_AVX2'] = '1'
        print("AVX2 optimizations enabled")
    elif 'avx' in flags:
        os.environ['RANDOMX_FORCE_AVX'] = '1'
        print("AVX optimizations enabled")
    elif 'aes' in flags:
        os.environ['RANDOMX_FORCE_AES'] = '1'
        print("AES optimizations enabled")

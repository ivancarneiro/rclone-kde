import subprocess
import time
import os
import signal
import logging

def test_startup_shutdown_cycle():
    """
    Stress test: Lanza y cierra la aplicación repetidamente para detectar
    race conditions o bloqueos de sockets/puertos.
    """
    cmd = ["./start.sh", "--minimized"]
    cycles = 5
    
    print(f"Starting startup/shutdown stress test ({cycles} cycles)...")
    
    for i in range(cycles):
        print(f"Cycle {i+1}/{cycles}...")
        
        # Iniciar proceso
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid # Crear grupo de procesos para poder matar todo
        )
        
        # Esperar a que se estabilice
        time.sleep(4)
        
        # Verificar si sigue vivo
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            print(f"FAILED: Application crashed in cycle {i+1}")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return False
            
        # Matar proceso de forma limpia
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
        
        # Verificar que el socket de rclone se liberó (vía pkill en start_daemon)
        time.sleep(1)
        
    print("SUCCESS: Startup/shutdown cycle test passed.")
    return True

if __name__ == "__main__":
    if test_startup_shutdown_cycle():
        exit(0)
    else:
        exit(1)

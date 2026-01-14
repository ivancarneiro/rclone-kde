import sys
import os
import subprocess
import time
import logging

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from core.config import Config

logging.basicConfig(level=logging.INFO)

def test_rclone_integration():
    print(f"--- Rclone KDE Diagnostic ---")
    print(f"Config Path: {Config.RCLONE_CONF}")
    
    if not os.path.exists(Config.RCLONE_CONF):
        print("ERROR: Config file does not exist!")
        return

    # Check content briefly
    with open(Config.RCLONE_CONF, 'r') as f:
        head = f.read(100)
        print(f"Config Header: {head}...")

    rc_user = Config.RC_USER
    rc_pass = Config.get_rc_pass()
    rc_port = "5575" # Use different port to avoid conflict with running app
    rc_addr = f"localhost:{rc_port}"
    
    cmd = [
        "rclone", "rcd",
        f"--rc-addr={rc_addr}",
        f"--rc-user={rc_user}",
        f"--rc-pass={rc_pass}",
        f"--config={Config.RCLONE_CONF}",
        "-vv" # Verbose
    ]
    
    print(f"Launching Daemon: {' '.join(cmd)}")
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    try:
        # Give it time to start
        time.sleep(2)
        
        # Check if running
        if proc.poll() is not None:
             print(f"DAEMON DIED EARLY! LC: {proc.returncode}")
             print(proc.stdout.read())
             return

        # Try to connect
        url = f"http://{rc_addr}/config/listremotes"
        print(f"Querying: {url}")
        
        # Requests replacement
        import urllib.request
        import base64
        import json
        
        req = urllib.request.Request(url, method="POST")
        req.add_header('Content-Type', 'application/json')
        
        # Auth
        auth_str = f"{rc_user}:{rc_pass}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        req.add_header("Authorization", f"Basic {b64_auth}")
        
        data = "{}".encode('utf-8')
        
        with urllib.request.urlopen(req, data=data) as f:
             print(f"Status Code: {f.getcode()}")
             print(f"Response: {f.read().decode('utf-8')}")
        
    except Exception as e:
        print(f"EXCEPTION: {e}")
        
    finally:
        print("Killing Daemon...")
        proc.terminate()
        proc.wait()
        # Print output
        # output, _ = proc.communicate(timeout=1)
        # print("Daemon Output:")
        # print(output)

if __name__ == "__main__":
    test_rclone_integration()

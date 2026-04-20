import os
import sys
import time
import subprocess
import argparse
import signal
import numpy as np
import sounddevice as sd

# Configuration
MIN_THRESHOLD = 0.08    # Minimum absolute threshold
DYNAMIC_MULT = 2.0      # Trigger must be 2x the background noise floor
CREST_FACTOR_MIN = 5.5  # More permissive for noisy environments
COOLDOWN = 0.7 
SAMPLERATE = 16000
BLOCKSIZE = 1024        # ~64ms blocks

# Double Clap Configuration
MIN_GAP = 0.1
MAX_GAP = 1.0

# Global State for Filtering
prev_data = np.zeros(BLOCKSIZE)
background_rms = 0.01   # Rolling noise floor
last_log_time = 0.0

# Path logic - relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")

# Global state
last_spike_time = 0.0
waiting_for_second = False

def is_friday_running():
    """Checks if Friday is already active using pgrep."""
    try:
        result = subprocess.run(["pgrep", "-f", "python.*main.py"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        my_pid = str(os.getpid())
        active_pids = [pid for pid in pids if pid != my_pid]
        return len(active_pids) > 0
    except Exception as e:
        print(f"[ClapDetector] Error checking Friday status: {e}")
        return False

def launch_friday():
    """Starts Friday in the background."""
    print("[ClapDetector] Triggering Friday launch via Double Clap!")
    
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    error_log_path = os.path.join(logs_dir, "clap_launch_error.log")
    
    try:
        with open(error_log_path, "a") as err_log:
            subprocess.Popen(
                [VENV_PYTHON, MAIN_PY], 
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=err_log,
                start_new_session=True
            )
    except Exception as e:
        print(f"[ClapDetector] Failed to launch Friday: {e}")

def audio_callback(indata, frames, time_info, status):
    global last_spike_time, waiting_for_second, prev_data, background_rms, last_log_time
    
    if status:
        return

    # 1. High-Pass Filter (Simple Difference)
    # This removes steady-state noise like low-frequency hum or music beats
    hpf_data = indata.flatten() - prev_data
    prev_data = indata.flatten().copy()

    # 2. Calculate RMS and Peak from HPF data
    rms = float(np.sqrt(np.mean(hpf_data**2)))
    peak = float(np.max(np.abs(hpf_data)))
    
    # Update Background RMS (Slow Lecher)
    # We track the noise floor to adapt to loud rooms/music
    background_rms = background_rms * 0.98 + rms * 0.02
    
    # Periodic Status Log (every 3 seconds)
    now = time.time()
    if now - last_log_time > 3.0:
        print(f"[ClapDetector] Floor: {background_rms:.4f} | RMS: {rms:.4f} | Target: {max(MIN_THRESHOLD, background_rms * DYNAMIC_MULT):.4f}")
        last_log_time = now

    if rms > 0.0001:
        crest = peak / rms
        
        # 3. Dynamic Trigger Condition
        # Must be above MIN_THRESHOLD AND significantly above the current noise floor
        target_threshold = max(MIN_THRESHOLD, background_rms * DYNAMIC_MULT)
        
        if rms > target_threshold and crest > CREST_FACTOR_MIN:
            dt = now - last_spike_time
            
            # Ignore if too close to the last detected spike (debouncing)
            if dt < MIN_GAP:
                return

            if not waiting_for_second:
                # This is the first spike
                print(f"[ClapDetector] !!! First clap detected (RMS={rms:.3f}, Floor={background_rms:.3f}). Waiting for second...")
                last_spike_time = now
                waiting_for_second = True
            else:
                # We are waiting for the second spike
                if dt <= MAX_GAP:
                    # RHYTHMIC DOUBLE CLAP DETECTED!
                    print(f"[ClapDetector] SUCCESS! Double clap confirmed. Gap: {dt:.2f}s. Launching...")
                    last_spike_time = now
                    waiting_for_second = False
                    
                    if not is_friday_running():
                        launch_friday()
                    else:
                        print("[ClapDetector] Friday already running.")
                else:
                    # Too long since the last spike
                    print(f"[ClapDetector] Gap too long ({dt:.2f}s). Starting new sequence.")
                    last_spike_time = now
                    waiting_for_second = True

def stop_existing():
    """Kills any running clap_detector.py or snap_detector.py instances except this one."""
    try:
        # Search for both naming conventions to handle orphaned processes
        result = subprocess.run(["pgrep", "-f", "python.*(clap|snap)_detector.py"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        my_pid = str(os.getpid())
        count = 0
        for pid in pids:
            if pid != my_pid:
                # Use SIGINT or SIGTERM to let it clean up if needed
                os.kill(int(pid), signal.SIGTERM)
                count += 1
        return count
    except Exception as e:
        print(f"Error stopping existing instances: {e}")
        return 0

def get_status():
    """Checks if another clap_detector.py or snap_detector.py is running."""
    try:
        result = subprocess.run(["pgrep", "-f", "python.*(clap|snap)_detector.py"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        my_pid = str(os.getpid())
        active_pids = [pid for pid in pids if pid != my_pid]
        return len(active_pids) > 0
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="FRIDAY Double Clap Detector")
    parser.add_argument("--stop", action="store_true", help="Stop any running clap detector instances.")
    parser.add_argument("--status", action="store_true", help="Check if the clap detector is running.")
    parser.add_argument("--start", action="store_true", help="Start the clap detector (default if no args).")
    args = parser.parse_args()

    if args.stop:
        count = stop_existing()
        if count > 0:
            print(f"Stopped {count} running clap detector(s).")
        else:
            print("No running clap detector found.")
        return

    if args.status:
        if get_status():
            print("Clap detector is RUNNING.")
        else:
            print("Clap detector is NOT running.")
        return

    # Normal startup
    if get_status():
        print("Clap detector is already running in another process.")
        sys.exit(0)

    print("====================================================")
    print("      FRIDAY Double Clap Detector (Robust)          ")
    print("====================================================")
    print(f"Monitoring... (Min Threshold: {MIN_THRESHOLD}, Gap: {MIN_GAP}-{MAX_GAP}s)")
    
    if not os.path.exists(VENV_PYTHON):
        print(f"Error: Virtual environment not found at {VENV_PYTHON}")
        sys.exit(1)

    try:
        with sd.InputStream(
            samplerate=SAMPLERATE,
            blocksize=BLOCKSIZE,
            channels=1,
            dtype='float32',
            callback=audio_callback
        ):
            print("Listener ACTIVE. Clap TWICE to start Friday.")
            while True:
                # Cleanup: if waiting for second clap too long, reset internally
                now = time.time()
                global waiting_for_second, last_spike_time
                if waiting_for_second and (now - last_spike_time > MAX_GAP):
                    waiting_for_second = False
                
                time.sleep(1) # Check state periodically
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Hardware Error: {e}")

if __name__ == "__main__":
    main()

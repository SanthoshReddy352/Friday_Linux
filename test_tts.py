import os
import sys
import subprocess

piper_dir = os.path.abspath("data/piper_runtime")
piper_exe = os.path.join(piper_dir, "piper.exe")
model_path = os.path.abspath("models/en_US-lessac-medium.onnx")

print("Piper exe exists:", os.path.exists(piper_exe))
print("Model exists:", os.path.exists(model_path))

text = "Hello, this is a test of the text to speech system."

piper_cmd = [
    piper_exe,
    "--model", model_path,
    "--output_raw"
]

sd_script = "import sys, sounddevice as sd; stream = sd.RawOutputStream(samplerate=22050, channels=1, dtype='int16'); stream.start(); [stream.write(chunk) for chunk in iter(lambda: sys.stdin.buffer.read(4096), b'')]; stream.stop(); stream.close()"

playback_cmd = [sys.executable, "-c", sd_script]

print("Starting piper:", piper_cmd)
piper_proc = subprocess.Popen(
    piper_cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
)

print("Starting playback:", playback_cmd)
playback_proc = subprocess.Popen(
    playback_cmd,
    stdin=piper_proc.stdout,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
)

piper_proc.stdin.write(text.encode('utf-8'))
piper_proc.stdin.close()

playback_out, playback_err = playback_proc.communicate()
piper_out, piper_err = piper_proc.communicate()

print("Piper returned:", piper_proc.returncode)
print("Piper stderr:", piper_err.decode('utf-8'))
print("Playback returned:", playback_proc.returncode)
print("Playback stderr:", playback_err.decode('utf-8', errors='ignore'))

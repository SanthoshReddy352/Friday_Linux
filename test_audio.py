import sounddevice as sd
import numpy as np

print("Default output device:", sd.default.device[1])
devices = sd.query_devices()
for i, d in enumerate(devices):
    if d['max_output_channels'] > 0:
        print(f"[{i}] {d['name']}")

print("Playing a test tone on the default device...")
samplerate = 22050
duration = 2.0
t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)
audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz A4 tone

sd.play(audio, samplerate=samplerate)
sd.wait()
print("Test tone finished.")

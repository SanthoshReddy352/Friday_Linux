import os
import sys
import tempfile
from core.app import FridayApp
from modules.voice_io.tts import TextToSpeech

def test():
    print("Testing TTS initialization...")
    tts = TextToSpeech(None)
    
    print(f"Project Root: {tts.project_root}")
    print(f"Piper Dir (src): {tts._source_piper_dir}")
    print(f"Runtime Dir: {tts._runtime_dir}")
    print("Model path:", tts.model_path, "Exists:", os.path.exists(tts.model_path))
    
    prepared = tts._prepare_runtime()
    print("Runtime prepared:", prepared)
    print("Piper path:", tts.piper_path, "Exists:", os.path.exists(tts.piper_path))
    
    print("Trying to speak...")
    tts.speak_chunked("Hello, this is a test of the text to speech system.")
    
    import time
    time.sleep(5)
    print("Done")

if __name__ == "__main__":
    test()

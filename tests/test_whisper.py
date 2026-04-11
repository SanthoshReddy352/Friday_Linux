from faster_whisper import WhisperModel
import time

def test_whisper():
    print("Loading faster-whisper base.en model... this will download the model if not cached.")
    start = time.time()
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    end = time.time()
    print(f"Model loaded successfully in {end - start:.2f} seconds!")
    print("Whisper setup looks good.")

if __name__ == "__main__":
    test_whisper()

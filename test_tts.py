import time
from modules.voice_io.tts import TextToSpeech
from modules.voice_io.stt import STTEngine
from core.logger import logger

tts = TextToSpeech(None)
tts.warm_up()
tts.speak_chunked("Hello world, this is a test.")
time.sleep(3)
print("Finished!")

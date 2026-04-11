from huggingface_hub import hf_hub_download
from llama_cpp import Llama
import time
import shutil

def test_llama():
    print("Downloading/Locating Gemma 2 2B GGUF model...")
    model_path = hf_hub_download(
        repo_id="bartowski/gemma-2-2b-it-GGUF",
        filename="gemma-2-2b-it-Q4_K_M.gguf"
    )
    print(f"Downloaded Model Path: {model_path}")
    
    target_path = "/mnt/NewVolume/FRIDAY/models/gemma-2b-it.gguf"
    print(f"Copying model to {target_path} ...")
    shutil.copy(model_path, target_path)
    print("Loading Llama model...")
    
    llm = Llama(model_path=target_path, n_ctx=2048, verbose=False)
    
    prompt = "User said: 'can you open the browser'. Determine intent and respond ONLY with JSON. Example: {\"intent\": \"open_app\", \"args\": {\"app\": \"browser\"}}"
    
    print("Inference starting...")
    start = time.time()
    response = llm(prompt, max_tokens=100)
    end = time.time()
    
    print(f"Inference Time: {end - start:.2f}s")
    print("Response:")
    print(response['choices'][0]['text'])

if __name__ == "__main__":
    test_llama()

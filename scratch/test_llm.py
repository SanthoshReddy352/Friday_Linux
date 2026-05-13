import sys
sys.path.append("/home/tricky/Friday_Linux")
from llama_cpp import Llama

llm = Llama(
    model_path="/home/tricky/Friday_Linux/models/mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf",
    n_ctx=2048,
    verbose=False
)

prompt = "Based on the conversation, write a 1-sentence greeting. Conversation: user: what is the time? assistant: 10:35 AM."

response = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": "You are FRIDAY. DO NOT output <think> tags. DO NOT explain your reasoning. Just output the greeting directly."},
        {"role": "user", "content": prompt}
    ],
    max_tokens=50,
    temperature=0.7
)
print(repr(response["choices"][0]["message"]["content"]))

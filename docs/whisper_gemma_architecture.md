# Architecture Document: Local Voice & Intent Recognition Pipeline

## 1. Overview
The current FRIDAY AI assistant relies on standard text matching, fuzzy string matching, or regex parsing to extract intent from user commands. To make the assistant more robust, natural, and intelligent, the architecture is being updated to use a completely local AI pipeline:
1. **Speech-to-Text (STT/ASR)**: OpenAI's Whisper model (base tier).
2. **Intent Recognition / Function Calling**: Google's Gemma model (Low Parameter, e.g., 2B or 7B).

This decoupled architecture translates raw audio to text, and then uses semantic understanding to map that text to executable Python functions (e.g., `open_application`).

---

## 2. Component Details

### 2.1 Whisper (Speech to Text)
Instead of using the default OpenAI Whisper library which is not optimized for real-time latency, we will utilize **`faster-whisper`**. 
* **Backend**: CTranslate2
* **Model Size**: `base.en` or `base`
* **Purpose**: Quickly and accurately transcribe user audio into raw text strings, handling accents and minor background noise effectively.

### 2.2 Gemma (Intent & Argument Extraction)
A local Small Language Model (SLM) replaces brittle regex logic. 
* **Engine**: `llama-cpp-python` (embedded directly within the Python application, avoiding network overhead).
* **Model Size**: Gemma 2B Instruct, utilizing quantized weights (.gguf) to run smoothly on most consumer hardware with minimal RAM/VRAM footprint (~2-3 GB).
* **Purpose**: Parse transcribed text, identify the user's goal, and extract necessary arguments. 
* **Output Format**: Restricted to output valid JSON for seamless integration with Python tool execution.

---

## 3. Pros and Cons

### Pros
* **Absolute Privacy**: All voice data and processing remain completely local. No internet connection is required, and no API keys are needed.
* **Semantic Robustness**: Traditional regex fails if the user deviates from a script (e.g., "Can you fire up Chrome?" vs "Open Chrome"). Gemma naturally understands context and intent variations.
* **Cost Free**: Eliminates the need for paid cloud-based STT or LLM APIs.
* **Modularity**: The pipeline is strictly divided into transcription, intent parsing, and execution. Components can be swapped easily in the future.

### Cons
* **Hardware Dependent**: Requires a moderate CPU/GPU to run quickly. Without optimization, inferencing an LLM can spike system resources.
* **Latency Overhead**: Running sequential models (Whisper transcribing, then waiting for Gemma to infer) introduces higher latency than cloud solutions or simple regex matching.
* **Hallucinations**: Generative models can occasionally hallucinate incorrect tools or arguments if the prompt is not strict enough.

---

## 4. Key Lookouts and Challenges

* **JSON Formatting Constraints**: LLMs are conversational by nature. It is imperative to enforce "JSON Mode" or grammar-based constraints (supported natively in `llama-cpp-python`) or use strict system prompts to prevent Gemma from outputting conversational filler (e.g., "Sure, here's the parsed JSON: {...}").
* **Audio Silence & Turn-Taking**: To minimize latency, Voice Activity Detection (VAD) (like Silero VAD) should be used to precisely crop audio. Whisper shouldn't process seconds of dead silence. Furthermore, the microphone must be muted while the text-to-speech (TTS) is speaking to prevent the assistant from transcribing its own voice (echo loops).
* **Memory Management**: Keep both models loaded into memory (RAM/VRAM) simultaneously. Loading the model from disk per-query will cause massive delays (5-10 seconds).

---

## 5. Implementation Plan

### Phase 1: Pipeline Setup & Testing
* [ ] Install `faster-whisper` and replace current STT logic. Measure transcription latency on the local hardware.
* [ ] Install `llama-cpp-python` and download a quantized `.gguf` file of the `gemma-2b-it` model.
* [ ] Create sandbox Python scripts to test Whisper transcription and `llama-cpp-python` intent generation separately.

### Phase 2: Intent Engineering
* [ ] Define a standard JSON schema for function execution (e.g., `{"intent": "tool_name", "args": {"arg1": "value"}}`).
* [ ] Craft an optimized System Prompt for Gemma to force strict classification into available FRIDAY tools (e.g., `open_app`, `system_status`).
* [ ] Test complex and fuzzy phrasing to ensure Gemma handles edge cases better than the previous regex system.

### Phase 3: Integration into FRIDAY
* [ ] Connect the microphone input stream to `faster-whisper`.
* [ ] Route the returned text string to the local Gemma instance.
* [ ] Parse the returned JSON object in the central logic layer and route it to the specific execution modules (e.g., system ops, web search).
* [ ] Implement Voice Activity Detection (VAD) pre-processing to speed up the Whisper inference by removing silence padding.

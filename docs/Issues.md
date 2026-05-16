# **ROLE AND CONTEXT**

You are an Elite AI Systems Architect and Principal Engineer specializing in local-first, privacy-respecting, edge-deployed artificial intelligence. You are helping me completely refactor, harden, and elevate **FRIDAY**, a voice-first AI desktop assistant.

FRIDAY operates under incredibly strict hardware and architectural constraints. It relies purely on local CPU inference (utilizing models like Qwen3 1.7B/4B via Llama.cpp quantized to Q4\_K\_M) and operates on consumer-grade hardware (e.g., an Intel i5 12th Gen processor with 16GB of shared RAM and integrated graphics). Because it is a voice-first assistant, **conversational responsiveness and latency are our highest priorities.** A highly intelligent response that takes 15 seconds to generate is considered a failure; a slightly less complex but instant response is a success.

To achieve this, FRIDAY currently features a hybrid deterministic routing layer (fast-path) alongside LLM semantic fallbacks (deep-path) to save compute.

Recently, I ran a rigorous end-to-end execution test on main.py using my manual testing guide. The resulting logs revealed significant brittleness in our intent routing, massive context-bleed between multi-turn workflows, and critical failures in dictation and state management. Furthermore, the current Web Research Agent (which relies on local SearXNG instances) is failing entirely, timing out, and needs a complete architectural overhaul.

I need you to deeply analyze the provided logs and the 14 categorized issues below. Once you have absorbed this context, you must execute 4 Deep-Dive Research Tasks. Your final output will be a flawless, latency-aware implementation plan for the next major version of FRIDAY.

# **PART 1: THE EXECUTION LOGS & SYSTEMIC ANOMALIES**

*(Note: The context of the logs provided below where FRIDAY boots up, successfully loads extensions, but immediately begins struggling with rigid intent matching, context bleed between active tools, and unstable multi-turn state management.)*

**Key Log Anomalies Observed & Their Implications:**

* **Vector store unavailable: No module named 'chromadb' (Environment Issue):** \* *Implication:* This isn't just a simple missing package; it represents a catastrophic failure of the RAG pipeline on boot. Without ChromaDB, FRIDAY degrades to a "stateless" or "lite" mode, entirely losing its ability to perform cross-document search, semantic memory recall, and contextual awareness.  
* **Keyword Misses (e.g., User says "set voice to manual", router expects "set voice mode to manual"):**  
  * *Implication:* The deterministic router is overly reliant on rigid, hardcoded regular expressions. A human user does not speak in exact regex patterns. Dropping a single modifier word ("mode") causes the system to either fail completely or drop into a slow LLM fallback, destroying the illusion of natural conversation.  
* **Voice Interruptions (e.g., User says "enough" or "wait" during TTS):**  
  * *Implication:* The barge-in detector correctly pauses the audio stream (stopping TTS), but the *underlying task, workflow, or intent engine does not die*. The system is left in a zombie state where the workflow thinks it is still executing, leading to blocked inference locks and corrupted subsequent turns.  
* **Context Bleed (e.g., User asks to save generated Python code to reverse.py, but FRIDAY saves it to a previously active file ideas.md):**  
  * *Implication:* The TurnContext or DialogState is retaining stale references. The system failed to recognize a context switch. It blindly applied a generic "save this" action to the last known working artifact instead of parsing the explicit new target (reverse.py) provided in the user's prompt.  
* **Tool Hijacking (e.g., User says "...next year is my promotion" and the word "next" triggers the browser media control to skip a YouTube video):**  
  * *Implication:* Over-eager deterministic routing. Global keyword listeners are intercepting conversational dialogue because they lack semantic boundary checks. The media control tool should only trigger when the user is explicitly commanding media (e.g., "skip track", "play next"), not when the word "next" appears in a conversational sentence.

# **PART 2: THE 14 IDENTIFIED ISSUES**

Please review these 14 issues I have categorized from my testing. Your subsequent research and engineering solutions must address every single one of these flaws holistically.

**Environment & Dependencies**

1. **Missing markitdown:** The library is missing unless the virtual environment is manually activated.  
   * **Action:** We need a foolproof bootstrapping mechanism. Update requirements.txt with all dependencies, ensure strict version locking, and perhaps design a boot-check script that guarantees the environment is perfectly configured before initializing the heavy AI models.

**Intent & Routing Brittleness**

2\. **Rigid Regex/Matching:** Querying "set voice to manual" failed because the word "mode" was missing. The assistant feels robotic and unnatural. We need semantic flexibility without the latency cost of a 4B LLM call.

7\. **Semantic Confusion:** "What's on my calendar" reads the day's events, but "list calendar events" reads the task *reminders*. This is a fundamental misalignment in the intent taxonomy. Tools are overlapping and stealing each other's triggers.

8\. **Typo Failure:** "create a calender evnet" falls back to chat mode due to spelling mistakes. A good assistant should understand the intent despite minor typos, phonetic misinterpretations from the STT (Speech-to-Text) engine, or grammatical errors.

9\. **Over-eager Deterministic Routing:** User said, "Friday remember that I work as a backend engineer... Next year is my promotion." The word "next" hijacked the YouTube browser automation and skipped the video.

11\. **Entity Extraction Failure:** "Schedule a meeting in 15 minutes" parsed the event title as "in 15 minutes" instead of recognizing "Meeting" as the title and "15 minutes" as the temporal delta. Our Named Entity Recognition (NER) is fundamentally broken.

**Voice & Audio Handling**

3\. **Barge-in Logic:** "enough", "wait", "stop", etc. are not handled well.

* **Action:** These semantic stop words must act as a global interrupt. They must kill the active task/workflow thread entirely, flush the TTS queue, release any acquired inference locks, and reset the conversation state to neutral.

**Multi-Turn Workflows & State Management**

4\. **File Creation Flow:** Needs a robust, unbreakable state machine. The exact logic flow must be:

* **State 1:** Trigger file creation. If name is missing \-\> Ask user for name. Wait for response.  
* **State 2:** Ask: "Created file X. Would you like me to write anything in it?"  
  * If user says "No" \-\> Terminate flow gracefully.  
  * If user says "Yes" \-\> Proceed to State 3\.  
* **State 3:** Ask: "Will you dictate the content, or should I generate it for you?"  
  * **If Dictate:** Start dictation loop \-\> User speaks \-\> User says trigger phrase "Friday Stop" \-\> Save content to file.  
  * **If Generate:** Ask for topic (if not already extracted from previous context) \-\> Generate content via LLM \-\> Save to file.  
* **Global Rule:** The user saying "Friday Cancel" at any point must immediately terminate the flow and clear the state.  
* **Post-creation:** "read it" or "open it" must resolve pronouns correctly to the newly created file.  
5. **File Edit Flow:** Remove the basic "append" command and implement a comprehensive "edit" state machine with sub-states (Add, Delete, Update).  
   * Require File Name. If missing, prompt for it.  
   * **Add:** Ask for topic \-\> Prompt for Dictate vs. Generate \-\> Append to the end of the file.  
   * **Delete:** Ask what to delete \-\> *Crucially*, the LLM must evaluate the content, locate the specific information, and selectively remove it without destroying the rest of the file.  
   * **Update:** Ask what to update \-\> Prompt for Dictate vs. Generate \-\> Find the relevant section and rewrite it seamlessly.  
   * **Global Rule:** User saying "Friday Cancel" terminates. "read it" / "open it" must work immediately after the edit.  
6. **Save Note Mismatch:** "Save note" is currently misaligned with the actual dictation mode workflow, leading to dead ends.  
7. **Dictation Follow-up:** After a dictation memo is successfully saved, asking "read it" or "open it" fails. The WorkingArtifact state context is dropping immediately after the file is written.  
8. **Context Bleed:** User generated a Python function, then asked "save that to a file called reverse.py". FRIDAY saved it to the previously active file ideas.md. The context manager failed to update the active file target.

**Missing/Broken Tools**

12\. **Calendar Updates:** Cancel event or Update event is completely broken/missing. We need full CRUD operations for calendar management.

13\. **Weather:** Implement a weather checking tool for specific areas. This must be fast and shouldn't require spinning up the entire browser automation suite if a simple API call will suffice.

# **PART 3: THE 4 RESEARCH QUESTS**

Before writing a single line of Python code, I need you to mentally execute the following 4 research tasks. Draw upon the latest architectures in the AI agent space. After completing the research, evaluate your findings against FRIDAY's strict local, low-latency, CPU-only constraints, and provide a concrete implementation plan.

### **Research Task 1: Modern Web Research Agents**

**Objective:** Replace the failing, slow SearXNG instances with a modern, high-quality, lightweight research agent.

* **Research Focus:** How do modern, new-age AI agents (like Perplexity or advanced open-source web surfers) deep-dive the web to collect information free of cost with near 100% accuracy? What are the best architectures for effective, deep research content generation without relying on expensive paid APIs (like Google Custom Search or Bing API)? How do they bypass simple anti-bot protections, extract main content cleanly (avoiding JS clutter), and synthesize answers without massive token overhead?  
* **Actionable Output:** Evaluate your research insights against the current FRIDAY codebase. Figure out the perfect, lightweight implementation plan for a robust Research Agent workflow that can run reliably on a local machine.

### **Research Task 2: Advanced Memory Management Architecture**

**Objective:** Make FRIDAY more aware, personal, natural, and human-like without blowing up the context window.

* **Research Focus:** How do high-performing proprietary models (Claude, ChatGPT, DeepSeek, Gemini, Kimi) manage their massive context windows and memory? Specifically, how do they partition multiple memory tiers (e.g., semantic facts, episodic past events, immediate session state, and long-term user profile)? How do they mathematically or programmatically know *when* and *why* to invoke a particular memory in a specific situation? Furthermore, how do they shrink, compress, or summarize the context window after a long session to prevent Out-Of-Memory (OOM) errors?  
* **Actionable Output:** Evaluate this research against FRIDAY's current local memory system. Design an improved memory storage and retrieval architecture (utilizing ChromaDB and local SQLite) that seamlessly injects context *only when needed*, preventing the local 4B model from being overwhelmed by token bloat.

### **Research Task 3: Flawless Tool Creation Framework**

**Objective:** Create a unified, error-proof framework for ground-level, highly modular tools.

* **Research Focus:** How do top-tier frameworks (like LangChain, AutoGen, or MCP) actually standardize tools for AI agents? Design a framework to create tools and register them to the LLM cleanly via JSON schemas. What are the absolute rules for creating flawless tools for AI agents (e.g., strict typing, detailed docstrings, error boundary handling, yielding intermediate progress)?  
* **Actionable Output:** Propose a strategy to break our current monolithic tools down to their broadest, simplest, atomic levels. They must be modular enough to be used repetitively in multi-tool workflows. The goal is to prevent LLM hallucination, handle unpredictable human behavior (like a user changing their mind mid-workflow), and ensure that if a tool fails, it fails gracefully and reports back to the LLM for self-correction.

### **Research Task 4: Function Gemma 270M Evaluation**

**Objective:** Solve the bottlenecks of intent-based tool calling failure, rigid regex, context bleed, and unpredictable typos (Issues 2, 8, 9, 11).

* **Research Focus:** Investigate the feasibility of using the tiny Function Gemma 270M (or a similarly small, specialized parameter model). How effectively can a model of this size be used purely for intent routing, semantic boundary detection, and argument extraction compared to our current regex-heavy approach or spinning up the full 4B model?  
* **Actionable Output:** Evaluate whether using a specialized 270M model will eliminate the current routing errors. Critically evaluate the VRAM/RAM overhead and latency impact of keeping this model loaded in memory versus spinning it up on demand. Remember: less latency is highly preferred to keep the assistant feeling natural. If the 270M model adds 3 seconds of routing delay, we must find a different approach.

# **PART 4: REQUIRED DELIVERABLES**

Please structure your final response exactly as follows:

1. **Research Synthesis:** A detailed, highly technical breakdown of your findings for Research Tasks 1 (Web Agents), 2 (Memory), 3 (Tool Frameworks), and 4 (Gemma 270M Router).  
2. **Architectural Evaluation & Strategy:** An assessment of how your research findings directly apply to FRIDAY's strict constraints (local CPU, low latency, no cloud reliance). Explain what we will adopt and what we must discard.  
3. **The Engineering Master Plan:** A step-by-step refactoring guide explicitly addressing all 14 issues, incorporating your research. This section MUST include specific pseudo-state transitions and logic flows for the complex interactive state machines required for Issues 4 (File Creation) and 5 (File Edit).  
4. **Code Architecture & Interfaces:** Provide the specific Python interface designs (using typing, Pydantic models, or abstract base classes) for:  
   * The new Tool & Capability Framework.  
   * The proposed Tiered Memory Architecture.  
   * The State Machine manager for multi-turn workflows.

Take a deep breath, think step-by-step as an elite engineer, and prioritize low-latency execution, deterministic reliability, and a natural, interruption-friendly human interaction model.
# **Architecting Local Autonomous Security Assistants: Adapting Frontier Planning Models for Qwen3-4B within the FRIDAY Framework**

## **A. Executive Summary**

The transition from cloud-dependent artificial intelligence to local, privacy-preserving autonomous systems requires a fundamental redesign of how operational tasks are planned and executed. Frontier models possess the parameter density to execute zero-shot orchestration across highly ambiguous toolsets, maintaining context over extended planning horizons. Small-parameter models, specifically the Qwen3-4B architecture—comprising 3.6 billion non-embedding parameters and utilizing grouped-query attention—require strict deterministic scaffolding to achieve comparable reliability. This report details a comprehensive architectural blueprint for upgrading the FRIDAY local assistant to orchestrate complex cybersecurity tasks within authorized lab environments.

The analysis indicates that granting a 4-billion parameter model raw shell access results in catastrophic failure cascades, syntax degradation, and severe security violations. To mitigate this, the architecture must transition from open-ended autonomous loops to deterministic, graph-compiled workflows. By integrating strict capability wrappers, logit-level grammar constraints, and topological directed acyclic graph (DAG) execution, small models can successfully direct complex workflows without succumbing to local optimization traps. The LLM's role is deliberately constrained to intent classification, semantic slot-filling, and DAG drafting, while all execution, validation, and safety gating are offloaded to deterministic Python runtimes. This document provides the exhaustive schemas, prompts, and memory architectures necessary to implement a mobile-controlled, mathematically constrained cybersecurity assistant capable of reliable operation on edge hardware.

## **B. How Frontier Models Plan Workflows**

Advanced artificial intelligence models employ various cognitive architectures to navigate multi-step tool usage. Understanding the internal mechanics, advantages, and failure modes of these paradigms is critical for identifying which mechanisms can be compressed and ported to local hardware environments.

| Planning Paradigm | Internal Mechanics and Problem Solved | Suitability for Small Local Models (Qwen3-4B) |
| :---- | :---- | :---- |
| **ReAct (Reasoning \+ Action)** | Interleaves internal logical deduction with external environment observation in a continuous, autoregressive loop. It solves the problem of hallucination by grounding next steps in real-time environmental feedback. | **Low.** Small models easily fall into local optimization traps, infinite loops, and context exhaustion due to repetitive prompt injection and noise accumulation. |
| **Plan-and-Execute** | A primary planner drafts a comprehensive sequential list of steps upfront. An executor processes them one by one, returning to the planner only if a step fails. This decouples strategy from execution, reducing the cognitive load required at each discrete step. | **Moderate.** Viable if the environment is highly static. However, it is brittle; if the first step fails, the entire sequence is invalidated, requiring expensive replanning. |
| **ReWOO (Reasoning Without Observation)** | Generates a complete plan with variable placeholders (e.g., \#E1) that are populated asynchronously during execution. It eliminates redundant token generation and enables parallel execution of independent tool calls. | **High.** Highly token-efficient. Small models can be fine-tuned or prompted to learn the placeholder syntax, delegating the complex variable resolution entirely to deterministic Python code. |
| **DAG Planning (Beyond ReAct)** | Models formulate a Directed Acyclic Graph where nodes are tools and edges are data dependencies. This resolves the "myopia" of linear planning, allowing for complex parallelization and topological execution. | **High.** When paired with a deterministic graph compiler, the LLM only outputs structured JSON dependencies, minimizing logical drift and error propagation. |
| **Hierarchical Task Networks (HTN)** | Recursively breaks down high-level objectives into sub-goals until atomic tool actions are reached. This manages massive complexity by isolating context windows strictly to the current sub-goal. | **Moderate.** Requires a robust deterministic orchestrator to manage the tree state. The LLM must be tightly constrained to output only child nodes without losing global context. |
| **Toolformer / Function Calling** | Native structural constraints injected during model training to output specific API calls. Solves the problem of natural language ambiguity in tool selection. | **High.** Qwen3-4B is explicitly fine-tuned for function calling and performs exceptionally well when schemas are constrained and flat. |
| **Tree-of-Thought / Graph-of-Thought** | Simulates multiple future trajectories, scores them via a value function, and selects the optimal path using Monte Carlo Tree Search (MCTS). Provides lookahead capabilities, preventing irreversible destructive actions. | **Very Low.** Computationally prohibitive for local hardware. Requires massive parallel inference and token budgets incompatible with mobile latency constraints. |
| **Reflection and Self-Correction** | Employs a secondary pass where the model acts as a critic to review and correct its own outputs before final execution. | **Low to Moderate.** Small models often lack the parameter depth to effectively critique their own logic, sometimes hallucinating errors where none exist, though they can parse deterministic error logs. |
| **Retrieval-Augmented Tool Selection** | Uses vector search to dynamically load only the relevant tool schemas into the context window, solving the problem of context bloat when dealing with hundreds of APIs. | **High.** Absolutely essential for small models to prevent schema bloat and attention degradation. |

For a local mobile-controlled assistant, the architecture cannot rely on continuous, autoregressive observation loops. The optimal synthesis for FRIDAY is a hybrid of **DAG Planning**, **ReWOO**, and **Retrieval-Augmented Tool Selection**. The model should draft a topological JSON map of tool nodes and data dependencies. The execution, variable passing, and environment observation must be handled entirely by deterministic code, approximating the advanced reasoning of frontier models through strict structural templates and state machines.

## **C. Adapting Frontier Planning for Local Qwen3-4B Architecture**

Models in the 4-billion parameter class exhibit specific limitations: they struggle to maintain strict JSON formats over long contexts, they hallucinate tool parameters when faced with complex schemas, and they lose track of global objectives during multi-turn interactions. To force Qwen3-4B to perform at a frontier level, the architecture must absorb the cognitive burden through practical, programmatic methods.

The implementation of **constrained JSON output** is non-negotiable. Standard prompt engineering yields failure rates of up to 20% on complex schemas. By implementing grammar-based sampling using engines like XGrammar or Outlines, the decoding process is mathematically constrained at the logit level. Before a token is selected, the grammar mask blocks any token that would violate the predefined JSON schema. This ensures that Qwen3-4B will never output trailing commas, missing brackets, or hallucinated keys, allowing the model's parameters to focus entirely on semantic accuracy.

Furthermore, **tool schema compression** is required. The official Model Context Protocol (MCP) tool schemas can consume tens of thousands of tokens, which overwhelms small context windows. By stripping verbose natural-language descriptions, enums, and nested type documentation, and retaining only function names and parameter keys, token costs can be reduced by up to 88%. This prevents the attention mechanism of Qwen3-4B from degrading over long sessions.

The architecture must enforce a strict **planner-verifier split**. When Qwen3-4B drafts a plan, it is treated as an untrusted proposal. A deterministic Pydantic validation layer intercepts the JSON payload, verifying type matching, missing required parameters, and edge compatibility in the DAG. If an error is detected, the validator deterministically repairs missing fields if possible, or generates a structured error prompt requesting the LLM to correct the specific missing slot, bypassing the need for a second LLM-based critic.

To circumvent weak long-horizon planning, the system must utilize **workflow templates** and **skill cards**. Instead of asking the model to deduce a complex network enumeration strategy zero-shot, the system retrieves a human-approved YAML template based on the user's intent. The model's task is reduced from "architect a penetration test" to "extract the IP address from the user's prompt and insert it into this pre-defined schema."

Finally, **chain-of-thought (CoT) leakage** must be managed. Qwen3-4B Instruct models are prone to generating \<think\> blocks, which can break JSON parsers. The architecture must separate the reasoning scratchpad from the final output. The system will prompt the model to output a reason\_summary field within the JSON, satisfying the model's autoregressive need to output logic without violating the JSON structure.

## **D. Deterministic Boundaries in Execution**

In cybersecurity contexts, LLM autonomy introduces severe risks, including prompt injection, confused-deputy vulnerabilities, and cascading execution failures. Therefore, the boundary between generative text and system execution must be strictly demarcated. The LLM must be treated purely as a semantic processor, never as an execution engine.

Raw shell command generation by the LLM is explicitly prohibited. The LLM (Qwen3-4B) is strictly restricted to intent classification, semantic slot-filling, DAG drafting, and observation summarization.

The deterministic FRIDAY system exclusively handles:

* **Schema Validation:** Rejecting any LLM payload that fails Pydantic type-checking, preventing malformed arguments from reaching the execution layer.  
* **Topological Compilation:** Assembling the DAG, resolving variable placeholders (e.g., passing the output of Node A as the input to Node B), and orchestrating parallel execution without further LLM intervention.  
* **Execution Gating:** Enforcing network-scope rules and evaluating side-effect thresholds. If a tool wrapper declares a public network scope in a lab context, the deterministic engine blocks execution regardless of the LLM's instructions.  
* **Command Construction:** Translating the validated JSON parameters into sanitized, shlex\-escaped shell strings.  
* **Terminal Output Parsing:** Converting noisy, unstructured terminal stdout into clean XML or JSON payloads before the LLM is allowed to observe the results.

## **E. Recommended FRIDAY Planning Architecture**

To integrate these concepts, the FRIDAY architecture must evolve from a linear sequential pipeline to a resilient, graph-compiled execution engine. The proposed workflow operates as follows:

1. **Ingestion and Deterministic Fast-Path:** The mobile client transmits a natural language command. The RouteScorer evaluates the request. If the command matches a heavily cached, read-only local action with a confidence \> 0.95, it bypasses the LLM and executes immediately.  
2. **Intent Classification and Memory Retrieval:** If the fast-path fails, the request is routed to Qwen3-4B for intent classification. Simultaneously, the MemoryBroker performs a vector search against the CapabilityRegistry and ContextStore to retrieve relevant tool schemas and past workflow templates (Skill Cards).  
3. **Workflow Selection vs. Generation:**  
   * *Template Match Found:* If the intent maps cleanly to a retrieved workflow template, the CapabilityBroker uses Qwen3-4B in Slot-Filling Mode. The model extracts parameters from the user's prompt to satisfy the template's required inputs.  
   * *No Template Match:* If the task is novel, the CapabilityBroker engages Qwen3-4B in DAG Drafting Mode, requesting a structured sequence of available capabilities.  
4. **Static Validation:** The PlanCompiler strictly validates the proposed JSON DAG against the tool registries. Any missing mandatory slots trigger the IntentRecognizer to send a deterministic clarification request to the mobile UI.  
5. **Safety and Consent Gating:** The PermissionService evaluates the compiled graph. If any node contains a write or critical side-effect, execution is paused. The ConsentService dispatches a structured approval payload to the mobile client.  
6. **Graph Execution:** Upon cryptographic approval from the mobile client, the GraphCompiler and WorkflowOrchestrator execute the DAG. Independent nodes execute in parallel. Tool outputs are captured deterministically.  
7. **Observation Replanning:** If a node returns a failure code, the ModelRouter invokes Qwen3-4B to interpret the structured error and propose a retry parameter adjustment, subject to a strict maximum retry limit managed by the orchestrator.

## **F. Kali Workflow Planning Architecture**

Kali Linux utilities present a highly complex, often dangerous parameter space. Exposing raw terminal access to an LLM results in syntax errors, hallucinated flags, and destructive system alterations. The architecture abstracts these utilities into structured Capability Wrappers.

The architecture relies on specialized context objects to maintain state and enforce boundaries:

* **Target Context Object:** A deterministic object defining the authorized scope, managed independently of the LLM (e.g., allowed\_subnets: \["192.168.1.0/24"\]).  
* **Safety Context Object:** Defines the operational mode, enforcing strict rules based on the environment (e.g., mode: CTF, mode: Lab\_Defense).  
* **Run Context Object:** An ephemeral state object holding variables passed between DAG nodes during execution, implementing the ReWOO placeholder resolution.

The LLM interacts exclusively with the Tool Registry, a JSON schema database representing the wrappers. When the LLM proposes a plan, it invokes the wrapper's name and provides JSON arguments. The wrapper, written in Python, maps these JSON arguments to validated command-line templates, ensuring that the LLM cannot inject arbitrary bash logic.

## **G. Safety and Permission Model**

Implementing offensive security tools via AI requires military-grade process isolation. The system must employ an "out-of-process policy enforcement" model, similar to NVIDIA OpenShell, where the LLM's environment is heavily restricted and cannot alter its own constraints.

| Security Control | Implementation Mechanism | Purpose |
| :---- | :---- | :---- |
| **Process Sandboxing** | Executing Kali wrappers inside transient Docker containers with dropped Linux capabilities (cap\_drop: ALL). | Prevents a hallucinated or injected command from escaping the container and escalating privileges to the host operating system. |
| **Network Egress Filtering** | Deterministic strict filtering ensuring the Target Context matches the destination IP at the network layer. | Prevents the agent from accidentally scanning public infrastructure or pivoting outside the authorized lab environment, regardless of the prompt. |
| **Parameter Sanitization** | Passing LLM-generated arguments strictly through Python's shlex.quote() before subprocess execution. | Neutralizes command injection vulnerabilities if the LLM attempts to append malicious shell operators (e.g., ; rm \-rf /). |
| **Authorization Boundaries** | Any capability marked side\_effect\_level: critical or requires\_authorization: true automatically suspends the execution graph. | Enforces human-in-the-loop control for any action that mutates state, ensuring no critical action occurs without explicit mobile confirmation. |

## **H. Tool/Capability Schema**

Every Kali tool must conform to a heavily restricted capability wrapper schema. This JSON schema is compressed before being injected into Qwen3-4B's context window.

JSON

{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "KaliCapabilityWrapper",  
  "type": "object",  
  "properties": {  
    "tool\_name": {   
      "type": "string",  
      "description": "Unique identifier for the tool."  
    },  
    "description": {   
      "type": "string",  
      "description": "Semantic description used for retrieval."  
    },  
    "allowed\_use\_cases": {   
      "type": "array",   
      "items": { "type": "string" }   
    },  
    "forbidden\_use\_cases": {   
      "type": "array",   
      "items": { "type": "string" }   
    },  
    "input\_schema": {   
      "type": "object",  
      "description": "JSON schema for the arguments the LLM must provide."  
    },  
    "output\_schema": {   
      "type": "object",  
      "description": "JSON schema defining the structured observation output."  
    },  
    "required\_permissions": {   
      "type": "array",   
      "items": { "type": "string" }   
    },  
    "side\_effect\_level": {   
      "enum": \["read", "write", "critical"\]   
    },  
    "network\_scope": {   
      "enum": \["local", "lab", "public", "unknown"\]   
    },  
    "requires\_authorization": {   
      "type": "boolean"   
    },  
    "command\_templates": {   
      "type": "string",  
      "description": "Internal Python template for shlex construction. Hidden from LLM."  
    },  
    "timeout\_seconds": {   
      "type": "integer"   
    },  
    "parser": {  
      "type": "string",  
      "description": "Reference to the Python function that parses stdout to JSON."  
    }  
  },  
  "required": \["tool\_name", "input\_schema", "side\_effect\_level", "network\_scope", "requires\_authorization", "parser"\]  
}

## **I. Workflow Schema**

Workflows must be represented as Directed Acyclic Graphs (DAGs). Unlike linear arrays, DAGs allow the definition of explicit data dependencies, enabling the GraphCompiler to execute non-dependent nodes in parallel.

### **IntentClassification**

JSON

{  
  "type": "object",  
  "properties": {  
    "intent\_type": { "enum": \["chat", "single\_tool", "workflow", "multi\_step", "clarify", "refuse"\] },  
    "domain": { "type": "string" },  
    "confidence": { "type": "number" },  
    "risk\_level": { "enum": \["low", "medium", "high", "critical"\] },  
    "requires\_authorization": { "type": "boolean" },  
    "missing\_slots": { "type": "array", "items": { "type": "string" } },  
    "reason\_summary": { "type": "string" }  
  },  
  "required": \["intent\_type", "domain", "confidence", "risk\_level"\]  
}

### **ToolPlan**

JSON

{  
  "type": "object",  
  "properties": {  
    "mode": { "enum": \["tool", "workflow", "clarify", "refuse", "chat"\] },  
    "steps": {  
      "type": "array",  
      "items": {  
        "type": "object",  
        "properties": {  
          "step\_id": { "type": "string" },  
          "capability": { "type": "string" },  
          "args": { "type": "object" },  
          "depends\_on": {   
            "type": "array",   
            "items": { "type": "string" }  
          },  
          "expected\_observation": { "type": "string" }  
        },  
        "required": \["step\_id", "capability", "args", "depends\_on"\]  
      }  
    },  
    "missing\_slots": { "type": "array", "items": { "type": "string" } },  
    "ask\_user": { "type": "string" },  
    "confidence": { "type": "number" }  
  },  
  "required": \["mode", "steps", "confidence"\]  
}

### **WorkflowPlan**

JSON

{  
  "type": "object",  
  "properties": {  
    "workflow\_name": { "type": "string" },  
    "target": { "type": "object" },  
    "state": { "enum": \["pending", "active", "completed", "cancelled", "blocked\_awaiting\_consent"\] },  
    "execution\_graph": { "type": "array" },  
    "completed\_nodes": { "type": "array" },  
    "node\_outputs": { "type": "object" }  
  }  
}

### **Observation**

JSON

{  
  "type": "object",  
  "properties": {  
    "step\_id": { "type": "string" },  
    "capability": { "type": "string" },  
    "status": { "enum": \["success", "failure", "partial", "timeout"\] },  
    "summary": { "type": "string" },  
    "structured\_data": { "type": "object" },  
    "errors": { "type": "array", "items": { "type": "string" } }  
  }  
}

### **ReplanDecision**

JSON

{  
  "type": "object",  
  "properties": {  
    "decision": { "enum": \["continue", "retry", "ask\_user", "stop", "escalate", "refuse"\] },  
    "next\_step\_id": { "type": "string" },  
    "updated\_args": { "type": "object" },  
    "question": { "type": "string" },  
    "reason\_summary": { "type": "string" },  
    "confidence": { "type": "number" }  
  },  
  "required": \["decision", "reason\_summary", "confidence"\]  
}

## **J. Prompt Templates for Qwen3-4B**

To extract optimal performance from Qwen3-4B, prompts must bypass the "thinking" traces to avoid JSON corruption, and enforce strict roles. The system utilizes grammar-based sampling, but the prompt structure remains critical for semantic accuracy.

**A. Intent Classification Prompt**

\<|im\_start|\>system

You are the routing engine for FRIDAY, a cybersecurity assistant.

Classify the user's intent, identify missing mandatory parameters, and format the output strictly as JSON matching the IntentClassification schema.

Do not provide internal logic. Do not provide markdown formatting outside the JSON block.

Policy: Refuse any request targeting public IPs outside the authorized scope.

\<|im\_end|\>

\<|im\_start|\>user

User Request: "Run a directory brute force on the test server."

Target Context: {"test\_server": "192.168.1.15"}

\<|im\_end|\>

\<|im\_start|\>assistant

**B. Workflow Selection Prompt**

\<|im\_start|\>system

Select the appropriate workflow template for the user's request from the retrieved list.

If a match is found, extract the necessary variables to fill the input slots.

Output strict JSON matching the ToolPlan schema with mode="workflow".

\<|im\_end|\>

\<|im\_start|\>user

Request: "Do a basic network inventory on my lab subnet."

Retrieved Workflows: \["lab\_network\_inventory", "web\_app\_recon"\]

\<|im\_end|\>

\<|im\_start|\>assistant

**D. Tool-Plan Generation Prompt**

\<|im\_start|\>system

You are the DAG planning engine for FRIDAY. Construct an acyclic graph of tool operations to satisfy the user's request.

Available Capabilities:

1. scan\_network\_ports(target\_ip: string)  
2. enumerate\_directories(target\_url: string, wordlist: string)

Rules:

* If a step requires the output of a previous step, add the previous step\_id to the depends\_on array.  
* Use variable injection formatted as ${step\_id.key} in the args object.  
* Output ONLY valid JSON matching the ToolPlan schema.  
* \<|im\_end|\>  
* \<|im\_start|\>user  
* Request: "Scan 192.168.1.50 for open ports, then run a dirbuster on any web ports found."  
* \<|im\_end|\>  
* \<|im\_start|\>assistant

**F. Observation Interpretation Prompt**

\<|im\_start|\>system

Interpret the structured observation from the executed tool.

Summarize the findings concisely for the final report. Identify any critical errors or security findings.

Output strict JSON.

\<|im\_end|\>

\<|im\_start|\>user

Observation Data: {"status": "success", "structured\_data": {"open\_ports": }}

\<|im\_end|\>

\<|im\_start|\>assistant

**G. Replanning Prompt**

\<|im\_start|\>system

The previous step in the execution graph failed.

Review the error observation and decide the next action based on the ReplanDecision schema.

You may adjust arguments, ask the user for clarification, or abort.

\<|im\_end|\>

\<|im\_start|\>user

Error Observation: {"status": "timeout", "errors": \["Host 192.168.1.99 did not respond to ping sweep."\]}

\<|im\_end|\>

\<|im\_start|\>assistant

## **K. Example Safe Workflow Templates**

Rather than forcing the LLM to generate complex attack chains zero-shot, FRIDAY relies on deterministic YAML templates for standard procedures. The LLM's only job is to map user intent to the template and fill the inputs.

**Template: Basic Network Inventory in Lab**

YAML

workflow\_id: lab\_network\_inventory  
description: "Scan an authorized lab subnet to identify live hosts and open services."  
preconditions:  
  \- check\_network\_scope: "lab\_only"  
permission\_checks:  
  requires\_human\_approval: true  
  risk\_level: low  
inputs:  
  \- name: target\_subnet  
    type: string  
    validation\_regex: "^192\\\\.168\\\\.\\\\d{1,3}\\\\.0/24$"  
steps:  
  \- step\_id: host\_discovery  
    capability: run\_nmap\_ping\_sweep  
    args:  
      target: "${inputs.target\_subnet}"  
  \- step\_id: service\_scan  
    capability: run\_nmap\_service\_scan  
    depends\_on: \["host\_discovery"\]  
    args:  
      target\_list: "${host\_discovery.live\_hosts}"  
output\_parsers:  
  \- format: markdown\_table  
    source: "${service\_scan.parsed\_json}"

**Template: Web App Reconnaissance**

YAML

workflow\_id: web\_app\_recon  
description: "Enumerate directories on a target web server."  
preconditions:  
  \- check\_network\_scope: "lab\_only"  
permission\_checks:  
  requires\_human\_approval: true  
  risk\_level: medium  
inputs:  
  \- name: target\_url  
    type: string  
steps:  
  \- step\_id: dir\_fuzz  
    capability: run\_gobuster\_dir  
    args:  
      url: "${inputs.target\_url}"  
      wordlist: "common.txt"  
output\_parsers:  
  \- format: json\_list  
    source: "${dir\_fuzz.discovered\_paths}"

## **L. Observation and Replanning Loop**

When a capability wrapper finishes executing, the raw standard output (stdout) is often highly unstructured. Passing raw stdout into a 4-billion parameter model rapidly degrades the context window and induces severe hallucinations.

Therefore, every capability wrapper must include a deterministic Python parser (e.g., using xml parsers for nmap \-oX or regex for gobuster) that converts the terminal output into structured JSON observations. The LLM only receives this refined JSON payload.

### **The Replanning State Machine**

If an observation returns failure or timeout, the WorkflowOrchestrator engages the Replanning Loop:

1. **Context Update:** The structured Observation JSON is appended to the Run Context.  
2. **Evaluation:** Qwen3-4B receives the error context and the original intent.  
3. **Threshold Check:** The Python orchestrator evaluates retry\_count. If retry\_count \> 3, the orchestrator deterministically aborts the workflow and notifies the mobile client, preventing infinite LLM loops.  
4. **Decision:** If within retry limits, the LLM outputs a ReplanDecision JSON. If it opts to retry, it provides updated\_args (e.g., increasing a timeout value or switching a wordlist). If it opts to ask\_user, execution halts, and a push notification is sent to the mobile client.

## **M. Mobile-Control Workflow**

To facilitate mobile control over complex Kali workflows, the user interface must prioritize transparency, asynchronous monitoring, and strict authorization gates.

| Mobile UI Component | Functional Description | Architecture Integration |
| :---- | :---- | :---- |
| **Task Input & Classification** | Natural language text input. Real-time indicator showing the LLM categorizing the intent and identifying missing slots. | Connects to IntentRecognizer. Displays the missing\_slots array as prompt bubbles if clarification is required. |
| **DAG Preview Panel** | A visual node-graph showing the proposed tool sequence before execution begins. | Renders the ToolPlan JSON. Allows the user to inspect arguments, dependencies, and expected side-effects. |
| **Authorization Gate** | A prominent "Approve / Modify Scope / Cancel" overlay for any task marked write or critical. | Intercepts the WorkflowOrchestrator via the ConsentService. Execution remains blocked until cryptographic confirmation is received. |
| **Live Execution Tracker** | A progress interface updating node statuses (Pending \-\> Active \-\> Success/Fail). | Listens to Server-Sent Events (SSE) emitted by the GraphCompiler as nodes complete and Observation objects are generated. |
| **Artifact Summary** | A clean, parsed presentation of the final vulnerability report, stripping out raw terminal noise. | Renders the output of the final output\_parsers stage defined in the workflow template. |

## **N. Memory and Procedural Learning Design**

For a system to evolve beyond stateless tool calling, it requires a cognitive architecture capable of retrieving successful past behaviors. Following the CoALA (Cognitive Architectures for Language Agents) taxonomy, FRIDAY implements a distinct separation between Semantic Memory (factual knowledge) and Procedural Memory (skills and workflows).

Procedural knowledge is stored as artifacts known as "Skill Cards". These represent successfully verified command structures and workflow templates.

1. **Storage:** Skill Cards are stored in a local vector database, embedded using a lightweight embedding model. They contain strict metadata including task context, training conditions, and usage history.  
2. **Retrieval:** When the user provides a command, the IntentRecognizer embeds the query and performs a cosine similarity search against the Skill Library to measure relevance.  
3. **Progressive Disclosure:** To preserve Qwen3-4B's limited context window, only the metadata and input\_schemas of the top-3 retrieved skills are injected into the prompt. The full execution logic remains externalized in the deterministic execution engine.  
4. **Learning Loop:** If a dynamically generated DAG executes successfully and results in a high-value observation, the MemoryBroker deterministically converts the DAG into a new Skill Card. It appends this to the library for future zero-shot retrieval, effectively allowing the system to learn and cache new workflows without model fine-tuning.

## **O. Implementation Roadmap**

To transition FRIDAY to this architecture effectively, development must proceed in strictly gated phases.

| Phase | Milestone | Technical Focus |
| :---- | :---- | :---- |
| **Phase 1: Tool Registry Hardening** | Establish deterministic capability wrappers. | Map nmap, gobuster, etc., into Python wrappers with JSON schema inputs, shlex sanitization, and output parsers. |
| **Phase 2: Workflow Template Registry** | Externalize logic into YAML. | Develop static YAML DAG templates for routine lab operations, bypassing the LLM entirely for known tasks. |
| **Phase 3: Qwen Planner JSON Prompts** | Implement grammar-constrained decoding. | Integrate XGrammar or Outlines to force Qwen3-4B to output strictly formatted ToolPlan and IntentClassification JSONs. |
| **Phase 4: Plan Validator** | Build the PlanCompiler. | Implement Pydantic validation to statically verify LLM-generated DAG edges and type constraints before execution. |
| **Phase 5: Observation Parser** | Standardize environment feedback. | Develop Python parsers to convert raw shell stdout into structured Observation JSONs for the LLM to process without hallucination. |
| **Phase 6: Replanning Loop** | Enable error recovery. | Implement the WorkflowOrchestrator state machine to feed Observation errors back into Qwen3-4B for bounded retries, enforcing retry limits. |
| **Phase 7: Mobile Approval UI** | Build the human-in-the-loop frontend. | Create the SSE pipeline for real-time DAG visualization, progress tracking, and critical authorization gates. |
| **Phase 8: Procedural Memory** | Enable continuous improvement. | Integrate the vector database to store successful DAGs as retrievable Skill Cards via cosine similarity. |

## **P. Risks and Mitigations**

Deploying a small-parameter model as a central routing engine carries specific operational risks that must be actively managed.

1. **Context Exhaustion:** Qwen3-4B's reasoning degrades rapidly when context windows fill with terminal noise.  
   * *Mitigation:* Implement strict schema compression and ensure raw stdout is never passed directly into the prompt. All terminal output must pass through deterministic XML/JSON parsers first.  
2. **Schema Hallucination:** Small models frequently invent non-existent parameters when attempting to satisfy complex requests.  
   * *Mitigation:* The PlanCompiler strictly enforces Pydantic schemas. Any unmapped parameter causes a deterministic rejection of the execution graph before it reaches the environment.  
3. **Confused Deputy Attacks:** The LLM might be tricked by malicious input (e.g., a poisoned hostname) into executing destructive commands.  
   * *Mitigation:* Out-of-process policy enforcement. The Python execution layer verifies network scope and strips shell metacharacters via shlex before binary execution, ensuring the LLM cannot override physical security boundaries.  
4. **Chain-of-Thought Leakage:** Qwen3-4B Instruct variants may output \<think\> blocks that break standard JSON parsers.  
   * *Mitigation:* Use regex-based post-processing to strip \<think\> tags before passing the payload to the JSON parser, or utilize strict grammar decoding (XGrammar) to suppress the tokens entirely during generation.

## **Q. Final Recommendation**

The attempt to make a 4-billion parameter model operate with the unbounded autonomy of a frontier cloud model will inevitably result in systemic instability. However, Qwen3-4B exhibits exceptional zero-shot classification and structured output capabilities when heavily constrained by its environment.

The ideal implementation for the FRIDAY architecture is to relegate the LLM strictly to the role of a semantic router and slot-filler, rather than an autonomous execution engine. By shifting the cognitive burden of multi-step planning into static YAML Workflow Templates, and enforcing all execution logic through a deterministic DAG compiler and Python-based Capability Wrappers, the system achieves maximum reliability. The LLM's primary value is translating ambiguous mobile-client natural language into precise JSON schemas. This architecture guarantees safety, minimizes latency on edge hardware, and ensures that complex cybersecurity tasks in local environments are executed with enterprise-grade predictability.


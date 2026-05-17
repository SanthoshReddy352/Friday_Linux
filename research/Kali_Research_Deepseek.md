# FRIDAY Planning Architecture: Adapting Frontier Workflow Planning to Qwen3-4B for Local Kali Linux Assistants

## A. Executive Summary

Frontier cloud models (GPT‑4, Claude, Gemini) use a combination of chain‑of‑thought reasoning, tool‑use function calling, retrieval‑augmented generation, and feedback loops to plan and execute complex multi‑tool workflows. Directly replicating these methods on a small local model like Qwen3‑4B is impractical due to limited context, lower reasoning depth, and unreliable JSON generation. However, by shifting the bulk of the planning burden to **deterministic registries, validated templates, and constrained LLM tasks**, we can build a reliable, safe, and mobile‑controlled assistant for cybersecurity lab work.

This report designs a complete architecture where Qwen3‑4B acts as an **intent classifier, workflow selector, slot‑filler, and observation summarizer**, never generating raw commands. All dangerous actions are gated by a **Capability Registry**, a **Workflow Template Registry**, and **deterministic validators**. The result is a system that feels intelligent but is actually a rigorous state machine with a small LLM as one of many components.

---

## B. How Frontier Models Plan Workflows

### 1. ReAct (Reasoning + Action + Observation)
- **Problem**: Iteratively decide what tool to call based on previous results.
- **How it works**: The model outputs `Thought: … Action: tool_call(…) Observation: …`. The loop runs until a final answer.
- **Suitability for local model**: Too much context grows quickly; Qwen3‑4B would get lost after 3‑4 turns. We can implement a deterministic observation parser and only call the LLM for the next “thought/plan” step, keeping the loop short.

### 2. Plan‑and‑Execute Agents
- **Problem**: Long‑horizon tasks require upfront decomposition.
- **How it works**: Model creates a full plan (list of steps), then executes them sequentially, optionally replanning.
- **Suitability**: Partial. Qwen3‑4B can draft a plan if constrained to known capabilities. We’ll use **templates** for common workflows and only ask the LLM to fill slots.

### 3. Hierarchical Task Decomposition
- **Problem**: Complex goals break into sub‑goals and primitive actions.
- **How it works**: High‑level task → sub‑tasks → tool calls. Often using HTN (Hierarchical Task Networks).
- **Suitability**: Excellent for deterministic design. We predefine high‑level workflows (e.g., “Lab network inventory”) that expand into ordered steps, reducing LLM responsibility.

### 4. Toolformer‑style Tool‑use Learning
- **Problem**: Model learns when to call tools by seeing API descriptions in training.
- **How it works**: The LLM’s training data includes tool‑use examples; it learns to emit structured calls.
- **Suitability**: Qwen3‑4B can do this with few‑shot prompts if tool schemas are heavily compressed.

### 5. Function Calling / Structured Tool Calls
- **Problem**: Reliably produce JSON that matches a tool’s input schema.
- **How it works**: The API enforces a specific JSON Schema; the model’s output is validated.
- **Suitability**: A local model needs strict JSON grammar (e.g., constrained decoding). We will use `llama.cpp` grammar or regex‑based post‑processing to guarantee valid JSON.

### 6. Chain‑of‑Thought (CoT) vs Hidden Reasoning
- **Problem**: Reasoning improves accuracy but leaks internal steps.
- **How it works**: CoT exposes the reasoning; hidden reasoning uses internal scratchpads.
- **Suitability**: We **forbid** CoT in the final JSON output to keep prompts clean; the model can use an internal `scratchpad` field not shown to the user.

### 7. Tree‑of‑Thought / Graph‑of‑Thought
- **Problem**: Explore multiple plan branches at once.
- **How it works**: Model maintains multiple reasoning paths, evaluating them.
- **Suitability**: Too expensive for a local 4B model. Use a deterministic BFS over known workflow templates instead.

### 8. Reflection and Self‑Correction
- **Problem**: Detect and fix errors in plans.
- **How it works**: A second pass critiques the output and regenerates.
- **Suitability**: We can implement a lightweight verifier that checks schema, required fields, and safety constraints; if invalid, ask Qwen to retry with error feedback (max 2 retries).

### 9. Critic / Verifier Models
- **Problem**: Separate the planner from the evaluator.
- **How it works**: One model plans, another (often larger) checks.
- **Suitability**: Use deterministic rules as the verifier—cheap and bulletproof.

### 10. Task Graphs and DAG Planning
- **Problem**: Steps have dependencies that aren’t purely linear.
- **How it works**: Represent the plan as a Directed Acyclic Graph.
- **Suitability**: For known workflows we pre‑compile DAGs into templates. For dynamic ones, the LLM outputs a dependency list and a deterministic GraphCompiler builds the DAG, validating cycles.

### 11. State Machines for Workflows
- **Problem**: Long‑running, multi‑turn interactions with user interrupts.
- **How it works**: The workflow is a finite state machine (states like `planning`, `awaiting_confirmation`, `executing`, `reporting`).
- **Suitability**: Perfect. FRIDAY’s WorkflowOrchestrator will run a state machine, with transitions triggered by events.

### 12. Memory‑Augmented Planning
- **Problem**: Remember successful plans and user preferences.
- **How it works**: Store plans in a vector DB; retrieve similar past tasks to guide planning.
- **Suitability**: We’ll add a procedural memory that stores **approved** workflows, using embeddings to find similar tasks and feeding them as few‑shot examples.

### 13. Retrieval‑Augmented Tool Selection
- **Problem**: The LLM doesn’t know all tools.
- **How it works**: Retrieve top‑k relevant tool descriptions and inject into prompt.
- **Suitability**: Very useful. Our CapabilityRegistry can be indexed; the IntentRecognizer uses embedding similarity to shortlist 5‑10 tools, which are then passed to the LLM.

### 14. Skill Libraries and Procedural Memory
- **Problem**: Reuse known sequences of actions.
- **How it works**: The system learns “skills” as parameterized templates.
- **Suitability**: This is our Workflow Template Registry. Users can save a new workflow after a successful run and it becomes a retrievable skill.

### 15. Agentic Planning with Observation Feedback
- **Problem**: Real‑world tool outputs are messy; the agent must decide what to do next.
- **How it works**: After each tool call, parse output into a structured Observation, then replan.
- **Suitability**: Our Observation Parser deterministically extracts key fields; the LLM only sees a minimal summary and decides the next step from a limited set of options.

---

## C. What Can Be Copied into a Local Qwen3‑4B Architecture

| Frontier Feature            | Adapted for Qwen3‑4B                                           |
|-----------------------------|----------------------------------------------------------------|
| Function calling            | Constrained JSON grammar, strict schema, post‑validation       |
| Plan‑and‑execute            | Workflow templates + LLM slot‑filling for dynamic steps        |
| RAG tool selection          | BM25/embedding retrieval of Capability Registry entries        |
| Few‑shot examples           | Dynamic prompt construction from memory and templates          |
| Reflection                  | Deterministic schema & safety validator, retry with error hints|
| Memory‑augmented planning   | Vector store of past successful plans used as few‑shots        |
| Chain‑of‑thought (hidden)   | Optional internal `scratchpad` field never shown to user       |
| State machine               | Deterministic WorkflowOrchestrator driving the whole process   |

**Key principle**: Qwen3‑4B is never asked to reason about the entire universe of tools—it only sees a heavily curated subset and must output structured JSON. All critical decisions (permissions, target scope, command generation) are done in code.

---

## D. What Should Remain Deterministic

- **Capability Registry**: Fixed list of wrapped Kali tools with all schemas.
- **Workflow Template Registry**: Approved multi‑step workflows.
- **Permission & Consent Service**: All `requires_authorization`, `side_effect_level`, `network_scope` checks.
- **Command Building**: Capability wrappers construct the actual shell command from validated arguments.
- **Output Parsing**: Structured observation extraction from tool stdout.
- **Safety Validation**: Blocklist on targets, flags, and use‑case mismatches.
- **Graph Compilation**: From steps with dependencies to a safe execution DAG.
- **Plan Validation**: Checks all slots filled, dependencies resolved, no cycles, all steps legal.
- **Execution Loop**: Ordered or graph execution with timeouts, retries, and cancellation.
- **Logging & Audit Trail**: Every action, request, decision.

---

## E. Recommended FRIDAY Planning Architecture

```
User Request → IntentRecognizer (embedding + LLM) 
→ Intent Classification
→ [if workflow] Workflow Selector (Retrieval + LLM) → Workflow Template
→ [if multi‑step] LLM drafts plan → Plan Validator
→ CapabilityBroker fills missing args (ask user if needed)
→ ConsentService & PermissionService check
→ Preview to mobile, await confirmation if needed
→ WorkflowOrchestrator state machine starts
→ CapabilityExecutor runs steps via OrderedToolExecutor / GraphCompiler
→ Observation Parser structures output
→ Replanner (deterministic rules + LLM if needed) decides next
→ Final report generated
```

- **IntentRecognizer**: Routes to `chat`, `single_tool`, `workflow`, `multi_step`, `clarify`, `refuse`. Uses embedding retrieval over capability descriptions + LLM classification prompt A.
- **RouteScorer**: Deterministic fallback for simple mappings (e.g., “nmap my laptop” → `network_scan` capability).
- **ModelRouter**: Invokes Qwen3‑4B only when needed (classification, slot filling, plan drafting, replan ambiguity).
- **WorkflowOrchestrator**: Implements a state machine with states: `initial`, `planning`, `awaiting_authorization`, `executing`, `reporting`, `completed`, `cancelled`.
- **MemoryBroker**: Stores conversation context, workflow state, and successful plans in ContextStore.
- **Procedural Memory**: Indexed vector store of past approved plans and their outcomes.

---

## F. Kali Workflow Planning Architecture

Kali tools are never exposed as raw shell commands. Each tool is wrapped in a **Capability** object that:

- Holds a set of **command templates** (e.g., `nmap -sS {target} -p {ports} -oA {output_name}`).
- Validates arguments against an input schema.
- Contains a deterministic **parser** that converts raw output into structured observations.
- Includes safety metadata: `side_effect_level`, `network_scope`, `forbidden_use_cases`, `required_permissions`.

### Tool Registry Schema

```json
{
  "tool_name": "network_scan_syn",
  "display_name": "Nmap SYN Scan",
  "description": "Perform a TCP SYN scan on specified targets",
  "allowed_use_cases": ["authorized_lab_scan", "CTF_recon", "self_audit"],
  "forbidden_use_cases": ["unauthorized_scan", "internet_wide_scan"],
  "input_schema": {
    "type": "object",
    "properties": {
      "target": {"type": "string", "format": "hostname_or_ip"},
      "ports": {"type": "string", "pattern": "^\\d{1,5}(-\\d{1,5})?(,\\d{1,5})*$"},
      "timing_template": {"enum": ["T0","T1","T2","T3","T4","T5"]},
      "additional_flags": {"type": "string", "pattern": "^[-a-zA-Z0-9 ]*$"}
    },
    "required": ["target"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "open_ports": {"type": "array", "items": {"port": "int", "service": "string", "version": "string"}},
      "host_status": "string",
      "raw_scan_time": "string"
    }
  },
  "required_permissions": ["network_scan"],
  "side_effect_level": "read",  // read | write | critical
  "network_scope": "lab",       // local | lab | public | unknown
  "requires_authorization": true,
  "command_templates": [
    "nmap -sS {target} -p {ports} --min-rate {rate} -oN {output_file}",
    "nmap -sS {target} -p- -T4 -oA {output_name}"
  ],
  "argument_constraints": {
    "target": {"regex": "^(10\\.|172\\.(1[6-9]|2[0-9]|3[0-1])\\.|192\\.168\\.|lab-.*|ctf-.*)", "block_public_ip": true},
    "ports": {"max_range": "1-65535", "block_unsafe_flags": ["--script", "-O"]}
  },
  "timeout": 120,
  "parser": "parse_nmap_syn_output",
  "success_conditions": "host_status == 'up' and open_ports not empty",
  "failure_conditions": "timeout or host_down",
  "next_step_hints": ["enumerate_service_version", "vulnerability_scan"],
  "rollback_or_cleanup": "remove temporary output files",
  "logging_requirements": {"log_command": true, "log_output_summary": true}
}
```

---

## G. Safety and Permission Model

Every action passes through:

1. **Intent Classification** → risk_level computed.
2. **Target Scope Verification**: IP ranges must be in lab/CTF ranges; domain must be owned or authorized. The system maintains a `TargetContext` with an authorization token.
3. **Capability Permission**: user must have the required `permission` (e.g., `network_scan`).
4. **Side Effect Check**: `critical` actions always require explicit user consent; `write` actions may need confirmation.
5. **Network Scope Check**: `public` scope is blocked unless the user explicitly authorized a target with a signed waiver.
6. **Dynamic Argument Blocking**: The validator blocks dangerous flags (e.g., `--script` in nmap unless explicitly whitelisted for a specific capability mode).
7. **Human Approval**: For any step with `requires_authorization: true`, the mobile UI shows a plan preview and awaits confirmation before execution.

The `SafetyContext` object is attached to every run:

```json
{
  "run_id": "uuid",
  "user_id": "alice",
  "target_scope": {
    "ips": ["192.168.1.1/24"],
    "domains": ["lab.local"],
    "authorization_proof": "signed_lab_policy"
  },
  "risk_level": "medium",
  "permissions_granted": ["network_scan", "file_read"],
  "denied_flags": ["--script", "--osscan-guess"],
  "consent_token": "tok_abc123"
}
```

---

## H. Tool/Capability Schema (Full)

As already detailed, every capability includes all fields listed. The CapabilityRegistry is a dictionary keyed by `tool_name`, loaded at startup.

For Kali, a curated set might include:

- `network_scan_syn`
- `network_scan_udp`
- `service_version_scan`
- `web_directory_bruteforce` (gobuster)
- `dns_enum` (dig)
- `dns_zone_transfer` (dig axfr)
- `vulnerability_scan_basic` (nmap NSE safe scripts only)
- `hash_identification` (hash‑id)
- `password_audit_offline` (john)
- `report_generator` (markdown template)
- `evidence_collector` (cp, sha256sum)
- `cleanup_temp_files`

Each one has strict `allowed_use_cases` and `forbidden_use_cases`.

---

## I. Workflow Schema

A **Workflow Template** defines a reusable multi‑step plan.

```json
{
  "workflow_name": "lab_network_inventory",
  "display_name": "Basic Lab Network Inventory",
  "description": "Scan lab subnet for live hosts, then service scan on found hosts.",
  "required_inputs": ["target_subnet"],
  "optional_inputs": ["scan_speed", "port_range"],
  "preconditions": {
    "target_subnet": "must be in authorized lab range",
    "user_permissions": ["network_scan"]
  },
  "permission_checks": ["network_scan"],
  "stop_conditions": ["user_cancellation", "timeout", "unauthorized_target_detected"],
  "report_requirements": {
    "format": "markdown",
    "sections": ["host_summary", "open_ports_per_host", "services_found"]
  },
  "steps": [
    {
      "step_id": "1",
      "capability": "network_scan_syn",
      "mode": "syn_ping_sweep",
      "args": {"target": "{target_subnet}", "ports": "{port_range}"},
      "depends_on": [],
      "requires_confirmation": false,
      "side_effect_level": "read",
      "expected_observation": "list of live hosts"
    },
    {
      "step_id": "2",
      "capability": "service_version_scan",
      "mode": "quick_scan",
      "args": {"target": "{{ step.1.output.live_hosts }}"},
      "depends_on": ["1"],
      "requires_confirmation": false,
      "side_effect_level": "read"
    },
    {
      "step_id": "3",
      "capability": "report_generator",
      "mode": "markdown",
      "args": {
        "hosts_data": "{{ step.2.output }}",
        "template": "network_inventory_report"
      },
      "depends_on": ["2"],
      "requires_confirmation": false,
      "side_effect_level": "write",
      "requires_authorization": true
    }
  ]
}
```

Templates are stored in a `WorkflowRegistry`. The LLM picks the best match based on intent and filled slots, or a dynamic plan is created if no template matches.

---

## J. Prompt Templates for Qwen3‑4B

All prompts are **strict JSON output** using a constrained grammar. The system injects only the top‑5 relevant capabilities (compressed descriptions). No chain‑of‑thought in the output; optional `reason_summary` limited to one short sentence.

### A. Intent Classification Prompt

```text
You are FRIDAY intent classifier. Classify the user request into one of:
- chat
- single_tool
- workflow
- multi_step
- clarify
- refuse

Available domains: network_scan, web_enum, dns_enum, vulnerability_scan, password_audit, report, evidence, cleanup.
You have these capabilities: {capabilities_summary}

Rules:
- If request is clearly malicious or asks to exploit unauthorized targets, classify as refuse.
- If missing critical info (target, scope), mark clarify and list missing_slots.
- Risk_level: low (read-only, safe), medium (write/report), high (scanning multiple hosts), critical (password cracking, internet target).

Output JSON only:
{
  "intent_type": "...",
  "domain": "...",
  "confidence": 0.85,
  "risk_level": "...",
  "requires_authorization": true/false,
  "missing_slots": ["target", "ports"],
  "reason_summary": "Short non-CoT explanation"
}
```

### B. Workflow Selection Prompt

Given the intent is `workflow`, retrieve top‑3 matching templates and show their summaries.

```text
You are FRIDAY workflow selector. Given the user request and these possible workflows:
{workflow_list}

Choose the best matching workflow or answer "none". Fill slot values from user request.
Output:
{
  "workflow_name": "...",
  "confidence": 0.9,
  "slot_values": {"target_subnet": "192.168.1.0/24"},
  "missing_slots": [],
  "reason_summary": "..."
}
```

### C. Slot‑Filling Prompt

When a template is selected but slots are missing, ask the user a precise question.

```text
You are FRIDAY. To complete the workflow "{workflow_name}", the following information is still needed: {missing_slots}.
Generate a single, clear question to ask the user.
Output JSON:
{
  "question": "What is the target subnet or IP range for the scan?",
  "missing_slot": "target_subnet"
}
```

### D. Tool‑Plan Generation Prompt (dynamic multi‑step)

For requests that don’t match a template, generate a plan using only the provided capabilities.

```text
You are a planner. Create a step‑by‑step plan to fulfill the user request using only the listed capabilities.
Capabilities available:
{capabilities_details}

Guidelines:
- Dependencies: if a step uses output of previous step, list in depends_on.
- Only mark requires_confirmation true for write/critical actions.
- If you cannot complete the task, output mode "clarify" or "refuse".
- Do NOT generate raw shell commands; use capability names and mode.

Output JSON:
{
  "mode": "tool | workflow | clarify | refuse | chat",
  "steps": [ ... ],  // same ToolPlan structure
  "missing_slots": [],
  "ask_user": "",
  "safety_notes": [],
  "confidence": 0.75
}
```

### E. Plan Validation Prompt (not for LLM, deterministic)

Actually, validation is code. But we can have a small prompt to detect obvious semantic errors: “Does step 3 depend on step 2’s output that isn’t produced?” but we’ll trust the deterministic check.

### F. Observation Interpretation Prompt

When a step completes, we have structured observation; we ask the model only if we need to decide between ambiguous outcomes.

```text
Given the execution of "{capability}" on target {target}, the result was:
{observation_summary}

Success condition: {success_condition}
Actual status: {status}
Should we continue, retry with adjusted args, ask user, or stop? Reason briefly.
Output:
{
  "decision": "continue | retry | ask_user | stop | escalate",
  "next_step_id": "...",
  "updated_args": {},
  "question": "",
  "reason_summary": ""
}
```

### G. Replanning Prompt

If the plan fails or new information emerges.

```text
Current plan steps remaining: {remaining_steps}
Latest observation: {observation}
The user request was: {original_request}
Decide whether to continue, modify plan, or stop. Output ReplanDecision JSON.
```

### H. Final Report Summarization Prompt

```text
Summarize the following execution results into a concise report.
Results: {aggregated_observations}
Report format: {format} with sections {sections}
Output plain markdown.
```

All prompts include a header: `SAFETY POLICY: Do not suggest commands for unauthorized targets. If in doubt, refuse or ask for authorization.`

---

## K. Example Safe Workflow Templates

### 1. Basic Network Inventory in My Lab

(see earlier detailed template)

### 2. Scan My Own Machine for Open Services

Same, but target = `localhost`; permissions = `network_scan`; scope = `local`.

### 3. Enumerate a CTF Target After I Confirm Scope

Workflow `ctf_recon`:
- Step 1: dns_enum (dig)
- Step 2: network_scan_syn on found IPs
- Step 3: web_directory_bruteforce on port 80/443 hosts
- All steps require explicit confirmation due to `network_scope: ctf` and target authorization.

### 4. Generate a Security Report from Previous Scan Outputs

Workflow `generate_report_from_scan`:
- Step 1: retrieve previous scan result from ContextStore (memory)
- Step 2: report_generator using that data.

### 5. Compare Two Scan Results

- Step 1: load scan1 from memory
- Step 2: load scan2
- Step 3: run a diff capability (deterministic script) that produces structured diff
- Step 4: report.

All these are stored as YAML or JSON and can be displayed in the mobile UI as selectable “recipes”.

---

## L. Observation and Replanning Loop

After each step execution, the Observation Parser runs. It converts raw output to:

```json
{
  "step_id": "1",
  "capability": "network_scan_syn",
  "status": "success",
  "summary": "Discovered 5 hosts, 3 with open ports",
  "structured_data": {"live_hosts": ["192.168.1.1", ...], "open_ports": [...]},
  "errors": [],
  "next_step_hints": ["service_version_scan"]
}
```

The WorkflowOrchestrator then evaluates:

- **If success**: advance to next step.
- **If partial**: keep results, optionally trigger LLM replanning if next steps depend on missing data.
- **If failure**: check retry policy (max 2 retries with exponential backoff, maybe different args). On repeated failure, escalate to user.
- **If timeout**: cancel step, mark as failed, replan or stop.
- **Conflicting outputs**: (e.g., nmap says host up but ping failed) – capture discrepancy, ask LLM to interpret but default to safe assumption (host may be firewalled). Do not automatically retry aggressive probes.

Rules:
- Maximum total steps: 10.
- Maximum retries per step: 2.
- User cancellation from mobile immediately stops the workflow.
- Permission escalation during execution: if a step needs a higher permission not yet granted, pause and ask mobile.

---

## M. Mobile‑Control Workflow

1. User speaks or types command into mobile app → sent as HTTP request to FRIDAY server with `user_id`, `device_id`, `turn_id`.
2. FRIDAY’s API gateway creates `trace_id` and publishes `TaskRequested` event.
3. WorkflowOrchestrator picks up, runs IntentRecognizer → classification.
4. If `chat`, forward to chat module; response sent back.
5. If `single_tool` or `workflow`:
   - Build plan preview (list of steps, capabilities, required permissions).
   - Determine if any step needs authorization → if yes, send `plan_preview` to mobile.
   - Mobile UI shows:
     - Task summary (“Network inventory of lab subnet”)
     - Target / scope
     - Steps with capability names and descriptions
     - Required permissions
     - Estimated duration
     - Risk level
   - User can **approve**, **deny**, **modify scope**, or **cancel**.
   - On approval, ConsentService records token, and execution starts.
6. During execution, mobile receives progress events (step start/completion, observation summaries) via WebSocket/Server-Sent Events.
7. A cancel button is always available; hitting it triggers `cancel` event, WorkflowOrchestrator rolls back if possible.
8. Final report delivered to mobile as markdown, with option to save in ContextStore.

---

## N. Memory / Procedural Learning Design

### What to store (ProceduralMemory)

- **Plan record**: Original user request, classified intent, selected workflow/tool plan, slot values, execution outcome (success/failure, step results).
- **Outcome metrics**: Duration, errors, user rating (if mobile UI allows thumbs up/down).
- **Authorizations**: tokens are not reused, but the fact that a target range was approved can be remembered if scope is identical.

### What not to store

- Raw command outputs that could contain sensitive information unless user opts in.
- Any target without explicit consent; never automatically learn “good targets”.

### Retrieval

- Embed user request (or intent) with a lightweight sentence transformer.
- Retrieve top‑3 similar past plans from a vector DB (ChromaDB, Qdrant) filtered by `user_id` and `success=true`.
- Those plans are injected as few‑shot examples in the prompt for classification, workflow selection, or plan generation.

### Ranking and decay

- Success rate and recency score boost ranking.
- Old plans decay unless repeatedly reused.

### Use as few‑shot examples

For the plan generation prompt, we include a “similar past task” section showing the request and the chosen steps, which dramatically improves Qwen3‑4B’s output reliability.

---

## O. Implementation Roadmap

### Phase 1: Tool Registry Hardening
- Define Capability schema.
- Implement 10 Kali capability wrappers with command templates, parsers, safety checks.
- Deterministic validators for arguments, target scope, flag blocklists.

### Phase 2: Workflow Template Registry
- Create 5‑10 YAML workflow templates for common tasks.
- Template engine that substitutes variables and generates a ToolPlan.

### Phase 3: Qwen Planner JSON Prompts
- Integrate constrained decoding (llama.cpp grammar) for Qwen3‑4B.
- Implement all prompt templates A‑H.
- Build a prompt builder that injects retrieved capabilities and few‑shots.

### Phase 4: Plan Validator
- Deterministic checker: all required slots filled, dependencies form a DAG, all steps allowed, permission consistency.
- Retry loop: if validation fails, feed error back to LLM once.

### Phase 5: Observation Parser
- For each capability, a Python class that parses raw output into structured JSON.
- Default fallback: capture stdout/stderr, extract known patterns.

### Phase 6: Replanning Loop
- Implement WorkflowOrchestrator state machine with observation‑based branching.
- LLM replanning only invoked when pre‑defined rules cannot decide.

### Phase 7: Mobile Approval UI
- REST + WebSocket server in FRIDAY.
- Simple React Native mobile interface with plan preview, approve/deny, live progress, cancel.

### Phase 8: Procedural Memory
- Vector DB for plan records.
- Embedding index updated on plan completion.
- Few‑shot builder that retrieves relevant successes.

---

## P. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LLM hallucinates capabilities | Only allow capability names present in the shortlist; validator rejects unknown names |
| Qwen3‑4B produces invalid JSON | Constrained grammar + post‑processing fix (json_repair library) |
| Scope creep (user asks to expand attack) | All targets validated against authorized scope; any new target requires re‑authorization |
| Sensitive output leakage | Structured parsing strips raw IPs from summary unless user‑facing report; logs are secured |
| Replay of unsafe plans from memory | Memory retrieval only returns plans that passed safety approval for same user and context |
| Long‑running loops | Hard step/retry/timeout limits enforced by executor |

---

## Q. Final Recommendation

**Qwen3‑4B alone cannot plan Kali workflows reliably**, but paired with a strict deterministic framework it becomes a powerful and safe local assistant. The recommended architecture is:

- **Deterministic core**: Capability Registry, Workflow Templates, Plan Validator, Command Builder, Safety Checks.
- **LLM role**: Intent classification, workflow selection, slot filling, dynamic plan drafting (only when no template matches), observation ambiguity resolution, report summarization.
- **Memory**: Retrieval‑augmented few‑shot learning from approved past plans.

Start with Phase 1‑3 to achieve a minimal viable product that handles simple “scan my lab” requests with one tool or a known template. Gradually add dynamic planning, replanning, mobile UI, and memory. This layered approach balances capability, safety, and local resource constraints, yielding a FRIDAY that feels intelligent without compromising security.

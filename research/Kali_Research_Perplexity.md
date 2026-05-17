#Research Prompt
## You are a senior AI systems research agent. Your task is to research how frontier cloud models plan complex multi-tool workflows, and how those ideas can be adapted into a small local model setup, specifically Qwen3-4B, for a local desktop/mobile-controlled assistant called FRIDAY.

Context:
FRIDAY is a local AI assistant architecture. It has:

- A deterministic router / RouteScorer for fast-path tool matching.
- An IntentRecognizer for multi-action command parsing.
- A CapabilityBroker that converts user intent into a ToolPlan.
- A CapabilityRegistry containing tool descriptors.
- A CapabilityExecutor that runs tools.
- A WorkflowOrchestrator for multi-turn workflows.
- A ModelRouter / LLM planner fallback for ambiguous tool planning.
- OrderedToolExecutor for sequential execution.
- Optional GraphCompiler / LangGraph-style execution for graph workflows.
- ConsentService and PermissionService for online or dangerous actions.
- MemoryBroker and ContextStore for session memory, workflow state, semantic recall, and procedural learning.

The current FRIDAY planning pipeline is roughly:

1. Check pending online confirmation.
2. Continue active workflow if one exists.
3. Try multi-action deterministic planning through IntentRecognizer.
4. Try deterministic best-route through RouteScorer.
5. Detect online/current-info request and ask consent if needed.
6. Use LLM planner fallback if the task is complex.
7. Fall back to chat if no tool/action is suitable.

The target use case:
The user wants to control tasks from a mobile phone, where the mobile phone sends natural-language commands to FRIDAY. Some tasks are normal desktop tasks. Some tasks are cybersecurity / Kali Linux workflows. Kali Linux tasks may require one tool, multiple tools, or conditional combinations of tools. Each tool may have many possible commands, flags, modes, inputs, and outputs. Example categories:

- Reconnaissance
- Network scanning
- Service enumeration
- Web enumeration
- Directory brute forcing
- DNS enumeration
- Vulnerability scanning
- Password auditing in legal lab environments
- Report generation
- Evidence collection
- Cleanup and logging

Important safety boundary:
Research only legal, defensive, lab, CTF, and authorized security testing workflows. Do not provide exploit instructions for unauthorized targets. Focus on architecture, planning, orchestration, tool abstraction, validation, safety gating, and workflow design.

Main research goal:
Find how frontier cloud models plan complex tool workflows, then convert those methods into a practical local architecture that lets Qwen3-4B perform better at workflow planning without needing frontier-scale reasoning.

Research questions to answer in depth:

1. How do frontier cloud models actually plan multi-tool workflows?
Investigate the common planning patterns used by advanced AI agents:

- ReAct: reasoning + action + observation loop.
- Plan-and-execute agents.
- Hierarchical task decomposition.
- Toolformer-style tool-use learning.
- Function calling / structured tool calls.
- Chain-of-thought vs hidden reasoning vs structured planning.
- Tree-of-thought / graph-of-thought planning.
- Reflection and self-correction loops.
- Critic / verifier models.
- Task graphs and DAG planning.
- State machines for workflows.
- Memory-augmented planning.
- Retrieval-augmented tool selection.
- Skill libraries and procedural memory.
- Agentic planning with observation feedback.

For each pattern, explain:

- What problem it solves.
- How it works internally.
- Whether it is suitable for a small local model.
- What parts should be deterministic instead of LLM-driven.
- What parts can be approximated using templates, schemas, retrieval, or rules.

2. How should a small local model like Qwen3-4B be made to behave like a better planner?
Research practical methods:

- Constrained JSON output.
- Tool schema compression.
- Few-shot planning examples.
- Workflow templates.
- Retrieval of similar past workflows.
- Skill cards / tool cards.
- Command grammar constraints.
- Planner-verifier split.
- Draft-plan then validate.
- Deterministic repair of invalid JSON.
- Confidence scoring.
- Ask-clarification behavior.
- Step-by-step decomposition without exposing chain-of-thought.
- Use of intermediate structured scratchpads internally.
- Separating “intent classification”, “workflow selection”, “argument filling”, “execution monitoring”, and “final response”.

Explain which of these methods are realistic for Qwen3-4B running locally with limited context and latency constraints.

3. What should the planning architecture be for Kali Linux workflows?
Design an architecture where Kali tools are not exposed as raw shell commands directly to the LLM. Instead, define safe capability wrappers.

Research and propose:

- A Tool Registry schema for Kali tools.
- A Workflow Registry schema for known workflows.
- A Target Context object.
- A Task Context object.
- A Safety Context object.
- A Permission Context object.
- A Run Context object.
- A Tool Result object.
- A Workflow State object.

Each Kali capability should include:

- tool_name
- description
- allowed_use_cases
- forbidden_use_cases
- input_schema
- output_schema
- required_permissions
- side_effect_level: read/write/critical
- network_scope: local/lab/public/unknown
- requires_authorization: true/false
- command_templates
- argument_constraints
- timeout
- parser
- success_conditions
- failure_conditions
- next_step_hints
- rollback_or_cleanup
- logging_requirements

4. How should the planner decide between:

- one tool,
- multiple tools,
- a predefined workflow,
- a generated workflow,
- asking the user a clarification question,
- refusing or safety-blocking?

Create a decision framework with clear thresholds:

- If user intent matches a known workflow with high confidence, select workflow.
- If user intent maps to one capability, select one tool.
- If user intent contains multiple actions, split into steps.
- If required slots are missing, ask clarification.
- If target authorization is missing, ask for confirmation or block.
- If task is ambiguous, ask a narrow question.
- If task is risky, require explicit authorization and scope.
- If task asks for unauthorized exploitation, refuse.
- If output of one step is required for another, use observation-based planning.

5. How should workflows be represented?
Compare:

- Linear ordered steps.
- DAG / task graph.
- Finite-state machine.
- Behavior tree.
- LangGraph-style state graph.
- HTN / hierarchical task network.
- YAML workflow templates.
- Python workflow classes.

Recommend the best representation for FRIDAY:

- Simple tasks: ordered ToolPlan.
- Known multi-step tasks: YAML or Python workflow templates.
- Dynamic tasks: LLM drafts a plan, deterministic validator compiles it into a safe graph.
- Multi-turn tasks: WorkflowOrchestrator state machine.
- Long-running tasks: background task runner with progress events.

6. How should Kali workflow templates look?
Design concrete template examples for legal lab use. Do not include harmful exploit instructions. Focus on safe structure.

Example workflow template types:

- “Basic network inventory in my lab”
- “Scan my own machine for open services”
- “Enumerate a CTF target after I confirm scope”
- “Generate a security report from previous scan outputs”
- “Compare two scan results”
- “Monitor a host availability status”
- “Web app reconnaissance in authorized lab”
- “DNS enumeration for owned domain”

For each template, define:

- required inputs
- optional inputs
- preconditions
- permission checks
- steps
- tool choices
- output parsers
- branching conditions
- stop conditions
- final report format

7. How should tool command selection work?
Research how to avoid letting the LLM freely generate shell commands.

Propose a command-generation system:

- LLM selects capability + mode, not raw command.
- Capability wrapper owns command templates.
- Arguments are validated by schema.
- Dangerous flags are blocked.
- Target scope is checked.
- Commands are previewed before execution for critical actions.
- Outputs are parsed into structured observations.
- The planner receives observations, not raw noisy terminal output unless needed.
- Every command is logged with trace_id, user request, target, timestamp, and result.

8. How should observation-based replanning work?
Research how agents handle tool output and decide next steps.

Design a loop:

- User request
- Initial plan
- Validate plan
- Execute step
- Parse observation
- Check success/failure
- Decide next step:
    - continue
    - retry with adjusted args
    - ask user
    - stop
    - escalate to planner
    - generate report
- Final response

Include rules for:

- maximum steps
- maximum retries
- timeout handling
- partial success
- tool failure
- conflicting outputs
- empty outputs
- permission escalation
- user cancellation from mobile

9. How should Qwen3-4B be prompted for planning?
Create multiple prompt templates:
A. Intent classification prompt.
B. Workflow selection prompt.
C. Slot-filling prompt.
D. Tool-plan generation prompt.
E. Plan validation prompt.
F. Observation interpretation prompt.
G. Replanning prompt.
H. Final report summarization prompt.

Each prompt must:

- Use strict JSON output.
- Avoid chain-of-thought leakage.
- Ask for concise rationale only if needed.
- Include allowed tools only.
- Include safety policy.
- Include examples.
- Include confidence score.
- Include missing_slots.
- Include refusal_reason when blocked.
- Include next_question when clarification is needed.

10. What JSON schemas should be used?
Design exact JSON schemas for:

IntentClassification:
{
"intent_type": "chat | single_tool | workflow | multi_step | clarify | refuse",
"domain": "...",
"confidence": 0.0,
"risk_level": "low | medium | high | critical",
"requires_authorization": true,
"missing_slots": [],
"reason_summary": "short non-chain-of-thought explanation"
}

ToolPlan:
{
"mode": "tool | workflow | clarify | refuse | chat",
"steps": [
{
"step_id": "s1",
"capability": "...",
"mode": "...",
"args": {},
"depends_on": [],
"requires_confirmation": false,
"side_effect_level": "read | write | critical",
"expected_observation": "...",
"success_condition": "..."
}
],
"missing_slots": [],
"ask_user": "",
"safety_notes": [],
"confidence": 0.0
}

WorkflowPlan:
{
"workflow_name": "...",
"target": {},
"scope": {},
"authorization": {},
"state": "pending | active | completed | cancelled",
"steps": [],
"branching_rules": [],
"stop_conditions": [],
"report_requirements": {}
}

Observation:
{
"step_id": "...",
"capability": "...",
"status": "success | failure | partial | timeout",
"summary": "...",
"structured_data": {},
"errors": [],
"next_step_hints": []
}

ReplanDecision:
{
"decision": "continue | retry | ask_user | stop | escalate | refuse",
"next_step_id": "...",
"updated_args": {},
"question": "",
"reason_summary": "",
"confidence": 0.0
}

11. How should this integrate into the current FRIDAY architecture?
Map the proposed system onto FRIDAY’s existing components:

- CapabilityBroker
- CapabilityRegistry
- IntentRecognizer
- RouteScorer
- ModelRouter
- WorkflowOrchestrator
- OrderedToolExecutor
- GraphCompiler
- ConsentService
- PermissionService
- MemoryBroker
- ContextStore
- TaskRunner
- EventBus
- ResponseFinalizer

Give exact recommendations:

- What should stay deterministic.
- What should be handled by Qwen3-4B.
- What should be workflow templates.
- What should be graph execution.
- What should be memory retrieval.
- What should be safety validation.
- What should be logged.
- What should be exposed to the mobile UI.

12. How should mobile-phone task control work?
Research and propose the mobile workflow:

- Mobile app sends natural-language task.
- Server creates turn_id / trace_id.
- FRIDAY classifies task.
- If safe and clear, returns plan preview.
- For read-only low-risk tasks, execute directly.
- For write/critical/Kali tasks, ask confirmation.
- Mobile UI shows:
    - task summary
    - target/scope
    - planned steps
    - required permissions
    - estimated time
    - live progress
    - cancel button
    - final report
- User can approve, deny, pause, cancel, or modify scope.

13. How should the system learn from previous workflows?
Research:

- Procedural memory.
- Success/failure tracking.
- Bandit-style tool selection.
- Storing successful plans.
- Retrieving similar prior tasks.
- Avoiding unsafe memory reuse.
- Versioning workflows.
- Human-approved workflow templates.

Design:

- What to store.
- What not to store.
- How to retrieve.
- How to rank.
- How to decay old memories.
- How to use previous successful plans as few-shot examples for Qwen3-4B.

14. What are the limitations of Qwen3-4B?
Research and explain:

- Context limits.
- JSON reliability.
- Tool hallucination.
- Weak long-horizon planning.
- Error recovery limitations.
- Security risks.
- Latency.
- Need for deterministic validators.
- Need for templates and retrieval.

Give a realistic conclusion:
Can Qwen3-4B plan Kali workflows alone?
If not, what architecture makes it reliable?
What is the minimum viable implementation?
What is the ideal advanced implementation?

15. Deliverables required from this research:
Produce the final answer with these sections:

A. Executive summary.
B. How frontier models plan workflows.
C. What can be copied into a local Qwen3-4B architecture.
D. What should remain deterministic.
E. Recommended FRIDAY planning architecture.
F. Kali workflow planning architecture.
G. Safety and permission model.
H. Tool/capability schema.
I. Workflow schema.
J. Prompt templates for Qwen3-4B.
K. Example safe workflow templates.
L. Observation and replanning loop.
M. Mobile-control workflow.
N. Memory/procedural learning design.
O. Implementation roadmap:

- Phase 1: Tool registry hardening.
- Phase 2: Workflow template registry.
- Phase 3: Qwen planner JSON prompts.
- Phase 4: Plan validator.
- Phase 5: Observation parser.
- Phase 6: Replanning loop.
- Phase 7: Mobile approval UI.
- Phase 8: Procedural memory.
P. Risks and mitigations.
Q. Final recommendation.

Important constraints:

- Do not recommend raw shell command generation by the LLM.
- Do not recommend unrestricted autonomous Kali execution.
- Do not include offensive exploitation instructions.
- Keep all cybersecurity examples defensive, authorized, lab-based, or CTF-safe.
- Prefer deterministic validation over trusting the model.
- Prefer workflow templates for common tasks.
- Use Qwen3-4B mainly for classification, slot filling, workflow selection, plan drafting, observation summarization, and clarification questions.
- Use deterministic code for permission checks, schema validation, command construction, execution, logging, and safety blocking.

Research style:
Be practical, implementation-oriented, and specific. Avoid generic agent buzzwords unless you explain exactly how they map into FRIDAY. Where possible, compare alternatives and recommend one. Include diagrams or pseudo-code if useful. Include JSON schemas and prompt templates that can be directly used in code.

Below is a practical design for FRIDAY: use deterministic routing, validated capability wrappers, and workflow templates as the default; use Qwen3-4B only for bounded planning tasks like intent classification, slot filling, workflow selection, clarification, observation summarization, and draft-plan generation under strict JSON schemas. Frontier systems get reliability by combining routing, structured tool interfaces, stateful execution, observation feedback, and evaluator loops rather than by letting one model freely invent commands, and that same pattern transfers well to a local setup if you narrow the model’s role and keep execution deterministic.[^1][^2][^3]


#Reseach Output
## A. Executive summary

Frontier agents usually do not rely on a single giant “planner prompt.” They combine simpler patterns such as routing, prompt chaining, orchestrator-worker decomposition, evaluator loops, structured tool calling, memory, and observation-based replanning, with explicit stopping conditions and strong tool interfaces.[^2][^4][^1]

For FRIDAY, the right architecture is: deterministic first, templates second, Qwen planner third, and execution never directly from model-written shell. For Kali and security workflows, expose only safe capability wrappers with permission metadata, target scope checks, schema-validated arguments, structured observations, and human approval checkpoints for any networked, write, or high-risk action.[^5][^6][^1]

## B. How frontier models plan workflows

Anthropic’s production guidance distinguishes **workflows** from agents: workflows are predefined code paths that orchestrate LLMs and tools, while agents dynamically direct tool use based on feedback. Anthropic also recommends starting with the simplest solution, then only increasing complexity when evaluation shows it helps, which is directly relevant to FRIDAY because many desktop and Kali tasks are better served by deterministic workflows than open-ended agent loops.[^1]

Common frontier planning patterns map cleanly into FRIDAY:


| Pattern | What problem it solves | How it works | Fit for Qwen3-4B | What should stay deterministic |
| :-- | :-- | :-- | :-- | :-- |
| ReAct | Uncertain tasks where next step depends on observations | Loop of think/act/observe | Good only in short bounded loops | Tool execution, retry limits, safety checks, stop conditions [^1][^1] |
| Plan-and-execute | Predictable multi-step tasks | Draft plan first, execute steps deterministically | Very good | Plan validation, step compilation, command construction [^1][^7] |
| Hierarchical decomposition | Complex tasks too large for one prompt | Split high-level workflow into smaller subplans | Good if domain-specific | Workflow registry, subtask boundaries [^1] |
| Function calling / structured tools | Reliable tool invocation | Model selects tool and schema-valid args | Excellent | Actual function schema enforcement [^4][^2] |
| Routing | Different intents need different pipelines | Classify then dispatch | Excellent | RouteScorer and fast-path classifiers [^1] |
| Orchestrator-workers | Many subtasks or sources | Planner spawns workers and merges output | Limited locally; use only for report synthesis or safe analysis | Worker assignment, merge policy [^1][^3] |
| Evaluator-optimizer | Improve weak first drafts | Generator + critic loop | Good if critic is cheap and bounded | Acceptance criteria, max revisions [^1] |
| State graphs / DAGs | Conditional or parallel workflows | Nodes with typed state and edges | Good if compiled from safe templates | Graph compiler, transitions, dependency rules [^3][^8] |
| Memory-augmented planning | Reuse prior workflows and context | Retrieve similar runs, skills, targets | Very useful | Retrieval, ranking, decay, approval boundaries [^5][^1] |

### ReAct

ReAct solves tasks where you cannot know all steps upfront because the environment keeps changing; the model alternates short reasoning, a tool action, and an observation before deciding what to do next. Anthropic’s description of agents as LLMs operating in a loop with ground-truth feedback is essentially this pattern in production form.[^1]

For FRIDAY, use ReAct only inside a bounded shell: max 5 to 8 steps, max 1 to 2 retries per step, no direct shell generation, and only against capability wrappers. The model should see structured observations, not raw terminal noise, because small models degrade badly on long unstructured output.[^1]

### Plan-and-execute

Plan-and-execute solves predictable tasks by separating planning from doing: first draft a step list, then run execution deterministically. This is a strong fit for FRIDAY’s existing CapabilityBroker, OrderedToolExecutor, and WorkflowOrchestrator because it preserves control and gives the user a previewable plan.[^7][^1]

For Qwen3-4B, this is the main planning mode to prefer over free-form ReAct. The model should output a compact ToolPlan JSON, and your validator should reject or repair invalid fields before any executor sees the plan.[^2]

### Hierarchical task decomposition

This solves long-horizon planning by reducing one big task into smaller subgoals such as “determine scope,” “collect observations,” and “generate report.” Anthropic’s orchestrator-workers pattern is one version of this, where a central planner decides subtasks dynamically and workers solve them.[^1]

In FRIDAY, you should approximate hierarchy mostly with workflow templates and subworkflow references, not with recursive open-ended planning. A small local model can choose among registered subworkflows far more reliably than inventing a deep plan tree from scratch.[^3][^1]

### Toolformer-style tool learning

Toolformer-style ideas are mainly about teaching models when and how to call tools from examples, but in practice for local systems the transferable idea is not self-supervised tool discovery; it is **example-conditioned tool selection**. You can emulate the effect with few-shot plans, capability cards, and retrieved prior successful plans rather than trying to reproduce frontier-scale tool-use training.[^9][^2]

### Function calling and structured outputs

Structured outputs and function calling are the strongest frontier idea to copy into FRIDAY because they replace vague text planning with typed machine-readable decisions. OpenAI’s structured outputs documentation emphasizes schema adherence, explicit refusals, required fields, additionalProperties=false, and programmatic handling of refusals, all of which map directly to FRIDAY’s planner contracts.[^2]

For a local model that may not support hard constrained decoding as well as frontier APIs, you should still design around strict schemas and run deterministic JSON validation plus repair. The model’s job is to propose; code’s job is to enforce.[^2]

### Hidden reasoning vs structured planning

Frontier vendors increasingly avoid exposing raw chain-of-thought, but still rely on internal reasoning plus external structured traces. For FRIDAY, the correct adaptation is to ask the model for concise `reason_summary`, `missing_slots`, `confidence`, and `next_question`, while keeping any deeper scratchpad internal or omitted entirely.[^2][^1]

This matters because Qwen3-4B is more reliable when output fields are few, explicit, and semantically narrow. Asking for long explanations harms both latency and JSON validity.[^2]

### Tree-of-thought / graph-of-thought

These approaches solve branching search over multiple candidate plans, but they are expensive and fragile on small local models. The practical local adaptation is not true tree search by the model; it is deterministic branching through workflow graphs, plus optional multi-candidate draft plans where the validator picks the safest valid plan.[^8][^3]

### Reflection, self-correction, critic models

Evaluator-optimizer loops improve outputs when criteria are clear, such as “all required slots filled,” “no forbidden capability,” or “all targets within authorized scope.” Anthropic explicitly recommends evaluator loops where iterative refinement yields measurable value.[^1]

For FRIDAY, a lightweight planner-verifier split is realistic: Qwen drafts a plan, then either Qwen in verifier mode or deterministic validators check schema, permissions, slot completeness, risk, and workflow fit. Deterministic validation should be authoritative for safety; model-based critique should only suggest repairs.[^1]

### Task graphs, DAGs, state machines

LangGraph-style state graphs represent workflows as typed state plus nodes and conditional edges, which is useful when execution depends on previous observations or when some tasks can run in parallel. LangGraph’s examples show orchestrator nodes producing plans, worker nodes operating on state, and synthesizer nodes combining results, which is a direct blueprint for FRIDAY’s optional GraphCompiler.[^3][^8]

For FRIDAY, use three representations: linear ordered steps for simple tasks, compiled DAG/state graph for known branching workflows, and a WorkflowOrchestrator state machine for multi-turn or approval-gated interactions. That gives you most frontier reliability benefits without needing frontier reasoning depth.[^3][^1]

### Memory, retrieval, and skills

Anthropic defines the augmented LLM as an LLM with retrieval, tools, and memory. EY’s security orchestration article also highlights working, episodic, semantic, and procedural memory as distinct layers for security agents.[^5][^1]

For FRIDAY, memory should retrieve similar prior workflows, target context, last approved scopes, common argument defaults, and successful report formats. The model should not browse raw logs; it should receive compact retrieved “skill cards” and prior-plan exemplars.[^5][^1]

## C. What can be copied into a local Qwen3-4B architecture

The key transferable insight from frontier systems is **architectural decomposition**, not raw reasoning scale. You can copy structured outputs, routing, workflow templates, observation loops, critic passes, and memory retrieval, then shrink the model’s role to tasks where small models are good enough.[^2][^1]

Realistic methods for Qwen3-4B running locally:

- Constrained JSON output: highly recommended, because structured outputs reduce schema drift and enable deterministic repair.[^2]
- Tool schema compression: very important, because local context is limited and large tool catalogs confuse selection.[^1]
- Few-shot planning examples: useful if examples are short and domain-specific.[^1][^2]
- Workflow templates: essential for common desktop and Kali tasks.[^1]
- Retrieval of similar workflows: very useful; inject top 1 to 3 similar approved plans.[^5][^1]
- Skill cards / tool cards: essential; each tool needs a short, highly discriminative description.[^1]
- Command grammar constraints: essential for wrapped capabilities.[^2]
- Planner-verifier split: realistic and high-value.[^1]
- Deterministic repair of invalid JSON: essential for local reliability.[^2]
- Confidence scoring and ask-clarification behavior: useful, but confidence should be calibrated against downstream validator outcomes, not trusted alone.[^1]
- Intermediate structured scratchpads: useful if hidden from user and aggressively size-limited.[^2]

A good local decomposition is:

1. Intent classification.
2. Workflow selection.
3. Slot filling.
4. Draft plan generation.
5. Deterministic validation/repair.
6. Execution monitoring.
7. Observation summarization.
8. Replanning decision.
9. Final response formatting.[^2][^1]

## D. What should remain deterministic

Anything safety-critical, stateful, or syntax-sensitive should remain deterministic. Anthropic specifically stresses transparency, tool documentation, and careful agent-computer interfaces, and OpenAI’s structured-output guidance makes clear that even with strong schemas you still need application-side handling of refusals and mistakes.[^2][^1]

Keep these deterministic in FRIDAY:

- RouteScorer fast-path classification.
- CapabilityRegistry and WorkflowRegistry lookup.
- Permission and consent checks.
- Scope validation for targets, domains, hosts, interfaces, and lab ownership.
- Tool argument schema validation.
- Command template selection and shell escaping.
- Dangerous flag blocking.
- Plan compilation from draft JSON to executable graph.
- Retry, timeout, circuit breaker, and max-step logic.
- Parsing raw tool output into structured observations where possible.
- Audit logging, trace IDs, and report provenance.[^1][^2]

Qwen3-4B should not decide whether a target is authorized, whether a flag is dangerous, or how to construct raw shell commands. Those must be policy code and wrapper logic.[^6][^1]

## E. Recommended FRIDAY planning architecture

The recommended FRIDAY pipeline is a layered controller:

```text
Mobile/User Input
   ->
TurnManager(trace_id, turn_id)
   ->
PendingConfirmationCheck
   ->
WorkflowOrchestrator.resume_if_active()
   ->
IntentRecognizer + RouteScorer
   -> if high confidence deterministic route
       CapabilityBroker.build_from_rules()
   -> else
       MemoryBroker.retrieve_similar()
       ModelRouter.invoke_qwen(
         intent or workflow selection or plan draft
       )
   ->
PlanValidator
   ->
PermissionService + ConsentService
   ->
PlanCompiler
     -> OrderedToolExecutor for linear plans
     -> GraphCompiler + TaskRunner for branching/long jobs
   ->
ObservationParser
   ->
ReplanController
   ->
ResponseFinalizer + Mobile Progress Events
```

This follows Anthropic’s advice to start simple and add complexity only where needed, while borrowing LangGraph-style typed state and conditional edges for tasks that genuinely need branching.[^8][^1]

### Component mapping

| FRIDAY component | Recommended role |
| :-- | :-- |
| IntentRecognizer | Deterministic or lightweight model classification for simple domains |
| RouteScorer | Fast-path exact/semantic route ranking for single capability or known workflow |
| CapabilityBroker | Builds candidate ToolPlan/WorkflowPlan from registry metadata |
| CapabilityRegistry | Source of truth for safe wrappers, schemas, permissions, command templates |
| ModelRouter | Invokes Qwen only when deterministic confidence is low or task is multi-step/ambiguous |
| WorkflowOrchestrator | Owns multi-turn workflow state, approvals, pause/resume, cancellation |
| OrderedToolExecutor | Executes linear low-branch plans |
| GraphCompiler | Compiles safe draft workflow into a typed DAG/state graph |
| ConsentService | User-facing approvals for online, public network, write, or critical actions |
| PermissionService | Checks authorization, OS permissions, network scope, policy |
| MemoryBroker | Retrieves similar prior tasks, defaults, approved plans, user preferences |
| ContextStore | Stores turn state, workflow state, observations, approvals, reports |
| TaskRunner | Background execution for long-running scans/reports |
| EventBus | Progress and observation events |
| ResponseFinalizer | Converts final state into concise user-facing output |

## F. Kali workflow planning architecture

For Kali workflows, do not expose raw binaries or free-form shell to the model. Expose **safe capabilities** such as `network_inventory`, `host_service_scan`, `dns_enum_owned_domain`, `web_recon_lab`, `compare_scan_results`, and `security_report_generate`, each backed by a wrapper that owns command templates, allowed flags, parsing, and cleanup. This mirrors Anthropic’s emphasis on well-designed tools and “poka-yoke” interfaces that make mistakes harder.[^1]

### Safe wrapper model

```text
User intent
  -> capability or workflow selection
  -> validated args
  -> wrapper selects command template
  -> policy engine removes/blocks dangerous flags
  -> executor runs command in sandbox/controlled host
  -> parser emits structured observation
  -> planner sees observation only
```


### Tool Registry schema

```json
{
  "capability_id": "host_service_scan",
  "tool_name": "host_service_scan",
  "description": "Read-only authorized service discovery for a lab host.",
  "category": "network_scanning",
  "allowed_use_cases": [
    "inventory my lab host",
    "check open services on my own machine",
    "authorized CTF enumeration"
  ],
  "forbidden_use_cases": [
    "unauthorized target scanning",
    "stealth scanning for evasion",
    "exploit delivery",
    "credential attack outside legal lab"
  ],
  "input_schema": {
    "type": "object",
    "properties": {
      "target_host": { "type": "string" },
      "scan_profile": { "type": "string", "enum": ["quick", "standard", "safe_deep"] },
      "ports": { "type": ["string", "null"] },
      "timing_profile": { "type": "string", "enum": ["polite", "normal"] }
    },
    "required": ["target_host", "scan_profile", "ports", "timing_profile"],
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "reachable": { "type": "boolean" },
      "open_ports": { "type": "array", "items": { "type": "integer" } },
      "services": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "port": { "type": "integer" },
            "protocol": { "type": "string" },
            "service_name": { "type": "string" },
            "version_hint": { "type": ["string", "null"] }
          },
          "required": ["port", "protocol", "service_name", "version_hint"],
          "additionalProperties": false
        }
      }
    },
    "required": ["reachable", "open_ports", "services"],
    "additionalProperties": false
  },
  "required_permissions": ["authorized_scope", "network_access"],
  "side_effect_level": "read",
  "network_scope": "lab",
  "requires_authorization": true,
  "command_templates": {
    "quick": "SAFE_WRAPPER_TEMPLATE_ID_1",
    "standard": "SAFE_WRAPPER_TEMPLATE_ID_2",
    "safe_deep": "SAFE_WRAPPER_TEMPLATE_ID_3"
  },
  "argument_constraints": {
    "target_host": ["ipv4", "ipv6", "hostname"],
    "ports": ["null", "port_list", "top_ports_profile"],
    "deny_flags": ["aggressive", "spoofing", "fragmentation", "evasion"]
  },
  "timeout_sec": 300,
  "parser": "parse_host_service_scan_v1",
  "success_conditions": [
    "target reached or explicitly unreachable",
    "structured service list emitted"
  ],
  "failure_conditions": [
    "authorization missing",
    "target out of scope",
    "tool timeout without partial data"
  ],
  "next_step_hints": [
    "if http service found, suggest web_recon_lab",
    "if dns service found, suggest dns_enum_owned_domain",
    "if no services found, stop or retry with user approval"
  ],
  "rollback_or_cleanup": [
    "remove temporary output files",
    "retain audit log and user-approved report artifacts"
  ],
  "logging_requirements": [
    "trace_id",
    "turn_id",
    "user_id",
    "authorized_scope_id",
    "target_host",
    "command_template_id",
    "result_status"
  ]
}
```


### Workflow Registry schema

```json
{
  "workflow_name": "basic_network_inventory_lab",
  "version": "1.0.0",
  "description": "Read-only inventory of hosts and services in an authorized lab subnet.",
  "domain": "cybersecurity_lab",
  "tags": ["inventory", "lab", "authorized", "read_only"],
  "required_inputs": ["target_scope", "authorization"],
  "optional_inputs": ["scan_profile", "name_resolution"],
  "preconditions": [
    "target_scope.network_scope == 'lab'",
    "authorization.confirmed == true"
  ],
  "permission_checks": [
    "authorized_scope",
    "network_access"
  ],
  "steps": [
    "discover_hosts",
    "scan_services",
    "summarize_findings",
    "generate_report"
  ],
  "branching_rules": [
    "if no_live_hosts -> stop_with_summary",
    "if http_services_found -> optional_web_recon_branch"
  ],
  "stop_conditions": [
    "user_cancelled",
    "scope_invalid",
    "max_hosts_exceeded"
  ],
  "report_requirements": {
    "format": "markdown",
    "include_scope": true,
    "include_timestamps": true,
    "include_tools": true,
    "include_findings_only": true
  }
}
```


### Context objects

#### TargetContext

```json
{
  "target_type": "host | subnet | domain | url | file | workflow_artifact",
  "value": "",
  "normalized": {},
  "ownership_claim": "user_owned | lab | ctf | unknown",
  "scope_id": "",
  "environment": "desktop | kali_vm | lab | ctf",
  "network_scope": "local | lab | public | unknown"
}
```


#### TaskContext

```json
{
  "user_goal": "",
  "domain": "desktop | cybersecurity_lab | reporting | chat",
  "intent_type": "single_tool | workflow | multi_step | clarify | refuse | chat",
  "priority": "low | normal | high",
  "time_budget_sec": 0,
  "requires_current_info": false
}
```


#### SafetyContext

```json
{
  "risk_level": "low | medium | high | critical",
  "allowed_use_only": "defensive_lab_authorized",
  "blocked_reasons": [],
  "dangerous_elements_detected": [],
  "policy_version": "2026-05"
}
```


#### PermissionContext

```json
{
  "authorization_present": false,
  "authorization_type": "user_assertion | saved_scope | signed_policy | none",
  "consent_required": false,
  "consent_status": "not_needed | pending | granted | denied",
  "os_permissions": [],
  "network_permissions": []
}
```


#### RunContext

```json
{
  "trace_id": "",
  "turn_id": "",
  "workflow_id": "",
  "run_id": "",
  "executor": "ordered | graph | background",
  "started_at": "",
  "deadline_at": "",
  "max_steps": 8,
  "max_retries_per_step": 2,
  "user_can_cancel": true
}
```


#### ToolResult / Observation

```json
{
  "step_id": "",
  "capability": "",
  "status": "success | failure | partial | timeout",
  "summary": "",
  "structured_data": {},
  "errors": [],
  "artifacts": [],
  "next_step_hints": []
}
```


#### WorkflowState

```json
{
  "workflow_id": "",
  "workflow_name": "",
  "state": "pending | awaiting_consent | active | paused | completed | failed | cancelled",
  "current_step_id": "",
  "completed_steps": [],
  "pending_steps": [],
  "observations": [],
  "scope_snapshot": {},
  "authorization_snapshot": {},
  "last_updated_at": ""
}
```


## G. Safety and permission model

Security workflows need explicit policy boundaries because frontier autonomy amplifies mistakes. EY’s security orchestration guidance also highlights human escalation for high-impact decisions and persistent memory structures rather than stateless automation.[^5]

Use a multi-layer policy model:

1. **Intent policy**: refuse unauthorized exploitation, stealth, persistence, evasion, credential abuse outside legal lab, or ambiguous public-target requests.[^2]
2. **Scope policy**: require target type, ownership/authorization, and environment classification.
3. **Capability policy**: each wrapper lists allowed and forbidden uses.
4. **Execution policy**: read-only low-risk can auto-run; write/high/critical require confirmation.
5. **Observation policy**: block replans that would escalate risk without fresh consent.
6. **Reporting policy**: final reports include only defensive findings and authorized-scope metadata.[^6][^1]

### Permission thresholds

| Case | Decision |
| :-- | :-- |
| Local desktop read-only task | Auto-execute if high confidence |
| Local Kali read-only on saved lab scope | Plan preview, then optional auto-execute if user has standing consent |
| Public network or unknown scope | Ask clarification and require explicit scope confirmation |
| Any write or critical action | Require explicit approval |
| Missing authorization on security task | Ask for authorization or block |
| Unauthorized exploitation request | Refuse |

## H. Tool/capability schema

Use compact but discriminative tool cards. Anthropic advises that tool descriptions, examples, edge cases, and clear boundaries matter as much as the model prompt, and that tool interfaces should be designed to make mistakes harder.[^1]

### Recommended capability card

```json
{
  "tool_name": "dns_enum_owned_domain",
  "short_selector_hint": "Use for authorized DNS record lookup and owned-domain enumeration.",
  "description": "Read-only DNS enumeration for a domain the user owns or is authorized to test.",
  "allowed_use_cases": [
    "owned domain record inventory",
    "lab domain enumeration",
    "CTF DNS challenge after scope confirmation"
  ],
  "forbidden_use_cases": [
    "unauthorized domain reconnaissance",
    "bulk internet-wide enumeration",
    "evasion"
  ],
  "required_slots": ["domain", "authorization"],
  "optional_slots": ["record_types", "resolver_profile"],
  "input_schema_ref": "dns_enum_owned_domain.input.v1",
  "output_schema_ref": "dns_enum_owned_domain.output.v1",
  "required_permissions": ["authorized_scope"],
  "side_effect_level": "read",
  "network_scope": "lab",
  "requires_authorization": true,
  "timeout_sec": 120,
  "next_step_hints": [
    "if MX found, include in report",
    "if subdomains found, suggest authorized web recon"
  ]
}
```

Compression rule for local model prompts: include only `tool_name`, `short_selector_hint`, `required_slots`, `risk`, `network_scope`, and `requires_authorization` in the selection prompt, then inject the full schema only after the tool is chosen. This saves context and reduces tool confusion.[^2][^1]

## I. Workflow schema

A safe FRIDAY WorkflowPlan should include target, scope, authorization, state, steps, branching, and report requirements, with no executable shell inside the model-produced object. Structured outputs guidance recommends fixed required fields and `additionalProperties:false`, which is exactly what you want here.[^2]

### WorkflowPlan

```json
{
  "workflow_name": "basic_network_inventory_lab",
  "target": {
    "target_type": "subnet",
    "value": "192.168.56.0/24",
    "normalized": {
      "cidr": "192.168.56.0/24"
    }
  },
  "scope": {
    "network_scope": "lab",
    "scope_id": "lab-net-1",
    "ownership_claim": "lab"
  },
  "authorization": {
    "requires_authorization": true,
    "authorization_present": true,
    "consent_status": "granted"
  },
  "state": "pending",
  "steps": [
    {
      "step_id": "s1",
      "capability": "discover_hosts",
      "mode": "safe_ping_or_arp",
      "args": {
        "target_scope": "192.168.56.0/24"
      },
      "depends_on": [],
      "requires_confirmation": false,
      "side_effect_level": "read",
      "expected_observation": "live_hosts[]",
      "success_condition": "observation.structured_data.live_hosts.length >= 0"
    },
    {
      "step_id": "s2",
      "capability": "host_service_scan",
      "mode": "standard",
      "args": {
        "targets_from_step": "s1.live_hosts"
      },
      "depends_on": ["s1"],
      "requires_confirmation": false,
      "side_effect_level": "read",
      "expected_observation": "services_by_host",
      "success_condition": "observation.status in ['success','partial']"
    }
  ],
  "branching_rules": [
    {
      "if": "s1.live_hosts.length == 0",
      "then": "stop"
    },
    {
      "if": "http services present",
      "then": "suggest_optional_web_recon"
    }
  ],
  "stop_conditions": [
    "user_cancelled",
    "authorization_revoked",
    "max_steps_reached"
  ],
  "report_requirements": {
    "format": "markdown",
    "include_scope": true,
    "include_timestamps": true,
    "include_findings_only": true
  }
}
```


## J. Prompt templates for Qwen3-4B

All prompts should request strict JSON only, ask for no hidden reasoning, and include a small list of allowed tools or workflows. OpenAI’s structured-output guidance strongly supports schema-first prompting and explicit refusal handling, while Anthropic’s tool guidance supports investing heavily in tool descriptions and examples.[^1][^2]

### A. Intent classification prompt

```text
System:
You are FRIDAY's intent classifier. Return JSON only.
Do not output chain-of-thought.
Follow the schema exactly.
Safety policy:
- Security tasks must be defensive, authorized, lab, owned, or CTF-safe.
- Unauthorized exploitation or ambiguous risky requests must be refused or clarified.

Schema:
{
  "intent_type": "chat | single_tool | workflow | multi_step | clarify | refuse",
  "domain": "desktop | cybersecurity_lab | reporting | general",
  "confidence": 0.0,
  "risk_level": "low | medium | high | critical",
  "requires_authorization": true,
  "missing_slots": [],
  "reason_summary": ""
}

Examples:
User: "Open my downloads folder"
JSON: {"intent_type":"single_tool","domain":"desktop","confidence":0.97,"risk_level":"low","requires_authorization":false,"missing_slots":[],"reason_summary":"Single local desktop action."}

User: "Scan 10.10.10.5 and tell me services"
JSON: {"intent_type":"clarify","domain":"cybersecurity_lab","confidence":0.72,"risk_level":"high","requires_authorization":true,"missing_slots":["target_scope_authorization"],"reason_summary":"Security scan requires explicit authorized scope."}

User input:
{{user_text}}
```


### B. Workflow selection prompt

```text
System:
You are FRIDAY's workflow selector. Return JSON only.
Choose one of the provided workflows, or choose clarify/refuse.
Never invent workflow names.
Do not produce shell commands.

Available workflows:
{{workflow_cards_compact}}

Schema:
{
  "intent_type": "workflow | single_tool | clarify | refuse",
  "selected_workflow": "string | null",
  "selected_capability": "string | null",
  "confidence": 0.0,
  "missing_slots": [],
  "next_question": "",
  "refusal_reason": "",
  "reason_summary": ""
}

User:
{{user_text}}

Context:
{{retrieved_similar_workflows}}
```


### C. Slot-filling prompt

```text
System:
Extract required slots for the selected capability/workflow.
Return JSON only. Use null where not provided. Do not invent facts.

Selected item:
{{selected_card}}

Schema:
{
  "filled_slots": {},
  "missing_slots": [],
  "confidence": 0.0,
  "next_question": "",
  "reason_summary": ""
}

User:
{{user_text}}
```


### D. Tool-plan generation prompt

```text
System:
You are FRIDAY's bounded planner.
Return JSON only.
Use only the listed capabilities/workflows.
Never generate raw shell commands.
Prefer the smallest safe plan.
If required slots are missing, output mode=clarify.
If policy blocks the task, output mode=refuse.

Allowed capabilities:
{{capability_cards_compact}}

Allowed workflows:
{{workflow_cards_compact}}

Schema:
{
  "mode": "tool | workflow | clarify | refuse | chat",
  "steps": [
    {
      "step_id": "s1",
      "capability": "",
      "mode": "",
      "args": {},
      "depends_on": [],
      "requires_confirmation": false,
      "side_effect_level": "read | write | critical",
      "expected_observation": "",
      "success_condition": ""
    }
  ],
  "missing_slots": [],
  "ask_user": "",
  "safety_notes": [],
  "confidence": 0.0
}

User:
{{user_text}}

Context:
{{target_context}}
{{permission_context}}
{{retrieved_examples}}
```


### E. Plan validation prompt

Use this only as a secondary soft checker after deterministic validation fails or wants repair suggestions.

```text
System:
You are FRIDAY's plan reviewer.
Return JSON only.
Review the draft plan for missing slots, invalid capability choices, unsafe escalation, or unnecessary steps.
Do not add new tools not in the plan.

Schema:
{
  "valid": true,
  "issues": [],
  "repair_actions": [],
  "confidence": 0.0,
  "reason_summary": ""
}

Draft plan:
{{tool_plan_json}}

Capability/workflow catalog:
{{relevant_catalog_subset}}
```


### F. Observation interpretation prompt

```text
System:
You summarize structured tool observations for the planner.
Return JSON only.
Do not infer facts not present in the observation.

Schema:
{
  "step_id": "",
  "status": "success | failure | partial | timeout",
  "summary": "",
  "key_facts": [],
  "suggested_next_actions": [],
  "confidence": 0.0
}

Observation:
{{observation_json}}
```


### G. Replanning prompt

```text
System:
You decide the next planning action after a step result.
Return JSON only.
Do not create shell commands.
Use only: continue, retry, ask_user, stop, escalate, refuse.

Schema:
{
  "decision": "continue | retry | ask_user | stop | escalate | refuse",
  "next_step_id": "",
  "updated_args": {},
  "question": "",
  "reason_summary": "",
  "confidence": 0.0
}

Current workflow state:
{{workflow_state}}

Latest observation:
{{observation}}

Policy:
{{policy_summary}}
```


### H. Final report summarization prompt

```text
System:
You are FRIDAY's report summarizer.
Return JSON only.
Use concise factual summaries.
Do not mention hidden reasoning.
Do not include offensive guidance.

Schema:
{
  "task_summary": "",
  "scope_summary": "",
  "steps_completed": [],
  "key_findings": [],
  "limitations": [],
  "recommended_next_steps": [],
  "confidence": 0.0
}

Workflow result:
{{final_state}}
```


## K. Example safe workflow templates

Use templates for common, defensive, legal tasks. Anthropic’s guidance favors workflows for predictable tasks because they are more consistent and easier to control than full agents.[^1]

### 1. Basic network inventory in my lab

```yaml
name: basic_network_inventory_lab
required_inputs:
  - target_subnet
  - authorization
optional_inputs:
  - scan_profile
  - host_limit
preconditions:
  - target_scope.network_scope == "lab"
  - authorization.confirmed == true
permission_checks:
  - authorized_scope
  - network_access
steps:
  - id: s1
    capability: discover_hosts
    mode: standard
    args: { target_subnet: "{{target_subnet}}" }
    parser: live_hosts_parser
  - id: s2
    capability: host_service_scan
    mode: standard
    foreach: "s1.live_hosts"
    args: { target_host: "{{item}}" }
    parser: service_parser
  - id: s3
    capability: security_report_generate
    mode: inventory_summary
    args: { host_results_from: "s2" }
branching:
  - if: "s1.live_hosts == []"
    then: stop
stop_conditions:
  - user_cancelled
  - max_hosts_exceeded
final_report:
  format: markdown
  sections: [scope, timestamps, live_hosts, services, notes]
```


### 2. Scan my own machine for open services

```yaml
name: own_machine_open_services
required_inputs: [target_host]
optional_inputs: [scan_profile]
preconditions:
  - target_host in local_device_set or authorization.confirmed == true
permission_checks: [local_access]
steps:
  - id: s1
    capability: host_service_scan
    mode: quick
    args: { target_host: "{{target_host}}" }
  - id: s2
    capability: security_report_generate
    mode: host_summary
    args: { scan_result_from: "s1" }
final_report:
  format: markdown
  sections: [host, reachable, open_ports, services, recommendations]
```


### 3. Enumerate a CTF target after I confirm scope

```yaml
name: ctf_target_enumeration_safe
required_inputs: [target_host_or_domain, ctf_scope_confirmation]
optional_inputs: [depth]
preconditions:
  - target_scope.ownership_claim == "ctf"
  - authorization.confirmed == true
permission_checks: [authorized_scope]
steps:
  - id: s1
    capability: host_service_scan
    mode: standard
    args: { target_host: "{{target_host_or_domain}}" }
  - id: s2
    capability: web_recon_lab
    when: "s1 has http_service"
    mode: safe_enum
    args: { base_url_from: "s1" }
  - id: s3
    capability: dns_enum_owned_domain
    when: "input looks like domain"
    mode: standard
    args: { domain: "{{target_host_or_domain}}" }
  - id: s4
    capability: security_report_generate
    mode: ctf_enum_summary
    args: { inputs_from: ["s1", "s2", "s3"] }
stop_conditions: [user_cancelled, policy_violation]
```


### 4. Generate a security report from previous scan outputs

```yaml
name: report_from_scan_artifacts
required_inputs: [artifact_refs]
optional_inputs: [report_style]
preconditions:
  - artifacts_exist == true
permission_checks: []
steps:
  - id: s1
    capability: parse_scan_artifacts
    mode: normalize
    args: { artifact_refs: "{{artifact_refs}}" }
  - id: s2
    capability: security_report_generate
    mode: executive_plus_technical
    args: { normalized_results_from: "s1" }
final_report:
  format: markdown
  sections: [summary, scope, findings, differences, caveats]
```


### 5. Compare two scan results

```yaml
name: compare_two_scan_results
required_inputs: [artifact_a, artifact_b]
steps:
  - id: s1
    capability: compare_scan_results
    mode: diff
    args: { artifact_a: "{{artifact_a}}", artifact_b: "{{artifact_b}}" }
  - id: s2
    capability: security_report_generate
    mode: comparison_summary
    args: { diff_from: "s1" }
```


### 6. Monitor a host availability status

```yaml
name: monitor_host_availability
required_inputs: [target_host, duration]
optional_inputs: [interval_sec]
preconditions:
  - authorization.confirmed == true
permission_checks: [authorized_scope]
steps:
  - id: s1
    capability: host_availability_check
    mode: repeated
    args: { target_host: "{{target_host}}", duration: "{{duration}}", interval_sec: "{{interval_sec|default(30)}}" }
  - id: s2
    capability: security_report_generate
    mode: uptime_summary
    args: { check_result_from: "s1" }
stop_conditions: [user_cancelled, duration_elapsed]
```


### 7. Web app reconnaissance in authorized lab

```yaml
name: web_app_recon_lab
required_inputs: [base_url, authorization]
optional_inputs: [depth]
preconditions:
  - target_scope.network_scope in ["lab", "ctf"]
  - authorization.confirmed == true
permission_checks: [authorized_scope]
steps:
  - id: s1
    capability: web_recon_lab
    mode: safe_enum
    args: { base_url: "{{base_url}}" }
  - id: s2
    capability: directory_inventory_safe
    mode: common_paths
    args: { base_url: "{{base_url}}" }
  - id: s3
    capability: security_report_generate
    mode: web_recon_summary
    args: { inputs_from: ["s1", "s2"] }
```


### 8. DNS enumeration for owned domain

```yaml
name: dns_enum_owned_domain
required_inputs: [domain, authorization]
preconditions:
  - authorization.confirmed == true
  - target_scope.ownership_claim in ["user_owned", "lab", "ctf"]
permission_checks: [authorized_scope]
steps:
  - id: s1
    capability: dns_enum_owned_domain
    mode: standard
    args: { domain: "{{domain}}" }
  - id: s2
    capability: security_report_generate
    mode: dns_summary
    args: { dns_result_from: "s1" }
```


## L. Observation and replanning loop

Anthropic stresses that agents need ground truth from the environment at each step and should pause for human feedback at checkpoints or blockers. That maps directly to FRIDAY’s observation-based replanning loop.[^1]

### Recommended loop

```text
1. User request
2. Initial classification
3. Workflow/tool selection
4. Slot fill
5. Draft plan
6. Deterministic validate/repair
7. Permission + consent gate
8. Execute step
9. Parse raw output -> Observation
10. Evaluate success/failure/partial/timeout
11. Replan decision:
    continue | retry | ask_user | stop | escalate | refuse
12. Repeat until stop condition
13. Generate final report
```


### Rules

- Maximum steps: 5 for ad hoc plans, 8 to 12 for registered workflows.[^1]
- Maximum retries per step: 1 for syntax/timeout, 2 only for transient read-only failures.
- Timeout handling: return `status="timeout"` with partial artifacts if available.
- Partial success: continue only if downstream steps can consume partial data.
- Empty output: one retry with adjusted non-risky args, else ask user or stop.
- Conflicting outputs: escalate to verifier or ask user to confirm which artifact is authoritative.
- Permission escalation: any replan that increases risk level requires fresh consent.
- Mobile cancellation: EventBus must interrupt TaskRunner and set workflow state to `cancelled`.
- Raw output visibility: planners get structured observations by default; raw output stays available only for debugging UI.[^1]


### ReplanDecision schema

```json
{
  "decision": "continue | retry | ask_user | stop | escalate | refuse",
  "next_step_id": "s3",
  "updated_args": {},
  "question": "",
  "reason_summary": "Previous step produced partial host list; continue with available hosts.",
  "confidence": 0.84
}
```


## M. Mobile-control workflow

For mobile control, the key pattern is preview-before-execute for anything risky, with live progress and cancelability. This aligns with the broader frontier theme of transparency and checkpointed autonomy rather than invisible long-running action.[^1]

### Mobile flow

1. Mobile app sends natural-language command.
2. Server creates `turn_id`, `trace_id`, and lightweight session snapshot.
3. FRIDAY classifies request and drafts a plan.
4. If low-risk and read-only with high confidence, FRIDAY may execute immediately.
5. If write, critical, online, public-scope, or Kali-related, FRIDAY returns a plan preview and awaits approval.
6. UI shows:
    - Task summary
    - Target and scope
    - Planned steps
    - Required permissions
    - Risk level
    - Estimated time
    - Approve / deny / modify / pause / cancel
7. During execution, FRIDAY streams progress events.
8. Final screen shows report, artifacts, logs summary, and follow-up safe actions.[^1]

### Mobile UI payload

```json
{
  "trace_id": "tr_123",
  "task_summary": "Inventory hosts and open services in your lab subnet.",
  "target_scope": "192.168.56.0/24",
  "risk_level": "medium",
  "requires_confirmation": true,
  "planned_steps": [
    "Discover live hosts",
    "Scan open services",
    "Generate summary report"
  ],
  "required_permissions": ["authorized_scope", "network_access"],
  "estimated_time_sec": 240,
  "controls": ["approve", "deny", "modify_scope", "pause", "cancel"]
}
```


## N. Memory/procedural learning design

The best memory design here follows the layered idea from agentic systems and security orchestration: working memory for current run state, episodic memory for past runs, semantic memory for tool and policy knowledge, and procedural memory for approved reusable workflows.[^5][^1]

### What to store

- User-approved workflow instances.
- Final validated ToolPlans and WorkflowPlans.
- Execution outcomes: success, partial, fail, timeout.
- Tool performance stats by context.
- Common slot defaults by user and environment.
- Report formats the user prefers.
- Authorized saved scopes and lab profiles.
- Repair patterns for invalid plans.[^5]


### What not to store

- Secrets, plaintext credentials, tokens.
- Unapproved or policy-blocked plans as reusable exemplars.
- Raw sensitive outputs beyond retention policy.
- Unsafe command fragments.
- Ambiguous authorizations or unverifiable ownership claims.


### Retrieval and ranking

Rank by:

1. Same domain.
2. Same workflow/capability.
3. Same environment and target type.
4. Recent success.
5. Human-approved status.
6. Similar slot pattern.[^5][^1]

Decay old memories with time and demote plans that required multiple repairs or ended in failure. Only retrieve top 1 to 3 exemplars into the Qwen prompt to control context size.[^1]

### Using memory as few-shot input

Convert prior approved workflows into short exemplars:

```json
{
  "task": "Scan my Kali lab host for open services",
  "selected_workflow": "own_machine_open_services",
  "filled_slots": {"target_host":"192.168.56.10"},
  "plan_shape": ["host_service_scan", "security_report_generate"],
  "outcome": "success"
}
```

This is much safer than injecting raw historical terminal text.[^5]

## O. Implementation roadmap

### Phase 1: Tool registry hardening

Define safe capability wrappers, argument schemas, side-effect levels, scope metadata, logging fields, parsers, and command templates. This phase gives the biggest safety gain because it prevents the LLM from ever becoming a shell generator.[^1]

### Phase 2: Workflow template registry

Create YAML or Python templates for the top 10 to 20 recurring desktop and lab workflows. Start with linear plans and only add branching when real use cases require it.[^8][^1]

### Phase 3: Qwen planner JSON prompts

Implement the 8 prompt types with strict JSON, compact tool cards, and 2 to 5 domain-specific examples each. Keep prompt tokens small and split tasks into separate calls rather than one mega-prompt.[^2]

### Phase 4: Plan validator

Build deterministic validators for JSON schema, allowed capability names, required slots, scope rules, risk transitions, and dependency correctness. Add repair logic for common issues such as enum normalization, missing nulls, and extraneous keys.[^2]

### Phase 5: Observation parser

Wrap each tool with a parser that converts noisy CLI output into `Observation` objects. The planner should receive summaries and typed fields, not uncontrolled raw stdout.[^1]

### Phase 6: Replanning loop

Implement bounded observation-based replanning with max steps, retries, timeouts, escalation, and stop conditions. Start with linear workflows plus branch hooks before enabling general graph execution.[^8][^1]

### Phase 7: Mobile approval UI

Expose plan previews, scope, permissions, estimated time, progress events, and cancel/pause controls. Treat mobile approval as part of the safety system, not just UX.[^1]

### Phase 8: Procedural memory

Store approved successful plans and retrieve them as short exemplars for workflow selection and slot defaults. Add versioning so outdated workflows are not reused after tool or policy changes.[^5]

## P. Risks and mitigations

| Risk | Why it happens | Mitigation |
| :-- | :-- | :-- |
| JSON invalidity | Small model output drift | Strict schemas, deterministic repair, retries with error message [^2][^2] |
| Tool hallucination | Too many tools or vague descriptions | Compressed tool cards, limited candidate set, registry validation [^1] |
| Weak long-horizon planning | 4B models struggle with deep dependency chains | Use templates, hierarchical decomposition, bounded replanning [^1] |
| Unsafe escalation | Model infers next steps beyond scope | PermissionService checks every step and replan [^6] |
| Raw shell misuse | Model invents commands/flags | Capability wrapper owns command construction entirely [^1] |
| Context overflow | Large catalogs and logs | Retrieval-based prompt narrowing, structured observations, top-k exemplars [^5] |
| Latency on local device | Multi-pass planning loops | Deterministic fast paths, compact prompts, small candidate sets [^1] |
| Memory reuse of bad plans | Success artifacts mixed with unsafe or stale runs | Human-approved, versioned, decayed procedural memory [^5] |

## Q. Final recommendation

Qwen3-4B cannot reliably plan Kali workflows **alone** if “alone” means open-ended reasoning over raw tool catalogs, free-form command generation, and autonomous long-horizon adaptation. Frontier systems get reliability from architecture, not just model size, and FRIDAY should do the same by combining deterministic routing, capability wrappers, workflow templates, strict JSON planning, observation parsing, validator-gated replanning, and human approval for risky actions.[^3][^2][^1]

The minimum viable implementation is: hardened capability registry, 10 to 20 workflow templates, strict JSON prompts for classification/selection/slot filling/tool-plan generation, deterministic plan validator, structured observations, and mobile approval gates. The ideal advanced implementation adds graph-compiled workflows, planner-verifier loops, procedural memory retrieval, background task orchestration, and calibrated confidence scoring tied to validator outcomes rather than the model’s self-assessment.[^8][^5][^1]

Would you like me to turn this into a concrete FRIDAY spec pack next, with ready-to-drop TypeScript interfaces, Pydantic/Zod schemas, and validator pseudocode?
<span style="display:none">[^10][^11][^12][^13][^14][^15][^16][^17][^18][^19][^20]</span>

<div align="center">⁂</div>

[^1]: https://medium.com/@deolesopan/from-tools-to-agents-planning-multi-step-workflows-with-react-and-plan-execute-314419f0aec3

[^2]: https://qwen-3.com/ar/prompt-library/structuredOutput

[^3]: https://langchain-ai.github.io/langgraph/tutorials/workflows/

[^4]: https://developers.openai.com/api/docs/guides/function-calling

[^5]: https://www.ey.com/en_in/insights/ai/agentic-soc-multi-agent-orchestration-for-next-gen-security-operations

[^6]: https://github.github.com/gh-aw/introduction/architecture/

[^7]: https://www.linkedin.com/pulse/how-ai-agents-actually-work-react-vs-plan-and-execute-bouchard-jmere

[^8]: https://docs.langchain.com/oss/python/langgraph/workflows-agents

[^9]: https://pub.towardsai.net/building-intelligent-ai-agents-exploring-function-calling-rag-and-react-with-llama-index-23901dfd1b33

[^10]: https://huggingface.co/api/resolve-cache/models/eternis/sft_lora_0.6b_qwen_structured_output_no_think/e09234e6b6e3a161ca81479f301cf8edf8274c31/chat_template.jinja?download=true\&etag=%2201be9b307daa2d425f7c168c9fb145a286e0afb4%22

[^11]: https://github.com/QwenLM/Qwen3-VL/issues/761

[^12]: https://secportal.io/research/security-workflow-orchestration

[^13]: https://thedataguy.pro/writing/2025/08/llm-tool-calling-to-react-agent/

[^14]: https://machinelearningmastery.com/structured-outputs-vs-function-calling-which-should-your-agent-use/

[^15]: https://www.anthropic.com/engineering/writing-tools-for-agents

[^16]: https://developers.openai.com/api/docs/guides/structured-outputs

[^17]: https://www.anthropic.com/research/building-effective-agents

[^18]: https://www.linkedin.com/posts/rakeshgohel01_anthropic-uses-ai-agents-to-automate-their-activity-7449796598789791744-W3oU

[^19]: https://docs.langchain.com/oss/python/langgraph/graph-api

[^20]: https://dylancastillo.co/posts/function-calling-structured-outputs.html


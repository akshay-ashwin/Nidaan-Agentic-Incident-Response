# Nidaan

@SPEC.md

## Standing Rules

### 1. Source of Truth
- SPEC.md is frozen and is the single source of truth.
- Do not redesign the architecture or add features.
- Build only MUST HAVE items unless explicitly approved otherwise.
- Never build items in the CUT list.
- If something is difficult to implement, propose a simpler implementation that preserves the core agentic loop and wait for approval.
- Do not expand scope to solve implementation difficulty.

### 2. Core Agentic Loop
Always preserve:

observe → decide → act → environment changes → observe → replan → verify

The three architectural layers must remain explicit:

- LLM agent: decides
- SettleSim: changes state and enforces safety
- Deterministic verifier: checks the result

### 3. Four-Day Constraint
The project must remain comfortably implementable by 3 undergraduate students within the available deadline.

Prioritize:
1. Working core agentic loop
2. Deterministic simulator and tests
3. Agent/tool integration
4. Verifier and structured logging
5. Baselines and evaluation
6. UI and presentation polish

If time becomes limited, simplify presentation or optional features before weakening the core agentic loop.

### 4. Held-Out Evaluation and Blinding
Before the prompt is frozen:

- Only development fault types may be implemented:
  - F1
  - F2
  - F4
  - F6
  - F7

- Do NOT implement, expose, or reveal:
  - F3
  - F5
  - F8
  - held-out scenarios

The held-out faults and scenarios are added only during an explicitly started "held-out session" after the agent prompt has been frozen.

Never put held-out fault names, values, implementation details, or scenario-specific information into:
- the system prompt
- tool descriptions
- agent-visible logs
- agent-visible observations

The runbook baseline must remain genuinely strong and must use development fault types only.

### 5. Agent Prompt
The agent prompt must use general principles rather than explicitly naming faults or scenario-specific solutions.

The agent should:
- assess before acting
- collect evidence
- distinguish competing explanations
- use observed configuration values rather than guessing
- inspect before risky actions
- prefer minimal reversible changes
- reconsider its hypothesis when an action fails or exposes a new problem
- replan using fresh observations
- stop only when the goal is verified
- report only actions actually performed

Do not optimize for a predetermined number of LLM calls.

Measure actual:
- LLM calls
- tokens
- latency

Never estimate these values in advance.

If a metric is unavailable from the integration, report it as unavailable rather than inventing an estimate.

### 6. Logging
Never expose or store hidden chain-of-thought.

Logs may contain:
- structured plans
- plan versions
- observations
- actions
- tool results
- triggers
- concise reasons
- decisions
- verification results

Do not store private reasoning or hidden chain-of-thought.

Evaluation-only annotations must never be shown to the agent during a run.

### 7. Secrets
- Never print API keys or other secrets.
- Secrets belong in `.env`.
- `.env` must be included in `.gitignore`.
- Never hard-code API keys into source files.
- Never include secrets in logs.

### 8. Git
Claude Code must NOT:
- commit
- push
- create branches
- delete branches
- switch branches
- reset
- rebase
- stash
- restore/discard changes
- clean the repository
- otherwise modify Git history or branch state

The user handles all Git operations and commits.

### 9. Implementation Style
Keep SettleSim minimal.

SettleSim exists only as an experimental environment for:
- creating meaningful agent decisions
- exposing observations
- changing state through actions
- measuring outcomes

Do not add production infrastructure or unnecessary realism.

Do not add:
- databases
- Docker
- Kafka
- networking
- real UPI or bank APIs
- multi-agent systems
- RAG
- Grafana
- unnecessary infrastructure

unless the user explicitly changes the specification.

### 10. Development Workflow
Work in explicit phases.

Before each major phase:
1. Explain what will be built.
2. Explain why it is required.
3. State the completion gate.
4. State the expected files/changes.

After each phase:
1. List files created or modified.
2. List commands/tests run.
3. Report what passed.
4. Report what failed.
5. Report any deviation from SPEC.md.
6. Recommend the next phase.
7. STOP and wait for the user's explicit "go".

Do not automatically continue into the next phase.

### 11. Current Priority
The first implementation priority is Phase 0:

- inspect the repository
- establish the Python environment
- establish pinned dependencies
- configure `.env` safely
- determine currently available Gemini Flash models
- verify the selected model through LangChain's official Gemini integration
- run a minimal toy-tool smoke test
- demonstrate at least 3 dependent tool calls
- measure actual calls, tokens, and latency when available

Do not build SettleSim or the full Nidaan agent during Phase 0.

### 12. Quality Standard
Prefer a smaller implementation that actually works over a larger implementation that is fragile.

Do not hide failures.

If something fails:
- report it clearly
- diagnose it
- propose the smallest fix
- do not silently change the specification

The objective is a defensible IA project with a genuine agentic loop, not maximum code volume.

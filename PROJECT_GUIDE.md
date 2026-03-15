# 🗺️ EASY COMPANY: TOTAL BLUEPRINT & TECHNICAL ARCHITECTURE

This document is a comprehensive, granular guide to the entire **Easy Company** codebase. It covers every function, data structure, and logic flow in the project.

---

## 🏗️ 1. SYSTEM ARCHITECTURE & DATA FLOW

### The "Triangle" Communication Pattern
1.  **Frontend (Electron Renderer)**: UI (Canvas, Training Panel), Visual Logic (JS), API Calls (Fetch).
2.  **Middleman (Electron Main)**: Process Management (Spawning Python), Native APIs (File picker, Secure Storage).
3.  **Backend (Python/FastAPI)**: LLM Orchestration, Tool Execution, Local File Persistence.

### Data Storage Schemas
#### `backend/agents.json` (The Master Registry)
Array of objects containing:
- `id`: Unique string (e.g., `agent-Name-123456789`)
- `name`: Display name.
- `description`: Role/Purpose.
- `brain`: LLM provider (gemini, anthropic).
- `channel`: Communication destination.
- `workingDir`: Local path for agent file operations.
- `permissions`: Array of tool strings (e.g., `['web search', 'thinking']`).
- `x`, `y`: Visual coordinates on the canvas.
- `connections`: IDs of agents this agent can message.

#### `backend/agents_code/[ID]/history.json` (Short-term memory)
- Array of `{"role": "user" | "assistant", "content": "..."}` objects.
- Maintains a sliding window context (last 50 messages) for the LLM while keeping full history for the UI.

#### `backend/agents_code/[ID]/summary.json` (Long-term memory)
- Contains a cumulative distillation of the historical conversation.
- **Proactive Distillation**: When history exceeds 50 messages, the system automatically summarizes older context into this file to preserve memory without bloating the API context.

#### `backend/agents_code/[ID]/plan.json` (BDI Internal State)
- **Objective**: The agent's current high-level goal.
- **Steps**: Array of planned sub-tasks.
- **Completed**: Array of finished sub-tasks.
- This file is injected into the system prompt to ensure the agent never "forgets" where it is in a multi-step process.

#### `backend/agents_code/knowledge_base.json` (The Shared Ledger)
- A global repository for all agents.
- Stores insights, facts, and correlations discovered by individual agents.
- Implements **Stigmergy**: agents leave "scents" (data) in the ledger instead of whispering history to each other.

---

## 🌐 2. FRONTEND DETAIL (JavaScript)

### `main.js` (The Process Controller)
- **Globals**: `store` (persistent settings), `pythonProcess` (child process handle).
- **Functions**:
    - `startPythonBackend()`: 
        - Uses `child_process.spawn('python', ...)` to run `server.py`.
        - Monitors `stdout/stderr` and emits `backend-log` IPC events to the UI.
    - `createWindow()`: Standard Electron window setup. Loads `canvas.html`.
- **IPC Handlers**:
    - `set-api-key`: Uses `electron-store` to save encrypted-at-rest keys.
    - `get-api-key`: Retrieves keys based on provider name.
    - `select-directory`: Triggers `dialog.showOpenDialog` for the folder browser.
    - `open-external`: Forces links to open in the system browser (Chrome/Edge) instead of Electron.

### `canvas.js` (The Node-Link Engine)
- **Class `AgentCanvas`**:
    - **Constructor**: Initializes layers (nodes, svg, grid) and attaches global listeners.
    - `createNode(id, title, description, x, y, data)`:
        - Creates the DOM structure for an agent.
        - Injects the "Live Backend" terminal (`term-[id]`).
        - Attaches expansion logic for the settings panel.
    - `connectNodes(source, target)`: Appends a Bezier path to the SVG layer.
    - `updateConnections()`: Computes SVG `d` path attributes based on current node `offsetLeft/Top`.
    - `addAgentAtMouse()`: Triggered via Right Click menu; assigns unique ID based on timestamp.
    - `saveAgentData(id)`: Aggregates current visual state and sends `PUT` request to `/agents/{id}`.
    - `logToTerminal(agentId, message)`: 
        - Intercepts logs from Python.
        - Triggers the `.loading-dots` animation if keywords (Training, Searching) are found.

### `agent-training.js` (The Interactive Sidebar)
- **State Management**: `activeAgentId`, `activeAgentData`.
- **Functions**:
    - `openTrainingPanel(id, name)`: 
        - Fetches full agent data from backend.
        - Populates inputs.
        - Triggers `updateApiKeyVisibility()` to check if a key for the selected brain already exists.
    - `triggerSave()` / `queueAutoSave()`: Implementation of **Debouncing**. Saves changes to the backend 1 second after the user stops typing.
    - `markdownToHtml(text)`: 
        - Custom parser for headers, lists, code, and links.
        - Specifically identifies `(Source: ...)` to apply custom CSS styling for citations.
    - `animateWords(container)`: 
        - The "Word-by-Word" reveal effect.
        - Uses a `TreeWalker` to find text nodes and wrap every word in a `word-reveal` span with an incremental `animation-delay`.
    - `handleSend()`: 
        - Validates Brain selection and API key presence.
        - Shows `typing-indicator`.
        - Performs `fetchPOST` to `/chat`.

---

## 🐍 3. BACKEND DETAIL (Python)

### `server.py` (FastAPI Core)
- **Tool Routing**: `perform_tool_call()`
    - Decides which function in `toolkit.py` to run based on the detected tool command.
- **Persistence**: `load_data()` / `save_data()`
    - Thread-safe reading/writing of the `agents.json` registry.
- **Layered Prompt Architecture**:
    - **Identity Layer**: Persona, role, current date, and assigned working directory.
    - **Tool Manual Layer**: Dynamic documentation of available commands based on permissions.
    - **Transient Task Layer**: Live project context, global objectives, agent directory, and history summary.
- **The Reasoning Loop (`chat_with_agent`)**:
    1.  **Memory Load**: Retrieves history and any existing long-term summary.
    2.  **Context Construction**: Builds a layered system prompt and injects current task details.
    3.  **Iteration Loop** (Max 15 turns):
        -   **Gemini Native Tools**: Uses official Google Tool Schema to expose functions directly to Gemini models.
        -   **Error Handling**: Includes a fallback for `MALFORMED_FUNCTION_CALL` to handle hallucinated tools gracefully.
        -   **Tool Execution**: Regex/Native parsing for `[TOOL: name(args)]`. Triggers `perform_tool_call`, appends results to history, and iterates.
        -   **Final Response**: Sanitizes output (redacts code blocks/large dumps) and returns to the frontend.

### `toolkit.py` (The Agent Skills)
- `web_search(query, agent_id)`: **Quick Fact Search**. Returns raw titles, URLs, and snippets.
- `deep_search(query, agent_id)`: **Comprehensive Research**. Filters DuckDuckGo results using a Gemini-Flash 2.0 librarian step to pick the top 3-8 most relevant sources.
- `thinking(agent_id, topic)`: Simulates deep logical analysis with terminal status updates.
- `generate_report(agent_id, tool_input, working_dir)`: Writes a markdown report to the agent's folder.
- `report_generation(agent_id, tool_input, working_dir)`: **Premium PDF Synthesis**. Uses `ReportPDFGenerator` to create professional documents with executive summaries and citations.
- `message_agent(target_id, message, sender_id)`:
    - **Cross-Agent Delegation**. Launches a nested `/chat` request.
    - **Context Inversion**: Individual history snippets are disabled in favor of the **Shared Workspace Ledger**.
    - Uses `threading.Thread` to enable concurrent execution.
- `post_finding(insight | source)`: Writes key data to the Global Knowledge Graph for other agents to react to.
- `update_plan(objective | steps OR completed)`: Mutates the agent's internal BDI state.
- **File System Tools**: `scout_file`, `read_file`, `write_file`, `list_workspace`. Includes strict path traversal protection.

### `response_formatter.py` (The Stylizer)
- Uses `re.sub` for high-performance string transformation.
- **H1-H3**: Replaces with `━` line dividers and UPPERCASE labels.
- **Bullets**: Replaces `-` and `*` with the `•` symbol.
- **Code**: Wraps in double quotes for terminal readability.
- **Cleanup**: Collapses excessive whitespace to keep the node terminal clean.

---

## 🔌 4. IPC & API SPECIFICATION

### Backend REST API
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/agents` | Returns array of all agent metadata. |
| `POST` | `/agents` | Creates a new agent entry and its folder structure. |
| `PUT` | `/agents/{id}` | Updates metadata AND regenerates `prompt.md`/`personality.json`. |
| `DELETE` | `/agents/{id}` | Wipes database entry and deletes the local directory. |
| `POST` | `/chat` | Processes a message, handles tools, and updates `history.json`. |

### Electron IPC (Main <-> Renderer)
| Channel | Function |
| :--- | :--- |
| `select-directory` | Opens OS-native folder selection dialog. |
| `set-api-key` | Saves provider key to `config.json`. |
| `get-api-key` | Fetches provider key from `config.json`. |
| `backend-log` | Transfers Python `print()` statements to the JS side. |

---

## 🎨 5. VISUAL SYSTEM (CSS)

- **Grid Background**: Achieved via `background-image: radial-gradient(circle, #333 1px, transparent 1px);` with `background-size: 20px 20px;`.
- **Node Statuses**:
    - `.expanded`: Increases node height to show internal settings.
    - `.selected`: Adds a `#6c5ce7` (Purple) border glow.
- **Terminal Animation**: `.loading-dots` uses CSS keyframes to pulse three characters.
- **Word Reveal**: `.word-reveal` uses `opacity: 0` and `transform: translateY(5px)` rising to `opacity: 1` as the reveal animation runs.

---

## ⚖️ 6. CORE AGENT PROTOCOLS

1.  **Intent Discrimination**: Agents must verify if the user wants a tool action or just a conversational clarification.
2.  **Wait Rule**: Tool calls must be followed by a `STOP` until system results are provided, except for basic status updates.
3.  **Collaboration First**: If an agent lacks a tool (e.g., file access), it MUST check connected neighbors and delegate via `message_agent` instead of refusing.
4.  **Ruthless Sanitization**: Raw code blocks and massive data dumps are automatically redacted from chat history to maintain privacy and UI performance.
5.  **Proactive Memory**: High-frequency chats are distilled into summaries to prevent context loss at the 50-message boundary.
6.  **The Ledger Protocol (Stigmergy)**: Agents MUST read the `knowledge_base.json` before acting and post findings immediately upon discovery.
7.  **Atomic Plan Updates (BDI)**: Agents MUST use `update_plan` to cross off a task before sending a final message to the user.

---

## 🔄 7. COMPLETE EXECUTION FLOW (Life of a Request)

1.  **User Typing**: User hits "Enter" in Training Panel.
2.  **Context Loading**: Backend loads `agents.json`, `history.json`, and `summary.json`.
3.  **Prompt Assembly**: Layered prompt is built with live project context.
4.  **Distillation Check**: If history > 50 messages, a summary is proactively generated/updated.
5.  **Iteration 1**: LLM receives context + message. Returns tool call (e.g., `web_search`).
6.  **Tool Execution**: `toolkit.py` runs search -> results returned as `SYSTEM TOOL RESULT`.
7.  **Iteration 2+**: LLM analyzes results, potentially chains more tools (up to 15 turns).
8.  **Final Response**: Final answer is synthesized.
9.  **Sanitization**: `sanitize_ruthlessly` redacts sensitive/massive data.
10. **Formatting**: `response_formatter.py` stylizes Markdown for the terminal.
11. **Delivery**: Frontend receives JSON, runs animations, and updates UI status to "Ready".

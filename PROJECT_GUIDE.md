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
- Limited to the last 10 messages to maintain context window efficiency.

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
    - Decides which function in `capabilities.py` to run based on the detected tool command.
- **Persistence**: `load_data()` / `save_data()`
    - Thread-safe reading/writing of the `agents.json` registry.
- **The Reasoning Loop (`chat_with_agent`)**:
    1.  Load agent's custom `prompt.md` and conversation `history.json`.
    2.  Build **System Prompt**: Combines Identity + Capabilities + Connection Manual.
    3.  **Iteration Loop** (Max 5 turns):
        -   Call LLM API.
        -   Regex Search for `[TOOL: tool_name(input)]`.
        -   If found: Trigger `perform_tool_call`, append `SYSTEM TOOL RESULT` to messages, and re-call the LLM.
        -   If not found: Break and return final string.

### `capabilities.py` (The Agent Skills)
- `web_search(query, agent_id)`:
    - Uses `DDGS` (DuckDuckGo Search) to pull the top 15 results.
- `filter_sources(query, search_results, api_key)`:
    - **Optimization Step**: Sends the 15 results to Gemini-Flash 2.0.
    - Gemini returns a JSON array of the 3-8 most relevant result indices.
    - This trims "noise" and prevents context-window bloat in the final synthesis.
- `synthesize_with_gemini(query, search_results, api_key)`:
    - Generates a structured research brief with "Key Findings" and "Summary."
    - **Safety Feature**: Hard-codes the "Sources" section directly from the raw data to ensure URLs aren't hallucinated.
- `thinking(topic)`: A dummy 3-second sleep to simulate heavy computation (can be expanded to complex multi-step analysis).
- `generate_report(title, content)`: Writes a timestamped `.md` file to the agent's local directory.
- `message_agent(target_id, message, sender_name)`:
    - Launches a nested `/chat` request.
    - Uses `threading.Thread` to avoid FastAPI event-loop deadlocks when Agent A waits for Agent B.

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

## 🔄 6. COMPLETE EXECUTION FLOW (Life of a Request)

1.  **User Typing**: User hits "Enter" in Training Panel.
2.  **API Key Retrieval**: `agent-training.js` asks Electron Main for the key.
3.  **POST Request**: Frontend hits `localhost:8000/chat`.
4.  **Backend Assembly**: FastAPI reads `prompt.md` (System) + `history.json` (Context) + `User Message`.
5.  **Iteration 1**: Gemini returns `[TOOL: web_search("Deepseek model specs")]`.
6.  **Tool Execution**: `capabilities.py` runs search -> gets 15 results -> filters to top 5.
7.  **Iteration 2**: Backend sends Tool Results back to Gemini.
8.  **Final Response**: Gemini sends the summary.
9.  **Formatting**: `response_formatter.py` turns Markdown into Terminal Style.
10. **Delivery**: Frontend receives JSON, runs the word-reveal animation, and updates the Canvas node terminal to "Ready".

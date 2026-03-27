# 4-Agent Orchestration System - Complete Workflow Guide

## System Architecture

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                        USER QUERY                                 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                          │
                          ▼
             ┏━━━━━━━━━━━━━━━━━━━━━━━━━┓
             ┃  ORCHESTRATOR.PY       ┃
             ┃  Manages entire flow   ┃
             ┗━━━━━━━━┳━━━━━━━━━━━━━━┛
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
    PHASE 1                    PHASE 1
    SEQUENTIAL                 SEQUENTIAL
        │                           │
        ▼                           ▼

┌───────────────────────────────────────────────────────┐
│  PHASE 1: RESEARCH AGENT (Sequential)                 │
│  ────────────────────────────────────────────────────│
│  Model: Gemini 2.0 Flash (Fast scraping)             │
│  Input:  User query + research goal                  │
│  Process: hitl_engine.py (UNDERSTAND→GATHER→STORE)   │
│  Output: graph.json (facts, sources, topics)         │
│                                                       │
│  🔍 Recursively scrapes web sources                  │
│  ✅ Extracts verified facts with confidence scores   │
│  🏷️  Tags entities and topics                        │
│  🔗 Builds knowledge graph relationships             │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────┐
    │   graph.json ready      │
    │   • 50-100 nodes        │
    │   • 20-50 edges         │
    │   • Facts w/ metadata   │
    └─────────┬───────────────┘
              │
    ┌─────────┴──────────────────────┐
    │   PHASE 2: PARALLEL AGENTS      │
    │   ============================  │
    │   Run synthesis + visual        │
    │   analysis simultaneously       │
    │                                 │
    ▼                                 ▼

┌──────────────────────────┐    ┌──────────────────────────┐
│  SYNTHESIS AGENT         │    │  VISUAL ANALYST AGENT    │
│  ─────────────────────   │    │  ──────────────────────  │
│  Model: Gemini 3 Pro     │    │  Model: Gemini 3.1 Pro   │
│                          │    │                          │
│  Input: graph.json       │    │  Input: graph.json       │
│                          │    │                          │
│  Process:                │    │  Process:                │
│  • Analyze facts         │    │  • Scan for metrics      │
│  • Generate insights     │    │  • Extract money values  │
│  • Structure narrative   │    │  • Find percentages      │
│  • Add context          │    │  • Build timelines       │
│  • Citations            │    │  • Map networks          │
│                          │    │  • Rate confidence       │
│  Output:                │    │  Output:                 │
│  report_text.md         │    │  visuals.json            │
│                          │    │                          │
│  ✨ Polished text       │    │  📊 Structured data      │
│  🎯 Actionable insights │    │  📈 Chart specs          │
│  📚 Full references     │    │  📅 Timelines            │
│                          │    │  💰 Metrics              │
└────────┬─────────────────┘    └────────┬─────────────────┘
         │                              │
         └──────────────┬───────────────┘
                        │
                        ▼
         ┌──────────────────────────┐
         │  PHASE 3: PDF GENERATOR  │
         │  ────────────────────────│
         │  Model: Gemini 2.0 Flash │
         │                          │
         │  Inputs:                 │
         │  • report_text.md        │
         │  • visuals.json          │
         │  • graph.json            │
         │                          │
         │  Process:                │
         │  • Merge text sections   │
         │  • Generate charts       │
         │  • Embed visualizations  │
         │  • Format professionally │
         │  • Add table of contents │
         │  • Create PDF            │
         │                          │
         │  Output:                 │
         │  final_report.pdf        │
         │                          │
         │  📄 Polished PDF         │
         │  🎨 Formatted visuals    │
         │  📑 Complete report      │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  FINAL REPORT        │
         │  ════════════════    │
         │  (PDF + Visuals)     │
         │                      │
         │ Ready for use/share  │
         └──────────────────────┘
```

## Execution Flow

### 1️⃣ Phase 1: Research Agent (Sequential)
```python
# hitl_engine.hitl_loop(state) → graph.json
# Time: Variable (5-15 minutes depending on complexity)

UNDERSTAND → GATHER → STORE → REFLECT → ACT → PRESENT

Output structure:
{
  "nodes": [
    {"node_type": "source", "url": "...", "full_text": "..."},
    {"node_type": "fact", "content": "...", "confidence": 0.95},
    {"node_type": "topic", "label": "...", "summary": "..."}
  ],
  "links": [
    {"source": "fact_001", "target": "topic_xyz", "type": "mentions"}
  ]
}
```

### 2️⃣ Phase 2a: Synthesis Agent (Parallel)
```python
# Input: graph.json
# Time: ~30-60 seconds

Transforms knowledge graph → Narrative report
- Extracts key findings
- Generates analytical insights
- Structures sections
- Adds citations
- Creates logical flow

Output: report_text.md
```

### 2️⃣ Phase 2b: Visual Analyst Agent (Parallel)
```python
# Input: graph.json
# Time: ~15-30 seconds

Scans graph for:
✅ Monetary values ($500M, $2.3B, etc.)
✅ Percentages (92%, 65%, etc.)
✅ Dates (2020-2026 timeline)
✅ Entity relationships
✅ Confidence metrics

Output: visuals.json
{
  "charts": [
    {"type": "bar", "title": "...", "data": [...]}
  ],
  "timeline": {...},
  "metrics": {"money": [...], "percentages": [...]},
  "networks": [...]
}
```

### 3️⃣ Phase 3: PDF Generator (Sequential)
```python
# Inputs: report_text.md + visuals.json + graph.json
# Time: ~15-30 seconds

Merges components:
- Report text (main content)
- Generated charts (from visuals.json)
- Visual networks (relationships)
- Timeline visualization
- Metrics summary

Output: final_report.pdf
```

## Data Flows

### Sequential Dependencies
```
graph.json (from Research)
    ↓
    ├→ Synthesis Agent ──→ report_text.md ──┐
    │                                        ├→ PDF Generator → final_report.pdf
    └→ Visual Analyst ───→ visuals.json ────┘
```

### Parallel Execution
```
graph.json
    ├→ [Synthesis] (30-60s) ──┐
    │                          ├→ Merge outputs
    └→ [Visual Analyst] (15-30s) ┘

Time saved: ~20-40 seconds vs sequential
```

## Key Files

```
backend/
├── orchestrator.py                          # Main orchestration engine
├── AGENT_ORCHESTRATION.md                  # Architecture overview
├── ORCHESTRATION_WORKFLOW.md                # This file
├── agents_v4.json                          # 4-agent configuration
│
├── graph/
│   └── hitl_engine.py                      # Research Agent impl
│
├── pdf_generator.py                        # PDF Generator
│
└── agents_code/
    ├── agent-bot-1774568580435/            # Research Agent
    │   └── knowledge/
    │       ├── graph.json                  # Research output
    │       ├── ledger.json
    │       └── scratchpad.json
    │
    ├── Visual_Analyst/                     # NEW: Visual Analyst
    │   ├── main.py
    │   ├── personality.json
    │   └── visuals.json                    # Visual output (dummy)
    │
    └── synthesis_agent/                    # Synthesis Agent
        └── (existing implementation)
```

## Usage Example

```python
import asyncio
from orchestrator import Agent4Orchestrator

async def main():
    orchestrator = Agent4Orchestrator(
        agent_id="orchestrator-001",
        working_dir="path/to/knowledge/dir"
    )

    state = {
        "agent_id": "my-research-001",
        "goal": "Research AI developments in 2025-2026",
        "api_key": os.getenv("GOOGLE_API_KEY"),
        "user_effort": 5  # 1-10 scale
    }

    # Stream results as SSE events
    async for event in orchestrator.orchestrate(state):
        print(event)  # Each is a JSON SSE line
        # Forward to frontend for real-time updates

asyncio.run(main())
```

## Expected Output Structure

```
knowledge_dir/
├── graph.json                    # Research Agent output
├── report_text.md                # Synthesis Agent output
├── visuals.json                  # Visual Analyst output
├── final_report.pdf              # PDF Generator output
├── ledger.json                   # Execution metadata
└── communication.log             # Agent activity log
```

## Configuration

### agents_v4.json Schema
```json
{
  "id": "agent-unique-id",
  "name": "Display Name",
  "brain": "gemini-3.1-pro-preview",
  "phase": 1|2|3,                         // Execution order
  "parallelizable": true|false,           // Can run with others
  "input": "phase_input_spec",
  "output": "phase_output_spec",
  "permissions": ["..."],
  "status": "implemented|new|planned"
}
```

## Monitoring & Debugging

### Phase-Based Logging
Each agent logs:
- Start/end timestamps
- Input/output paths
- Success/failure status
- Performance metrics
- Error details

### SSE Events
```
data: {
  "phase": "RESEARCH|SYNTHESIS|VISUAL_ANALYST|PDF_GENERATION|COMPLETE",
  "status": "starting|completed|error",
  "message": "Human-readable update",
  "timestamp": "2026-03-27T10:30:00Z",
  "stats": {...}
}
```

## Performance Targets

| Phase | Time | Model | Bottleneck |
|-------|------|-------|-----------|
| Research | 5-15m | Gemini 2 Flash | Web scraping |
| Synthesis | 30-60s | Gemini 3 Pro | LLM processing |
| Visual | 15-30s | Gemini 3.1 Pro | Pattern detection |
| PDF | 15-30s | Gemini 2 Flash | Rendering |
| **Total** | **5-16m** | Mixed | Research |

**Parallel execution saves:** ~50-70 seconds on synthesis + visual phases

## Next Steps

1. ✅ Create Visual Analyst Agent (DONE)
2. ⏳ Integrate with existing Synthesis Agent
3. ⏳ Test with real data flows
4. ⏳ Add chart rendering in PDF
5. ⏳ Implement frontend visualization

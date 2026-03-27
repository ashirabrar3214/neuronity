# Live Workflow Execution Guide

## How the 3-Agent Workflow Works

When you run a workflow, you'll see **real-time agent-to-agent communication** on the canvas.

---

## What Happens Step-by-Step

### Phase 1: Research Agent Works 🔍

**Duration:** 5-10 seconds (simulated)

```
┌──────────────────────────────────────┐
│ Research Agent [MASTER]              │
│ Status: WORKING 🟠                   │
├──────────────────────────────────────┤
│ Progress: ████████░░ 80%             │
│                                      │
│ LIVE BACKEND:                        │
│ > Searching for resources...         │
│ > Scraping page 1 of 5               │
│ > Building knowledge graph...        │
│ > Extracted 89 facts                 │
│ > Knowledge map complete ✓           │
│                                      │
│ 📊 Stats:                            │
│  Sources: 5                          │
│  Facts: 89                           │
│  Nodes: 247                          │
│  Edges: 1043                         │
└──────────────────────────────────────┘
     ↓ passes knowledge.json
```

**What the agent does:**
1. 🔍 Searches for relevant web pages
2. 📄 Scrapes content from each page
3. 🔗 Extracts facts and links sources
4. 📊 Builds knowledge graph with nodes and edges
5. 💾 Creates `knowledge.json` with all findings

**Output:** `knowledge.json` (89 facts, 247 nodes, 1043 edges)

---

### Phase 2: Analyst Agent Works 📖

**Duration:** 5-10 seconds (simulated)

```
     knowledge.json arrives
            ↓
┌──────────────────────────────────────┐
│ Analyst Agent [WORKER]               │
│ Status: WORKING 🟠                   │
├──────────────────────────────────────┤
│ Progress: ███████░░░ 75%             │
│                                      │
│ LIVE BACKEND:                        │
│ > Reading knowledge map (89 facts)   │
│ > Analyzing relationships...         │
│ > Identifying patterns...            │
│ > Drawing conclusions...             │
│ > Analysis complete ✓                │
│                                      │
│ 📊 Stats:                            │
│  Insights: 42                        │
│  Patterns: 7                         │
│  Confidence: 0.87 avg               │
│  Sections: 5                         │
└──────────────────────────────────────┘
     ↓ passes analysis.json
```

**What the agent does:**
1. 📖 Reads the knowledge graph
2. 🔍 Analyzes relationships between facts
3. 💡 Identifies patterns in the data
4. 🎯 Draws conclusions and insights
5. 📝 Creates `analysis.json` with findings

**Output:** `analysis.json` (42 insights, 7 patterns, 0.87 confidence)

---

### Phase 3: PDF Generator Works 📑

**Duration:** 5-10 seconds (simulated)

```
     analysis.json arrives
            ↓
┌──────────────────────────────────────┐
│ PDF Generator [WORKER]               │
│ Status: WORKING 🟠                   │
├──────────────────────────────────────┤
│ Progress: ███████░░░ 85%             │
│                                      │
│ LIVE BACKEND:                        │
│ > Reading analysis data...           │
│ > Formatting sections...             │
│ > Embedding visualizations...        │
│ > Creating table of contents...      │
│ > Generating PDF...                  │
│ > Report saved ✓                     │
│                                      │
│ 📊 Stats:                            │
│  Pages: 18                           │
│  File size: 2048 KB                 │
│  Generated: 2026-03-27T10:32:45Z    │
└──────────────────────────────────────┘
     ↓
  report.pdf created ✓
```

**What the agent does:**
1. 📑 Reads the analysis results
2. 🎨 Formats sections with headers and organization
3. 📊 Embeds charts and visualizations
4. 📑 Creates professional table of contents
5. 💾 Generates final `report.pdf`

**Output:** `report.pdf` (18 pages, 2048 KB)

---

## Canvas Display During Execution

### Before Workflow Starts
```
Research Agent          Analyst Agent          PDF Generator
   (Left)                (Center)               (Right)
┌─────────────┐       ┌──────────────┐      ┌──────────────┐
│ MASTER      │──────→│ WORKER       │─────→│ WORKER       │
│ Ready       │       │ Idle         │      │ Idle         │
└─────────────┘       └──────────────┘      └──────────────┘
```

### During Execution
```
Research Agent          Analyst Agent          PDF Generator
   (Left)                (Center)               (Right)
┌─────────────┐       ┌──────────────┐      ┌──────────────┐
│ MASTER      │ data  │ WORKER       │ data │ WORKER       │
│ 🟠 WORKING  │──────→│ 🟠 WAITING   │─────→│ 🔵 IDLE      │
│ 80% ████░░  │       │ reading...   │      │ waiting...   │
└─────────────┘       └──────────────┘      └──────────────┘
                            ↓
                      [analyzing facts]
```

### After Each Phase Completes
```
Phase 1 Done:          Phase 2 Done:          Phase 3 Done:
┌─────────────┐       ┌──────────────┐      ┌──────────────┐
│ MASTER      │       │ WORKER       │      │ WORKER       │
│ 🟢 COMPLETE │───→   │ 🟠 WORKING   │──→   │ 🔵 IDLE      │
│ Data ready  │  data │ 75% ███░░░   │ data │ waiting...   │
└─────────────┘       └──────────────┘      └──────────────┘
                            ↓                      ↓
                      [analyzing]              [waiting]
```

### Fully Complete
```
┌─────────────┐       ┌──────────────┐      ┌──────────────┐
│ MASTER      │       │ WORKER       │      │ WORKER       │
│ 🟢 COMPLETE │ data  │ 🟢 COMPLETE  │ data │ 🟢 COMPLETE  │
│ Done ✓      │───→   │ Done ✓       │──→   │ Done ✓       │
└─────────────┘       └──────────────┘      └──────────────┘

Status: ✓ Workflow complete! All agents finished.
```

---

## Visual Indicators

### Agent Status Colors
- **🔵 Idle (Blue):** Waiting for data, not working
- **🟠 Working (Orange):** Currently processing data
- **🟢 Complete (Green):** Finished, work done

### Progress Bars
- **Width:** Shows % complete (0-100%)
- **Color:** Orange gradient while working, green when done
- **Text:** Displays percentage (0%, 25%, 75%, etc.)

### Connection Lines Between Agents
- **Gray:** Idle (no data flow)
- **Orange glow:** Active data flow
- **Animated pulse:** Data being transferred

---

## Terminal Output

Each agent shows a live terminal with what it's doing:

**Research Agent Terminal:**
```
> Agent initialized...
[10:30:45] Searching for relevant resources...
[10:30:46] Scraping page 1 of 5: AI Research
[10:30:47] Scraping page 2 of 5: Deep Learning
[10:30:48] Scraping page 3 of 5: NLP Models
[10:30:49] Scraping page 4 of 5: Training Data
[10:30:50] Scraping page 5 of 5: Applications
[10:30:51] Linking sources to facts...
[10:30:52] Building knowledge graph (247 nodes, 1,043 edges)
[10:30:53] Extracted 89 facts with confidence scores
[10:30:54] Knowledge map complete ✓
[10:30:55] Passing data to Analyst Agent...
```

**Analyst Agent Terminal:**
```
> Agent initialized...
[10:30:55] Waiting for Research Agent...
[10:30:56] Received knowledge.json (89 facts)
[10:30:57] Reading knowledge map...
[10:30:58] Analyzing fact relationships...
[10:30:59] Identifying key patterns...
[10:31:00] Drawing conclusions from data...
[10:31:01] Generating insights...
[10:31:02] Analysis complete (42 insights found)
[10:31:03] Confidence scores: avg 0.87, min 0.72, max 0.96
[10:31:04] Passing data to PDF Generator...
```

**PDF Generator Terminal:**
```
> Agent initialized...
[10:31:04] Waiting for Analyst Agent...
[10:31:05] Received analysis.json
[10:31:06] Reading analysis data...
[10:31:07] Formatting sections...
[10:31:08] Embedding visualizations...
[10:31:09] Creating table of contents...
[10:31:10] Generating PDF (18 pages)...
[10:31:11] Adding metadata...
[10:31:12] Saving report.pdf ✓
[10:31:13] Workflow complete!
```

---

## Data Files Created

### knowledge.json (Created by Research Agent)
```json
{
    "sources": 5,
    "facts": 89,
    "topics": 12,
    "edges": 1043,
    "timestamp": "2026-03-27T10:30:54Z"
}
```

### analysis.json (Created by Analyst Agent)
```json
{
    "insights": 42,
    "patterns_found": 7,
    "confidence_avg": 0.87,
    "sections": 5,
    "timestamp": "2026-03-27T10:31:04Z"
}
```

### report.pdf (Created by PDF Generator)
```
18-page professional report with:
- Executive summary
- Research findings
- Analysis and insights
- Charts and visualizations
- Conclusions and recommendations
```

---

## How to Run a Workflow

1. **Create the workflow:**
   - Click "Add Workflow"
   - Select "Deep Web Research Workflow"
   - 3 agents appear on canvas

2. **Configure (optional):**
   - Click on Research Agent
   - Click "Configure & Train"
   - Enter research query
   - Adjust other settings

3. **Start workflow:**
   - Click "Start" or "Run Workflow" button
   - Workflow begins executing

4. **Watch progress:**
   - See each agent working in real-time
   - Read terminals for detailed logs
   - Watch progress bars fill up
   - See connection lines animate with data flow

5. **Get results:**
   - When complete, download `report.pdf`
   - Check `knowledge.json` and `analysis.json` in output folder

---

## Files for This System

| File | Purpose |
|------|---------|
| `agent_workflow.py` | Orchestrates 3-agent execution |
| `workflow_api.py` | REST API endpoints for workflow control |
| `workflow-executor.js` | Canvas updates from workflow events |
| `workflow-progress.css` | Animations and visual styling |
| `3_AGENT_WORKFLOW.md` | This guide |

---

## Architecture Diagram

```
Canvas Display (Frontend)
    ↑
    │ SSE Events (streaming)
    │
Workflow API (Backend)
    ↑
    │ Start request
    │
Agent Workflow Orchestrator
    │
    ├→ Research Agent (Phase 1)
    │  └→ knowledge.json
    │
    ├→ Analyst Agent (Phase 2)
    │  └→ analysis.json
    │
    └→ PDF Generator (Phase 3)
       └→ report.pdf
```

---

**Status:** ✅ Ready to execute 3-agent workflows with live canvas updates!

Start the backend and try running a workflow to see real-time agent-to-agent communication! 🚀

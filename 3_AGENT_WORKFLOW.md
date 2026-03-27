# 3-Agent Workflow with Visible Communication

## New Architecture

**Removed:** Visual Analyst Agent
**New Focus:** Real agent-to-agent communication with progress visibility

---

## 3-Agent Pipeline

```
Research Agent (Left)
    ↓ scrapes resources
    ↓ builds knowledge.json
    ↓
Analyst Agent (Center)
    ↓ reads knowledge.json
    ↓ analyzes findings
    ↓ creates analysis.json
    ↓
PDF Generator (Right)
    ↓ reads analysis.json
    ↓ creates report.pdf
```

---

## Agent Work Breakdown

### 1️⃣ Research Agent (Master)
**What it does:**
- 🔍 Searches for relevant resources
- 📄 Scrapes web pages
- 🔗 Links sources to facts
- 📊 Builds knowledge graph (nodes + edges)
- 💾 Outputs: `knowledge.json`

**Canvas Display:**
```
┌──────────────────────────┐
│ Research Agent [MASTER]  │
├──────────────────────────┤
│ 📄 Scraping page 1 of 5  │
│ ████████░░ 80%           │
│                          │
│ 🔗 Built: 247 nodes      │
│ 📊 1,043 edges           │
└──────────────────────────┘
```

---

### 2️⃣ Analyst Agent (Worker)
**What it does:**
- 📖 Reads knowledge graph
- 🔍 Analyzes fact relationships
- 💡 Identifies patterns
- 🎯 Draws conclusions
- 📝 Generates insights
- 💾 Outputs: `analysis.json`

**Canvas Display:**
```
┌──────────────────────────┐
│ Analyst Agent [WORKER]   │
├──────────────────────────┤
│ 📖 Reading 89 facts      │
│ 💡 Identifying patterns  │
│ ████████░░ 75%           │
│                          │
│ 📊 42 insights found     │
│ 📈 Avg confidence: 0.87  │
└──────────────────────────┘
```

---

### 3️⃣ PDF Generator (Worker)
**What it does:**
- 📑 Reads analysis data
- 🎨 Formats sections
- 📊 Embeds visualizations
- 📑 Creates table of contents
- 💾 Outputs: `report.pdf`

**Canvas Display:**
```
┌──────────────────────────┐
│ PDF Generator [WORKER]   │
├──────────────────────────┤
│ 📑 Generating PDF...     │
│ ████████░░ 85%           │
│                          │
│ 📑 Pages: 18             │
│ 💾 Size: 2048 KB         │
└──────────────────────────┘
```

---

## Live Canvas Display

When you run a workflow, you'll see:

```
RESEARCH AGENT                ANALYST AGENT              PDF GENERATOR
(Left)                        (Center)                   (Right)
┌─────────────────┐          ┌─────────────────┐        ┌─────────────────┐
│ 🔍 Research     │    →     │ 📖 Analyst      │   →    │ 📑 PDF          │
│ [MASTER]        │          │ [WORKER]        │        │ [WORKER]        │
├─────────────────┤          ├─────────────────┤        ├─────────────────┤
│ Scraping...     │          │ Reading...      │        │ Generating...   │
│ ████░░ 40%      │   data   │ ████████░░ 80% │  data  │ ███████░░ 70%   │
│                 │ ------→  │                 │ ---→   │                 │
│ Sources: 12     │          │ Patterns: 7     │        │ Pages: 18       │
│ Facts: 89       │          │ Insights: 42    │        │ Size: 2048 KB   │
│ Edges: 1043     │          │ Confidence: 0.87│        │ Status: Done ✓  │
└─────────────────┘          └─────────────────┘        └─────────────────┘

Timeline at bottom:
[WORKFLOW START] → [Research Agent running...] → [Analyst reading knowledge.json]
                 → [PDF reading analysis.json] → [WORKFLOW COMPLETE] ✓
```

---

## Agent Communication Flow

### Step 1: Research → Analyst
```
Research Agent creates knowledge.json:
{
    "sources": 5,
    "facts": 89,
    "topics": 12,
    "edges": 1043,
    "timestamp": "2026-03-27T10:30:45Z"
}
           ↓ passes file
Analyst Agent reads it and starts analyzing
```

### Step 2: Analyst → PDF Generator
```
Analyst Agent creates analysis.json:
{
    "insights": 42,
    "patterns_found": 7,
    "confidence_avg": 0.87,
    "sections": 5,
    "timestamp": "2026-03-27T10:31:45Z"
}
           ↓ passes file
PDF Generator reads it and starts creating report
```

### Step 3: Final Output
```
PDF Generator creates report.pdf:
{
    "pages": 18,
    "file_size_kb": 2048,
    "timestamp": "2026-03-27T10:32:45Z"
}
           ↓
Final report ready to download/view
```

---

## Terminal/Log View

Each agent shows live progress in their terminal:

**Research Agent Terminal:**
```
> Agent initialized...
> Searching for relevant resources...
> Scraping page 1 of 5: AI Research
> Scraping page 2 of 5: Deep Learning
> Scraping page 3 of 5: NLP Models
> Scraping page 4 of 5: Training Data
> Scraping page 5 of 5: Applications
> Linking sources to facts...
> Building knowledge graph (247 nodes, 1,043 edges)
> Extracted 89 facts with confidence scores
> Knowledge map complete ✓
> Passing data to Analyst Agent...
```

**Analyst Agent Terminal:**
```
> Agent initialized...
> Waiting for Research Agent to complete...
> Received knowledge.json (89 facts)
> Reading knowledge map...
> Analyzing fact relationships...
> Identifying key patterns...
> Drawing conclusions from data...
> Generating insights...
> Analysis complete (42 insights found)
> Confidence scores: avg 0.87, min 0.72, max 0.96
> Passing data to PDF Generator...
```

**PDF Generator Terminal:**
```
> Agent initialized...
> Waiting for Analyst Agent to complete...
> Received analysis.json
> Reading analysis data...
> Formatting sections...
> Embedding visualizations...
> Creating table of contents...
> Generating PDF (18 pages)...
> Adding metadata...
> Saving report.pdf ✓
> Workflow complete!
```

---

## Changes Made

### 1. Removed Visual Analyst
- ✅ Deleted from workflow template
- ✅ Updated layout to 3 agents
- ✅ Simplified orchestration

### 2. Created Agent Workflow Engine
- ✅ `backend/agent_workflow.py` - Orchestrates agent communication
- ✅ Shows real-time progress
- ✅ Streams events to canvas
- ✅ Tracks data passing between agents

### 3. Updated Canvas Layout
- ✅ 3 agents in linear layout (left → center → right)
- ✅ Shows agent progress and stats
- ✅ Displays agent-to-agent data flow

---

## Data Passing

```
Research Agent
    ↓
    knowledge.json (89 facts, 247 nodes)
    ↓
Analyst Agent
    ↓
    analysis.json (42 insights, patterns)
    ↓
PDF Generator
    ↓
    report.pdf (18 pages)
```

---

## Files Updated

| File | Changes |
|------|---------|
| `agent-training.js` | Removed Visual Analyst, 3-agent workflow |
| `canvas.js` | Updated layout for 3 agents (left-center-right) |
| `agent_workflow.py` | NEW - Agent orchestration & communication |

---

## How It Works

1. **User starts workflow** with a query
2. **Research Agent begins:**
   - Shows scraping progress on canvas
   - Builds knowledge graph
   - Creates `knowledge.json`
3. **Analyst Agent receives data:**
   - Reads `knowledge.json`
   - Shows analysis progress
   - Creates `analysis.json`
4. **PDF Generator receives data:**
   - Reads `analysis.json`
   - Shows generation progress
   - Creates `report.pdf`
5. **Workflow complete:**
   - All agents show ✓ status
   - Report ready to download

---

## Status: ✅ Ready to Test

3-agent workflow with visible communication is ready!

**Next:** Start backend and click "Add Workflow" to see agents work! 🚀

# Deep Web Research Workflow - Quick Reference

## What Changed?

### Before
- Button said "Add Agent"
- Modal said "Your Agents"
- Had to manually add 4 separate agents
- No automatic connections

### After ✨
- Button says "Add Workflow"
- Modal says "Workflows"
- **One click** adds all 4 agents pre-connected
- Automatic layout and connections

## How to Use

### Step 1: Click "Add Workflow"
```
Bottom-left corner of canvas → Click "Add Workflow" button
```

### Step 2: Select "Deep Web Research Workflow"
```
Modal opens with workflow options:
- Custom Agent (blank template)
- Deep Web Researcher (single agent)
- Deep Web Research Workflow ⭐ NEW (4 agents)
```

### Step 3: Instant 4-Agent System
```
All 4 agents appear on canvas:

┌────────────────────────┐
│  1. Research Agent     │  ← Gemini 2.0 Flash
│  Scrapes web sources   │
└────────────────────────┘
           ↓ connects to both:
    ┌──────┴──────┐
    │             │
┌───────────┐  ┌──────────────┐
│ Synthesis │  │Visual Analyst│  ← Gemini 3 Pro & 3.1 Pro
│  Agent    │  │   Agent      │
└─────┬─────┘  └──────┬───────┘
      │               │
      └───────┬───────┘
              ↓
        ┌────────────┐
        │    PDF     │  ← Gemini 2.0 Flash
        │ Generator  │
        └────────────┘
```

## Agents in the Workflow

### 1️⃣ Research Agent (Top)
- **Input:** User query about topic
- **Process:** Scrapes 20+ sources, extracts facts, builds knowledge graph
- **Output:** `graph.json` with facts, sources, topics
- **Time:** 5-15 minutes
- **Model:** Gemini 2.0 Flash (fast)

### 2️⃣ Synthesis Agent (Middle-Left)
- **Input:** `graph.json` from Research
- **Process:** Reads facts, generates insights, writes analytical prose
- **Output:** `report_text.md` with polished narrative
- **Time:** 30-60 seconds
- **Model:** Gemini 3.0 Pro (reasoning)
- **Runs in Parallel** with Visual Analyst

### 3️⃣ Visual Analyst Agent (Middle-Right) ⭐ NEW
- **Input:** `graph.json` from Research
- **Process:** Extracts percentages, money values, dates, relationships
- **Output:** `visuals.json` with chart specs, timelines, metrics
- **Time:** 15-30 seconds
- **Model:** Gemini 3.1 Pro (pattern detection)
- **Runs in Parallel** with Synthesis

### 4️⃣ PDF Generator (Bottom)
- **Input:** `report_text.md` + `visuals.json`
- **Process:** Merges text and charts, formats professionally
- **Output:** `final_report.pdf` with integrated visuals
- **Time:** 15-30 seconds
- **Model:** Gemini 2.0 Flash (fast)

## Data Flow

```
User Query (e.g., "Research AlphaFold glycan prediction")
    ↓
[Research Agent] ──→ graph.json (20+ sources, 50+ facts)
    ↓
    ├→ [Synthesis Agent] ──→ report_text.md (analytical prose)
    │  (30-60 seconds)
    │
    └→ [Visual Analyst] ──→ visuals.json (4 charts, timeline, metrics)
       (15-30 seconds, PARALLEL)

    ↓
[PDF Generator] ──→ final_report.pdf (complete report)
    (15-30 seconds)

✓ Total Time: 5-16 minutes (Research is bottleneck)
  Parallel processing saves ~50 seconds!
```

## What Each Agent Extracts

### Graph.json (Research Agent)
```json
{
  "nodes": [
    {"id": "src_001", "type": "source", "url": "..."},
    {"id": "fact_001", "type": "fact", "content": "...", "confidence": 0.95},
    {"id": "topic_xyz", "type": "topic", "label": "..."}
  ],
  "links": [{"source": "fact_001", "target": "topic_xyz"}]
}
```

### Visuals.json (Visual Analyst)
```json
{
  "charts": [
    {"type": "bar", "title": "Key Percentages", "data": [...]}
  ],
  "timeline": {
    "events": [
      {"date": "2026-03-15", "event": "..."}
    ]
  },
  "metrics": {
    "money": [{"value": "$500M", "context": "..."}],
    "percentages": [{"value": 92, "context": "..."}],
    "quantities": [{"value": "200M", "unit": "structures"}]
  },
  "networks": [{...}]
}
```

### Report_text.md (Synthesis Agent)
```markdown
# Research Report: AlphaFold Glycan Prediction

## Executive Summary
More than half of all human proteins are glycosylated...

## Key Findings
1. AlphaFold has revealed millions of protein structures
2. Glycan prediction accuracy is 68% (vs 92% for proteins)
3. Industry adoption growing rapidly

## Detailed Analysis
...
```

### final_report.pdf (PDF Generator)
```
📄 Professional PDF with:
- Formatted report text
- Embedded charts and graphs
- Timeline visualization
- Metrics and statistics
- Professional styling
- Table of contents
```

## Workflow Performance

| Phase | Time | Parallel? | Notes |
|-------|------|-----------|-------|
| Research | 5-15m | ❌ | Sequential, web-dependent |
| Synthesis | 30-60s | ✅ | Runs with Visual |
| Visual Analyst | 15-30s | ✅ | Runs with Synthesis |
| PDF Generation | 15-30s | ❌ | Depends on both |
| **Total** | **5-16m** | ~50% | Parallel saves time |

## Configuration Details

Each agent has pre-configured:
- ✅ Model choice (Gemini 2.0, 3.0, 3.1 Pro)
- ✅ Permissions (scrape, synthesis, visualization, etc.)
- ✅ Brain (LLM model)
- ✅ Agent type (specialist)
- ✅ Responsibility (what phase they handle)

All customizable later via training panel!

## Automatic Connections

When workflow created, connections auto-established:
```
Research → Synthesis (passes graph.json)
Research → Visual Analyst (passes graph.json)
Synthesis → PDF Generator (passes report_text.md)
Visual Analyst → PDF Generator (passes visuals.json)
```

Visible as lines between agents on canvas.

## Testing the Workflow

### Quick Test
1. Click "Add Workflow"
2. Select "Deep Web Research Workflow"
3. Should see 4 agents appear in vertical stack
4. Check connections (lines between agents)
5. All agents have correct names and descriptions

### Full Integration Test
1. Right-click on Research Agent → Configure & Train
2. Enter research query (e.g., "AlphaFold developments")
3. Set user_effort to 5 (medium thoroughness)
4. Run workflow
5. Monitor progress in agent terminals
6. Check output folder for graph.json, report.md, visuals.json, final.pdf

## Troubleshooting

**Q: Only 1 agent appearing?**
- A: Check browser console for errors, reload page, try again

**Q: Agents not connected?**
- A: Check that `connectNodes()` is being called (it should auto-happen)
- Manually draw connection by dragging from one agent's right port to another's left port

**Q: Backend error creating agents?**
- A: Ensure `http://localhost:8000` is running
- Check Python logs: `python interpreter.py`

**Q: Visual Analyst not working?**
- A: Ensure `backend/agents_code/Visual_Analyst/` folder exists
- Check that graph.json was properly generated by Research Agent

## Key Advantages

✨ **One-Click Setup** - All 4 agents ready instantly
✨ **Auto-Connected** - Proper data flow established
✨ **Optimized Layout** - Vertical stack is clean and readable
✨ **Pre-Configured** - Each agent has correct settings
✨ **Parallel Processing** - Synthesis + Visual run together
✨ **Complete Pipeline** - From research to PDF delivery

## Architecture Behind the Scenes

### Frontend (canvas.js)
```javascript
// When "Deep Web Research Workflow" clicked:
addWorkflowAgents(workflow) {
  // Create 4 agents in sequence
  // Auto-position them vertically
  // Auto-connect in proper order
  // Send all to backend
}
```

### Backend Integration
- Each agent sends POST to `/agents` endpoint
- Backend stores in agents database
- Connections saved in agent metadata
- Ready for orchestration via `orchestrator.py`

### Orchestration (orchestrator.py)
```python
# When workflow runs:
1. Research Agent → graph.json (5-15m)
2. Synthesis Agent + Visual Analyst → parallel (30-60s)
3. PDF Generator → final_report.pdf (15-30s)
# Total: 5-16m with parallel efficiency
```

---

**Status:** ✅ Ready to Use
**Version:** 1.0
**Date:** March 27, 2026

🚀 **Next:** Click "Add Workflow" and select "Deep Web Research Workflow"!

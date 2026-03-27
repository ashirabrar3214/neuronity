# 4-Agent Orchestration System

## Visual Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER QUERY                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  1. RESEARCH AGENT             │
        │  (Gemini 2.0 Flash)            │
        │                                │
        │  • Web scraping & verification │
        │  • Populates: graph.json       │
        │  • Extracts facts, sources     │
        │  • Confidence scoring          │
        │                                │
        │  Input: {goal, query}          │
        │  Output: graph.json            │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  2. SYNTHESIS AGENT            │
        │  (Gemini 3.0 Pro)              │
        │                                │
        │  • Analytical writing          │
        │  • Contextual narrative        │
        │  • Insight generation          │
        │                                │
        │  Input: graph.json             │
        │  Output: report_text.md        │
        └────────┬───────────────────────┘
                 │
        ┌────────┴──────────────────────┐
        │                               │
        ▼                               ▼
┌─────────────────────────┐  ┌──────────────────────────┐
│  3a. VISUAL ANALYST     │  │  4. PDF GENERATOR        │
│  (Gemini 3.1 Pro)       │  │  (Gemini 2.0 Flash)      │
│                         │  │                          │
│  • Scans graph.json     │  │  • Merges text + visuals │
│  • Extracts metrics:    │  │  • Generates PDF         │
│    - Money values       │  │  • Formatting & layout   │
│    - Percentages        │  │                          │
│    - Dates              │  │  Input: report_text.md,  │
│  • Chart suggestions    │  │          visuals.json    │
│                         │  │  Output: final_report.pdf
│  Input: graph.json      │  └──────────────────────────┘
│  Output: visuals.json   │
└─────────────┬───────────┘
              │
              └──────────┬──────────────┘
                         │
                         ▼
               ┌──────────────────────┐
               │  FINAL REPORT PDF    │
               │  (Text + Visuals)    │
               └──────────────────────┘
```

## Agent Configuration

### 1. Research Agent
- **Model**: Gemini 2.0 Flash (fast scraping)
- **Role**: Deep web researcher with recursive verification
- **Output**: `graph.json` (facts, sources, topics)
- **Status**: ✅ Already implemented

### 2. Synthesis Agent
- **Model**: Gemini 3.0 Pro (reasoning)
- **Role**: Analytical writing and insight generation
- **Output**: `report_text.md`
- **Status**: ✅ Already implemented

### 3. Visual Analyst Agent ⭐ NEW
- **Model**: Gemini 3.1 Pro (pattern detection)
- **Role**: Extract structured data for visualization
- **Input**: `graph.json`
- **Output**: `visuals.json`
- **Extracts**:
  - Monetary values with context
  - Percentages and metrics
  - Timeline data
  - Relationship networks
- **Status**: 🔨 New agent to build

### 4. PDF Generator
- **Model**: Gemini 2.0 Flash (fast formatting)
- **Role**: Merge text and visuals into final PDF
- **Status**: ✅ Already implemented

## Data Flow

```
graph.json (Research)
    ├─→ [Synthesis Agent] ──→ report_text.md
    │
    └─→ [Visual Analyst] ──→ visuals.json
            │
            └─→ [PDF Generator] ──→ final_report.pdf
                  (with report_text.md)
```

## Orchestration Engine

The orchestrator will:
1. Run Research Agent → graph.json
2. Trigger Synthesis Agent (background)
3. Trigger Visual Analyst Agent (parallel)
4. Merge outputs via PDF Generator
5. Return final PDF

## Visuals.json Schema

```json
{
  "metadata": {
    "generated_at": "2026-03-27T10:30:00Z",
    "agent_version": "v1"
  },
  "charts": [
    {
      "id": "chart_001",
      "type": "bar|pie|line|timeline",
      "title": "Chart Title",
      "data": [...],
      "source_facts": ["fact_001", "fact_002"],
      "confidence": 0.95
    }
  ],
  "timeline": {
    "events": [
      {"date": "2026-01-15", "event": "...", "source": "src_001"}
    ]
  },
  "metrics": {
    "money": [...],
    "percentages": [...],
    "comparisons": [...]
  },
  "networks": [
    {
      "id": "net_001",
      "label": "Entity relationships",
      "nodes": [...],
      "edges": [...]
    }
  ]
}
```

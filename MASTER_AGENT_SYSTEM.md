# Master Agent System - Implementation Details

## Overview

The Research Agent is the **Master Agent** for each workflow. When deleted, the entire workflow (all 4 agents) is deleted.

---

## Changes Made

### 1. ✅ Research Agent Marked as Master
**File:** `agent-training.js`

```javascript
{
    name: 'Research Agent',
    // ... other config ...
    agentType: 'master',        // ← NEW
    workflowId: true,           // ← NEW - tracks workflow membership
}
```

### 2. ✅ Workflow ID Tracking
**File:** `canvas.js` - `addWorkflowAgents()`

When creating a workflow, each agent stores:
- `workflowId`: Unique identifier for the workflow
- `agentType`: 'master' for Research, 'worker' for others

```javascript
const workflowId = `workflow-${Date.now()}`;

const newAgent = {
    id,
    name: agentTemplate.name,
    // ... other fields ...
    workflowId: workflowId,     // All agents in same workflow
    agentType: agentTemplate.agentType || 'worker'
};
```

### 3. ✅ Dynamic Delete Button Text
**File:** `canvas.js` - `createNode()`

Delete button text changes based on agent type:
- **Master Agent:** "Delete Workflow"
- **Worker Agent:** "Delete Agent"

```javascript
const updateDeleteButtonText = () => {
    const agentType = data.agentType || 'worker';
    const btnText = agentType === 'master' ? 'Delete Workflow' : 'Delete Agent';
    deleteBtn.textContent = btnText;
    deleteBtn.title = agentType === 'master'
        ? 'Delete entire workflow (all 4 agents)'
        : 'Delete this agent only';
};
```

### 4. ✅ Smart Delete Logic
**File:** `canvas.js` - `deleteAgent()`

When deleting a master agent:
1. Finds all agents with same `workflowId`
2. Deletes **all agents** in the workflow
3. Deletes all **connections** between them
4. Updates confirmation message to show scope

```javascript
async deleteAgent(agentId, agentData) {
    // Check if master agent
    const isMaster = agentData && agentData.agentType === 'master';
    const workflowId = agentData && agentData.workflowId;

    let agentsToDelete = [agentId];

    // If master agent, get all agents in workflow
    if (isMaster && workflowId) {
        agentsToDelete = this.nodes
            .filter(n => n.data && n.data.workflowId === workflowId)
            .map(n => n.id);
    }

    // Delete all agents
    for (const id of agentsToDelete) {
        // DELETE request to backend
        // Remove from UI
    }
}
```

---

## Behavior

### Creating a Workflow
```
Click "Add Workflow"
    ↓
Select "Deep Web Research Workflow"
    ↓
4 agents created:
  1. Research Agent (MASTER) ← Can delete entire workflow
  2. Synthesis Agent (WORKER)
  3. Visual Analyst (WORKER)
  4. PDF Generator (WORKER)
```

### Deleting the Master Agent
```
Right-click Research Agent → Expand settings
    ↓
Click "Delete Workflow" button
    ↓
Confirmation: "Are you sure you want to delete the entire workflow? This cannot be undone."
    ↓
Click OK
    ↓
All 4 agents deleted instantly
All connections removed
Canvas cleaned up
```

### Deleting a Worker Agent
```
Right-click Synthesis/Visual/PDF Agent
    ↓
Click "Delete Agent" button
    ↓
Confirmation: "Are you sure you want to delete 'Agent Name'? This cannot be undone."
    ↓
Click OK
    ↓
Only that agent deleted
Other agents remain
Connections to that agent removed
```

---

## UI Changes

### Delete Button States

**Master Agent:**
```
┌─────────────────────┐
│ Research Agent      │
│ [MASTER]            │
├─────────────────────┤
│ Working Dir: Not set│
│ [Configure & Train] │
│ [Delete Workflow] ← Red button (dangerous)
└─────────────────────┘
```

**Worker Agent:**
```
┌──────────────────────┐
│ Synthesis Agent      │
│ [WORKER]             │
├──────────────────────┤
│ Working Dir: Not set │
│ [Configure & Train]  │
│ [Delete Agent] ← Gray button (safe)
└──────────────────────┘
```

---

## Data Structure

### Agent Data with Workflow Info
```javascript
{
    id: "agent-bot-1234567890",
    name: "Research Agent",
    description: "Scrapes full articles...",
    x: 150,
    y: 200,
    brain: "gemini-2.0-flash",
    agentType: "master",           // ← Master or Worker
    workflowId: "workflow-1234567", // ← Groups agents
    permissions: [...],
    specialRole: "deep-web-researcher",
    responsibility: "Phase 1: ..."
}
```

---

## Safety Features

✅ **Confirmation Dialog** - User must confirm deletion
✅ **Clear Messaging** - Different text for workflow vs agent deletion
✅ **Cascade Delete** - All related connections removed
✅ **UI Cleanup** - Canvas automatically updated
✅ **Training Panel** - Closed if deleted agent was being trained

---

## Testing Checklist

- [ ] Create "Deep Web Research Workflow"
- [ ] Verify Research Agent shows "MASTER" badge
- [ ] Verify Research Agent has "Delete Workflow" button
- [ ] Verify other agents have "Delete Agent" button
- [ ] Click "Delete Agent" on Synthesis Agent
  - [ ] Only that agent is deleted
  - [ ] Others remain
- [ ] Undo/redo if available
- [ ] Delete Research Agent (master)
  - [ ] Confirmation says "delete the entire workflow"
  - [ ] All 4 agents deleted
  - [ ] Canvas is clean
- [ ] Try deleting via keyboard (Delete key)
  - [ ] Works the same way

---

## Backward Compatibility

✅ Existing single agents still work
✅ Manual agent creation unchanged
✅ Agent type toggle still works
✅ No breaking changes to backend API

---

## Future Enhancements

- [ ] Prevent toggling master agent to worker
- [ ] Undo/Redo functionality
- [ ] Archive workflows instead of delete
- [ ] Workflow templates library
- [ ] Multiple workflow support on same canvas

---

**Status:** ✅ Implemented & Ready to Test

Master Agent system is now fully integrated!

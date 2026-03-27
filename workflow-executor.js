/**
 * Workflow Executor - Runs 3-agent workflows on the canvas
 * Streams progress updates to agent nodes in real-time
 */

class WorkflowExecutor {
    constructor(canvasInstance) {
        this.canvas = canvasInstance;
        this.currentWorkflow = null;
        this.eventSource = null;
    }

    /**
     * Start workflow execution and stream progress to canvas
     */
    async executeWorkflow(workflowId, researchAgentId, analystAgentId, pdfAgentId, query) {
        try {
            // Create SSE connection to backend
            const response = await fetch('http://localhost:8000/workflow/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workflow_id: workflowId,
                    research_agent_id: researchAgentId,
                    analyst_agent_id: analystAgentId,
                    pdf_agent_id: pdfAgentId,
                    query: query,
                    working_dir: '/tmp/workflow'
                })
            });

            if (!response.ok) throw new Error('Failed to start workflow');

            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        const eventType = line.substring(7);
                        const nextLine = lines.shift();
                        if (nextLine?.startsWith('data: ')) {
                            const data = JSON.parse(nextLine.substring(6));
                            this.handleWorkflowEvent(eventType, data);
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Workflow execution error:', error);
            this.showError(`Workflow failed: ${error.message}`);
        }
    }

    /**
     * Handle incoming workflow events
     */
    handleWorkflowEvent(eventType, data) {
        switch (eventType) {
            case 'WORKFLOW_START':
                this.onWorkflowStart(data);
                break;
            case 'AGENT_START':
                this.onAgentStart(data);
                break;
            case 'AGENT_WORKING':
                this.onAgentWorking(data);
                break;
            case 'AGENT_COMPLETE':
                this.onAgentComplete(data);
                break;
            case 'WORKFLOW_COMPLETE':
                this.onWorkflowComplete(data);
                break;
            default:
                console.log(`Unknown event: ${eventType}`, data);
        }
    }

    /**
     * Workflow started
     */
    onWorkflowStart(data) {
        console.log('Workflow started:', data);
        // Update canvas header
        this.showStatus(`Starting workflow: ${data.query}`);
    }

    /**
     * Agent started work
     */
    onAgentStart(data) {
        const agentNode = document.getElementById(data.agent_id);
        if (!agentNode) return;

        // Update agent node with active state
        agentNode.classList.add('agent-working');

        // Update terminal
        this.logToAgent(data.agent_id, `Starting: ${data.task}`);

        // Update status badge
        this.updateAgentStatus(data.agent_id, 'WORKING', '#FFA500');
    }

    /**
     * Agent is working on a task
     */
    onAgentWorking(data) {
        const agentNode = document.getElementById(data.agent_id);
        if (!agentNode) return;

        // Update progress bar
        this.updateAgentProgress(data.agent_id, data.progress, data.task);

        // Log to terminal
        this.logToAgent(data.agent_id, `${data.task} (${data.progress}%)`);
    }

    /**
     * Agent completed work
     */
    onAgentComplete(data) {
        const agentNode = document.getElementById(data.agent_id);
        if (!agentNode) return;

        // Update agent node with complete state
        agentNode.classList.remove('agent-working');
        agentNode.classList.add('agent-complete');

        // Update status badge
        this.updateAgentStatus(data.agent_id, 'COMPLETE', '#00AA00');

        // Log completion
        this.logToAgent(data.agent_id, `✓ Completed: ${data.output}`);

        // Show stats
        if (data.stats) {
            const statsText = Object.entries(data.stats)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' | ');
            this.logToAgent(data.agent_id, `📊 ${statsText}`);
        }
    }

    /**
     * Workflow completed
     */
    onWorkflowComplete(data) {
        console.log('Workflow completed:', data);
        this.showStatus('✓ Workflow complete!', 'success');

        // Remove working state from all agents
        document.querySelectorAll('.agent-working').forEach(node => {
            node.classList.remove('agent-working');
        });
    }

    /**
     * Update agent progress on canvas
     */
    updateAgentProgress(agentId, progress, task) {
        const agentNode = document.getElementById(agentId);
        if (!agentNode) return;

        // Find or create progress bar
        let progressBar = agentNode.querySelector('.agent-progress');
        if (!progressBar) {
            progressBar = document.createElement('div');
            progressBar.className = 'agent-progress';
            progressBar.innerHTML = '<div class="progress-fill"></div><div class="progress-text">0%</div>';
            agentNode.querySelector('.node-body').appendChild(progressBar);
        }

        // Update progress
        const fill = progressBar.querySelector('.progress-fill');
        const text = progressBar.querySelector('.progress-text');
        fill.style.width = `${progress}%`;
        text.textContent = `${progress}%`;
    }

    /**
     * Update agent status badge
     */
    updateAgentStatus(agentId, status, color) {
        const agentNode = document.getElementById(agentId);
        if (!agentNode) return;

        let statusBadge = agentNode.querySelector('.agent-status-badge');
        if (!statusBadge) {
            statusBadge = document.createElement('div');
            statusBadge.className = 'agent-status-badge';
            agentNode.querySelector('.node-header').appendChild(statusBadge);
        }

        statusBadge.textContent = status;
        statusBadge.style.backgroundColor = color;
    }

    /**
     * Log message to agent terminal
     */
    logToAgent(agentId, message) {
        const terminal = document.getElementById(`term-${agentId}`);
        if (!terminal) return;

        const timestamp = new Date().toLocaleTimeString();
        const line = document.createElement('div');
        line.textContent = `[${timestamp}] ${message}`;
        terminal.appendChild(line);

        // Auto-scroll to bottom
        terminal.scrollTop = terminal.scrollHeight;
    }

    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);
        // Could update a status bar on canvas here
    }

    /**
     * Show error message
     */
    showError(message) {
        console.error('ERROR:', message);
        alert(`Workflow Error: ${message}`);
    }
}

// Export for use in canvas
if (typeof window !== 'undefined') {
    window.WorkflowExecutor = WorkflowExecutor;
}

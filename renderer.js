function initAgentCanvas() {
    const workspace = document.getElementById('main-workspace');
    if(workspace) workspace.classList.remove('hidden');

    document.body.classList.add('canvas-mode');

    if (!window.agentCanvasInstance) {
        setTimeout(() => {
            window.agentCanvasInstance = new window.AgentCanvas('agent-canvas');
            if (window.initTrainingUI) window.initTrainingUI();
        }, 50); // Small delay to ensure DOM is ready
    }
}

initAgentCanvas();

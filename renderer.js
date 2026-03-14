// Step Elements
const steps = {
    1: document.getElementById('step-1'),
    2: document.getElementById('step-2'),
    3: document.getElementById('step-3'),
    4: document.getElementById('step-4'),
    5: document.getElementById('step-5')
};

// Button Elements
const nextToStep2Btn = document.getElementById('next-to-step-2');
const nextToStep3Btn = document.getElementById('next-to-step-3');
const nextToStep4Btn = document.getElementById('next-to-step-4');
const saveKeyBtn = document.getElementById('save-key-btn');
const quitBtn = document.getElementById('quit-btn');

// Input Elements
const brainProviderSelect = document.getElementById('brain-provider');
const apiKeyInput = document.getElementById('api-key-input');
const providerNameSpan = document.getElementById('provider-name');

// Function to show a specific step
function showStep(stepNumber) {
    Object.values(steps).forEach(stepEl => stepEl.classList.add('hidden'));
    if (steps[stepNumber]) {
        steps[stepNumber].classList.remove('hidden');
    }
}

// Navigation Logic
nextToStep2Btn.addEventListener('click', () => {
    showStep(2);
});

nextToStep3Btn.addEventListener('click', () => {
    showStep(3);
});

nextToStep4Btn.addEventListener('click', () => {
    showStep(5); // Skip Step 4 (API Key) as it's now in the agent panel
});

// API Key management is now in the agent training panel.
// Removing old saveKeyBtn listener.

quitBtn.addEventListener('click', () => {
    window.electronAPI.closeApp();
});

// Show the first step initially
showStep(1);

// --- Agent Canvas Integration ---

function initAgentCanvas() {
    // 1. Hide the wizard and show the workspace
    document.getElementById('setup-wizard').classList.add('hidden');
    const workspace = document.getElementById('main-workspace');
    workspace.classList.remove('hidden');

    // 2. Add the canvas-mode class to the body for your CSS styling
    document.body.classList.add('canvas-mode');

    // 3. Initialize the canvas only if it hasn't been already
    if (!window.agentCanvasInstance) {
        window.agentCanvasInstance = new window.AgentCanvas('agent-canvas');
    }
}

const launchWorkspaceBtn = document.getElementById('launch-workspace-btn');
if (launchWorkspaceBtn) {
    launchWorkspaceBtn.addEventListener('click', () => {
        initAgentCanvas();
    });
}



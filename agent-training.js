// ─── GLOBALS & STATE ────────────────────────────────────────────────────────
let activeAgentId = null;
let activeAgentData = {};
let isTrainingPanelOpen = false;
let isTrainingUIInitialized = false;
let saveTimeout = null;
let autoSaveStatus = null;

// ─── GLOBALS ────────────────────────────────────────────────────────────────
window.activeTrainingAgentId = null;
window.isTrainingPanelOpen = false;

window.copyToClipboard = (btn) => {
    const pre = btn.parentElement.nextElementSibling;
    const code = pre.querySelector('code').textContent;
    navigator.clipboard.writeText(code).then(() => {
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = originalText; }, 2000);
    });
};

// ─── Module-level markdown renderer (Enhanced & Robust) ──────────────────────
function _markdownToHtml(text) {
    if (!text) return "";

    // FIRST: Extract and preserve interactive HTML elements (buttons, divs for execution plans)
    const interactiveElements = [];
    let processedText = text;

    // Extract button HTML before escaping
    processedText = processedText.replace(/<div[^>]*class="[^"]*start-autonomous[^"]*"[^>]*>[\s\S]*?<\/div>/gi, (match) => {
        const id = `__INTERACTIVE_${interactiveElements.length}__`;
        interactiveElements.push(match);
        return id;
    });

    let html = processedText
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    const codeBlocks = [];
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const id = `__CODE_BLOCK_${codeBlocks.length}__`;
        const displayLang = lang || 'code';
        codeBlocks.push(`
            <div class="code-header">
                <span>${displayLang.toUpperCase()}</span>
                <button class="copy-btn" onclick="window.copyToClipboard(this)">Copy</button>
            </div>
            <pre><code class="language-${lang}">${code.trim()}</code></pre>
        `);
        return id;
    });

    // 2. Blockquotes
    html = html.replace(/^&gt;[ \t]*(.+)$/gm, '<blockquote>$1</blockquote>');

    // 3. Lists (Bullet and Numbered)
    html = html.replace(/^[ \t]*[-*+][ \t]+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/gs, '<ul>$&</ul>');

    html = html.replace(/^[ \t]*(\d+)\.[ \t]+(.+)$/gm, '<li class="num-list-item">$2</li>');
    html = html.replace(/(<li class="num-list-item">.*<\/li>\n?)+/gs, '<ol>$&</ol>');

    // 4. Headers
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');

    // 5. Hard rules
    html = html.replace(/^---$/gm, '<hr>');

    // 6. Semantic Inline Styling
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="msg-link">$1</a>');
    html = html.replace(/\(Source: (.+?)\)/g, '<span class="msg-citation">Source: $1</span>');

    // 7. Paragraph Wrapping
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return '';
        // Don't wrap if it's already a structural tag
        if (/^<(h[2-4]|ul|ol|blockquote|pre|hr|__CODE_BLOCK)/.test(trimmed)) return trimmed;
        return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');

    // 8. Restore Code Blocks
    codeBlocks.forEach((block, i) => {
        html = html.replace(`__CODE_BLOCK_${i}__`, block);
    });

    // 9. Restore Interactive Elements (buttons, execution plan divs)
    interactiveElements.forEach((element, i) => {
        html = html.replace(`__INTERACTIVE_${i}__`, element);
    });

    return html;
}

// Expose open function globally so canvas.js can trigger it
window.openTrainingPanel = async (agentId, agentName) => {
    // 1. CANCEL PENDING SAVE from previous agent to prevent race conditions
    if (saveTimeout) {
        clearTimeout(saveTimeout);
        saveTimeout = null;
    }

    activeAgentId = agentId;
    window.activeTrainingAgentId = agentId;
    window.isTrainingPanelOpen = true;
    document.getElementById('agent-name').textContent = `Training: ${agentName}`;

    // Load local data fallback
    let agentData = JSON.parse(localStorage.getItem('agentTrainingData') || '{}');
    if (agentData.id !== agentId) agentData = {}; // Clear if switching agents locally

    // Fetch latest data from backend to ensure consistency
    try {
        const response = await fetch(`http://localhost:8000/agents`);
        const agents = await response.json();
        const backendAgentData = agents.find(a => a.id === agentId);
        if (backendAgentData) {
            agentData = backendAgentData;
        }
    } catch (error) {
        console.error("Could not fetch latest agent data from backend, using localStorage.", error);
    }

    activeAgentData = agentData;

    // Populate UI with the most up-to-date data
    document.getElementById('detail-name').value = agentData.name || '';
    document.getElementById('detail-description').value = agentData.description || '';
    document.getElementById('detail-responsibility').value = agentData.responsibility || '';
    document.getElementById('detail-responsibility').value = agentData.responsibility || '';
    document.getElementById('detail-channel').value = agentData.channel || 'Gmail';
    document.getElementById('detail-workdir').value = agentData.workingDir || '';
    document.getElementById('detail-tools').value = agentData.tools || '';
    document.getElementById('detail-agent-type').value = agentData.agentType || 'worker';

    // Show/hide plan button based on agent type
    const planBtn = document.getElementById('generate-plan-btn');
    if (planBtn) {
        planBtn.style.display = (agentData.agentType === 'master') ? 'block' : 'none';
    }

    // Sync capability buttons
    const capBtns = document.querySelectorAll('.cap-btn');
    const agentPerms = agentData.permissions || [];
    capBtns.forEach(btn => {
        const cap = btn.getAttribute('data-cap');
        if (agentPerms.includes(cap)) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Clear old chat area except for the first greeting
    const chatArea = document.getElementById('chat-area');
    chatArea.innerHTML = `
        <div class="message agent-message">
            Hello! I am ready to be trained. You can upload documents or give me specific instructions here.
        </div>
    `;

    // Load and render saved conversation history from backend
    try {
        const histRes = await fetch(`http://localhost:8000/history/${agentId}`);
        const history = await histRes.json();

        if (history && history.length > 0) {
            // Filter out internal agent-to-agent system messages
            const visibleHistory = history.filter(h => {
                const c = h.content || '';
                return !c.startsWith('[MESSAGE FROM ANOTHER AGENT]') && !c.startsWith('SYSTEM TOOL RESULT:');
            });

            if (visibleHistory.length > 0) {
                // Clear the default greeting since we have real history
                chatArea.innerHTML = '';
                visibleHistory.forEach(h => {
                    const isUser = h.role === 'user';
                    const msgDiv = document.createElement('div');
                    msgDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;
                    if (isUser) {
                        msgDiv.textContent = h.content;
                    } else {
                        msgDiv.innerHTML = _markdownToHtml(h.content);
                    }
                    chatArea.appendChild(msgDiv);
                });
                // Scroll to bottom after loading
                chatArea.scrollTop = chatArea.scrollHeight;
            }
        }
    } catch (err) {
        console.warn('Could not load chat history:', err);
    }

    // Slide panel in
    const panel = document.getElementById('training-overlay');
    panel.classList.add('active');
    document.body.classList.add('training-panel-active');
    isTrainingPanelOpen = true;

    // Show persistent training status on canvas node
    if (window.agentCanvasInstance) {
        window.agentCanvasInstance.logToTerminal(agentId, 'Training');
    }

    // After the panel transition, notify the canvas to resize/update elements
    if (window.agentCanvasInstance && typeof window.agentCanvasInstance.onResize === 'function') {
        setTimeout(() => window.agentCanvasInstance.onResize(), 400); // 400ms to match CSS transition
    }

    // AUTO-FOCUS the input after sliding in to ensure its ready for typing
    setTimeout(() => {
        const input = document.getElementById('message-input');
        if (input) {
            input.focus();
            // Ensure pointer events are active in case a transition stuck them
            input.style.pointerEvents = 'auto';
        }
    }, 500);

    // Sync UI with current toggle state
    const toggle = document.getElementById('work-train-toggle');
    if (toggle) {
        updateModeState(toggle.checked);
    }
};

// ─── WORK/TRAIN MODE TOGGLE ──────────────────────────────────────────────
function updateModeState(isTrainMode) {
    const sidebar = document.getElementById('details-sidebar');
    const trainLabel = document.getElementById('train-label');
    const workLabel = document.querySelector('.mode-label:not(#train-label)');

    if (isTrainMode) {
        sidebar.classList.remove('disabled');
        trainLabel.classList.add('active');
        if (workLabel) workLabel.classList.remove('active');
    } else {
        sidebar.classList.add('disabled');
        trainLabel.classList.remove('active');
        if (workLabel) workLabel.classList.add('active');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('work-train-toggle');
    if (toggle) {
        toggle.addEventListener('change', (e) => {
            updateModeState(e.target.checked);
        });
    }
});

// ─── AUTO-SAVE SYSTEM ────────────────────────────────────────────────────
async function triggerSave() {
    if (!activeAgentId) return;

    if (autoSaveStatus) {
        autoSaveStatus.textContent = 'Saving...';
        autoSaveStatus.style.opacity = '1';
    }

    // Collect active permissions/capabilities
    const permissions = Array.from(document.querySelectorAll('.cap-btn.active'))
        .map(btn => btn.getAttribute('data-cap'));

    const updatedData = {
        ...activeAgentData,
        id: activeAgentId, // CRITICAL: Enforce ID match to prevent accidental renames/duplications
        name: document.getElementById('detail-name').value,
        description: document.getElementById('detail-description').value,
        responsibility: document.getElementById('detail-responsibility').value,
        channel: document.getElementById('detail-channel').value,
        workingDir: document.getElementById('detail-workdir').value,
        tools: document.getElementById('detail-tools').value,
        agentType: document.getElementById('detail-agent-type').value,
        permissions: permissions
    };

    try {

        const response = await fetch(`http://localhost:8000/agents/${activeAgentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updatedData)
        });

        if (response.ok) {
            localStorage.setItem('agentTrainingData', JSON.stringify(updatedData));
            activeAgentData = updatedData;
            document.getElementById('agent-name').textContent = `Training: ${updatedData.name}`;

            // Selective sync node instead of full canvas wipe
            if (window.agentCanvasInstance && typeof window.agentCanvasInstance.updateNodeInPlace === 'function') {
                window.agentCanvasInstance.updateNodeInPlace(activeAgentId, updatedData);
            }

            if (autoSaveStatus) {
                autoSaveStatus.textContent = 'Saved';
                setTimeout(() => {
                    if (autoSaveStatus) autoSaveStatus.style.opacity = '0.6';
                }, 2000);
            }
        }
    } catch (error) {
        console.error('Auto-save error:', error);
        if (autoSaveStatus) autoSaveStatus.textContent = 'Error saving';
    }
}

function queueAutoSave() {
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(triggerSave, 1000); // 1 second debounce
}

function initTrainingUI() {
    if (isTrainingUIInitialized) return;
    isTrainingUIInitialized = true;

    const closeBtn = document.getElementById('close-training-btn');
    const sendBtn = document.getElementById('send-btn');
    const messageInput = document.getElementById('message-input');
    const chatArea = document.getElementById('chat-area');

    // ── INTERACTION HANDLERS ────────────────────────────────────────────────
    // Open all source/citation links in the system default browser, not inside Electron
    chatArea.addEventListener('click', (e) => {
        const link = e.target.closest('.msg-link');
        if (link) {
            e.preventDefault();
            const url = link.getAttribute('href');
            if (url && window.electronAPI && window.electronAPI.openExternal) {
                window.electronAPI.openExternal(url);
            }
        }
    });

    const closeTrainingPanel = () => {
        const panel = document.getElementById('training-overlay');
        if (!panel) return;

        panel.classList.remove('active');
        document.body.classList.remove('training-panel-active');
        isTrainingPanelOpen = false;
        window.isTrainingPanelOpen = false;

        // Reset terminal status to ready on close
        if (window.agentCanvasInstance && activeAgentId) {
            window.agentCanvasInstance.logToTerminal(activeAgentId, 'Ready');
        }

        activeAgentId = null;
        window.activeTrainingAgentId = null;

        // Ensure no leftover resizing states block the UI
        window.isResizingPanelGlobal = false;
        window.isResizingSidebarGlobal = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        // After the panel transition, notify the canvas to resize/update elements
        if (window.agentCanvasInstance && typeof window.agentCanvasInstance.onResize === 'function') {
            setTimeout(() => window.agentCanvasInstance.onResize(), 400); // 400ms to match CSS transition
        }
    };

    window.closeTrainingPanel = closeTrainingPanel;
    closeBtn.addEventListener('click', closeTrainingPanel);

    // Working Directory Browse
    const browseWorkdirBtn = document.getElementById('browse-workdir-btn');
    if (browseWorkdirBtn) {
        browseWorkdirBtn.addEventListener('click', async () => {
            const path = await window.electronAPI.selectDirectory();
            if (path) {
                document.getElementById('detail-workdir').value = path;
                queueAutoSave();
            }
        });
    }

    // Capability button toggles
    const capBtns = document.querySelectorAll('.cap-btn');
    capBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            btn.classList.toggle('active');
            queueAutoSave();
        });
    });

    // Agent Type change
    const typeSelect = document.getElementById('detail-agent-type');
    typeSelect.addEventListener('change', () => {
        const planBtn = document.getElementById('generate-plan-btn');
        if (planBtn) {
            planBtn.style.display = (typeSelect.value === 'master') ? 'block' : 'none';
        }
        queueAutoSave();
    });

    // Link autoSaveStatus to the global
    autoSaveStatus = document.getElementById('auto-save-status');

    // Attach listeners to all inputs/selects for auto-save
    const autoSaveInputs = [
        'detail-name', 'detail-description', 'detail-responsibility',
        'detail-channel', 'detail-tools', 'detail-workdir',
        'detail-agent-type'
    ];

    autoSaveInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', queueAutoSave);
            el.addEventListener('change', queueAutoSave);
        }
    });

    // Clear Chat button
    const clearChatBtn = document.getElementById('clear-chat-btn');
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', async () => {
            if (!activeAgentId) return;
            const confirmed = await window.customConfirm('Clear all chat history for this agent? This cannot be undone.');
            if (!confirmed) return;
            try {
                await fetch(`http://localhost:8000/history/${activeAgentId}`, { method: 'DELETE' });
            } catch (e) {
                console.warn('Could not clear history on backend:', e);
            }

            // Reset UI to blank greeting
            document.getElementById('chat-area').innerHTML = `
                <div class="message agent-message">
                    Chat history cleared. Ready for a fresh start!
                </div>
            `;
        });
    }

    // ── RENDERERS ──────────────────────────────────────────────────────────
    function markdownToHtml(text) {
        return _markdownToHtml(text);
    }

    function animateWords(containerEl) {
        const MAX_ANIMATED_WORDS = 120; // Words beyond this all appear at the same time
        const MS_PER_WORD = 18;         // Delay between each word

        // Walk all text nodes in the rendered HTML tree, skipping code blocks
        const walker = document.createTreeWalker(containerEl, NodeFilter.SHOW_TEXT, {
            acceptNode: (node) => {
                // Reject text nodes that are children of <pre> or .code-header
                if (node.parentElement.closest('pre') || node.parentElement.closest('.code-header')) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        const textNodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.textContent.trim()) textNodes.push(node);
        }

        let wordIndex = 0;
        textNodes.forEach(textNode => {
            // Split preserving whitespace tokens
            const parts = textNode.textContent.split(/(\s+)/);
            const fragment = document.createDocumentFragment();

            parts.forEach(part => {
                if (/^\s+$/.test(part)) {
                    fragment.appendChild(document.createTextNode(part));
                } else if (part) {
                    const span = document.createElement('span');
                    span.className = 'word-reveal';
                    const delay = Math.min(wordIndex, MAX_ANIMATED_WORDS) * MS_PER_WORD;
                    span.style.animationDelay = `${delay}ms`;
                    span.textContent = part;
                    fragment.appendChild(span);
                    wordIndex++;
                }
            });

            textNode.parentNode.replaceChild(fragment, textNode);
        });

        // Scroll as words appear — recalculate at peak animation time
        const peakMs = Math.min(wordIndex, MAX_ANIMATED_WORDS) * MS_PER_WORD + 400;
        const scrollInterval = setInterval(() => {
            chatArea.scrollTop = chatArea.scrollHeight;
        }, 80);
        setTimeout(() => clearInterval(scrollInterval), peakMs);
    }

    function addMessage(text, isUser = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;
        if (isUser) {
            msgDiv.textContent = text;
            chatArea.appendChild(msgDiv);
            chatArea.scrollTop = chatArea.scrollHeight;
        } else {
            msgDiv.innerHTML = markdownToHtml(text);
            chatArea.appendChild(msgDiv);

            // Attach event listeners to interactive buttons
            const startBtn = msgDiv.querySelector('.start-autonomous-btn');
            if (startBtn) {
                startBtn.addEventListener('click', async () => {
                    const agentId = startBtn.getAttribute('data-agent-id');
                    const task = startBtn.getAttribute('data-task');

                    if (agentId && task) {
                        addMessage(`Starting execution of plan for: "${task}"`, true);

                        try {
                            const response = await fetch('http://localhost:8000/execute_autonomous', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    agent_id: agentId,
                                    message: task
                                })
                            });

                            if (response.ok) {
                                const result = await response.json();
                                addMessage(result.response || "Execution completed.", false);
                            } else {
                                addMessage(`Error executing plan: ${response.statusText}`, false);
                            }
                        } catch (error) {
                            addMessage(`Error: ${error.message}`, false);
                        }
                    }
                });
                startBtn.style.cursor = 'pointer';
            }

            animateWords(msgDiv);
        }
    }

    function showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.id = 'typing-indicator';
        indicator.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        chatArea.appendChild(indicator);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    async function handleSend() {
        if (!activeAgentId) return;
        const text = messageInput.value.trim();
        if (!text) return;

        addMessage(text, true);
        messageInput.value = '';

        showTypingIndicator();

        const toggleEl = document.getElementById('work-train-toggle');
        const isTraining = toggleEl ? toggleEl.checked : false;
        const mode = isTraining ? 'training' : 'work';

        // In training mode, always use /chat (no autonomous planning).
        // In work mode, master agents use /run_autonomous for tasks.
        const agentType = activeAgentData.agentType || 'worker';
        let endpoint = 'http://localhost:8000/chat';
        if (!isTraining && agentType === 'master' && text.length > 10) {
            endpoint = 'http://localhost:8000/run_autonomous';
        }

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: activeAgentId,
                    message: text,
                    mode: mode
                })
            });

            if (!response.ok) {
                removeTypingIndicator();
                addMessage(`Error: ${response.statusText}`, false);
                return;
            }

            removeTypingIndicator();

            // --- STREAM HANDLING (for /chat) ---
            if (endpoint.includes('/chat')) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                let messageDiv = document.createElement('div');
                messageDiv.className = 'message agent-message';
                chatArea.appendChild(messageDiv);

                let thoughtDetails = null;
                let thoughtContent = null;
                let responseContent = "";
                let fullThoughtText = "";

                let initialStatus = document.createElement('div');
                initialStatus.className = 'stream-status';
                initialStatus.innerHTML = `<i>Thinking...</i>`;
                messageDiv.appendChild(initialStatus);

                let unprocessedText = "";
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    unprocessedText += decoder.decode(value, { stream: true });
                    const lines = unprocessedText.split('\n');
                    unprocessedText = lines.pop();

                    for (let line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        let dataText = line.slice(6).trim();
                        if (dataText === '[DONE]') break;

                        try {
                            const data = JSON.parse(dataText);
                            if (initialStatus) { initialStatus.remove(); initialStatus = null; }

                            if (data.type === 'thought') {
                                if (!thoughtDetails) {
                                    thoughtDetails = document.createElement('details');
                                    thoughtDetails.className = 'thought-block';
                                    thoughtDetails.innerHTML = `<summary>🧠 <i>Thinking...</i></summary><div class="thought-content"></div>`;
                                    messageDiv.appendChild(thoughtDetails);
                                    thoughtContent = thoughtDetails.querySelector('.thought-content');
                                }
                                fullThoughtText += data.content;
                                thoughtContent.textContent = fullThoughtText;
                            }
                            else if (data.type === 'text') {
                                responseContent += data.content;
                                let textSpan = messageDiv.querySelector('.response-text');
                                if (!textSpan) {
                                    textSpan = document.createElement('div');
                                    textSpan.className = 'response-text';
                                    messageDiv.appendChild(textSpan);
                                }
                                textSpan.innerHTML = markdownToHtml(responseContent);
                            }
                            else if (data.type === 'status' || data.type === 'tool_start') {
                                let statusEl = messageDiv.querySelector('.stream-status');
                                if (!statusEl) {
                                    statusEl = document.createElement('div');
                                    statusEl.className = 'stream-status';
                                    messageDiv.appendChild(statusEl);
                                }
                                statusEl.innerHTML = `<i>${data.content || 'Action...'}</i>`;
                            }
                            else if (data.type === 'error') {
                                messageDiv.innerHTML += `<div class="error-text">⚠️ ${data.content}</div>`;
                            }
                        } catch (e) {
                            console.error("Error parsing stream chunk:", e, dataText);
                        }
                    }
                    chatArea.scrollTop = chatArea.scrollHeight;
                }

                const sEl = messageDiv.querySelector('.stream-status');
                if (sEl) sEl.remove();

                processPlanResponse(responseContent, text, true); // true = already displayed
            }
            // --- REGULAR JSON HANDLING (for /run_autonomous) ---
            else {
                const data = await response.json();
                if (data.response) {
                    processPlanResponse(data.response, text, false); // false = not displayed yet
                } else if (data.error) {
                    addMessage(`Error: ${data.error}`, false);
                }
            }

        } catch (error) {
            removeTypingIndicator();
            addMessage(`Error: ${error.message}`, false);
        }
    }

    sendBtn.addEventListener('click', handleSend);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });

    // Generate Plan button handler
    const generatePlanBtn = document.getElementById('generate-plan-btn');
    if (generatePlanBtn) {
        generatePlanBtn.addEventListener('click', async () => {
            const text = messageInput.value.trim();
            if (!text) {
                addMessage("Please enter a task before generating a plan.", true);
                return;
            }

            addMessage(`Generate master plan for: ${text}`, true);
            messageInput.value = '';

            const toggleEl = document.getElementById('work-train-toggle');
            const mode = (toggleEl && toggleEl.checked) ? 'training' : 'work';

            showTypingIndicator();
            try {
                const response = await fetch('http://localhost:8000/run_autonomous', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        agent_id: activeAgentId,
                        message: text,
                        mode: mode
                    })
                });

                removeTypingIndicator();
                const data = await response.json();

                if (data.response) {
                    processPlanResponse(data.response, text);
                } else {
                    addMessage(data.error || "Failed to generate plan.", false);
                }
            } catch (error) {
                removeTypingIndicator();
                addMessage("Error connecting to planning service.", false);
            }
        });
    }

    function processPlanResponse(responseText, originalTask, isAlreadyDisplayed = false) {
        // Check if this is an execution plan response
        if (responseText.includes("Execution Plan Generated") || responseText.includes("### 📝")) {
            // Extract plan steps and show in dedicated area
            const planAreaDiv = document.getElementById('autonomous-plan-area');
            const planContentDiv = document.getElementById('plan-content');

            // Extract the steps (lines starting with number followed by period)
            const stepsMatch = responseText.match(/(\d+\.\s+.+?)(?=\n\d+\.|Plan file|$)/gs);
            if (stepsMatch) {
                const stepsHtml = stepsMatch
                    .map(step => step.trim())
                    .map(step => `<div class="plan-step">• ${step}</div>`)
                    .join('');
                planContentDiv.innerHTML = stepsHtml;
                planAreaDiv.style.display = 'block';

                // Store plan info for execution button
                planAreaDiv.dataset.agentId = activeAgentId;
                planAreaDiv.dataset.task = originalTask;

                // Don't show this in chat, only show a summary message
                addMessage(`✓ Execution plan generated with ${stepsMatch.length} steps. Use the plan panel to execute.`, false);
            } else if (!isAlreadyDisplayed) {
                addMessage(responseText, false);
            }
        } else if (!isAlreadyDisplayed) {
            addMessage(responseText, false);
        }
    }

    // ── AUTONOMOUS EXECUTION PLAN HANDLERS ──────────────────────
    const autonomousPlanArea = document.getElementById('autonomous-plan-area');
    const startExecutionBtn = document.getElementById('start-execution-btn');
    const closePlanBtn = document.getElementById('close-plan-btn');

    if (startExecutionBtn) {
        startExecutionBtn.addEventListener('click', async () => {
            const agentId = autonomousPlanArea.dataset.agentId;
            const task = autonomousPlanArea.dataset.task;

            if (!agentId || !task) return;

            // Hide the plan area immediately
            autonomousPlanArea.style.display = 'none';

            // Show loading message
            showTypingIndicator();
            addMessage(`▶ Starting autonomous execution...`, true);

            try {
                const response = await fetch('http://localhost:8000/execute_autonomous', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        agent_id: agentId,
                        message: task
                    })
                });

                removeTypingIndicator();

                if (response.ok) {
                    const result = await response.json();
                    addMessage(result.response || "Execution completed.", false);
                } else {
                    addMessage(`Error executing plan: ${response.statusText}`, false);
                }
            } catch (error) {
                removeTypingIndicator();
                addMessage(`Error: ${error.message}`, false);
            }
        });
    }

    if (closePlanBtn) {
        closePlanBtn.addEventListener('click', () => {
            autonomousPlanArea.style.display = 'none';
        });
    }

    // ── RESIZING LOGIC ──────────────────────────────────────────
    const panel = document.getElementById('training-overlay');
    const panelResizer = document.getElementById('panel-resizer');
    const sidebarResizer = document.getElementById('sidebar-resizer');
    const sidebar = document.getElementById('details-sidebar');

    // 1. Panel Resize (Left Edge)
    window.isResizingPanelGlobal = false;
    if (panelResizer) {
        panelResizer.addEventListener('mousedown', (e) => {
            window.isResizingPanelGlobal = true;
            panelResizer.classList.add('dragging');
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none';
            panel.style.transition = 'none';
            e.preventDefault();
        });
    }

    // 2. Sidebar Resize (Middle)
    window.isResizingSidebarGlobal = false;
    if (sidebarResizer) {
        sidebarResizer.addEventListener('mousedown', (e) => {
            window.isResizingSidebarGlobal = true;
            sidebarResizer.classList.add('dragging');
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none';
            // Ensure sidebar has an explicit width to start with
            if (!sidebar.style.width) {
                sidebar.style.width = sidebar.offsetWidth + 'px';
            }
            e.preventDefault();
        });
    }

    document.addEventListener('mousemove', (e) => {
        if (window.isResizingPanelGlobal) {
            const newWidth = window.innerWidth - e.clientX;
            if (newWidth > 350 && newWidth < window.innerWidth * 0.95) {
                panel.style.width = `${newWidth}px`;
                if (window.agentCanvasInstance) window.agentCanvasInstance.onResize();
            }
        }

        if (window.isResizingSidebarGlobal) {
            const panelRect = panel.getBoundingClientRect();
            // Calculate width based on mouse distance from the panel left edge
            const newSidebarWidth = e.clientX - panelRect.left;
            const minW = 200;
            const maxW = panelRect.width - 200;

            if (newSidebarWidth > minW && newSidebarWidth < maxW) {
                sidebar.style.width = `${newSidebarWidth}px`;
                sidebar.style.flex = 'none'; // Ensure it respects the width
            }
        }
    });

    document.addEventListener('mouseup', () => {
        if (window.isResizingPanelGlobal) {
            window.isResizingPanelGlobal = false;
            panelResizer.classList.remove('dragging');
            panel.style.transition = 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
        }
        if (window.isResizingSidebarGlobal) {
            window.isResizingSidebarGlobal = false;
            sidebarResizer.classList.remove('dragging');
        }
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });

    // ── CLICK PROTECTION ────────────────────────────────────────
    if (panel) {
        panel.addEventListener('mousedown', (e) => e.stopPropagation());
        panel.addEventListener('click', (e) => e.stopPropagation());
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTrainingUI);
} else {
    initTrainingUI();
}
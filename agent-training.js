let activeAgentId = null;
let activeAgentData = {};
let isTrainingPanelOpen = false;
let isTrainingUIInitialized = false;

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

async function updateApiKeyVisibility(brainValue) {
    const wrapper = document.getElementById('api-key-wrapper');
    const status = document.getElementById('api-key-status');
    const input = document.getElementById('detail-api-key');

    if (!brainValue) {
        wrapper.style.display = 'none';
        return;
    }

    wrapper.style.display = 'block';

    try {
        const key = await window.electronAPI.getApiKey(brainValue.toLowerCase());
        if (key) {
            wrapper.style.display = 'none';
        } else {
            status.style.display = 'block';
            status.textContent = 'API keys not found. Please enter it below:';
            status.style.color = '#ff4d4d';
            input.parentElement.style.display = 'block';
            input.placeholder = '••••••••••••••••';
        }
    } catch (e) {
        console.error("Error checking API key:", e);
    }
}

// ─── Module-level markdown renderer (Enhanced & Robust) ──────────────────────
function _markdownToHtml(text) {
    if (!text) return "";

    // 1. Escaping and Triple-Backtick Code Blocks first (to preserve content)
    let html = text
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

    return html;
}
window.openTrainingPanel = async (agentId, agentName) => {
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
    document.getElementById('detail-brain').value = agentData.brain || '';
    document.getElementById('detail-channel').value = agentData.channel || 'Gmail';
    document.getElementById('detail-workdir').value = agentData.workingDir || '';
    document.getElementById('detail-tools').value = agentData.tools || 'Gmail';
    document.getElementById('detail-api-key').value = ''; // Always clear on open for security/freshness
    await updateApiKeyVisibility(agentData.brain);

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
        setTimeout(() => window.agentCanvasInstance.onResize(), 400);
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
};

function initTrainingUI() {
    if (isTrainingUIInitialized) return;
    isTrainingUIInitialized = true;

    const closeBtn = document.getElementById('close-training-btn');
    const sendBtn = document.getElementById('send-btn');
    const messageInput = document.getElementById('message-input');
    const chatArea = document.getElementById('chat-area');

    // ── INTERACTION HANDLERS ────────────────────────────────────────────────
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
            setTimeout(() => window.agentCanvasInstance.onResize(), 400);
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

    const capBtns = document.querySelectorAll('.cap-btn');
    capBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            btn.classList.toggle('active');
            queueAutoSave();
        });
    });

    const brainSelect = document.getElementById('detail-brain');
    brainSelect.addEventListener('change', async () => {
        await updateApiKeyVisibility(brainSelect.value);
    });

    // ── AUTO-SAVE SYSTEM ────────────────────────────────────────────────────
    let saveTimeout = null;
    const autoSaveStatus = document.getElementById('auto-save-status');

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
            name: document.getElementById('detail-name').value,
            description: document.getElementById('detail-description').value,
            responsibility: document.getElementById('detail-responsibility').value,
            brain: document.getElementById('detail-brain').value,
            channel: document.getElementById('detail-channel').value,
            workingDir: document.getElementById('detail-workdir').value,
            tools: document.getElementById('detail-tools').value,
            permissions: permissions
        };

        const apiKey = document.getElementById('detail-api-key').value.trim();

        try {
            if (apiKey && updatedData.brain) {
                await window.electronAPI.setApiKey({
                    provider: updatedData.brain.toLowerCase(),
                    apiKey: apiKey
                });
                document.getElementById('detail-api-key').value = '';
                await updateApiKeyVisibility(updatedData.brain);
            }

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
                    setTimeout(() => { autoSaveStatus.style.opacity = '0.6'; }, 2000);
                }
            }
        } catch (error) {
            console.error('Auto-save error:', error);
            if (autoSaveStatus) autoSaveStatus.textContent = 'Error saving';
        }
    }

    function queueAutoSave() {
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(triggerSave, 1000);
    }

    // Listeners for auto-save
    const autoSaveInputs = [
        'detail-name', 'detail-description', 'detail-responsibility',
        'detail-brain', 'detail-channel', 'detail-tools', 'detail-workdir', 'detail-api-key'
    ];

    autoSaveInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', queueAutoSave);
            el.addEventListener('change', queueAutoSave);
        }
    });

    // Special case for API key - also save on blur
    document.getElementById('detail-api-key')?.addEventListener('blur', triggerSave);

    // Clear Chat button
    const clearChatBtn = document.getElementById('clear-chat-btn');
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', async () => {
            if (!activeAgentId) return;
            if (!confirm('Clear all chat history for this agent? This cannot be undone.')) return;
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

        const brain = document.getElementById('detail-brain').value;
        if (!brain) {
            addMessage("Error: No Brain selected. Please configure it in the sidebar.", false);
            return;
        }

        const apiKey = await window.electronAPI.getApiKey(brain.toLowerCase());
        if (!apiKey) {
            addMessage(`Error: API Key for ${brain} is missing. Please save it in the agent settings.`, false);
            return;
        }

        showTypingIndicator();

        try {
            const response = await fetch('http://localhost:8000/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: activeAgentId,
                    message: text,
                    api_key: apiKey,
                    provider: brain
                })
            });
            removeTypingIndicator();
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                addMessage(`Error: ${data.detail || response.statusText || 'Unknown backend error'}`, false);
                return;
            }

            if (data.error) {
                addMessage(`Error: ${data.error}`, false);
            } else {
                addMessage(data.response, false);
            }
        } catch (error) {
            removeTypingIndicator();
            console.error(error);
            addMessage("Error: Could not connect to agent backend.", false);
        }
    }

    sendBtn.addEventListener('click', handleSend);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });

    // ── RESIZING LOGIC (REWRITTEN) ──────────────────────────────────────────
    const panel = document.getElementById('training-overlay');

    const handleResizing = () => {
        const leftResizer = document.querySelector('.resizer-left');
        const midResizer = document.querySelector('.sidebar-resizer');

        let activeResizer = null;

        const startResize = (e, type) => {
            activeResizer = type;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            window.isResizingPanelGlobal = true;
            e.preventDefault();
        };

        if (leftResizer) leftResizer.addEventListener('mousedown', (e) => startResize(e, 'main'));
        if (midResizer) midResizer.addEventListener('mousedown', (e) => startResize(e, 'internal'));

        document.addEventListener('mousemove', (e) => {
            if (!activeResizer) return;

            if (activeResizer === 'main' && panel) {
                let calculatedWidth = window.innerWidth - e.clientX;
                if (calculatedWidth < 400) calculatedWidth = 400;
                panel.style.width = `${calculatedWidth}px`;
                if (window.agentCanvasInstance?.onResize) window.agentCanvasInstance.onResize();
            }

            else if (activeResizer === 'internal' && midResizer) {
                const leftPane = midResizer.previousElementSibling;
                const rightPane = midResizer.nextElementSibling;
                const container = midResizer.parentElement;

                if (leftPane && rightPane && container) {
                    const containerRect = container.getBoundingClientRect();
                    let leftWidth = e.clientX - containerRect.left;

                    const minSide = 250;
                    if (leftWidth < minSide) leftWidth = minSide;
                    if (leftWidth > containerRect.width - minSide) leftWidth = containerRect.width - minSide;

                    container.style.display = 'flex';
                    leftPane.style.flex = `0 0 ${leftWidth}px`;
                    leftPane.style.width = `${leftWidth}px`;
                    rightPane.style.flex = '1 1 0%';
                    rightPane.style.width = 'auto';
                }
            }
        });

        document.addEventListener('mouseup', () => {
            if (!activeResizer) return;
            activeResizer = null;
            document.body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
            window.isResizingPanelGlobal = false;
        });
    };

    handleResizing();

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
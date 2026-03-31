// ─── GLOBALS & STATE ────────────────────────────────────────────────────────
let activeAgentId = null;
let activeAgentData = {};
let isTrainingPanelOpen = false;
let isTrainingUIInitialized = false;
let saveTimeout = null;
let autoSaveStatus = null;
let connectedToolsSet = new Set(); // Tracks connected MCP tool IDs for the active agent

// ─── AGENT GALLERY TEMPLATES ───────────────────────────────────────────────
const AGENT_GALLERY = [
    {
        id: 'custom',
        name: 'Custom Agent',
        icon: '⚙️',
        description: 'A blank agent you configure yourself',
        permissions: [],
        responsibility: '',
    },
    {
        id: 'deep-web-researcher',
        name: 'Deep Web Researcher',
        icon: '🔍',
        description: 'Elite investigator that scrapes full articles and resolves contradictions using recursive verification',
        permissions: ['scrape website', 'report generation'],
        responsibility: 'Perform deep, multi-source investigative research and verify facts.',
        brain: 'gemini-3.1-pro-preview',
    },
    {
        id: 'deep-web-research-workflow',
        name: 'Deep Web Research Workflow',
        icon: '🚀',
        description: '4-agent pipeline: Research → Analysis + Visuals → PDF Report',
        isWorkflow: true,
        agents: [
            {
                name: 'Research Agent',
                description: 'Scrapes full articles, resolves contradictions, builds knowledge graph',
                brain: 'gemini-2.0-flash',
                permissions: ['scrape website', 'recursive verification', 'knowledge graph construction'],
                responsibility: 'Phase 1: Deep web scraping, fact extraction, knowledge map construction',
                specialRole: 'deep-web-researcher',
                agentType: 'master',
            },
            {
                name: 'Synthesis Agent',
                description: 'Reads knowledge map, analyzes findings, writes analytical report',
                brain: 'gemini-3.0-pro',
                permissions: ['content synthesis', 'insight generation', 'narrative composition'],
                responsibility: 'Phase 2: Analyze knowledge map, identify gaps, write report with citations',
                specialRole: 'synthesis',
                agentType: 'worker',
            },
            {
                name: 'Visual Analyst',
                description: 'Extracts critical metrics and produces elegant charts from the knowledge graph',
                brain: 'gemini-3.1-pro-preview',
                permissions: ['data visualization', 'metric extraction', 'pattern detection'],
                responsibility: 'Phase 3: Analyze graph for numerical events, timelines, and generate visual charts',
                specialRole: 'visual-analyst',
                agentType: 'worker',
            },
            {
                name: 'PDF Generator',
                description: 'Compiles text analysis and visual charts into a polished PDF report',
                brain: 'gemini-2.0-flash',
                permissions: ['pdf generation', 'content formatting', 'image embedding'],
                responsibility: 'Phase 4: Generate final combined, formatted PDF from analysis components',
                specialRole: 'pdf-generation',
                agentType: 'worker',
            },
        ],
    },
];

// ─── MCP TOOLS REGISTRY ────────────────────────────────────────────────────
const MCP_TOOLS_REGISTRY = [
    // Search & Research
    { id: 'brave-search', name: 'Brave Search', category: 'Search & Research', icon: 'icons/brave.svg', description: 'Web search via Brave Search API' },
    { id: 'tavily', name: 'Tavily', category: 'Search & Research', icon: 'icons/tavily.svg', description: 'AI-optimized search engine' },
    { id: 'exa', name: 'Exa', category: 'Search & Research', icon: 'icons/exa.svg', description: 'Neural search for content discovery' },
    { id: 'google-search', name: 'Google Search', category: 'Search & Research', icon: 'icons/google.svg', description: 'Google Custom Search integration' },

    // Communication
    { id: 'gmail', name: 'Gmail', category: 'Communication', icon: 'icons/gmail.svg', description: 'Draft replies, summarize threads, and search your inbox' },
    { id: 'slack', name: 'Slack', category: 'Communication', icon: 'icons/slack.svg', description: 'Send messages, create canvases, and fetch Slack data' },
    { id: 'discord', name: 'Discord', category: 'Communication', icon: 'icons/discord.svg', description: 'Discord bot and server messaging' },
    { id: 'ms-teams', name: 'Microsoft Teams', category: 'Communication', icon: 'icons/teams.svg', description: 'Teams messaging and channels' },
    { id: 'telegram', name: 'Telegram', category: 'Communication', icon: 'icons/telegram.svg', description: 'Telegram Bot API messaging' },

    // Productivity
    { id: 'google-drive', name: 'Google Drive', category: 'Productivity', icon: 'icons/gdrive.svg', description: 'File storage and management' },
    { id: 'google-docs', name: 'Google Docs', category: 'Productivity', icon: 'icons/gdocs.svg', description: 'Document creation and editing' },
    { id: 'google-sheets', name: 'Google Sheets', category: 'Productivity', icon: 'icons/gsheets.svg', description: 'Spreadsheet operations' },
    { id: 'google-calendar', name: 'Google Calendar', category: 'Productivity', icon: 'icons/gcalendar.svg', description: 'Manage your schedule and coordinate meetings' },
    { id: 'notion', name: 'Notion', category: 'Productivity', icon: 'icons/notion.svg', description: 'Connect your Notion workspace to search, update, and power workflows' },
    { id: 'todoist', name: 'Todoist', category: 'Productivity', icon: 'icons/todoist.svg', description: 'Task and project management' },
    { id: 'linear', name: 'Linear', category: 'Productivity', icon: 'icons/linear.svg', description: 'Manage issues, projects and team workflows' },

    // Browser & Scraping
    { id: 'puppeteer', name: 'Puppeteer', category: 'Browser', icon: 'icons/puppeteer.svg', description: 'Headless browser automation' },
    { id: 'playwright', name: 'Playwright', category: 'Browser', icon: 'icons/playwright.svg', description: 'Cross-browser testing and scraping' },
    { id: 'firecrawl', name: 'Firecrawl', category: 'Browser', icon: 'icons/firecrawl.svg', description: 'Web crawling and data extraction' },
    { id: 'fetch', name: 'Fetch', category: 'Browser', icon: 'icons/fetch.svg', description: 'Simple HTTP request tool' },

    // File System
    { id: 'filesystem', name: 'Filesystem', category: 'File System', icon: 'icons/filesystem.svg', description: 'Local file system read/write access' },

    // Code & Dev
    { id: 'github', name: 'GitHub', category: 'Code & Dev', icon: 'icons/github.svg', description: 'Repos, issues, PRs, and actions' },
    { id: 'gitlab', name: 'GitLab', category: 'Code & Dev', icon: 'icons/gitlab.svg', description: 'GitLab project management' },
    { id: 'jira', name: 'Jira', category: 'Code & Dev', icon: 'icons/jira.svg', description: 'Jira issue tracking' },
    { id: 'atlassian', name: 'Atlassian', category: 'Code & Dev', icon: 'icons/atlassian.svg', description: 'Access Jira and Confluence from your agent' },

    // Database
    { id: 'postgresql', name: 'PostgreSQL', category: 'Database', icon: 'icons/postgresql.svg', description: 'PostgreSQL database queries' },
    { id: 'sqlite', name: 'SQLite', category: 'Database', icon: 'icons/sqlite.svg', description: 'SQLite local database access' },
    { id: 'supabase', name: 'Supabase', category: 'Database', icon: 'icons/supabase.svg', description: 'Supabase backend services' },
    { id: 'mongodb', name: 'MongoDB', category: 'Database', icon: 'icons/mongodb.svg', description: 'MongoDB document database' },

    // Cloud & Infra
    { id: 'aws', name: 'AWS', category: 'Cloud', icon: 'icons/aws.svg', description: 'Amazon Web Services integration' },
    { id: 'cloudflare', name: 'Cloudflare', category: 'Cloud', icon: 'icons/cloudflare.svg', description: 'Cloudflare Workers, DNS, and KV' },
    { id: 'vercel', name: 'Vercel', category: 'Cloud', icon: 'icons/vercel.svg', description: 'Frontend deployment platform' },

    // Knowledge & Memory
    { id: 'memory', name: 'Memory', category: 'Knowledge', icon: 'icons/memory.svg', description: 'Persistent knowledge graph' },
    { id: 'qdrant', name: 'Qdrant', category: 'Knowledge', icon: 'icons/qdrant.svg', description: 'Vector similarity search engine' },

    // Maps & Location
    { id: 'google-maps', name: 'Google Maps', category: 'Maps', icon: 'icons/gmaps.svg', description: 'Maps, geocoding, and directions' },

    // Media & Design
    { id: 'canva', name: 'Canva', category: 'Media', icon: 'icons/canva.svg', description: 'Search, create, autofill and export Canva designs' },
    { id: 'figma', name: 'Figma', category: 'Media', icon: 'icons/figma.svg', description: 'Generate diagrams and code from Figma context' },
    { id: 'everart', name: 'EverArt', category: 'Media', icon: 'icons/everart.svg', description: 'AI image generation' },
    { id: 'stability-ai', name: 'Stability AI', category: 'Media', icon: 'icons/stability.svg', description: 'Stable Diffusion image generation' },

    // Other
    { id: 'sequential-thinking', name: 'Sequential Thinking', category: 'Other', icon: 'icons/thinking.svg', description: 'Step-by-step structured reasoning' },
    { id: 'sentry', name: 'Sentry', category: 'Other', icon: 'icons/sentry.svg', description: 'Error tracking and monitoring' },
    { id: 'hubspot', name: 'HubSpot', category: 'Other', icon: 'icons/hubspot.svg', description: 'Chat with your CRM data for personalized insights' },
    { id: 'intercom', name: 'Intercom', category: 'Other', icon: 'icons/intercom.svg', description: 'Access Intercom data for customer insights' },
    { id: 'monday', name: 'monday.com', category: 'Other', icon: 'icons/monday.svg', description: 'Manage projects, boards, and workflows' },
    { id: 'miro', name: 'Miro', category: 'Other', icon: 'icons/miro.svg', description: 'Online whiteboard collaboration' },
    { id: 'gamma', name: 'Gamma', category: 'Other', icon: 'icons/gamma.svg', description: 'Create presentations, docs, socials, and sites with AI' },
];

// ─── MCP TOOLS RENDERING ────────────────────────────────────────────────────

function renderMcpToolIcon(iconPath) {
    // Try loading SVG icon, fallback to first letter
    const name = iconPath.replace('icons/', '').replace('.svg', '');
    return `<img src="${iconPath}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span class="mcp-icon-fallback" style="display:none">${name.charAt(0).toUpperCase()}</span>`;
}

function renderMcpToolsModal(activeCategory = 'All', searchQuery = '') {
    const tabsContainer = document.getElementById('mcp-category-tabs');
    const gridContainer = document.getElementById('mcp-tools-grid');
    const countEl = document.getElementById('mcp-selected-count');
    if (!tabsContainer || !gridContainer) return;

    // Build unique category list
    const categories = ['All', ...new Set(MCP_TOOLS_REGISTRY.map(t => t.category))];

    // Render tabs
    tabsContainer.innerHTML = categories.map(cat => `
        <button class="mcp-cat-tab ${cat === activeCategory ? 'active' : ''}" data-category="${cat}">
            ${cat}
        </button>
    `).join('');

    // Tab click handlers
    tabsContainer.querySelectorAll('.mcp-cat-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const search = document.getElementById('mcp-search-input')?.value || '';
            renderMcpToolsModal(tab.dataset.category, search);
        });
    });

    // Filter tools
    let filtered = MCP_TOOLS_REGISTRY;
    if (activeCategory !== 'All') {
        filtered = filtered.filter(t => t.category === activeCategory);
    }
    if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter(t =>
            t.name.toLowerCase().includes(q) ||
            t.description.toLowerCase().includes(q) ||
            t.category.toLowerCase().includes(q)
        );
    }

    // Render cards
    gridContainer.innerHTML = filtered.map(tool => {
        const isConnected = connectedToolsSet.has(tool.id);
        return `
            <div class="mcp-tool-card ${isConnected ? 'connected' : ''}" data-tool-id="${tool.id}">
                <div class="mcp-tool-icon">${renderMcpToolIcon(tool.icon)}</div>
                <div class="mcp-tool-info">
                    <div class="mcp-tool-name">${tool.name}</div>
                    <div class="mcp-tool-desc">${tool.description}</div>
                </div>
                <button class="mcp-tool-connect-btn">${isConnected ? '&#10003;' : '+'}</button>
            </div>
        `;
    }).join('');

    // Card click handlers
    gridContainer.querySelectorAll('.mcp-tool-card').forEach(card => {
        card.addEventListener('click', () => {
            const toolId = card.dataset.toolId;
            if (connectedToolsSet.has(toolId)) {
                connectedToolsSet.delete(toolId);
            } else {
                connectedToolsSet.add(toolId);
            }
            renderMcpToolsModal(activeCategory, searchQuery);
            updateToolsSummary();
        });
    });

    // Update footer count
    if (countEl) {
        countEl.textContent = `${connectedToolsSet.size} tool${connectedToolsSet.size !== 1 ? 's' : ''} connected`;
    }
}

function updateToolsSummary() {
    const countEl = document.getElementById('mcp-tools-count');
    const badgesEl = document.getElementById('mcp-connected-badges');

    if (countEl) {
        countEl.textContent = `${connectedToolsSet.size} connected`;
    }

    if (badgesEl) {
        const connectedTools = MCP_TOOLS_REGISTRY.filter(t => connectedToolsSet.has(t.id));
        const maxVisible = 6;
        const visible = connectedTools.slice(0, maxVisible);
        const remaining = connectedTools.length - maxVisible;

        badgesEl.innerHTML = visible.map(t =>
            `<span class="mcp-badge">${t.name}</span>`
        ).join('') + (remaining > 0 ? `<span class="mcp-badge">+${remaining} more</span>` : '');
    }
}

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

window.sendInteractiveReply = (text) => {
    const input = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');

    if (input && sendBtn) {
        // Drop the text in the input and click send automatically
        input.value = text;
        sendBtn.click();

        // Optional: Disable buttons in the chat history so they can't be double-clicked
        document.querySelectorAll('.glass-box-btn').forEach(btn => {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        });
    }
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

    // NEW: Interactive Glass Box Buttons
    html = html.replace(/\[BUTTON:\s*(.+?)\]/g, (match, btnText) => {
        const id = `__INTERACTIVE_${interactiveElements.length}__`;
        // Create a button that calls a global function with the button's text
        interactiveElements.push(`<button class="glass-box-btn" onclick="window.sendInteractiveReply('${btnText.replace(/'/g, "\\'")}')">${btnText}</button>`);
        return id;
    });

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
    if (document.getElementById('detail-name')) document.getElementById('detail-name').textContent = agentData.name || '';
    if (document.getElementById('detail-description')) document.getElementById('detail-description').textContent = agentData.description || '';
    if (document.getElementById('detail-responsibility')) document.getElementById('detail-responsibility').value = agentData.responsibility || '';
    if (document.getElementById('detail-channel')) document.getElementById('detail-channel').value = agentData.channel || 'Gmail';
    const effortSlider = document.getElementById('detail-user-effort');
    if (effortSlider) {
        effortSlider.value = agentData.userEffort || 1;
        const effortDisplay = document.getElementById('effort-value-display');
        if (effortDisplay) effortDisplay.textContent = effortSlider.value;
    }
    const expertiseSlider = document.getElementById('detail-human-expertise');
    if (expertiseSlider) {
        expertiseSlider.value = agentData.humanExpertise || 5;
        const expertiseDisplay = document.getElementById('expertise-value-display');
        if (expertiseDisplay) expertiseDisplay.textContent = expertiseSlider.value;
    }
    // Project Size toggle
    const savedSize = agentData.projectSize || 'small';
    const projectSizeEl = document.getElementById('detail-project-size');
    if (projectSizeEl) projectSizeEl.value = savedSize;
    document.querySelectorAll('.size-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.size === savedSize);
    });
    // Load connected MCP tools
    if (agentData.connectedTools && Array.isArray(agentData.connectedTools)) {
        connectedToolsSet = new Set(agentData.connectedTools);
    } else {
        // Migration: try matching old single-string 'tools' value to an MCP tool
        const oldTool = (agentData.tools || '').toLowerCase();
        const match = MCP_TOOLS_REGISTRY.find(t => t.name.toLowerCase() === oldTool);
        connectedToolsSet = new Set(match ? [match.id] : []);
    }
    updateToolsSummary();

    const typeEl = document.getElementById('detail-agent-type');
    if (typeEl) typeEl.value = agentData.agentType || 'worker';

    // Show/hide plan button based on agent type
    const planBtn = document.getElementById('generate-plan-btn');
    if (planBtn) {
        planBtn.style.display = (agentData.agentType === 'master') ? 'block' : 'none';
    }

    const isMaster = (agentData.agentType === 'master');
    const sidebar = document.getElementById('details-sidebar');
    const modeBadge = document.getElementById('mode-badge');

    // sidebar should be enabled for all agents to allow configuration
    if (sidebar) {
        sidebar.classList.remove('disabled');
    }
    if (modeBadge) {
        modeBadge.textContent = isMaster ? 'Work' : 'Chat';
    }


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
            // Filter out internal system messages AND stale tool-call artifacts
            const visibleHistory = history.filter(h => {
                const c = h.content || '';
                if (c.startsWith('[MESSAGE FROM ANOTHER AGENT]')) return false;
                if (c.startsWith('SYSTEM TOOL RESULT:')) return false;
                // Filter out bare "Executed: tool_name" lines from old history files
                if (/^Executed:\s*\w+\s*$/.test(c.trim())) return false;
                return true;
            });

            if (visibleHistory.length > 0) {
                chatArea.innerHTML = '';
                let hasWorkmapMessage = false;

                visibleHistory.forEach(h => {
                    const isUser = h.role === 'user';
                    const msgDiv = document.createElement('div');
                    msgDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;

                    // Strip any remaining "Executed: ..." lines from mixed content
                    let content = h.content;
                    if (!isUser) {
                        content = content.replace(/^Executed:\s*\w+\s*$/gm, '').trim();
                    }

                    if (isUser) {
                        msgDiv.textContent = content;
                    } else {
                        msgDiv.innerHTML = _markdownToHtml(content);
                        // Detect workmap-related responses to inject button later
                        if (/workmap|Workmap|PLAY.*canvas|execution.*engine/i.test(content)) {
                            hasWorkmapMessage = true;
                        }
                    }
                    chatArea.appendChild(msgDiv);
                });

                // Re-inject "View Project Workmap" button if history contains workmap messages
                if (hasWorkmapMessage && agentId) {
                    const btnDiv = document.createElement('div');
                    btnDiv.style.textAlign = 'center';
                    btnDiv.style.padding = '6px 0';
                    const btn = document.createElement('button');
                    btn.className = 'view-workmap-btn';
                    btn.textContent = '\u{1F5FA}  View Project Workmap';
                    btn.addEventListener('click', () => openWorkmapView(agentId));
                    btnDiv.appendChild(btn);
                    chatArea.appendChild(btnDiv);
                }

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

};


// ─── AUTO-SAVE SYSTEM ────────────────────────────────────────────────────
async function triggerSave() {
    if (!activeAgentId) return;

    if (autoSaveStatus) {
        autoSaveStatus.textContent = 'Saving...';
        autoSaveStatus.style.opacity = '1';
    }

    const updatedData = {
        ...activeAgentData,
        id: activeAgentId, // CRITICAL: Enforce ID match to prevent accidental renames/duplications
        name: activeAgentData.name || '',
        description: activeAgentData.description || '',
        responsibility: document.getElementById('detail-responsibility')?.value || activeAgentData.responsibility || '',
        channel: document.getElementById('detail-channel')?.value || activeAgentData.channel || 'Gmail',
        workingDir: activeAgentData.workingDir || '',
        userEffort: parseInt(document.getElementById('detail-user-effort')?.value || activeAgentData.userEffort || '1', 10),
        humanExpertise: parseInt(document.getElementById('detail-human-expertise')?.value || activeAgentData.humanExpertise || '5', 10),
        projectSize: document.getElementById('detail-project-size')?.value || activeAgentData.projectSize || 'small',
        connectedTools: Array.from(connectedToolsSet),
        agentType: activeAgentData.agentType || 'worker',
        permissions: activeAgentData.permissions || [],
        specialRole: activeAgentData.specialRole || 'custom'
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

window.initTrainingUI = function() {
    if (isTrainingUIInitialized) return;
    isTrainingUIInitialized = true;

    const closeBtn = document.getElementById('close-training-btn');
    const sendBtn = document.getElementById('send-btn');
    const messageInput = document.getElementById('message-input');
    const chatArea = document.getElementById('chat-area');

    // ── INTERACTION HANDLERS ────────────────────────────────────────────────
    // Open all source/citation links in a new tab
    chatArea.addEventListener('click', (e) => {
        const link = e.target.closest('.msg-link');
        if (link) {
            e.preventDefault();
            const url = link.getAttribute('href');
            if (url) {
                window.open(url, '_blank');
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
    if (closeBtn) closeBtn.addEventListener('click', closeTrainingPanel);

    // ── MCP Tools Modal Wiring ──────────────────────────────────────────────
    const manageToolsBtn = document.getElementById('manage-tools-btn');
    const mcpOverlay = document.getElementById('mcp-tools-overlay');
    const mcpCloseBtn = document.getElementById('mcp-modal-close');
    const mcpDoneBtn = document.getElementById('mcp-modal-done');
    const mcpSearchInput = document.getElementById('mcp-search-input');

    if (manageToolsBtn) {
        manageToolsBtn.addEventListener('click', () => {
            renderMcpToolsModal('All', '');
            mcpOverlay.style.display = 'flex';
            if (mcpSearchInput) {
                mcpSearchInput.value = '';
                mcpSearchInput.focus();
            }
        });
    }

    const closeMcpModal = () => {
        if (mcpOverlay) mcpOverlay.style.display = 'none';
        queueAutoSave();
    };

    if (mcpCloseBtn) mcpCloseBtn.addEventListener('click', closeMcpModal);
    if (mcpDoneBtn) mcpDoneBtn.addEventListener('click', closeMcpModal);

    if (mcpOverlay) {
        mcpOverlay.addEventListener('click', (e) => {
            if (e.target === mcpOverlay) closeMcpModal();
        });
    }

    if (mcpSearchInput) {
        mcpSearchInput.addEventListener('input', (e) => {
            const activeTab = document.querySelector('.mcp-cat-tab.active');
            const category = activeTab ? activeTab.dataset.category : 'All';
            renderMcpToolsModal(category, e.target.value);
        });
    }



    // Link autoSaveStatus to the global
    autoSaveStatus = document.getElementById('auto-save-status');

    // Attach listeners to all inputs/selects for auto-save
    const autoSaveInputs = [
        'detail-responsibility',
        'detail-channel', 'detail-user-effort', 'detail-human-expertise'
    ];

    autoSaveInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', queueAutoSave);
            el.addEventListener('change', queueAutoSave);
        }
    });

    // Human Effort slider — live value display
    const effortSliderEl = document.getElementById('detail-user-effort');
    if (effortSliderEl) {
        effortSliderEl.addEventListener('input', () => {
            const display = document.getElementById('effort-value-display');
            if (display) display.textContent = effortSliderEl.value;
        });
    }

    // Human Expertise slider — live value display
    const expertiseSliderEl = document.getElementById('detail-human-expertise');
    if (expertiseSliderEl) {
        expertiseSliderEl.addEventListener('input', () => {
            const display = document.getElementById('expertise-value-display');
            if (display) display.textContent = expertiseSliderEl.value;
        });
    }

    // Project Size toggle buttons
    document.querySelectorAll('.size-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('detail-project-size').value = btn.dataset.size;
            queueAutoSave();
        });
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
        setBusy(true);
        showTypingIndicator();

        const agentType = activeAgentData.agentType || 'worker';
        const mode = (agentType === 'master') ? 'work' : 'training';
        let endpoint = 'http://localhost:8000/chat';

        currentAbortController = new AbortController();
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: activeAgentId,
                    message: text,
                    mode: mode
                }),
                signal: currentAbortController.signal
            });

            if (!response.ok) {
                removeTypingIndicator();
                addMessage(`Error: ${response.statusText}`, false);
                setBusy(false);
                return;
            }

            await parseResponse(response, text);
        } catch (error) {
            removeTypingIndicator();
            if (error.name !== 'AbortError') {
                addMessage(`Error: ${error.message}`, false);
            }
        } finally {
            setBusy(false);
            currentAbortController = null;
        }
    }

    async function parseResponse(response, originalText) {
        removeTypingIndicator();
        const contentType = response.headers.get('Content-Type') || '';
        const isStream = contentType.includes('text/event-stream');

        if (isStream) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let messageDiv = document.createElement('div');
            messageDiv.className = 'message agent-message';
            chatArea.appendChild(messageDiv);

            let responseContent = "";
            let reactContainer = null;   // holds all .react-iteration divs
            let currentIterDiv = null;   // current iteration's container div

            // Typewriter queue — renders text character-by-character regardless of chunk size
            const twQueue = [];
            let twRunning = false;
            async function twDrain() {
                if (twRunning) return;
                twRunning = true;
                while (twQueue.length > 0) {
                    const item = twQueue.shift();
                    if (item.onChar) {
                        item.onChar(item.ch);
                    } else {
                        item.el.textContent += item.ch;
                    }
                    chatArea.scrollTop = chatArea.scrollHeight;
                    await new Promise(r => setTimeout(r, 14));
                }
                twRunning = false;
            }
            function typewrite(el, text) {
                for (const ch of text) twQueue.push({ el, ch });
                twDrain();
            }
            let responseVisible = "";
            function typewriteMarkdown(textSpan, text) {
                for (const ch of text) {
                    twQueue.push({ ch, onChar: (c) => {
                        responseVisible += c;
                        textSpan.innerHTML = markdownToHtml(responseVisible);
                    }});
                }
                twDrain();
            }

            let initialStatus = document.createElement('div');
            initialStatus.className = 'stream-status thinking-status';
            initialStatus.innerHTML = `<span class="thinking-label">let me think</span><div class="typing-indicator-mini"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
            messageDiv.appendChild(initialStatus);

            let unprocessedText = "";
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    unprocessedText += decoder.decode(value, { stream: true });
                    const lines = unprocessedText.split('\n');
                    unprocessedText = lines.pop();

                    for (let line of lines) {
                        await new Promise(r => setTimeout(r, 0));
                        if (!line.trim() || !line.startsWith('data: ')) continue;
                        let dataText = line.trim();
                        // Robust stripping of all SSE data prefixes
                        while (dataText.startsWith('data: ')) {
                            dataText = dataText.slice(6).trim();
                        }
                        if (!dataText || dataText === '[DONE]') break;

                        try {
                            const data = JSON.parse(dataText);

                            if (data.type === 'iteration_start') {
                                // Ensure the react container exists
                                if (!reactContainer) {
                                    reactContainer = document.createElement('div');
                                    reactContainer.className = 'react-container';
                                    messageDiv.appendChild(reactContainer);
                                }
                                // New iteration block
                                currentIterDiv = document.createElement('div');
                                currentIterDiv.className = 'react-iteration';
                                reactContainer.appendChild(currentIterDiv);
                            }
                            else if (data.type === 'thought') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                const line = document.createElement('div');
                                line.className = 'thought-line';
                                const text = data.content.length > 80 ? data.content.slice(0, 80) + '…' : data.content;
                                (currentIterDiv || messageDiv).appendChild(line);
                                typewrite(line, text);
                            }
                            else if (data.type === 'thought_token') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                const parent = currentIterDiv || messageDiv;
                                let last = parent.querySelector('.thought-line:last-child');
                                if (!last) {
                                    last = document.createElement('div');
                                    last.className = 'thought-line';
                                    parent.appendChild(last);
                                }
                                typewrite(last, data.content);
                            }
                            else if (data.type === 'action') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                const line = document.createElement('div');
                                line.className = 'action-line';
                                line.textContent = data.content;
                                (currentIterDiv || messageDiv).appendChild(line);
                            }
                            else if (data.type === 'action_result') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                const line = document.createElement('div');
                                line.className = 'action-result-line';
                                line.textContent = data.content;
                                (currentIterDiv || messageDiv).appendChild(line);
                            }
                            else if (data.type === 'hitl_question' || data.type === 'hitl_checkpoint') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                const bubble = document.createElement('div');
                                bubble.className = 'hitl-checkpoint-bubble';
                                if (data.checkpoint_mode) {
                                    bubble.setAttribute('data-mode', data.checkpoint_mode);
                                }
                                const text = document.createElement('span');
                                bubble.appendChild(text);
                                (currentIterDiv || messageDiv).appendChild(bubble);
                                typewriteMarkdown(text, data.content);
                                // Also capture as response content for history saving
                                responseContent += (responseContent ? '\n\n' : '') + data.content;
                            }
                            else if (data.type === 'response' || data.type === 'text') {
                                if (initialStatus) { initialStatus.remove(); initialStatus = null; }
                                responseContent += data.content;
                                let textSpan = messageDiv.querySelector('.response-text');
                                if (!textSpan) {
                                    textSpan = document.createElement('div');
                                    textSpan.className = 'response-text';
                                    messageDiv.appendChild(textSpan);
                                }
                                typewriteMarkdown(textSpan, data.content);
                            }
                            else if (data.type === 'status' || data.type === 'tool_start') {
                                let statusEl = messageDiv.querySelector('.stream-status');
                                if (!statusEl) {
                                    statusEl = document.createElement('div');
                                    statusEl.className = 'stream-status';
                                    messageDiv.appendChild(statusEl);
                                }
                                statusEl.innerHTML = `<i>${data.content || 'Working...'}</i> <div class="typing-indicator-mini"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
                            }
                            else if (data.type === 'error') {
                                messageDiv.innerHTML += `<div class="error-text">Error: ${data.content}</div>`;
                            }
                        } catch (e) {
                            console.error("Error parsing stream chunk:", e, dataText);
                        }
                    }
                    chatArea.scrollTop = chatArea.scrollHeight;
                }
            } finally {
                if (initialStatus) initialStatus.remove();
                const sEl = messageDiv.querySelector('.stream-status');
                if (sEl) sEl.remove();
            }

            processPlanResponse(responseContent, originalText, true);
        }
        else {
            const data = await response.json();
            if (data.response) {
                processPlanResponse(data.response, originalText, false);
            } else if (data.error) {
                addMessage(`Error: ${data.error}`, false);
            }
        }
    }

    let isAgentBusy = false;
    let currentAbortController = null;

    const SEND_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`;
    const STOP_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>`;

    function setBusy(busy) {
        isAgentBusy = busy;
        sendBtn.innerHTML = busy ? STOP_ICON : SEND_ICON;
        sendBtn.title = busy ? 'Stop' : 'Send';
        messageInput.disabled = busy;
        sendBtn.classList.toggle('is-stop', busy);
    }

    sendBtn.addEventListener('click', () => {
        if (isAgentBusy) {
            if (currentAbortController) currentAbortController.abort();
            setBusy(false);
            removeTypingIndicator();
        } else {
            handleSend();
        }
    });
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !isAgentBusy) handleSend();
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

                await parseResponse(response, text);
            } catch (error) {
                removeTypingIndicator();
                addMessage("Error connecting to planning service.", false);
            }
        });
    }

    function processPlanResponse(responseText, originalTask, isAlreadyDisplayed = false) {
        // Detect workmap creation — inject a "View Workmap" button into chat
        const isWorkmapResponse = (
            responseText.includes("workmap") || responseText.includes("Workmap") ||
            responseText.includes("PLAY") || responseText.includes("canvas")
        );

        if (isWorkmapResponse && activeAgentId) {
            // Show the response text first
            if (!isAlreadyDisplayed) {
                addMessage(responseText, false);
            }
            // Refresh the agent canvas — workmap generation may have auto-created new agents
            if (window.agentCanvasInstance && typeof window.agentCanvasInstance.loadAgents === 'function') {
                window.agentCanvasInstance.loadAgents();
            }
            // Inject the "View Workmap" button into the chat
            const chatArea = document.getElementById('chat-area');
            const btnDiv = document.createElement('div');
            btnDiv.style.textAlign = 'center';
            btnDiv.style.padding = '6px 0';
            const btn = document.createElement('button');
            btn.className = 'view-workmap-btn';
            btn.textContent = '🗺  View Project Workmap';
            btn.addEventListener('click', () => openWorkmapView(activeAgentId));
            btnDiv.appendChild(btn);
            chatArea.appendChild(btnDiv);
            chatArea.scrollTop = chatArea.scrollHeight;
            return;
        }

        // Check if this is an execution plan response using varied headers
        if (responseText.includes("Execution Plan Generated") ||
            responseText.includes("### 📝") ||
            responseText.includes("### 🎯")) {
            const planAreaDiv = document.getElementById('autonomous-plan-area');
            const planContentDiv = document.getElementById('plan-content');

            const stepsMatch = responseText.match(/(\d+\.\s+.+?)(?=\n\d+\.|Plan file|$)/gs);
            if (stepsMatch) {
                const stepsHtml = stepsMatch
                    .map(step => step.trim())
                    .map(step => `<div class="plan-step">• ${step}</div>`)
                    .join('');
                planContentDiv.innerHTML = stepsHtml;
                planAreaDiv.style.display = 'block';
                planAreaDiv.dataset.agentId = activeAgentId;
                planAreaDiv.dataset.task = originalTask;
                addMessage(`Execution plan generated with ${stepsMatch.length} steps. Use the plan panel to execute.`, false);
            } else if (!isAlreadyDisplayed) {
                addMessage(responseText, false);
            }
        } else {
            if (!isAlreadyDisplayed) {
                addMessage(responseText, false);
            }
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


// ── WORKMAP TREE VIEW (Full-Screen DAG Canvas) ──────────────────────

let _workmapPollInterval = null;
let _workmapAgentId = null;
let _workmapCache = null;          // cached workmap data for modal use
let _availableAgents = [];         // cached agent list for dropdowns
let _editingNodeId = null;         // currently editing node

// ── PAN + ZOOM STATE ─────────────────────────────────────────────────
let _wmPan = { x: 0, y: 0 };
let _wmZoom = 1;
let _wmIsPanning = false;
let _wmPanEventsAttached = false;

function _wmApplyTransform() {
    const panLayer = document.getElementById('workmap-pan-layer');
    const grid = document.querySelector('.wm-grid-layer');
    if (panLayer) {
        panLayer.style.transform = `translate(${_wmPan.x}px, ${_wmPan.y}px) scale(${_wmZoom})`;
    }
    if (grid) {
        grid.style.backgroundPosition = `${_wmPan.x}px ${_wmPan.y}px`;
        grid.style.backgroundSize = `${24 * _wmZoom}px ${24 * _wmZoom}px`;
    }
}

function _wmInitPanZoom() {
    if (_wmPanEventsAttached) return;
    const container = document.getElementById('workmap-tree-container');
    if (!container) return;
    _wmPanEventsAttached = true;

    // Pan — mousedown on empty canvas area
    container.addEventListener('mousedown', (e) => {
        // Ignore clicks on nodes (they open the edit modal) or toolbar
        if (e.target.closest('.wm-node') || e.target.closest('.workmap-toolbar')) return;
        if (e.button !== 0) return;
        _wmIsPanning = true;
        container.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
        if (!_wmIsPanning) return;
        _wmPan.x += e.movementX;
        _wmPan.y += e.movementY;
        _wmApplyTransform();
    });

    document.addEventListener('mouseup', () => {
        if (!_wmIsPanning) return;
        _wmIsPanning = false;
        const container = document.getElementById('workmap-tree-container');
        if (container) container.style.cursor = 'grab';
    });

    // Zoom — mouse wheel
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.08 : 0.08;
        const newZoom = Math.min(2.5, Math.max(0.25, _wmZoom + delta));

        // Zoom toward mouse pointer
        const rect = container.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const scale = newZoom / _wmZoom;
        _wmPan.x = mx - scale * (mx - _wmPan.x);
        _wmPan.y = my - scale * (my - _wmPan.y);
        _wmZoom = newZoom;

        _wmApplyTransform();
    }, { passive: false });
}

function _wmResetView() {
    _wmPan = { x: 0, y: 0 };
    _wmZoom = 1;
    _wmApplyTransform();
}

function openWorkmapView(agentId) {
    _workmapAgentId = agentId;
    const overlay = document.getElementById('workmap-overlay');
    if (!overlay) return;
    overlay.style.display = 'flex';

    // Init pan/zoom (event listeners attach once)
    _wmInitPanZoom();
    _wmResetView();

    // Load available agents for dropdowns
    _loadAvailableAgents(agentId);

    // Fetch and render immediately
    fetchAndRenderWorkmap(agentId);

    // Start live polling (every 3s while the view is open)
    clearInterval(_workmapPollInterval);
    _workmapPollInterval = setInterval(() => fetchAndRenderWorkmap(agentId), 3000);
}
window.openWorkmapView = openWorkmapView;

function closeWorkmapView() {
    const overlay = document.getElementById('workmap-overlay');
    if (overlay) overlay.style.display = 'none';
    clearInterval(_workmapPollInterval);
    _workmapPollInterval = null;
    _workmapAgentId = null;
    _workmapCache = null;
    _wmIsPanning = false;
    closeNodeModal();
}

async function _loadAvailableAgents(agentId) {
    try {
        const r = await fetch(`http://localhost:8000/workmap/${agentId}/agents`);
        if (r.ok) _availableAgents = await r.json();
    } catch (_) {
        _availableAgents = [{ id: 'self', name: 'Master (self)' }];
    }
}

async function fetchAndRenderWorkmap(agentId) {
    try {
        const r = await fetch(`http://localhost:8000/workmap/${agentId}`);
        if (!r.ok) return;
        const wm = await r.json();
        _workmapCache = wm;
        renderWorkmapTree(wm, agentId);
    } catch (_) { }
}

function _wmAutoLayout(nodes) {
    // Topological BFS to assign levels, then compute x/y for each node
    const NODE_W = 270, NODE_H = 150, GAP_X = 60, GAP_Y = 100, PAD = 80;
    const levels = {};
    const visited = new Set();
    const queue = [];

    nodes.forEach(n => {
        if (!n.dependencies || n.dependencies.length === 0) {
            levels[n.id] = 0; queue.push(n.id); visited.add(n.id);
        }
    });
    while (queue.length > 0) {
        const cur = queue.shift();
        nodes.forEach(n => {
            if (n.dependencies && n.dependencies.includes(cur) && !visited.has(n.id)) {
                if (n.dependencies.every(d => visited.has(d))) {
                    levels[n.id] = Math.max(...n.dependencies.map(d => levels[d] || 0)) + 1;
                    visited.add(n.id); queue.push(n.id);
                }
            }
        });
    }
    nodes.forEach(n => { if (!(n.id in levels)) levels[n.id] = 0; });

    const maxLevel = Math.max(...Object.values(levels), 0);
    const levelGroups = [];
    for (let i = 0; i <= maxLevel; i++) levelGroups.push(nodes.filter(n => levels[n.id] === i));

    // Find the widest level to center everything around it
    const maxGroupWidth = Math.max(...levelGroups.map(g => g.length * NODE_W + (g.length - 1) * GAP_X));
    const centerX = PAD + maxGroupWidth / 2;

    const positions = {};
    levelGroups.forEach((group, lvl) => {
        const totalW = group.length * NODE_W + (group.length - 1) * GAP_X;
        const startX = centerX - totalW / 2;
        group.forEach((n, idx) => {
            positions[n.id] = {
                x: Math.max(PAD, startX + idx * (NODE_W + GAP_X)),
                y: PAD + lvl * (NODE_H + GAP_Y)
            };
        });
    });
    return positions;
}

function renderWorkmapTree(workmap, agentId) {
    const nodesContainer = document.getElementById('workmap-nodes');
    const edgesSvg = document.getElementById('workmap-edges');
    const statusBadge = document.getElementById('workmap-status-badge');
    const titleEl = document.getElementById('workmap-title');
    const deadlineInput = document.getElementById('wm-deadline-input');
    if (!nodesContainer || !edgesSvg) return;

    // Update toolbar
    const st = (workmap.status || 'PAUSED').toUpperCase();
    statusBadge.textContent = st;
    statusBadge.className = 'workmap-badge workmap-badge-' + st.toLowerCase();
    titleEl.textContent = 'Project Workmap — ' + (workmap.project_id || '');

    if (deadlineInput && document.activeElement !== deadlineInput) {
        deadlineInput.value = workmap.deadline_hours || '';
    }

    const nodes = workmap.nodes || [];
    if (nodes.length === 0) {
        nodesContainer.innerHTML = '<div style="color:rgba(255,255,255,0.3); text-align:center; padding:60px;">No nodes yet. Click "+ Add Node" or right-click to add.</div>';
        return;
    }

    // Compute auto-layout for nodes that don't have saved positions
    const autoPos = _wmAutoLayout(nodes);
    // Render nodes with absolute positioning
    nodesContainer.style.position = 'relative';
    nodesContainer.innerHTML = '';

    nodes.forEach(n => {
        const posX = (n.x != null) ? n.x : (autoPos[n.id] ? autoPos[n.id].x : 60);
        const posY = (n.y != null) ? n.y : (autoPos[n.id] ? autoPos[n.id].y : 60);

        const statusKey = (n.status || 'PENDING').toLowerCase().replace('_', '-');
        const timeStr = n.estimated_minutes ? `<span class="wm-node-time">${n.estimated_minutes}m</span>` : '';
        const label = n.label || n.id;
        const agentDisplay = (n.agent === agentId || n.agent === 'self') ? 'Master (self)' : n.agent;
        const el = document.createElement('div');
        el.className = `wm-node wm-node-${statusKey} wm-node-abs`;
        el.setAttribute('data-node-id', n.id);
        el.style.left = posX + 'px';
        el.style.top = posY + 'px';
        el.innerHTML = `
            <div class="wm-node-header">
                <span class="wm-node-label">${label}</span>
                <div class="wm-node-header-right">
                    ${timeStr}
                    <span class="wm-node-status">${n.status || 'PENDING'}</span>
                </div>
            </div>
            <div class="wm-node-task">${n.task}</div>
            <div class="wm-node-meta">
                <span class="wm-node-agent">${agentDisplay}</span>
                <span class="wm-node-id">${n.id}</span>
            </div>
            ${n.dependencies && n.dependencies.length ? `<div class="wm-node-deps">after: ${n.dependencies.map(d => { const dn = nodes.find(nd => nd.id === d); return dn && dn.label ? dn.label : d; }).join(', ')}</div>` : ''}
        `;

        // Double-click to edit
        el.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            openNodeModal(n.id);
        });

        // Right-click on node — show context with Edit + Remove
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            _wmShowContextMenu(e.clientX, e.clientY, n.id);
        });

        // Drag to move
        _wmMakeNodeDraggable(el, n.id);

        nodesContainer.appendChild(el);
    });

    requestAnimationFrame(() => drawWorkmapEdges(nodes, nodesContainer, edgesSvg));
}

function drawWorkmapEdges(nodes, container, svg) {
    // Nodes are absolutely positioned inside the container — read left/top + size directly
    let paths = '';
    let maxRight = 0, maxBottom = 0;

    nodes.forEach(node => {
        if (!node.dependencies) return;
        const targetEl = container.querySelector(`[data-node-id="${node.id}"]`);
        if (!targetEl) return;

        node.dependencies.forEach(depId => {
            const sourceEl = container.querySelector(`[data-node-id="${depId}"]`);
            if (!sourceEl) return;

            // Read positions from style (absolute coords within nodes container)
            const sx = sourceEl.offsetLeft + sourceEl.offsetWidth / 2;
            const sy = sourceEl.offsetTop + sourceEl.offsetHeight;
            const tx = targetEl.offsetLeft + targetEl.offsetWidth / 2;
            const ty = targetEl.offsetTop;

            maxRight = Math.max(maxRight, sx, tx);
            maxBottom = Math.max(maxBottom, sy, ty);

            const depNode = nodes.find(n => n.id === depId);
            let edgeClass = 'wm-edge';
            if (node.status === 'IN_PROGRESS') edgeClass = 'wm-edge wm-edge-active';
            else if (depNode && depNode.status === 'COMPLETED' && node.status === 'COMPLETED') edgeClass = 'wm-edge wm-edge-done';

            const midY = (sy + ty) / 2;
            paths += `<path class="${edgeClass}" d="M ${sx} ${sy} C ${sx} ${midY}, ${tx} ${midY}, ${tx} ${ty}" />\n`;
        });
    });

    svg.innerHTML = paths;
    svg.style.width = (maxRight + 300) + 'px';
    svg.style.height = (maxBottom + 200) + 'px';
}

function _wmRedrawEdgesLive() {
    // Redraw edges using cached data while dragging — avoids a full re-render
    if (!_workmapCache) return;
    const container = document.getElementById('workmap-nodes');
    const svg = document.getElementById('workmap-edges');
    if (container && svg) drawWorkmapEdges(_workmapCache.nodes || [], container, svg);
}


// ── NODE DRAGGING ────────────────────────────────────────────────────

let _wmDragState = null;   // { el, nodeId, startX, startY, origLeft, origTop, moved }

function _wmMakeNodeDraggable(el, nodeId) {
    // Entire node is the drag handle (like the agent canvas)
    el.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;     // left click only
        e.stopPropagation();            // don't trigger canvas pan
        _wmDragState = {
            el,
            nodeId,
            startX: e.clientX,
            startY: e.clientY,
            origLeft: parseInt(el.style.left) || 0,
            origTop: parseInt(el.style.top) || 0,
            moved: false
        };
        el.classList.add('wm-node-dragging');
    });
}

document.addEventListener('mousemove', (e) => {
    if (!_wmDragState) return;
    const dx = (e.clientX - _wmDragState.startX) / _wmZoom;
    const dy = (e.clientY - _wmDragState.startY) / _wmZoom;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) _wmDragState.moved = true;
    _wmDragState.el.style.left = (_wmDragState.origLeft + dx) + 'px';
    _wmDragState.el.style.top = (_wmDragState.origTop + dy) + 'px';
    _wmRedrawEdgesLive();
});

document.addEventListener('mouseup', () => {
    if (!_wmDragState) return;
    const { el, nodeId, moved } = _wmDragState;
    el.classList.remove('wm-node-dragging');

    if (moved && _workmapAgentId) {
        const newX = parseInt(el.style.left) || 0;
        const newY = parseInt(el.style.top) || 0;

        // Persist position to backend (fire-and-forget)
        fetch(`http://localhost:8000/workmap/${_workmapAgentId}/node/${nodeId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x: newX, y: newY })
        }).catch(() => { });

        // Update local cache so polling doesn't snap it back
        if (_workmapCache) {
            const n = (_workmapCache.nodes || []).find(nd => nd.id === nodeId);
            if (n) { n.x = newX; n.y = newY; }
        }
    }
    _wmDragState = null;
});


// ── RIGHT-CLICK CONTEXT MENU ─────────────────────────────────────────

let _wmCtxNodeId = null;    // node that was right-clicked (null = empty canvas)
let _wmCtxX = 0;            // canvas-relative X for new node placement
let _wmCtxY = 0;

function _wmShowContextMenu(clientX, clientY, nodeId) {
    const menu = document.getElementById('wm-context-menu');
    if (!menu) return;
    _wmCtxNodeId = nodeId || null;

    // Position menu at cursor
    menu.style.left = clientX + 'px';
    menu.style.top = clientY + 'px';
    menu.style.display = 'flex';

    // Show/hide node-specific actions
    menu.querySelector('[data-action="edit-step"]').style.display = nodeId ? 'block' : 'none';
    menu.querySelector('[data-action="remove-step"]').style.display = nodeId ? 'block' : 'none';

    // Calculate canvas-relative position for the new node
    const panLayer = document.getElementById('workmap-pan-layer');
    if (panLayer) {
        const rect = panLayer.getBoundingClientRect();
        _wmCtxX = (clientX - rect.left) / _wmZoom;
        _wmCtxY = (clientY - rect.top) / _wmZoom;
    }
}

function _wmHideContextMenu() {
    const menu = document.getElementById('wm-context-menu');
    if (menu) menu.style.display = 'none';
    _wmCtxNodeId = null;
}

// Wire up context menu on the tree container (empty canvas right-click)
document.addEventListener('DOMContentLoaded', () => {
    const treeContainer = document.getElementById('workmap-tree-container');
    if (treeContainer) {
        treeContainer.addEventListener('contextmenu', (e) => {
            // Only fire if we're in the workmap overlay
            const overlay = document.getElementById('workmap-overlay');
            if (!overlay || overlay.style.display === 'none') return;
            e.preventDefault();
            // If right-click was on a node, that node's own handler fired first
            if (e.target.closest('.wm-node')) return;
            _wmShowContextMenu(e.clientX, e.clientY, null);
        });
    }

    // Context menu action dispatch
    const ctxMenu = document.getElementById('wm-context-menu');
    if (ctxMenu) {
        ctxMenu.addEventListener('click', async (e) => {
            const action = e.target.getAttribute('data-action');
            if (!action) return;
            _wmHideContextMenu();

            if (action === 'add-step') {
                // Open the add-node modal, pre-set position
                openAddNodeModal(_wmCtxX, _wmCtxY);
            } else if (action === 'edit-step' && _wmCtxNodeId) {
                openNodeModal(_wmCtxNodeId);
            } else if (action === 'remove-step' && _wmCtxNodeId) {
                const ok = confirm(`Delete ${_wmCtxNodeId}? Dependencies will be cleaned up.`);
                if (!ok) return;
                try {
                    await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/node/${_wmCtxNodeId}`, { method: 'DELETE' });
                } catch (_) { }
                fetchAndRenderWorkmap(_workmapAgentId);
            }
        });
    }

    // Close context menu on any left click or Escape
    document.addEventListener('click', _wmHideContextMenu);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') _wmHideContextMenu(); });
});


// ── NODE EDIT MODAL ──────────────────────────────────────────────────

function openNodeModal(nodeId) {
    if (!_workmapCache || !_workmapAgentId) return;
    const node = (_workmapCache.nodes || []).find(n => n.id === nodeId);
    if (!node) return;

    _editingNodeId = nodeId;

    // Populate fields
    document.getElementById('wm-edit-node-id').value = nodeId;
    document.getElementById('wm-modal-title').textContent = `Edit: ${node.label || nodeId}`;
    document.getElementById('wm-edit-label').value = node.label || '';
    document.getElementById('wm-edit-task').value = node.task || '';
    document.getElementById('wm-edit-status').value = node.status || 'PENDING';
    document.getElementById('wm-edit-time').value = node.estimated_minutes || '';

    // Populate agent dropdown
    const agentSel = document.getElementById('wm-edit-agent');
    agentSel.innerHTML = _availableAgents.map(a =>
        `<option value="${a.id}" ${a.id === node.agent ? 'selected' : ''}>${a.name}</option>`
    ).join('');

    // Populate dependencies as toggleable chips
    const depsContainer = document.getElementById('wm-edit-deps');
    const otherNodes = (_workmapCache.nodes || []).filter(n => n.id !== nodeId);
    const currentDeps = new Set(node.dependencies || []);
    depsContainer.innerHTML = otherNodes.map(n => {
        const active = currentDeps.has(n.id) ? 'active' : '';
        return `<button class="wm-dep-chip ${active}" data-dep="${n.id}" type="button">${n.id}</button>`;
    }).join('');

    // Toggle chip on click
    depsContainer.querySelectorAll('.wm-dep-chip').forEach(chip => {
        chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    // Show/hide delete button (don't show for the last remaining node)
    const deleteBtn = document.getElementById('wm-modal-delete');
    deleteBtn.style.display = (_workmapCache.nodes || []).length > 1 ? 'inline-flex' : 'none';

    // Show modal
    document.getElementById('wm-node-modal-overlay').style.display = 'flex';
}

let _newNodeX = 0, _newNodeY = 0;  // position for newly created nodes

function openAddNodeModal(x, y) {
    if (!_workmapCache || !_workmapAgentId) return;

    _editingNodeId = null; // null signals "create new"
    _newNodeX = x || 0;
    _newNodeY = y || 0;

    document.getElementById('wm-edit-node-id').value = '';
    document.getElementById('wm-modal-title').textContent = 'Add New Step';
    document.getElementById('wm-edit-label').value = '';
    document.getElementById('wm-edit-task').value = '';
    document.getElementById('wm-edit-status').value = 'PENDING';
    document.getElementById('wm-edit-time').value = '';

    // Agent dropdown
    const agentSel = document.getElementById('wm-edit-agent');
    agentSel.innerHTML = _availableAgents.map(a =>
        `<option value="${a.id}">${a.name}</option>`
    ).join('');

    // Dependencies — all existing nodes available as chips
    const depsContainer = document.getElementById('wm-edit-deps');
    depsContainer.innerHTML = (_workmapCache.nodes || []).map(n =>
        `<button class="wm-dep-chip" data-dep="${n.id}" type="button">${n.id}</button>`
    ).join('');
    depsContainer.querySelectorAll('.wm-dep-chip').forEach(chip => {
        chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    // Hide delete button for new nodes
    document.getElementById('wm-modal-delete').style.display = 'none';

    document.getElementById('wm-node-modal-overlay').style.display = 'flex';
}

function closeNodeModal() {
    document.getElementById('wm-node-modal-overlay').style.display = 'none';
    _editingNodeId = null;
}

function _getSelectedDeps() {
    return Array.from(document.querySelectorAll('#wm-edit-deps .wm-dep-chip.active'))
        .map(chip => chip.getAttribute('data-dep'));
}

async function saveNodeChanges() {
    if (!_workmapAgentId) return;

    const label = document.getElementById('wm-edit-label').value.trim();
    const task = document.getElementById('wm-edit-task').value.trim();
    if (!task) { alert('Task description is required.'); return; }

    const agent = document.getElementById('wm-edit-agent').value;
    const status = document.getElementById('wm-edit-status').value;
    const time = parseInt(document.getElementById('wm-edit-time').value) || 0;
    const deps = _getSelectedDeps();

    try {
        if (_editingNodeId) {
            // UPDATE existing node
            await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/node/${_editingNodeId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, task, agent, status, estimated_minutes: time, dependencies: deps })
            });
        } else {
            // CREATE new node at the position where user right-clicked (or 0,0)
            await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/node`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label: label || task.slice(0, 30), task, agent, dependencies: deps, estimated_minutes: time, x: _newNodeX, y: _newNodeY })
            });
        }
    } catch (err) {
        console.error('Save node error:', err);
    }

    closeNodeModal();
    fetchAndRenderWorkmap(_workmapAgentId);
}

async function deleteCurrentNode() {
    if (!_editingNodeId || !_workmapAgentId) return;

    const confirmed = confirm(`Delete ${_editingNodeId}? This will also remove it from other nodes' dependencies.`);
    if (!confirmed) return;

    try {
        await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/node/${_editingNodeId}`, {
            method: 'DELETE'
        });
    } catch (err) {
        console.error('Delete node error:', err);
    }

    closeNodeModal();
    fetchAndRenderWorkmap(_workmapAgentId);
}

async function saveDeadline(value) {
    if (!_workmapAgentId) return;
    const hours = parseInt(value);
    if (isNaN(hours) || hours < 1) return;
    try {
        await fetch(`http://localhost:8000/workmap/${_workmapAgentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deadline_hours: hours })
        });
    } catch (err) {
        console.error('Save deadline error:', err);
    }
}


// ── WIRE UP ALL TOOLBAR + MODAL BUTTONS ──────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const backBtn = document.getElementById('workmap-back-btn');
    const playBtn = document.getElementById('workmap-play-btn');
    const pauseBtn = document.getElementById('workmap-pause-btn');
    const addNodeBtn = document.getElementById('workmap-add-node-btn');
    const deadlineInput = document.getElementById('wm-deadline-input');

    if (backBtn) backBtn.addEventListener('click', closeWorkmapView);

    if (playBtn) playBtn.addEventListener('click', async () => {
        if (!_workmapAgentId) return;
        await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/play`, { method: 'POST' });
        fetchAndRenderWorkmap(_workmapAgentId);
    });

    if (pauseBtn) pauseBtn.addEventListener('click', async () => {
        if (!_workmapAgentId) return;
        await fetch(`http://localhost:8000/workmap/${_workmapAgentId}/pause`, { method: 'POST' });
        fetchAndRenderWorkmap(_workmapAgentId);
    });

    if (addNodeBtn) addNodeBtn.addEventListener('click', () => {
        // Place new node near the center of the visible viewport
        const panLayer = document.getElementById('workmap-pan-layer');
        const container = document.getElementById('workmap-tree-container');
        let cx = 300, cy = 200;
        if (panLayer && container) {
            const cRect = container.getBoundingClientRect();
            cx = (cRect.width / 2 - _wmPan.x) / _wmZoom;
            cy = (cRect.height / 2 - _wmPan.y) / _wmZoom;
        }
        openAddNodeModal(cx, cy);
    });

    // Deadline — save on blur or Enter
    if (deadlineInput) {
        deadlineInput.addEventListener('change', (e) => saveDeadline(e.target.value));
        deadlineInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.target.blur(); saveDeadline(e.target.value); }
        });
    }

    // Modal buttons
    const modalClose = document.getElementById('wm-modal-close');
    const modalCancel = document.getElementById('wm-modal-cancel');
    const modalSave = document.getElementById('wm-modal-save');
    const modalDelete = document.getElementById('wm-modal-delete');
    const modalOverlay = document.getElementById('wm-node-modal-overlay');

    if (modalClose) modalClose.addEventListener('click', closeNodeModal);
    if (modalCancel) modalCancel.addEventListener('click', closeNodeModal);
    if (modalSave) modalSave.addEventListener('click', saveNodeChanges);
    if (modalDelete) modalDelete.addEventListener('click', deleteCurrentNode);

    // Close modal on background click
    if (modalOverlay) modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeNodeModal();
    });
});
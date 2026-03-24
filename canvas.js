class AgentCanvas {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.nodesLayer = document.getElementById('nodes-layer');
        this.svgLayer = this.container.querySelector('.connections-layer');
        this.gridLayer = this.container.querySelector('.grid-layer');

        this.nodes = [];
        this.connections = [];
        this.draggedNode = null;
        this.draggedConnection = null;
        this.offset = { x: 0, y: 0 };

        this.isPanning = false;
        this.pan = { x: 0, y: 0 };
        this.nodeIdCounter = 1;

        // Selection Lasso
        this.isSelecting = false;
        this.selectionStart = { x: 0, y: 0 };
        this.selectionBox = null;
        this.selectedNodes = new Set();

        this.initContextMenu();
        this.initGalleryButton();
        this.initEventListeners();
        this.loadAgents();

        // Listen for backend logs
        if (window.electronAPI && window.electronAPI.onBackendLog) {
            window.electronAPI.onBackendLog((log) => {
                // Pattern 1: [STATUS:agent-id] Message — updates the active agent's terminal
                const statusRegex = /\[STATUS:([\w-]+)\]\s*(.*)/g;
                let match;
                while ((match = statusRegex.exec(log)) !== null) {
                    const agentId = match[1];
                    const statusText = match[2].trim();
                    if (statusText) {
                        this.logToTerminal(agentId, statusText);
                    }
                }

                // Pattern 2: [AGENT_MSG:sender->target] — animate the TARGET node too
                const agentMsgRegex = /\[AGENT_MSG:([\w-]+)->([\w-]+)\]/g;
                let agentMatch;
                while ((agentMatch = agentMsgRegex.exec(log)) !== null) {
                    const targetId = agentMatch[2];
                    // Show the target as receiving an incoming message
                    this.logToTerminal(targetId, 'Message incoming');
                }
            });
        }
    }

    initEventListeners() {
        this.container.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.container.addEventListener('contextmenu', (e) => this.onContextMenu(e));
        document.addEventListener('mousemove', (e) => this.onMouseMove(e));
        document.addEventListener('mouseup', (e) => this.onMouseUp(e));
        document.addEventListener('click', () => this.hideContextMenu());
        document.addEventListener('keydown', (e) => this.onKeyDown(e));
        window.addEventListener('resize', () => this.onResize());
    }

    onResize() {
        // Redraw connections when the window or panel resizes
        this.updateConnections();
    }

    createNode(id, title, content, x, y, data = {}) {
        const nodeEl = document.createElement('div');
        nodeEl.className = 'agent-node';
        nodeEl.id = id;
        nodeEl.style.left = `${x}px`;
        nodeEl.style.top = `${y}px`;

        const agentType = data.agentType || 'worker';
        const isMaster = agentType === 'master';
        if (isMaster) nodeEl.classList.add('master-role');

        nodeEl.innerHTML = `
            <div class="node-port port-in"></div>
            <div class="node-header">
                <span class="node-title" contenteditable="true" spellcheck="false" style="outline:none; min-width: 50px;">${title}</span>
                <span class="agent-type-badge ${isMaster ? '' : 'worker'}" data-type="${agentType}" title="Click to toggle Master/Worker role">${isMaster ? 'MASTER' : 'WORKER'}</span>
                <span class="expand-btn" style="opacity:0.5; cursor: pointer; font-size: 12px;">▼</span>
            </div>
            <div class="node-settings" style="display:none;">
                <div class="setting-row" style="margin-top: 10px;">
                    <label>Working Dir:</label>
                    <span class="workdir-display" title="${data.workingDir || ''}">${data.workingDir || 'Not set'}</span>
                </div>
                <button class="train-btn">Configure & Train</button>
                <button class="delete-btn">Delete Agent</button>
            </div>
            <div class="node-body">${content}</div>
            <div class="workmap-dag" id="dag-${id}" style="display:none;">
                <div class="dag-header">
                    <span class="dag-title">WORKMAP</span>
                    <div class="dag-controls">
                        <button class="dag-play-btn" data-agent="${id}" title="Resume execution">&#9654;</button>
                        <button class="dag-pause-btn" data-agent="${id}" title="Pause execution">&#9646;&#9646;</button>
                    </div>
                </div>
                <div class="dag-nodes" id="dag-nodes-${id}"></div>
            </div>
            <div class="node-terminal">
                <div class="terminal-header">LIVE BACKEND</div>
                <div class="terminal-content" id="term-${id}">> Agent initialized...</div>
            </div>
            <div class="node-port port-out"></div>
        `;

        // Agent Type Toggle
        const typeBadge = nodeEl.innerHTML !== "" ? nodeEl.querySelector('.agent-type-badge') : null;
        if (typeBadge) {
            typeBadge.addEventListener('mousedown', (e) => e.stopPropagation());
            typeBadge.addEventListener('click', async (e) => {
                e.stopPropagation();
                const currentType = typeBadge.getAttribute('data-type');
                const newType = (currentType === 'master') ? 'worker' : 'master';

                // UI Update
                typeBadge.setAttribute('data-type', newType);
                typeBadge.innerText = newType.toUpperCase();
                if (newType === 'master') {
                    typeBadge.classList.remove('worker');
                    nodeEl.classList.add('master-role');
                } else {
                    typeBadge.classList.add('worker');
                    nodeEl.classList.remove('master-role');
                }

                // Data Update
                const nodeObj = this.nodes.find(n => n.id === id);
                if (nodeObj) {
                    nodeObj.data.agentType = newType;

                    // Save to Backend
                    await this.saveAgentData(id);

                    // If this agent is currently open in training panel, sync it
                    if (window.activeTrainingAgentId === id) {
                        const planBtn = document.getElementById('generate-plan-btn');
                        if (planBtn) {
                            planBtn.style.display = (newType === 'master') ? 'block' : 'none';
                        }
                    }
                }
            });
        }

        // Settings Toggle
        const expandBtn = nodeEl.querySelector('.expand-btn');
        const settingsPanel = nodeEl.querySelector('.node-settings');

        expandBtn.addEventListener('mousedown', (e) => e.stopPropagation());
        expandBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = settingsPanel.style.display === 'none';
            settingsPanel.style.display = isHidden ? 'block' : 'none';
            expandBtn.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';

            if (isHidden) {
                nodeEl.classList.add('expanded');
            } else {
                nodeEl.classList.remove('expanded');
            }
        });
        settingsPanel.addEventListener('mousedown', (e) => e.stopPropagation());

        // Workmap Play/Pause buttons
        const dagPlayBtn = nodeEl.querySelector('.dag-play-btn');
        const dagPauseBtn = nodeEl.querySelector('.dag-pause-btn');
        if (dagPlayBtn) {
            dagPlayBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            dagPlayBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    await fetch(`http://localhost:8000/workmap/${id}/play`, { method: 'POST' });
                    this.logToTerminal(id, 'Workmap RESUMED');
                } catch (err) { console.error('Workmap play error:', err); }
            });
        }
        if (dagPauseBtn) {
            dagPauseBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            dagPauseBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    await fetch(`http://localhost:8000/workmap/${id}/pause`, { method: 'POST' });
                    this.logToTerminal(id, 'Workmap PAUSED');
                } catch (err) { console.error('Workmap pause error:', err); }
            });
        }

        // Train Button
        const trainBtn = nodeEl.querySelector('.train-btn');
        trainBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const currentTitle = nodeEl.querySelector('.node-title').innerText;
            if (window.openTrainingPanel) {
                window.openTrainingPanel(id, currentTitle);
            } else {
                console.error("Training panel script not loaded.");
            }
        });
        trainBtn.addEventListener('mousedown', (e) => e.stopPropagation());

        // Delete Button
        const deleteBtn = nodeEl.querySelector('.delete-btn');
        deleteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const agentName = nodeEl.querySelector('.node-title').innerText;
            const confirmed = await window.customConfirm(`Are you sure you want to delete "${agentName}"?`);
            if (confirmed) {
                this.deleteAgent(id);
            }
        });
        deleteBtn.addEventListener('mousedown', (e) => e.stopPropagation());

        // Drag Handle
        const header = nodeEl.querySelector('.node-header');
        header.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('node-title')) return;

            this.draggedNode = nodeEl;
            this.offset.x = e.clientX - nodeEl.offsetLeft;
            this.offset.y = e.clientY - nodeEl.offsetTop;

            // Visual selection
            document.querySelectorAll('.agent-node').forEach(n => n.classList.remove('selected'));
            nodeEl.classList.add('selected');
        });

        // Connection Drag Start (Output Port)
        const portOut = nodeEl.querySelector('.port-out');
        portOut.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            this.startConnectionDrag(id, e);
        });

        // Auto-save listeners for text and selects
        const titleEl = nodeEl.querySelector('.node-title');
        titleEl.addEventListener('blur', () => this.saveAgentData(id));
        titleEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                titleEl.blur();
            }
        });
        nodeEl.querySelector('.node-body').addEventListener('blur', () => this.saveAgentData(id));

        this.nodesLayer.appendChild(nodeEl);
        this.nodes.push({ id, el: nodeEl, data });
        return nodeEl;
    }

    deleteConnection(sourceId, targetId) {
        const index = this.connections.findIndex(c => c.sourceId === sourceId && c.targetId === targetId);
        if (index !== -1) {
            this.connections[index].path.remove();
            this.connections.splice(index, 1);
            this.saveAgentData(sourceId); // Assuming saving source updates connections
        }
    }

    connectNodes(sourceId, targetId) {
        if (this.connections.some(c => c.sourceId === sourceId && c.targetId === targetId)) return;

        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.classList.add('connection-line');
        path.setAttribute('id', `conn-${sourceId}-${targetId}`);
        this.svgLayer.appendChild(path);

        this.connections.push({ sourceId, targetId, path });
        this.updateConnections();
    }

    updateConnections() {
        this.connections.forEach(conn => {
            const source = document.getElementById(conn.sourceId);
            const target = document.getElementById(conn.targetId);
            if (!source || !target) return;

            // Calculate port positions
            const sourceRect = source.getBoundingClientRect();
            const targetRect = target.getBoundingClientRect();

            // Start from right side of source, end at left side of target
            const x1 = source.offsetLeft + sourceRect.width;
            const y1 = source.offsetTop + 29; // Approx port height
            const x2 = target.offsetLeft;
            const y2 = target.offsetTop + 29;

            // Cubic Bezier Curve
            const cpOffset = Math.abs(x2 - x1) * 0.5;
            const d = `M ${x1} ${y1} C ${x1 + cpOffset} ${y1}, ${x2 - cpOffset} ${y2}, ${x2} ${y2}`;

            conn.path.setAttribute('d', d);
        });
    }

    startConnectionDrag(sourceId, e) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.classList.add('connection-line');
        path.style.pointerEvents = 'none'; // Ensure mouse events pass through to target port
        this.svgLayer.appendChild(path);
        this.draggedConnection = { sourceId, path };
        this.updateTempConnection(e);
    }

    updateTempConnection(e) {
        const sourceNode = document.getElementById(this.draggedConnection.sourceId);
        if (!sourceNode) return;

        // Calculate start point (Right side of source node)
        const x1 = sourceNode.offsetLeft + sourceNode.offsetWidth;
        const y1 = sourceNode.offsetTop + 29;

        // Calculate end point (Mouse position transformed to world space)
        const rect = this.container.getBoundingClientRect();
        const x2 = (e.clientX - rect.left) - this.pan.x;
        const y2 = (e.clientY - rect.top) - this.pan.y;

        // Cubic Bezier Curve
        const cpOffset = Math.abs(x2 - x1) * 0.5;
        const d = `M ${x1} ${y1} C ${x1 + cpOffset} ${y1}, ${x2 - cpOffset} ${y2}, ${x2} ${y2}`;

        this.draggedConnection.path.setAttribute('d', d);
    }

    onMouseDown(e) {
        const node = e.target.closest('.agent-node');

        // Right-click drag = Lasso Selection
        if (e.button === 2) {
            if (!node) {
                if (!e.shiftKey) {
                    this.selectedNodes.clear();
                    document.querySelectorAll('.agent-node').forEach(n => n.classList.remove('selected'));
                }
                this.isSelecting = true;
                this.selectionStart = { x: e.clientX, y: e.clientY };
                this.selectionBox = document.createElement('div');
                this.selectionBox.className = 'selection-box';
                document.body.appendChild(this.selectionBox);
                this.container.style.cursor = 'crosshair';
                this.lassoDragStarted = false; // Reset lasso drag flag
                return;
            }
        }

        // Left-click (button 0)
        if (e.button !== 0) return;

        if (!node) {
            // Clicked on empty canvas (Left Click)
            this.isPanning = true;
            this.container.style.cursor = 'grabbing';
            return;
        }

        // Clicked on a node
        const nodeId = node.id;
        if (e.shiftKey) {
            // Multi-toggle
            if (this.selectedNodes.has(nodeId)) {
                this.selectedNodes.delete(nodeId);
                node.classList.remove('selected');
            } else {
                this.selectedNodes.add(nodeId);
                node.classList.add('selected');
            }
        } else {
            // Single select (if not already selected)
            if (!this.selectedNodes.has(nodeId)) {
                this.selectedNodes.clear();
                document.querySelectorAll('.agent-node').forEach(n => n.classList.remove('selected'));
                this.selectedNodes.add(nodeId);
                node.classList.add('selected');
            }
        }

        this.draggedNode = node;
        this.offset.x = e.clientX - node.offsetLeft;
        this.offset.y = e.clientY - node.offsetTop;

        // Remember offsets for all selected nodes for multi-drag
        this.selectedNodeOffsets = new Map();
        this.selectedNodes.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                this.selectedNodeOffsets.set(id, {
                    x: e.clientX - el.offsetLeft,
                    y: e.clientY - el.offsetTop
                });
            }
        });
    }

    onMouseMove(e) {
        if (this.draggedNode) {
            this.selectedNodes.forEach(id => {
                const nodeEl = document.getElementById(id);
                const offset = this.selectedNodeOffsets.get(id);
                if (nodeEl && offset) {
                    nodeEl.style.left = `${e.clientX - offset.x}px`;
                    nodeEl.style.top = `${e.clientY - offset.y}px`;
                }
            });
            this.updateConnections();
        } else if (this.draggedConnection) {
            this.updateTempConnection(e);
        } else if (this.isSelecting) {
            this.lassoDragStarted = true;
            const currentX = e.clientX;
            const currentY = e.clientY;
            const x = Math.min(this.selectionStart.x, currentX);
            const y = Math.min(this.selectionStart.y, currentY);
            const width = Math.abs(this.selectionStart.x - currentX);
            const height = Math.abs(this.selectionStart.y - currentY);

            this.selectionBox.style.left = `${x}px`;
            this.selectionBox.style.top = `${y}px`;
            this.selectionBox.style.width = `${width}px`;
            this.selectionBox.style.height = `${height}px`;
        } else if (this.isPanning) {
            this.pan.x += e.movementX;
            this.pan.y += e.movementY;
            this.updateTransform();
        }
    }

    onMouseUp(e) {
        if (this.draggedConnection) {
            const target = e.target;
            if (target.classList.contains('port-in')) {
                const targetNode = target.closest('.agent-node');
                if (targetNode && targetNode.id !== this.draggedConnection.sourceId) {
                    this.connectNodes(this.draggedConnection.sourceId, targetNode.id);
                    this.saveAgentData(this.draggedConnection.sourceId);
                }
            }
            this.draggedConnection.path.remove();
            this.draggedConnection = null;
            return;
        }

        if (this.isSelecting) {
            const rect = this.selectionBox.getBoundingClientRect();
            this.nodes.forEach(node => {
                const nodeRect = node.el.getBoundingClientRect();
                if (
                    nodeRect.left >= rect.left &&
                    nodeRect.right <= rect.right &&
                    nodeRect.top >= rect.top &&
                    nodeRect.bottom <= rect.bottom
                ) {
                    this.selectedNodes.add(node.id);
                    node.el.classList.add('selected');
                }
            });
            this.selectionBox.remove();
            this.selectionBox = null;
            this.isSelecting = false;
        }

        if (this.draggedNode) {
            this.selectedNodes.forEach(id => this.saveAgentData(id));
        }

        this.draggedNode = null;
        this.selectedNodeOffsets = null;
        this.isPanning = false;
        this.container.style.cursor = 'grab';
    }

    async onKeyDown(e) {
        if (e.key === 'Delete' || e.key === 'Backspace') {
            // Only if not typing in a field
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;

            if (this.selectedNodes.size > 0) {
                const confirmed = await window.customConfirm(`Delete ${this.selectedNodes.size} selected agents?`);
                if (confirmed) {
                    const toDelete = Array.from(this.selectedNodes);
                    this.selectedNodes.clear();
                    for (const id of toDelete) {
                        await this.deleteAgent(id);
                    }
                }
            }
        }
    }

    updateTransform() {
        this.nodesLayer.style.transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
        this.svgLayer.style.transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
        this.gridLayer.style.backgroundPosition = `${this.pan.x}px ${this.pan.y}px`;
    }

    initContextMenu() {
        this.contextMenu = document.createElement('div');
        this.contextMenu.className = 'context-menu';
        this.contextMenu.innerHTML = `<div class="context-menu-item">Add an Agent</div>`;
        document.body.appendChild(this.contextMenu);

        this.contextMenu.querySelector('.context-menu-item').addEventListener('click', () => {
            this.addAgentAtMouse();
            this.hideContextMenu();
        });
    }

    onContextMenu(e) {
        e.preventDefault();
        if (this.lassoDragStarted) {
            this.lassoDragStarted = false;
            return;
        }
        this.contextMenuMousePosition = { x: e.clientX, y: e.clientY };
        this.contextMenu.style.left = `${e.clientX}px`;
        this.contextMenu.style.top = `${e.clientY}px`;
        this.contextMenu.style.display = 'block';
    }

    hideContextMenu() {
        if (this.contextMenu) this.contextMenu.style.display = 'none';
    }

    addAgentAtMouse() {
        this.nodeIdCounter++;
        const name = ''; // Empty name to start
        // Generate ID: agent-X-Timestamp
        const id = `agent-bot-${Date.now()}`;
        const x = this.contextMenuMousePosition.x - this.pan.x;
        const y = this.contextMenuMousePosition.y - this.pan.y;

        const newAgent = {
            id, name, description: 'Agent description...', x, y,
            brain: '', channel: 'Gmail', role: 'Assistant',
            workingDir: '', permissions: [], specialRole: 'Custom'
        };

        // Render immediately
        const nodeEl = this.createNode(id, name, 'Agent description...', x, y, newAgent);

        // Put cursor in the name field immediately
        const titleEl = nodeEl.querySelector('.node-title');
        setTimeout(() => {
            titleEl.focus();
            // Optional: check if we should put a placeholder or just leave it empty
        }, 100);

        // Save to Python Backend
        fetch('http://localhost:8000/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newAgent)
        }).catch(err => console.error("Error creating agent:", err));
    }

    initGalleryButton() {
        const addBtn = document.getElementById('add-agent-btn');
        const overlay = document.getElementById('gallery-overlay');
        const closeBtn = document.getElementById('gallery-modal-close');
        const grid = document.getElementById('gallery-modal-grid');
        if (!addBtn || !overlay || !grid) return;

        // Render gallery cards from AGENT_GALLERY (defined in agent-training.js)
        const renderGalleryCards = () => {
            const templates = (typeof AGENT_GALLERY !== 'undefined') ? AGENT_GALLERY : [];
            grid.innerHTML = templates.map(tpl => `
                <div class="gallery-modal-card" data-template="${tpl.id}">
                    <span class="gallery-modal-icon">${tpl.icon}</span>
                    <div class="gallery-modal-info">
                        <span class="gallery-modal-name">${tpl.name}</span>
                        <span class="gallery-modal-desc">${tpl.description}</span>
                    </div>
                </div>
            `).join('');

            grid.querySelectorAll('.gallery-modal-card').forEach(card => {
                card.addEventListener('click', () => {
                    const templateId = card.dataset.template;
                    const tpl = templates.find(t => t.id === templateId);
                    overlay.classList.remove('open');
                    this.addAgentFromTemplate(tpl);
                });
            });
        };

        addBtn.addEventListener('click', () => {
            renderGalleryCards();
            overlay.classList.add('open');
        });

        if (closeBtn) {
            closeBtn.addEventListener('click', () => overlay.classList.remove('open'));
        }

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.classList.remove('open');
        });
    }

    addAgentFromTemplate(template) {
        this.nodeIdCounter++;
        const id = `agent-bot-${Date.now()}`;

        // Place at center of viewport
        const cx = (window.innerWidth / 2) - this.pan.x;
        const cy = (window.innerHeight / 2) - this.pan.y;

        const newAgent = {
            id,
            name: template && template.id !== 'custom' ? template.name : '',
            description: template && template.id !== 'custom' ? template.description : 'Agent description...',
            x: cx, y: cy,
            brain: '', channel: 'Gmail', role: 'Assistant',
            workingDir: '',
            permissions: template ? [...template.permissions] : [],
            specialRole: template ? template.id : 'custom'
        };

        if (template && template.responsibility) {
            newAgent.responsibility = template.responsibility;
        }

        const nodeEl = this.createNode(id, newAgent.name, newAgent.description, cx, cy, newAgent);

        // Focus name field if custom, otherwise just select it
        const titleEl = nodeEl.querySelector('.node-title');
        setTimeout(() => titleEl.focus(), 100);

        fetch('http://localhost:8000/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newAgent)
        }).catch(err => console.error("Error creating agent:", err));
    }

    async saveAgentData(id) {
        const nodeEl = document.getElementById(id);
        if (!nodeEl) return;

        const nodeObj = this.nodes.find(n => n.id === id);
        const existingData = nodeObj ? nodeObj.data : {};

        const name = nodeEl.querySelector('.node-title').innerText;
        const description = nodeEl.querySelector('.node-body').innerText;

        const x = parseInt(nodeEl.style.left) || 0;
        const y = parseInt(nodeEl.style.top) || 0;

        const connections = this.connections
            .filter(c => c.sourceId === id)
            .map(c => c.targetId);

        const brain = nodeEl.querySelector('.brain-provider-select')?.value || existingData.brain;

        const agentData = {
            ...existingData,
            name, description, x, y, connections, brain
        };

        if (nodeObj) nodeObj.data = agentData;

        try {
            await fetch(`http://localhost:8000/agents/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(agentData)
            });
        } catch (error) {
            console.error("Error saving agent data:", error);
        }
    }

    async deleteAgent(agentId) {
        try {
            const response = await fetch(`http://localhost:8000/agents/${agentId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to delete agent on backend');
            }

            const nodeToRemove = document.getElementById(agentId);
            if (nodeToRemove) {
                nodeToRemove.remove();
            }

            // If the deleted agent was being trained, close the panel
            if (window.activeTrainingAgentId === agentId && window.closeTrainingPanel) {
                window.closeTrainingPanel();
            }

            // Clean up internal state
            this.nodes = this.nodes.filter(n => n.id !== agentId);
            this.connections = this.connections.filter(conn => {
                if (conn.sourceId === agentId || conn.targetId === agentId) {
                    conn.path.remove();
                    return false;
                }
                return true;
            });

            // Ensure we don't think we're dragging a deleted node
            if (this.draggedNode && this.draggedNode.id === agentId) {
                this.draggedNode = null;
            }

            // Fallback for Electron UI freezing after deletions
            setTimeout(() => {
                document.body.style.userSelect = '';
                document.body.style.pointerEvents = '';
            }, 50);

        } catch (error) {
            console.error("Error deleting agent:", error);
            await window.customConfirm(`Could not delete agent: ${error.message}`);
        }
    }

    clearCanvas() {
        if (this.nodes) {
            this.nodes.forEach(n => {
                if (n.el && n.el.parentNode) n.el.remove();
            });
        }
        if (this.connections) {
            this.connections.forEach(c => {
                if (c.path && c.path.parentNode) c.path.remove();
            });
        }
        this.nodes = [];
        this.connections = [];
    }

    async loadAgents(retries = 5) {
        // ALWAYS clear before starting a fresh load to prevent duplication
        this.clearCanvas();

        try {
            const response = await fetch('http://localhost:8000/agents');
            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const agents = await response.json();

            // Re-render all agents
            agents.forEach(agent => {
                this.createNode(agent.id, agent.name, agent.description, agent.x, agent.y, agent);
            });

            // Restore connections
            agents.forEach(agent => {
                if (agent.connections) {
                    agent.connections.forEach(targetId => {
                        this.connectNodes(agent.id, targetId);
                    });
                }
            });

            // Center view on nodes
            if (agents.length > 0) {
                setTimeout(() => this.centerView(), 50);
            }

            // Start workmap polling once agents are loaded
            if (!this._workmapPollingStarted) {
                this._workmapPollingStarted = true;
                this.startWorkmapPolling();
            }
        } catch (error) {
            if (retries > 0) {
                console.log(`Backend not ready, retrying in 1s... (${retries} retries left)`);
                setTimeout(() => this.loadAgents(retries - 1), 1000);
            } else {
                console.error("Failed to load agents from backend after retries:", error);
                // Fallback only if backend is definitely unreachable
                this.createNode('agent-MasterBot-001', 'MasterBot', 'Main orchestrator agent.', 100, 150);
            }
        }
    }

    updateWorkmapNodes(agentId, workmap) {
        const dagEl = document.getElementById(`dag-${agentId}`);
        const dagNodesEl = document.getElementById(`dag-nodes-${agentId}`);
        if (!dagEl || !dagNodesEl) return;

        const nodes = workmap && workmap.nodes;
        if (!nodes || nodes.length === 0) {
            dagEl.style.display = 'none';
            return;
        }

        dagEl.style.display = 'block';
        dagNodesEl.innerHTML = nodes.map(node => {
            const statusClass = 'dag-node-status-' + node.status.toLowerCase().replace('_', '-');
            const label = node.task.length > 42 ? node.task.substring(0, 42) + '...' : node.task;
            return `<div class="dag-node ${statusClass}" title="${node.task}">
                <span class="dag-node-label">${label}</span>
                <span class="dag-node-badge">${node.status}</span>
            </div>`;
        }).join('');
    }

    startWorkmapPolling() {
        // Polls all agents for workmaps every 5 seconds (matches backend tick interval).
        // Also runs once immediately so existing workmaps render on page load.
        const pollAll = async () => {
            for (const nodeObj of this.nodes) {
                try {
                    const r = await fetch(`http://localhost:8000/workmap/${nodeObj.id}`);
                    if (r.ok) this.updateWorkmapNodes(nodeObj.id, await r.json());
                } catch (_) { /* worker agent — no workmap, expected */ }
            }
        };

        // Run immediately on startup, then every 5 seconds
        pollAll();
        setInterval(pollAll, 5000);
    }

    centerView() {
        if (this.nodes.length === 0) return;

        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;

        this.nodes.forEach(node => {
            const el = node.el;
            const x = parseInt(el.style.left) || 0;
            const y = parseInt(el.style.top) || 0;
            const w = el.offsetWidth || 300;
            const h = el.offsetHeight || 200;

            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x + w > maxX) maxX = x + w;
            if (y + h > maxY) maxY = y + h;
        });

        const contentCenterX = (minX + maxX) / 2;
        const contentCenterY = (minY + maxY) / 2;

        const rect = this.container.getBoundingClientRect();
        const containerCenterX = rect.width / 2;
        const containerCenterY = rect.height / 2;

        this.pan.x = containerCenterX - contentCenterX;
        this.pan.y = containerCenterY - contentCenterY;

        this.updateTransform();
    }

    updateNodeInPlace(id, data) {
        const node = this.nodes.find(n => n.id === id);
        if (!node) return;

        node.data = { ...node.data, ...data };
        const el = node.el;

        if (data.name) {
            const titleEl = el.querySelector('.node-title');
            if (titleEl) titleEl.innerText = data.name;
        }
        if (data.description) {
            const bodyEl = el.querySelector('.node-body');
            if (bodyEl) bodyEl.innerText = data.description;
        }
    }

    logToTerminal(agentId, message) {
        const terminal = document.getElementById(`term-${agentId}`);
        if (!terminal || !message) return;

        // If the training panel is open for this agent, ignore "Ready" status
        // and keep it as "Training"
        if (window.isTrainingPanelOpen && window.activeTrainingAgentId === agentId) {
            if (message.trim().toLowerCase() === 'ready') {
                return; // Suppress "Ready" while panel is open
            }
        }

        // Clean trailing dots to avoid double dots with animation
        let cleanMessage = message.replace(/\.+$/, '').trim();

        // Clean the terminal
        terminal.innerHTML = `> ${cleanMessage}`;

        // Add animated dots if we are performing an action
        const lowerMsg = cleanMessage.toLowerCase();
        const keywords = ['training', 'searching', 'thinking', 'generating', 'processing', 'talking', 'message received', 'incoming', 'contacting'];
        if (keywords.some(kw => lowerMsg.includes(kw))) {
            const dots = document.createElement('span');
            dots.className = 'loading-dots';
            terminal.appendChild(dots);
        }
    }
}

// Global Custom Confirm Modal to replace buggy Electron native confirm()
window.customConfirm = function (message) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('custom-confirm-overlay');
        const msgEl = document.getElementById('custom-confirm-message');
        const btnCancel = document.getElementById('custom-confirm-cancel');
        const btnOk = document.getElementById('custom-confirm-ok');

        if (!overlay) {
            // Fallback if HTML is missing
            resolve(confirm(message));
            return;
        }

        msgEl.textContent = message;
        overlay.style.display = 'flex';

        // Cleanup function to remove listeners
        const cleanup = () => {
            overlay.style.display = 'none';
            btnCancel.removeEventListener('click', onCancel);
            btnOk.removeEventListener('click', onOk);
        };

        const onCancel = () => { cleanup(); resolve(false); };
        const onOk = () => { cleanup(); resolve(true); };

        btnCancel.addEventListener('click', onCancel);
        btnOk.addEventListener('click', onOk);
    });
};

window.AgentCanvas = AgentCanvas;
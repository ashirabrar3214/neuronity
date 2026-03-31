class AgentCanvas {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.nodesLayer = document.getElementById('nodes-layer');
        this.svgLayer = this.container.querySelector('.connections-layer');

        this.nodes = [];
        this.connections = [];
        this.draggedNode = null;
        this.draggedConnection = null;
        this.offset = { x: 0, y: 0 };

        this.isPanning = false;
        this.pan = { x: 0, y: 0 };
        this.zoom = 1;
        this.nodeIdCounter = 1;

        // Selection Lasso
        this.isSelecting = false;
        this.selectionStart = { x: 0, y: 0 };
        this.selectionBox = null;
        this.selectedNodes = new Set();

        this.selectedNodes = new Set();
        this.initGalleryButton();
        this.initEventListeners();
        this.updateTransform(); // Apply grid styles immediately on first paint
        this.loadAgents();

    }

    initEventListeners() {
        this.container.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.container.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });
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
                <span class="node-title" style="min-width: 50px;">${title}</span>
                <span class="agent-type-badge ${isMaster ? '' : 'worker'}" data-type="${agentType}">${isMaster ? 'MASTER' : 'WORKER'}</span>
                <span class="expand-btn" style="opacity:0.5; cursor: pointer; font-size: 12px;">▼</span>
            </div>
            <div class="node-settings" style="display:none;">
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

        // Delete Button (with dynamic text based on agent type)
        const deleteBtn = nodeEl.querySelector('.delete-btn');
        const updateDeleteButtonText = () => {
            const agentType = data.agentType || 'worker';
            const btnText = agentType === 'master' ? 'Delete Workflow' : 'Delete Agent';
            deleteBtn.textContent = btnText;
            deleteBtn.title = agentType === 'master' ? 'Delete entire workflow (all 4 agents)' : 'Delete this agent only';
        };
        updateDeleteButtonText();

        deleteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const agentName = nodeEl.querySelector('.node-title').innerText;
            const agentType = data.agentType || 'worker';
            const isMaster = agentType === 'master';
            const actionText = isMaster ? 'delete the entire workflow' : `delete "${agentName}"`;
            const confirmed = await window.customConfirm(`Are you sure you want to ${actionText}? This cannot be undone.`);
            if (confirmed) {
                this.deleteAgent(id, data);
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

            // Use offsetWidth/Height for original (unscaled) dimensions
            // x1 is right side of source, x2 is left side of target
            const x1 = source.offsetLeft + source.offsetWidth;
            const y1 = source.offsetTop + 29; // Center of port (top 24px + 5px radius)
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

        const x1 = sourceNode.offsetLeft + sourceNode.offsetWidth;
        const y1 = sourceNode.offsetTop + 29;

        // Transform mouse position to world space
        const rect = this.container.getBoundingClientRect();
        const x2 = (e.clientX - rect.left - this.pan.x) / this.zoom;
        const y2 = (e.clientY - rect.top - this.pan.y) / this.zoom;

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
        const rect = this.container.getBoundingClientRect();
        const mx = (e.clientX - rect.left - this.pan.x) / this.zoom;
        const my = (e.clientY - rect.top - this.pan.y) / this.zoom;

        // Remember offsets for all selected nodes for multi-drag
        this.selectedNodeOffsets = new Map();
        this.selectedNodes.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                this.selectedNodeOffsets.set(id, {
                    x: mx - el.offsetLeft,
                    y: my - el.offsetTop
                });
            }
        });
    }

    onMouseMove(e) {
        const rect = this.container.getBoundingClientRect();
        // Update spotlight position
        this.container.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
        this.container.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);

        if (this.draggedNode) {
            const rect = this.container.getBoundingClientRect();
            const mx = (e.clientX - rect.left - this.pan.x) / this.zoom;
            const my = (e.clientY - rect.top - this.pan.y) / this.zoom;

            this.selectedNodes.forEach(id => {
                const nodeEl = document.getElementById(id);
                const offset = this.selectedNodeOffsets.get(id);
                if (nodeEl && offset) {
                    nodeEl.style.left = `${mx - offset.x}px`;
                    nodeEl.style.top = `${my - offset.y}px`;
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
                        const nodeObj = this.nodes.find(n => n.id === id);
                        await this.deleteAgent(id, nodeObj ? nodeObj.data : null);
                    }
                }
            }
        }
    }

    updateTransform() {
        const t = `translate(${this.pan.x}px, ${this.pan.y}px) scale(${this.zoom})`;
        this.nodesLayer.style.transform = t;
        this.svgLayer.style.transform = t;
        this.nodesLayer.style.transformOrigin = '0 0';
        this.svgLayer.style.transformOrigin = '0 0';

        const majorSize = `${200 * this.zoom}px ${200 * this.zoom}px`;
        const minorSize = `${40  * this.zoom}px ${40  * this.zoom}px`;
        const bgPos = `${this.pan.x}px ${this.pan.y}px`;
        document.querySelectorAll('.grid-layer').forEach(grid => {
            grid.style.backgroundPosition = `${bgPos}, ${bgPos}, ${bgPos}, ${bgPos}`;
            grid.style.backgroundSize = `${majorSize}, ${majorSize}, ${minorSize}, ${minorSize}`;
        });
    }

    onWheel(e) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.05 : 0.05;
        const newZoom = Math.min(2, Math.max(0.3, this.zoom + delta));

        // Zoom toward cursor position
        const rect = this.container.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        this.pan.x = mx - (mx - this.pan.x) * (newZoom / this.zoom);
        this.pan.y = my - (my - this.pan.y) * (newZoom / this.zoom);
        this.zoom = newZoom;
        this.updateTransform();
        this.updateConnections();
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
            // Close the menu bar dropdown if open
            document.querySelectorAll('.menu-bar-item').forEach(m => m.classList.remove('open'));
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
        // Handle workflow templates (multiple agents)
        if (template && template.isWorkflow && template.agents && template.agents.length > 0) {
            this.addWorkflowAgents(template);
            return;
        }

        // Handle single agent templates
        this.nodeIdCounter++;
        const id = `agent-bot-${Date.now()}`;

        // Place at center of viewport
        const rect = this.container.getBoundingClientRect();
        const cx = ((rect.width / 2) - this.pan.x) / this.zoom;
        const cy = ((rect.height / 2) - this.pan.y) / this.zoom;

        const newAgent = {
            id,
            name: template && template.id !== 'custom' ? template.name : '',
            description: template && template.id !== 'custom' ? template.description : 'Agent description...',
            x: cx, y: cy,
            brain: (template && template.brain) || '', channel: 'Gmail', role: 'Assistant',
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

    addWorkflowAgents(workflow) {
        // Arrange agents in layout
        const rect = this.container.getBoundingClientRect();
        const centerX = ((rect.width / 2) - this.pan.x) / this.zoom;
        const centerY = ((rect.height / 2) - this.pan.y) / this.zoom;

        // Generate unique workflow ID
        const workflowId = `workflow-${Date.now()}`;

        let positions;
        const isFourAgent = workflow.agents.length === 4;
        
        if (isFourAgent) {
            // Diamond pipeline: Research (left) → Synthesis (top) / Visual (bottom) → PDF (right)
            positions = [
                { x: centerX - 350, y: centerY, label: "Research Agent" },      // 0: Left
                { x: centerX, y: centerY - 160, label: "Synthesis Agent" },     // 1: Center Top
                { x: centerX, y: centerY + 160, label: "Visual Analyst" },      // 2: Center Bottom
                { x: centerX + 350, y: centerY, label: "PDF Generator" }        // 3: Right
            ];
        } else {
            // Linear pipeline fallback
            positions = [
                { x: centerX - 350, y: centerY, label: "Research Agent" },      // 0: Left (MASTER)
                { x: centerX, y: centerY, label: "Synthesis Agent" },           // 1: Center
                { x: centerX + 350, y: centerY, label: "PDF Generator" }        // 2: Right
            ];
        }

        const createdAgentIds = [];

        workflow.agents.forEach((agentTemplate, index) => {
            this.nodeIdCounter++;
            const id = `agent-bot-${Date.now() + index}`;
            const pos = positions[index] || { x: centerX, y: centerY };

            const newAgent = {
                id,
                name: agentTemplate.name || '',
                description: agentTemplate.description || '',
                x: pos.x,
                y: pos.y,
                brain: agentTemplate.brain || 'gemini-3.0-pro',
                channel: 'Direct',
                role: 'Assistant',
                workingDir: '',
                permissions: agentTemplate.permissions ? [...agentTemplate.permissions] : [],
                specialRole: agentTemplate.specialRole || 'custom',
                agentType: agentTemplate.agentType || 'worker',
                responsibility: agentTemplate.responsibility || '',
                workflowId: workflowId,  // Track which workflow this agent belongs to
            };

            this.createNode(id, newAgent.name, newAgent.description, pos.x, pos.y, newAgent);
            createdAgentIds.push(id);

            // Send to backend
            fetch('http://localhost:8000/agents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newAgent)
            }).catch(err => console.error("Error creating agent:", err));
        });

        // Auto-connect agents based on size
        if (isFourAgent && createdAgentIds.length >= 4) {
            // Diamond Connections
            this.connectNodes(createdAgentIds[0], createdAgentIds[1]); // Research -> Synthesis
            this.connectNodes(createdAgentIds[0], createdAgentIds[2]); // Research -> Visual
            this.connectNodes(createdAgentIds[1], createdAgentIds[3]); // Synthesis -> PDF
            this.connectNodes(createdAgentIds[2], createdAgentIds[3]); // Visual -> PDF
            createdAgentIds.forEach(id => this.saveAgentData(id));
        } else if (createdAgentIds.length >= 3) {
            // Linear Connections
            this.connectNodes(createdAgentIds[0], createdAgentIds[1]);
            this.connectNodes(createdAgentIds[1], createdAgentIds[2]);
            createdAgentIds.forEach(id => this.saveAgentData(id));
        }
    }

    async saveAgentData(id) {
        const nodeEl = document.getElementById(id);
        if (!nodeEl) return;

        const nodeObj = this.nodes.find(n => n.id === id);
        const existingData = nodeObj ? nodeObj.data : {};

        const name = existingData.name || nodeEl.querySelector('.node-title').innerText;
        const description = existingData.description || nodeEl.querySelector('.node-body').innerText;

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

    async deleteAgent(agentId, agentData) {
        try {
            // Check if this is a master agent - if so, delete entire workflow
            const isMaster = agentData && agentData.agentType === 'master';
            const workflowId = agentData && agentData.workflowId;

            let agentsToDelete = [agentId];

            // If master agent, find all agents in the same workflow
            if (isMaster && workflowId) {
                agentsToDelete = this.nodes
                    .filter(n => n.data && n.data.workflowId === workflowId)
                    .map(n => n.id);
            }

            // Delete all agents (usually just 1 unless it's a master agent deleting the workflow)
            for (const id of agentsToDelete) {
                const response = await fetch(`http://localhost:8000/agents/${id}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to delete agent on backend');
                }

                const nodeToRemove = document.getElementById(id);
                if (nodeToRemove) {
                    nodeToRemove.remove();
                }

                // If the deleted agent was being trained, close the panel
                if (window.activeTrainingAgentId === id && window.closeTrainingPanel) {
                    window.closeTrainingPanel();
                }
            }

            // Clean up internal state
            this.nodes = this.nodes.filter(n => !agentsToDelete.includes(n.id));
            this.connections = this.connections.filter(conn => {
                if (agentsToDelete.includes(conn.sourceId) || agentsToDelete.includes(conn.targetId)) {
                    conn.path.remove();
                    return false;
                }
                return true;
            });

            // Ensure we don't think we're dragging a deleted node
            if (this.draggedNode && agentsToDelete.includes(this.draggedNode.id)) {
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

            // Auto-open training panel for the master agent
            const master = agents.find(a => a.agentType === 'master');
            if (master && window.openTrainingPanel) {
                setTimeout(() => window.openTrainingPanel(master.id, master.name), 200);
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
                // No fallback agent - user must create workflow explicitly
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
        const keywords = ['training', 'searching', 'thinking', 'generating', 'processing', 'talking', 'message received', 'incoming', 'contacting', 'gathering', 'scraping', 'building', 'analyzing', 'reading', 'writing', 'compiling', 'receiving', 'sending'];
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
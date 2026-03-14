const fs = require('fs');
const path = require('path');

class Agent {
    constructor(config) {
        this.id = config.id;
        this.name = config.name;
        this.description = config.description;
        
        // Configuration from UI
        this.brain = config.brain; // e.g., 'Anthropic', 'Gemini'
        this.channel = config.channel;
        this.role = config.role;
        this.permissions = config.permissions || [];
        this.specialRoles = config.specialRoles || [];
        this.workingDirectory = config.workingDirectory;

        // Runtime state
        this.context = [];
        this.isBusy = false;
    }

    // Generates the system prompt based on configuration
    buildSystemPrompt() {
        let prompt = `You are ${this.name}, acting as a ${this.role}.\n`;
        prompt += `Description: ${this.description}\n`;
        
        if (this.workingDirectory) {
            prompt += `Current Working Directory: ${this.workingDirectory}\n`;
        }

        if (this.permissions.length > 0) {
            prompt += `You have the following capabilities: ${this.permissions.join(', ')}\n`;
        }

        return prompt;
    }

    async execute(input) {
        this.isBusy = true;
        console.log(`[${this.name}] Processing:`, input);
        
        // TODO: Implement LLM API calls here based on this.brain
        
        this.isBusy = false;
        return { status: 'success', message: 'Agent logic not yet connected to LLM.' };
    }
}

class AgentOrchestrator {
    constructor() {
        this.agents = new Map();
    }

    createAgent(config) {
        const agent = new Agent(config);
        this.agents.set(agent.id, agent);
        console.log(`Agent created: ${agent.name} (${agent.id})`);
        return agent;
    }

    getAgent(id) {
        return this.agents.get(id);
    }

    removeAgent(id) {
        this.agents.delete(id);
    }

    getAllAgents() {
        return Array.from(this.agents.values());
    }
}

module.exports = new AgentOrchestrator();
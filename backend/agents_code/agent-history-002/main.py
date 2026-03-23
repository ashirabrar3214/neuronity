
class agent_history_002:
    def __init__(self):
        self.id = "agent-history-002"
        self.name = "History"
        self.working_dir = r""
        self.permissions = ['web search', 'file access']
        self.tools = "Custom"

    def get_personality(self):
        import json
        import os
        try:
            with open(os.path.join(os.path.dirname(__file__), 'personality.json'), 'r', encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

if __name__ == "__main__":
    agent = agent_history_002()
    print(f"Agent {agent.name} initialized.")

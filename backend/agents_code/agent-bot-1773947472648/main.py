
class agent_bot_1773947472648:
    def __init__(self):
        self.id = "agent-bot-1773947472648"
        self.name = "A"
        self.working_dir = r""
        self.permissions = []
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
    agent = agent_bot_1773947472648()
    print(f"Agent {agent.name} initialized.")

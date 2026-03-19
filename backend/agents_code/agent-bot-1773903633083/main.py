
class agent_bot_1773903633083:
    def __init__(self):
        self.id = "agent-bot-1773903633083"
        self.name = "Geopolitics Researcher"
        self.working_dir = r""
        self.permissions = ['web search']
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
    agent = agent_bot_1773903633083()
    print(f"Agent {agent.name} initialized.")

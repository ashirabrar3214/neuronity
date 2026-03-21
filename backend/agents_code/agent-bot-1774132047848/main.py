
class agent_bot_1774132047848:
    def __init__(self):
        self.id = "agent-bot-1774132047848"
        self.name = "Maater"
        self.working_dir = r"D:\New folder"
        self.permissions = ['web search', 'thinking', 'report generation', 'scheduling', 'file access']
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
    agent = agent_bot_1774132047848()
    print(f"Agent {agent.name} initialized.")

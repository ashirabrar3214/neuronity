
class agent_bot_1774326906234:
    def __init__(self):
        self.id = "agent-bot-1774326906234"
        self.name = "MasterAgent"
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
    agent = agent_bot_1774326906234()
    print(f"Agent {agent.name} initialized.")

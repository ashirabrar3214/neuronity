
class agent_sociopolitical_001:
    def __init__(self):
        self.id = "agent-sociopolitical-001"
        self.name = "Sociopolitical"
        self.working_dir = r"D:\New folder"
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
    agent = agent_sociopolitical_001()
    print(f"Agent {agent.name} initialized.")

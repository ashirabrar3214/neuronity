
class agent_NewAgent_1773504720806:
    def __init__(self):
        self.id = "agent-NewAgent-1773504720806"
        self.name = "Reporter"
        self.working_dir = r"D:\New folder"
        self.permissions = ['report generation', 'file access']
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
    agent = agent_NewAgent_1773504720806()
    print(f"Agent {agent.name} initialized.")

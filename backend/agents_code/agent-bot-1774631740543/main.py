
class agent_bot_1774631740543:
    def __init__(self):
        self.id = "agent-bot-1774631740543"
        self.name = "Research Agent"
        self.working_dir = r"D:\New folder"
        self.permissions = ['scrape website', 'recursive verification', 'knowledge graph construction']
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
    agent = agent_bot_1774631740543()
    print(f"Agent {agent.name} initialized.")

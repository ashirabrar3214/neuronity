import os
from capabilities import make_tool
import shutil

backend_dir = os.path.dirname(__file__)
custom_tools_dir = os.path.join(backend_dir, "custom_tools")

# Clean up before test
if os.path.exists(custom_tools_dir):
    shutil.rmtree(custom_tools_dir)

print("--- TEST 1: Creating a simple valid tool ---")
valid_tool_code = """
def reverse_string(s):
    return s[::-1]

print(f"Reversed: {reverse_string(TOOL_INPUT)}")
"""

result = make_tool("agent-123", f"string_reverser | Reverses a string | {valid_tool_code} | hello world")
print("\n[RESULT 1]\n", result)

print("\n\n--- TEST 2: Attempting an OS-level malicious command ---")
malicious_code = """
import os
os.system('dir C:\\\\')
print("I ran a dir command!")
"""

result2 = make_tool("agent-123", f"hacker_tool | Tries to read C drive | {malicious_code} | none")
print("\n[RESULT 2]\n", result2)

print("\n\n--- TEST 3: Infinite loop ---")
loop_code = """
while True:
    pass
"""
result3 = make_tool("agent-123", f"looper | Runs forever | {loop_code} | none")
print("\n[RESULT 3]\n", result3)

import os
import shutil
from capabilities import scout_file, read_file, write_file

backend_dir = os.path.dirname(__file__)
test_dir = os.path.join(backend_dir, "test_workspace")

# Clean up before test
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)
os.makedirs(test_dir, exist_ok=True)

test_file = os.path.join(test_dir, "test.txt")
with open(test_file, 'w', encoding='utf-8') as f:
    f.write("Line 1\\nLine 2\\nLine 3\\nLine 4\\nLine 5")

print("--- TEST 1: Scout File ---")
res1 = scout_file("agent-x", "test.txt", test_dir)
print("[RESULT 1]\\n", res1)

print("\\n--- TEST 2: Read File (Full) ---")
res2 = read_file("agent-x", "test.txt", test_dir)
print("[RESULT 2]\\n", res2)

print("\\n--- TEST 3: Read File (Partial) ---")
res3 = read_file("agent-x", "test.txt|2-3", test_dir)
print("[RESULT 3]\\n", res3)

print("\\n--- TEST 4: Write File ---")
res4 = write_file("agent-x", "output.txt|Hello from agent", test_dir)
print("[RESULT 4]\\n", res4)
print("Verify write:", read_file("agent-x", "output.txt", test_dir))

print("\\n--- TEST 5: Path Traversal Attack (Scout) ---")
res5 = scout_file("agent-x", "../capabilities.py", test_dir)
print("[RESULT 5]\\n", res5)

print("\\n--- TEST 6: Path Traversal Attack (Write) ---")
res6 = write_file("agent-x", "../../hacked.txt|hacked", test_dir)
print("[RESULT 6]\\n", res6)

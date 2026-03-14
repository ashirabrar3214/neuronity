import os

def verify_file(filename):
    if os.path.exists(filename):
        print(f"File '{filename}' exists.")
    else:
        print(f"File '{filename}' does not exist.")

verify_file(TOOL_INPUT)
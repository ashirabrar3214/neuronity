import os

def find_file(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)
    return None

file_path = find_file("graph.png", ".")

if file_path:
    print(f"The graph.png file is located at: {file_path}")
else:
    print("The graph.png file was not found in the file system.")
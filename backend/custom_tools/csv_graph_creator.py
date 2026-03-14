import csv

def create_graph(filename):
    try:
        x_values = []
        y_values = []
        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    x_values.append(float(row['Temperature']))
                    y_values.append(float(row['Humidity']))
                except ValueError:
                    print(f"Skipping row due to invalid data: {row}")
                    continue
        
        if not x_values or not y_values:
            print("No valid data found for Temperature or Humidity.")
            return

        # Simple text-based graph representation
        max_x = max(x_values)
        max_y = max(y_values)
        
        graph_lines = []
        for y in range(int(max_y) + 1):
            line = ''
            for x in range(int(max_x) + 1):
                if x in x_values and y in y_values:
                    line += '#'  # Mark data points with #
                else:
                    line += ' '  # Use space for empty points
            graph_lines.append(line)

        graph_lines.reverse()  # Flip the graph to have the origin at the bottom-left

        with open('graph.txt', 'w') as outfile:
            for line in graph_lines:
                outfile.write(line + '\n')

        print("Graph generated and saved as graph.txt")

    except FileNotFoundError:
        print("Error: File not found. Please provide a valid file path.")
    except Exception as e:
        print(f"An error occurred: {e}")

create_graph(TOOL_INPUT)
import csv

def create_graph_10(filename):
    try:
        x_values = []
        y_values = []
        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            for i, row in enumerate(reader):
                if i >= 10:
                    break
                try:
                    x = float(row['Temperature'])
                    y = float(row['Humidity'])
                    x_values.append(x)
                    y_values.append(y)
                except ValueError:
                    print(f"Skipping row {i+1} due to invalid data.")
                    continue

        # Simple text-based graph
        if not x_values or not y_values:
            print("No valid data to plot.")
            return

        x_min = min(x_values)
        x_max = max(x_values)
        y_min = min(y_values)
        y_max = max(y_values)

        x_range = max(1e-9, x_max - x_min)  # Avoid division by zero
        y_range = max(1e-9, y_max - y_min)  # Avoid division by zero

        width = 50
        height = 20

        graph = [[' ' for _ in range(width)] for _ in range(height)]

        for i in range(len(x_values)):
            x_norm = (x_values[i] - x_min) / x_range
            y_norm = (y_values[i] - y_min) / y_range

            x_pixel = int(x_norm * (width - 1))
            y_pixel = int((1 - y_norm) * (height - 1))  # Invert y-axis

            if 0 <= x_pixel < width and 0 <= y_pixel < height:
                graph[y_pixel][x_pixel] = '*'

        # Print the graph
        with open("graph.txt", "w") as f:
            for row in graph:
                f.write(''.join(row) + '\n')

        print("Graph generated and saved as graph.txt")

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except KeyError:
        print("Error: 'Temperature' or 'Humidity' column not found in the CSV file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
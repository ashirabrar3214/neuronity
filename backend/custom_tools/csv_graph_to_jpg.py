import csv
import os

def create_graph_jpg(filename):
    try:
        temperature = []
        humidity = []
        with open(filename, 'r') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for i, row in enumerate(csv_reader):
                if i >= 10:
                    break
                temperature.append(float(row['Temperature']))
                humidity.append(float(row['Humidity']))

        # Create a dummy graph using text
        width = 60
        height = 20
        graph = [[' ' for _ in range(width)] for _ in range(height)]

        # Normalize the data to fit within the graph dimensions
        max_temp = max(temperature)
        min_temp = min(temperature)
        max_hum = max(humidity)
        min_hum = min(humidity)

        for i in range(len(temperature)):
            x = int((i / 9) * (width - 1))  # Scale x to the width of the graph
            y_temp = int(((temperature[i] - min_temp) / (max_temp - min_temp)) * (height - 1))
            y_hum = int(((humidity[i] - min_hum) / (max_hum - min_hum)) * (height - 1))

            graph[height - 1 - y_temp][x] = 'T'
            graph[height - 1 - y_hum][x] = 'H'

        # Save the text-based graph to a file named graph.jpg
        with open('graph.jpg', 'w') as f:
            for row in graph:
                f.write(''.join(row) + os.linesep)

        print("Text-based graph generated and saved as graph.jpg")

    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except KeyError:
        print("Error: 'Temperature' or 'Humidity' column not found in the CSV file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
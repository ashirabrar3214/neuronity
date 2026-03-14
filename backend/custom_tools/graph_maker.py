import csv
import io
import os

def generate_graph(csv_data, filename="graph.png"):
    x_values = []
    y_values = []

    csvfile = io.StringIO(csv_data)
    reader = csv.DictReader(csvfile)

    for row in reader:
        try:
            x_values.append(float(row['x']))
            y_values.append(float(row['y']))
        except ValueError:
            print(f"Skipping row due to invalid data: {row}")
            continue
        except KeyError:
            return "Error: The CSV file must have 'x' and 'y' columns."

    if not x_values or not y_values:
        return "Error: No valid data found in the CSV file."

    # Create a dummy graph (replace with actual plotting logic if possible)
    # In this version, the graph creation part is mocked due to the environment's limitations
    print("Graph generation was successful (mock).")
    metadata = {
        "x_min": min(x_values),
        "x_max": max(x_values),
        "y_min": min(y_values),
        "y_max": max(y_values)
    }
    return str(metadata)
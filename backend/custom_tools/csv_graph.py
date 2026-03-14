import csv
import io

def generate_graph(csv_data):
    x_values = []
    y_values = []
    
    csvfile = io.StringIO(csv_data)
    reader = csv.DictReader(csvfile)
    
    for row in reader:
        try:
            x_values.append(float(row['Temperature']))
            y_values.append(float(row['Humidity']))
        except ValueError:
            print("Error: Could not convert a value to float. Skipping row.")
            continue
        except KeyError as e:
            print(f"Error: Key {e} not found in CSV. Check column names.")
            return None
            
    
    if not x_values or not y_values:
        print("Error: No data found for Temperature or Humidity.")
        return None

    graph_str = ""
    for i in range(len(x_values)):
        graph_str += f"({x_values[i]:.2f}, {y_values[i]:.2f})\n"

    return graph_str


csv_data = TOOL_INPUT
graph_output = generate_graph(csv_data)

if graph_output:
    print(graph_output)
else:
    print("Graph generation failed.")
import csv

# matplotlib is not available in the sandbox
# Using a workaround to create a simple text-based graph
def graph_generator(csv_file_path):
    x_data = []
    y_data = []

    try:
        with open(csv_file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                x_val = row.get('x')
                y_val = row.get('y')

                if x_val is not None and y_val is not None:
                    try:
                        x_data.append(float(x_val))
                        y_data.append(float(y_val))
                    except ValueError:
                        return "Error: Could not convert x values to float. Check data types."

                    try:
                        y_data.append(float(y_val))
                    except ValueError:
                        return "Error: Could not convert y values to float. Check data types."
                else:
                    return "Error: 'x' or 'y' column not found in the CSV file."

        if not x_data or not y_data:
            return "Error: No data found in 'x' or 'y' columns."

        # Create a simple text-based graph
        graph_str = "Text-based Graph:\
"
        for i in range(len(x_data)):
            graph_str += f"({x_data[i]}, {y_data[i]})\
"

        # Save the graph string to a file
        with open('graph.txt', 'w') as f:
            f.write(graph_str)

        return "Text-based graph successfully generated and saved as graph.txt"

    except FileNotFoundError:
        return "Error: File not found. Please provide a valid file path."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

if __name__ == "__main__":
    TOOL_INPUT = "data.csv"
    result = graph_generator(TOOL_INPUT)
    print(result)
import csv

def calculate_stats(filename):
    temperatures = []
    humidities = []

    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                temperatures.append(float(row['Temperature']))
                humidities.append(float(row['Humidity']))
            except ValueError:
                print(f"Skipping row due to invalid data: {row}")
                continue
            except KeyError as e:
                raise KeyError(f"Missing column: {e}")

    if not temperatures or not humidities:
        return "Error: No valid temperature or humidity data found."

    avg_temp = sum(temperatures) / len(temperatures)
    avg_humidity = sum(humidities) / len(humidities)

    max_temp = max(temperatures)
    min_temp = min(temperatures)

    max_humidity = max(humidities)
    min_humidity = min(humidities)

    result_string = "Temperature: Avg=" + str(round(avg_temp, 2)) + ", Max=" + str(round(max_temp, 2)) + ", Min=" + str(round(min_temp, 2)) + "\n" + "Humidity: Avg=" + str(round(avg_humidity, 2)) + ", Max=" + str(round(max_humidity, 2)) + ", Min=" + str(round(min_humidity, 2))
    return result_string

try:
    result = calculate_stats(TOOL_INPUT)
    print(result)
except FileNotFoundError:
    print("Error: File not found.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
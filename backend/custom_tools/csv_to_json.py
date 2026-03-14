import csv, json

def csv_to_json(csv_file_path):
    json_array = []
    with open(csv_file_path, encoding="utf-8") as csvf:
        csv_reader = csv.DictReader(csvf)
        for row in csv_reader:
            json_array.append(row)

    return json_array

csv_file = TOOL_INPUT

json_data = csv_to_json(csv_file)

print(json.dumps(json_data, indent=4))
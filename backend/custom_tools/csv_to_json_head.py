import csv, json

def csv_to_json_head(csv_file_path):
    json_list = []
    with open(csv_file_path, 'r') as file:
        csv_reader = csv.DictReader(file)
        for i, row in enumerate(csv_reader):
            if i >= 10:
                break
            json_list.append(row)
    return json.dumps(json_list, indent=4)

print(csv_to_json_head(TOOL_INPUT))
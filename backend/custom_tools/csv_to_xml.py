import csv
import xml.etree.ElementTree as ET

def csv_to_xml(csv_string):
    reader = csv.DictReader(csv_string.splitlines())
    root = ET.Element("root")
    for row in reader:
        record = ET.SubElement(root, "record")
        for key, value in row.items():
            if key:
                element = ET.SubElement(record, key)
                element.text = value
    return ET.tostring(root, encoding="utf8", method="xml").decode()

print(csv_to_xml(TOOL_INPUT))
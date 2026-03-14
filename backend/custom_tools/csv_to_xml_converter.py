import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom
import io

def create_xml_from_csv(csv_string):
    csv_file = io.StringIO(csv_string)
    csv_data = csv.reader(csv_file)
    header = next(csv_data)
    root = ET.Element("root")
    for row in csv_data:
        record = ET.SubElement(root, "record")
        for i, value in enumerate(row):
            field = ET.SubElement(record, header[i].strip())
            field.text = value.strip()
    xml_string = ET.tostring(root, encoding='utf8', method='xml').decode()
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ")
    return pretty_xml

print(create_xml_from_csv(TOOL_INPUT))
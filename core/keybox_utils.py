import xml.etree.ElementTree as ET
import os
from core.app_paths import get_data_root

def get_keybox_serial(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        
        # Depending on structure, it could be <Keybox DeviceID="..."> directly inside root
        keybox = root.find(".//Keybox")
        if keybox is not None and "DeviceID" in keybox.attrib:
            return keybox.attrib["DeviceID"]
            
        # fallback if it's top-level
        if root.tag == "Keybox" and "DeviceID" in root.attrib:
            return root.attrib["DeviceID"]
            
    except Exception as e:
        print(f"Error parsing Keybox: {e}")
        return None
    return None

def _resolve_keybox_dir(directory):
    if directory:
        return directory
    return os.path.join(get_data_root(), "keyboxes")


def find_keybox_in_folder(barcode_serial, directory=None):
    """Auto-detects a keybox file matching the given barcode_serial."""
    directory = _resolve_keybox_dir(directory)
    if not os.path.exists(directory):
        return None
        
    for file in os.listdir(directory):
        if file.endswith(".xml") and file != "standard.xml":
            filepath = os.path.join(directory, file)
            extracted_serial = get_keybox_serial(filepath)
            if extracted_serial == barcode_serial:
                return filepath
    return None

def generate_keybox_from_standard(barcode_serial, directory=None):
    """Generates a <serialno>.xml file from standard.xml by replacing PlaceHolder."""
    directory = _resolve_keybox_dir(directory)
    standard_path = os.path.join(directory, "standard.xml")
    if not os.path.exists(standard_path):
        return None
        
    try:
        with open(standard_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Replace PlaceHolder with the actual serial number
        new_content = content.replace("PlaceHolder", barcode_serial)
        
        new_path = os.path.join(directory, f"{barcode_serial}.xml")
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return new_path
    except Exception as e:
        print(f"Error generating from standard.xml: {e}")
        return None

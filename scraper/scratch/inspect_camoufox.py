import inspect
import os
import camoufox

camoufox_dir = os.path.dirname(camoufox.__file__)
fingerprints_path = os.path.join(camoufox_dir, "fingerprints.py")

print("Checking fingerprints.py content:")
with open(fingerprints_path, "r", encoding="utf-8") as f:
    lines = f.readlines()
    # Print lines that look like configurations or constructor options
    for i, line in enumerate(lines):
        if "def " in line or "class " in line or "self." in line or "config" in line or "options" in line:
            if i < 150: # check first 150 lines
                print(f"{i+1}: {line.strip()}")

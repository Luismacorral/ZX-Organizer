import os
import re
import shutil
from scanner import DirectoryScanner

# Mock config
config = {'TS_PATH': 'test_ts', 'FE_PATH': 'test_fe'}
scanner = DirectoryScanner(config)

# Setup test directories
base_path_f = "test_ts/TOSEC_v40.9/02 CLASICOS/ALFABETO CLASICOS/F/TAPs"
base_path_n = "test_ts/TOSEC_v40.9/02 CLASICOS/ALFABETO CLASICOS/N/TAPs"

os.makedirs(base_path_f, exist_ok=True)
os.makedirs(base_path_n, exist_ok=True)

# Create F folders
f_folders = [
    "F-FERNA",
    "FERRO - FLIPI",
    "FLIPP - FP",
    "FRA - FROZE",
    "FRUIT - FY-FY"
]
for f in f_folders:
    os.makedirs(os.path.join(base_path_f, f), exist_ok=True)

# Create N folders
# Assuming some previous folders exist to test the "gap" logic
n_folders = [
    "NA - NE",
    "NIGHTFL - NY"
]
for f in n_folders:
    os.makedirs(os.path.join(base_path_n, f), exist_ok=True)

print("--- Testing F ---")
title_f = "Fruity March"
result_f = scanner._find_range_folder(base_path_f, title_f)
print(f"Title: {title_f}")
print(f"Expected: FRUIT - FY-FY")
print(f"Result:   {result_f}")

print("\n--- Testing N ---")
title_n = "Nightfall"
result_n = scanner._find_range_folder(base_path_n, title_n)
print(f"Title: {title_n}")
print(f"Expected: NIGHTFL - NY (according to user)")
print(f"Result:   {result_n}")

print("\n--- Testing FROZEN ---")
title_frozen = "Frozen"
result_frozen = scanner._find_range_folder(base_path_f, title_frozen)
print(f"Title: {title_frozen}")
print(f"Expected: FRA - FROZE (closest match)")
print(f"Result:   {result_frozen}")

# Clean up
# shutil.rmtree("test_ts")

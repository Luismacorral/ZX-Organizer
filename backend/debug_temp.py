import os
import sys
from scanner import DirectoryScanner

CONFIG = {
    'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
    'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
    'TEMP_PATH': r'c:\ZX\TEMP',
    'TS_TOSEC_SUBPATH': 'TOSEC_v40.9',
    'BACKUP_PATH': r'C:\ZX\Backups'
}

def debug_temp():
    print(f"Checking TEMP_PATH: {CONFIG['TEMP_PATH']}")
    if not os.path.exists(CONFIG['TEMP_PATH']):
        print("TEMP_PATH does not exist!")
        return

    files = os.listdir(CONFIG['TEMP_PATH'])
    print(f"Files in TEMP (os.listdir): {files}")

    scanner = DirectoryScanner(CONFIG)
    result = scanner.scan_temp_files(CONFIG['TEMP_PATH'])
    print(f"Scanner result files count: {len(result.get('files', []))}")
    for f in result.get('files', []):
        print(f" - {f['name']} ({f['status']})")

    # Test Multicopy suggestion for a sample file
    if files:
        sample_file = files[0]
        print(f"\nTesting suggestions for: {sample_file}")
        # Mock TOSEC info parsing
        tosec_info = scanner._parse_tosec_filename(sample_file)
        ext = os.path.splitext(sample_file)[1].lower()
        suggestions = scanner._suggest_destination(tosec_info, ext, sample_file)
        print("Suggestions TS:")
        for s in suggestions['TS']:
            print(f" - {s}")

if __name__ == "__main__":
    debug_temp()

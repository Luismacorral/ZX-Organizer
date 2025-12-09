import os
import sys

# Mock config
CONFIG = {
    'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
    'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
    'TEMP_PATH': r'c:\ZX\TEMP',
    'TS_TOSEC_SUBPATH': 'TOSEC_v40.9',
    'BACKUP_PATH': r'C:\ZX\Backups'
}

def check_access(full_path):
    ROOT_PATHS = [
        CONFIG['FE_PATH'],
        os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH']),
        CONFIG['TEMP_PATH']
    ]
    
    print(f"Checking path: {full_path}")
    print(f"Allowed roots: {ROOT_PATHS}")
    
    is_allowed = any(full_path.startswith(root) for root in ROOT_PATHS)
    print(f"Is allowed: {is_allowed}")
    return is_allowed

# Test cases
check_access(r'c:\ZX\ZX_v40.9_TS')
check_access(r'c:\ZX\ZX_v40.9_TS\TOSEC_v40.9')

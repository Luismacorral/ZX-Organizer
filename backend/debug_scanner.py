
import sys
import os
sys.path.append('c:\\ZX\\zx-organizer\\backend')

try:
    from scanner import DirectoryScanner
    print("Import successful")
    
    config = {
        'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
        'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
        'TEMP_PATH': r'c:\ZX\TEMP'
    }
    
    scanner = DirectoryScanner(config)
    print("Scanner initialized")
    
    print("Calling get_multicopy_roots...")
    roots = scanner.get_multicopy_roots()
    print("Roots:", roots)
    
except Exception as e:
    import traceback
    traceback.print_exc()

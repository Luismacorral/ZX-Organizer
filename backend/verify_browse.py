
import requests
import json

API_BASE = 'http://localhost:5000/api'

def test_browse():
    print("Testing /api/multicopy/browse...")
    
    # 1. Test Root
    try:
        r = requests.get(f"{API_BASE}/multicopy/browse")
        if r.status_code == 200:
            print("ROOT: OK")
            print(json.dumps(r.json(), indent=2))
        else:
            print(f"ROOT: FAILED {r.status_code}")
    except Exception as e:
        print(f"ROOT: EXCEPTION {e}")

    # 2. Test FE Root (should use fast_scan)
    # We need to find the FE path from root first
    try:
        r = requests.get(f"{API_BASE}/multicopy/browse")
        items = r.json().get('items', [])
        fe_item = next((i for i in items if 'FE' in i['name']), None)
        
        if fe_item:
            fe_path = fe_item['full_path']
            print(f"Browsing FE: {fe_path}")
            r = requests.get(f"{API_BASE}/multicopy/browse/{fe_path}")
            if r.status_code == 200:
                data = r.json()
                print(f"FE Browse: OK. Items: {len(data.get('items', []))}")
                # Check if file_count is 0 (fast_scan) or present
                # Actually, fast_scan sets total_files=0 for folders in the list
                first_folder = next((i for i in data.get('items', []) if i['type'] == 'folder'), None)
                if first_folder:
                    print(f"First folder stats: {first_folder}")
            else:
                print(f"FE Browse: FAILED {r.status_code}")
        else:
            print("FE Root not found")
            
    except Exception as e:
        print(f"FE Browse: EXCEPTION {e}")

    # 3. Test TS Root Access (Fix Verification)
    print("\nTesting TS Root Access...")
    try:
        # We know the TS path from config/scanner defaults
        ts_path = r'c:\ZX\ZX_v40.9_TS'
        r = requests.get(f"{API_BASE}/multicopy/browse/{ts_path}")
        if r.status_code == 200:
            print(f"TS Root ({ts_path}): OK")
            data = r.json()
            print(f"Items: {len(data.get('items', []))}")
        else:
            print(f"TS Root ({ts_path}): FAILED {r.status_code}")
            print(r.text)
    except Exception as e:
        print(f"TS Root: EXCEPTION {e}")

if __name__ == "__main__":
    test_browse()

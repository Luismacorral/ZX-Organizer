
import requests
import os
import json

API_BASE = 'http://localhost:5000/api'
TEMP_PATH = r'c:\ZX\TEMP'
FE_PATH = r'c:\ZX\ZX_v40.9_FE'
TS_PATH = r'c:\ZX\ZX_v40.9_TS'

def test_multicopy():
    print("Testing /api/multicopy/execute...")
    
    # 1. Create dummy files in TEMP
    test_file_1 = os.path.join(TEMP_PATH, 'test_copy_1.txt')
    test_file_2 = os.path.join(TEMP_PATH, 'test_copy_2.txt')
    
    with open(test_file_1, 'w') as f: f.write("Content 1")
    with open(test_file_2, 'w') as f: f.write("Content 2")
    
    # 2. Define payload
    payload = {
        'files': ['test_copy_1.txt', 'test_copy_2.txt'], # Relative to TEMP
        'dest_collection': 'FE',
        'dest_path': 'Test_Multicopy_Folder'
    }
    
    # 3. Call endpoint
    try:
        response = requests.post(f"{API_BASE}/multicopy/execute", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("SUCCESS: Endpoint returned success.")
                
                # Verify files exist in destination
                dest_dir = os.path.join(FE_PATH, 'Test_Multicopy_Folder')
                if os.path.exists(os.path.join(dest_dir, 'test_copy_1.txt')) and \
                   os.path.exists(os.path.join(dest_dir, 'test_copy_2.txt')):
                    print("VERIFIED: Files found in destination.")
                else:
                    print("FAILED: Files not found in destination.")
            else:
                print("FAILED: Endpoint returned success=False")
        else:
            print("FAILED: Non-200 status code")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

    # Cleanup
    try:
        os.remove(test_file_1)
        os.remove(test_file_2)
        # Optional: remove created dest folder if you want to be clean, 
        # but maybe keep it for manual inspection if needed.
        # shutil.rmtree(os.path.join(FE_PATH, 'Test_Multicopy_Folder'))
    except:
        pass

if __name__ == "__main__":
    test_multicopy()

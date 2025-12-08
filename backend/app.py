from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS
import os
import csv
import subprocess
import platform
import base64
import shutil
import time
import threading
from scanner import DirectoryScanner

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

CONFIG = {
    'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
    'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
    'TEMP_PATH': r'c:\ZX\TEMP',
    'TS_TOSEC_SUBPATH': 'TOSEC_v40.9',
    'BACKUP_PATH': r'C:\ZX\Backups'
}

cache = {'FE': None, 'TS': None, 'TEMP': None, 'stats': None}
scanner = DirectoryScanner(CONFIG)

# Estado global para compresión
compress_status = {'running': False, 'progress': '', 'percent': 0, 'done': False, 'error': None}

def get_collection_base_path(collection):
    if collection == 'FE':
        return CONFIG['FE_PATH']
    elif collection == 'TS':
        return os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH'])
    return None

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/config')
def get_config():
    ts_full_path = os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH'])
    return jsonify({
        'collections': {
            'FE': {'name': 'Full Edition', 'path': CONFIG['FE_PATH'], 'exists': os.path.exists(CONFIG['FE_PATH'])},
            'TS': {'name': 'The Spectrum', 'path': ts_full_path, 'exists': os.path.exists(ts_full_path)}
        },
        'temp_path': CONFIG['TEMP_PATH'],
        'temp_exists': os.path.exists(CONFIG['TEMP_PATH'])
    })

@app.route('/api/scan/<collection>')
def scan_collection(collection):
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    path = get_collection_base_path(collection)
    if not os.path.exists(path):
        return jsonify({'error': f'La ruta {path} no existe'}), 404
    try:
        structure = scanner.scan_root_folders(path, max_depth=3)
        cache[collection] = structure
        return jsonify(structure)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse/<collection>/<path:subpath>')
def browse_path(collection, subpath):
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    base_path = get_collection_base_path(collection)
    full_path = os.path.join(base_path, subpath)
    if not os.path.exists(full_path):
        return jsonify({'error': f'Ruta no encontrada: {subpath}'}), 404
    try:
        items = scanner.get_folder_contents(full_path, collection=collection)
        return jsonify(items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/temp/scan')
def scan_temp():
    if not os.path.exists(CONFIG['TEMP_PATH']):
        return jsonify({'error': 'La carpeta TEMP no existe'}), 404
    try:
        files = scanner.scan_temp_files(CONFIG['TEMP_PATH'])
        cache['TEMP'] = files
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/temp/delete', methods=['POST'])
def delete_temp_file():
    data = request.get_json()
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'No se proporcionó nombre de archivo'}), 400
    try:
        result = scanner.delete_temp_file(filename)
        if result['success']:
            cache['TEMP'] = None
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/open-file', methods=['POST'])
def open_file():
    data = request.get_json()
    file_path = data.get('path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Archivo no encontrado'}), 404
    try:
        if platform.system() == 'Windows':
            os.startfile(file_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/serve-file')
def serve_file():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Path no especificado'}), 400
    
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(file_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed or not os.path.exists(file_path):
        return jsonify({'error': 'Acceso denegado'}), 404
    
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=False)

@app.route('/api/copy-between', methods=['POST'])
def copy_between_collections():
    data = request.get_json()
    source_path = data.get('source_path')
    dest_collection = data.get('dest_collection')
    dest_folder = data.get('dest_folder')
    
    if not source_path or not dest_collection or not os.path.exists(source_path):
        return jsonify({'error': 'Parámetros inválidos'}), 400
    
    try:
        filename = os.path.basename(source_path)
        dest_base = get_collection_base_path(dest_collection)
        dest_full = os.path.join(dest_base, dest_folder, filename) if dest_folder else os.path.join(dest_base, filename)
        
        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        shutil.copy2(source_path, dest_full)
        
        cache['FE'] = None
        cache['TS'] = None
        
        return jsonify({'success': True, 'message': f'Copiado: {filename}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/clear')
def clear_cache():
    global cache
    cache = {'FE': None, 'TS': None, 'TEMP': None, 'stats': None}
    return jsonify({'message': 'Caché limpiada'})

@app.route('/api/process-file', methods=['POST'])
def process_file():
    data = request.get_json()
    filename = data.get('filename')
    destinations = data.get('destinations', {})
    if not filename:
        return jsonify({'error': 'No se proporcionó nombre'}), 400
    try:
        result = scanner.process_temp_file(filename, destinations)
        cache['FE'] = None
        cache['TS'] = None
        cache['TEMP'] = None
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse-folders/<collection>')
def browse_folders_for_rules(collection):
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    base_path = get_collection_base_path(collection)
    try:
        folders = []
        for item in sorted(os.listdir(base_path)):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                folders.append({'name': item, 'path': item, 'has_subfolders': scanner._has_subfolders(item_path)})
        return jsonify({'folders': folders, 'base': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse-folders/<collection>/<path:subpath>')
def browse_subfolders_for_rules(collection, subpath):
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    base_path = get_collection_base_path(collection)
    full_path = os.path.join(base_path, subpath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'Ruta no encontrada'}), 404
    try:
        folders = []
        for item in sorted(os.listdir(full_path)):
            item_path = os.path.join(full_path, item)
            if os.path.isdir(item_path):
                folders.append({'name': item, 'path': os.path.join(subpath, item), 'has_subfolders': scanner._has_subfolders(item_path)})
        return jsonify({'folders': folders, 'base': subpath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== COMPRESIÓN CON PROGRESO ==============

@app.route('/api/compress/start', methods=['POST'])
def compress_start():
    global compress_status
    
    if compress_status['running']:
        return jsonify({'error': 'Ya hay una compresión en curso'}), 400
    
    data = request.get_json()
    collection = data.get('collection')
    dest_path = data.get('dest_path')
    volume_size_mb = data.get('volume_size_mb', 4700)
    compress_format = data.get('format', 'zip')
    
    if not collection or not dest_path:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    source_path = get_collection_base_path(collection)
    if not os.path.exists(source_path):
        return jsonify({'error': f'Colección {collection} no encontrada'}), 404
    
    compress_status = {'running': True, 'progress': 'Iniciando...', 'percent': 0, 'done': False, 'error': None}
    
    def run_compression():
        global compress_status
        try:
            os.makedirs(dest_path, exist_ok=True)
            
            compress_status['progress'] = 'Calculando tamaño...'
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(source_path):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))
                    file_count += 1
            
            compress_status['progress'] = f'Total: {file_count} archivos ({total_size/1024/1024/1024:.2f} GB)'
            time.sleep(1)
            
            archive_name = f"TOSEC_{collection}"
            
            seven_zip_path = r"c:\Program Files\7-Zip\7z.exe"
            if not os.path.exists(seven_zip_path):
                seven_zip_path = r"c:\Program Files (x86)\7-Zip\7z.exe"
            
            if not os.path.exists(seven_zip_path):
                compress_status['error'] = '7-Zip no encontrado'
                compress_status['running'] = False
                return
            
            if compress_format == '7z':
                cmd = [seven_zip_path, 'a', '-t7z', f'-v{volume_size_mb}m', '-bsp1', f'{os.path.join(dest_path, archive_name)}.7z', f'{source_path}\\*']
            else:
                cmd = [seven_zip_path, 'a', '-tzip', f'-v{volume_size_mb}m', '-bsp1', f'{os.path.join(dest_path, archive_name)}.zip', f'{source_path}\\*']
            
            compress_status['progress'] = 'Comprimiendo...'
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            for line in process.stdout:
                line = line.strip()
                if '%' in line:
                    try:
                        parts = line.split('%')
                        if parts:
                            pct = int(parts[0].strip().split()[-1])
                            compress_status['percent'] = pct
                            compress_status['progress'] = f'Comprimiendo... {pct}%'
                    except:
                        pass
            
            process.wait()
            
            if process.returncode == 0:
                volumes = len([f for f in os.listdir(dest_path) if f.startswith(archive_name)])
                compress_status['progress'] = f'¡Completado! {volumes} volúmenes creados'
                compress_status['percent'] = 100
                compress_status['done'] = True
            else:
                compress_status['error'] = 'Error en compresión'
                
        except Exception as e:
            compress_status['error'] = str(e)
        finally:
            compress_status['running'] = False
    
    thread = threading.Thread(target=run_compression)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Compresión iniciada'})

@app.route('/api/compress/status')
def compress_get_status():
    return jsonify(compress_status)

# ============== MULTICOPIA ==============

@app.route('/api/multicopy', methods=['POST'])
def multicopy_files():
    data = request.get_json()
    files = data.get('files', [])
    destinations = data.get('destinations', [])
    
    if not files or not destinations:
        return jsonify({'error': 'Faltan archivos o destinos'}), 400
    
    results = []
    success_count = 0
    
    try:
        for file_path in files:
            if not os.path.isabs(file_path):
                file_path = os.path.join(CONFIG['TEMP_PATH'], file_path)
            
            if not os.path.exists(file_path):
                results.append({'file': os.path.basename(file_path), 'status': 'error', 'message': 'No encontrado'})
                continue
            
            filename = os.path.basename(file_path)
            
            for dest in destinations:
                try:
                    if ':' in dest:
                        coll, subpath = dest.split(':', 1)
                    else:
                        coll = 'FE'
                        subpath = dest
                    
                    base_path = get_collection_base_path(coll)
                    if not base_path:
                        continue
                    
                    full_dest_path = os.path.join(base_path, subpath)
                    os.makedirs(full_dest_path, exist_ok=True)
                    
                    shutil.copy2(file_path, os.path.join(full_dest_path, filename))
                    results.append({'file': filename, 'dest': dest, 'status': 'ok'})
                    success_count += 1
                except Exception as e:
                    results.append({'file': filename, 'dest': dest, 'status': 'error', 'message': str(e)})
        
        cache['FE'] = None
        cache['TS'] = None
        
        return jsonify({
            'success': True,
            'processed': len(files),
            'copied': success_count,
            'details': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== GESTIÓN DE ARCHIVOS/CARPETAS ==============

@app.route('/api/folder/create', methods=['POST'])
def create_folder():
    data = request.get_json()
    collection = data.get('collection')
    path = data.get('path', '')
    name = data.get('name')
    
    if not collection or not name:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    base_path = get_collection_base_path(collection)
    if not base_path:
        return jsonify({'error': 'Colección inválida'}), 400
    
    full_path = os.path.join(base_path, path, name) if path else os.path.join(base_path, name)
    
    try:
        if os.path.exists(full_path):
            return jsonify({'error': 'La carpeta ya existe'}), 400
        os.makedirs(full_path)
        cache[collection] = None
        return jsonify({'success': True, 'message': f'Carpeta creada: {name}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folder/delete', methods=['POST'])
def delete_folder():
    data = request.get_json()
    collection = data.get('collection')
    path = data.get('path')
    force = data.get('force', False)
    
    if not collection or not path:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    base_path = get_collection_base_path(collection)
    if not base_path:
        return jsonify({'error': 'Colección inválida'}), 400
    
    full_path = os.path.join(base_path, path)
    
    if not os.path.exists(full_path):
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    
    try:
        if force:
            shutil.rmtree(full_path)
        else:
            os.rmdir(full_path)
        cache[collection] = None
        return jsonify({'success': True, 'message': 'Carpeta eliminada'})
    except OSError as e:
        if 'not empty' in str(e).lower():
            return jsonify({'error': 'La carpeta no está vacía'}), 400
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/delete', methods=['POST'])
def delete_files():
    data = request.get_json()
    files = data.get('files', [])
    
    if not files:
        return jsonify({'error': 'No se especificaron archivos'}), 400
    
    results = []
    success_count = 0
    
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    
    for file_path in files:
        is_allowed = any(file_path.startswith(root) for root in allowed_roots)
        
        if not is_allowed:
            results.append({'file': file_path, 'status': 'error', 'message': 'Ruta no permitida'})
            continue
        
        if not os.path.exists(file_path):
            results.append({'file': file_path, 'status': 'error', 'message': 'No encontrado'})
            continue
        
        try:
            os.remove(file_path)
            results.append({'file': os.path.basename(file_path), 'status': 'ok'})
            success_count += 1
        except Exception as e:
            results.append({'file': os.path.basename(file_path), 'status': 'error', 'message': str(e)})
    
    cache['FE'] = None
    cache['TS'] = None
    cache['TEMP'] = None
    
    return jsonify({
        'success': success_count > 0,
        'deleted': success_count,
        'total': len(files),
        'details': results
    })

# ============== BACKUP NAS ==============

@app.route('/api/backup/list-files')
def list_backup_files():
    backup_path = CONFIG['BACKUP_PATH']
    if not os.path.exists(backup_path):
        os.makedirs(backup_path, exist_ok=True)
        return jsonify({'files': [], 'path': backup_path})
    
    try:
        files = []
        for f in os.listdir(backup_path):
            fp = os.path.join(backup_path, f)
            if os.path.isfile(fp):
                files.append({'name': f, 'size': os.path.getsize(fp), 'modified': os.path.getmtime(fp)})
        files.sort(key=lambda x: x['name'])
        return jsonify({'files': files, 'path': backup_path})
    except Exception as e:
        return jsonify({'error': str(e), 'files': []})

@app.route('/api/backup/ftp-test', methods=['POST'])
def ftp_test_connection():
    import ftplib
    data = request.get_json()
    password = data.get('password')
    
    if not password:
        return jsonify({'success': False, 'error': 'Se requiere contraseña'}), 400
    
    try:
        ftp = ftplib.FTP_TLS()
        ftp.connect('revisteo.synology.me', 21, timeout=10)
        ftp.auth()
        ftp.prot_p()
        ftp.login('Flunky', password)
        
        try:
            ftp.cwd('/ZxTosec')
            folder_exists = True
            remote_files = ftp.nlst()
        except:
            folder_exists = False
            remote_files = []
        
        ftp.quit()
        return jsonify({'success': True, 'folder_exists': folder_exists, 'remote_files': remote_files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/backup/ftp-upload-single', methods=['POST'])
def ftp_upload_single():
    import ftplib
    data = request.get_json()
    password = data.get('password')
    filename = data.get('filename')
    
    if not password or not filename:
        return jsonify({'success': False, 'error': 'Faltan parámetros'}), 400
    
    local_file = os.path.join(CONFIG['BACKUP_PATH'], filename)
    if not os.path.exists(local_file):
        return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
    
    file_size = os.path.getsize(local_file)
    
    try:
        ftp = ftplib.FTP_TLS()
        ftp.connect('revisteo.synology.me', 21, timeout=30)
        ftp.auth()
        ftp.prot_p()
        ftp.login('Flunky', password)
        
        try:
            ftp.cwd('/ZxTosec')
        except:
            ftp.mkd('/ZxTosec')
            ftp.cwd('/ZxTosec')
        
        start_time = time.time()
        with open(local_file, 'rb') as f:
            ftp.storbinary(f'STOR {filename}', f)
        elapsed = time.time() - start_time
        
        remote_size = ftp.size(filename)
        ftp.quit()
        
        speed = (file_size / 1024 / 1024) / elapsed if elapsed > 0 else 0
        
        return jsonify({
            'success': True,
            'filename': filename,
            'size': file_size,
            'remote_size': remote_size,
            'elapsed_seconds': round(elapsed, 1),
            'speed_mbps': round(speed, 2),
            'verified': remote_size == file_size
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============== EMULADOR ==============

@app.route('/api/emulator')
def emulator_page():
    file_path = request.args.get('path')
    
    if not file_path or not os.path.exists(file_path):
        return "Archivo no encontrado", 404
    
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(file_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed:
        return "Acceso denegado", 403
    
    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    file_url = f'/api/serve-file?path={file_path}'
    
    is_tape = ext in ['.tap', '.tzx']
    is_snapshot = ext in ['.z80', '.sna']
    is_disk = ext in ['.trd', '.scl', '.dsk']
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ZX Spectrum - {filename}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #1a1a2e; min-height: 100vh; display: flex; flex-direction: column; font-family: sans-serif; color: #fff; }}
        .header {{ background: rgba(0,0,0,0.5); padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #7b2cbf; }}
        .header h1 {{ font-size: 16px; color: #00d4ff; }}
        .content {{ flex: 1; display: flex; gap: 20px; padding: 20px; }}
        .emulator-panel {{ flex: 2; background: #000; border-radius: 10px; overflow: hidden; border: 2px solid #7b2cbf; }}
        .emulator-panel iframe {{ width: 100%; height: 100%; border: none; }}
        .control-panel {{ width: 280px; display: flex; flex-direction: column; gap: 10px; }}
        .card {{ background: rgba(0,0,0,0.4); border: 1px solid rgba(123,44,191,0.3); border-radius: 8px; padding: 12px; }}
        .card h3 {{ font-size: 13px; color: #7b2cbf; margin-bottom: 8px; }}
        .card p {{ font-size: 11px; color: #aaa; margin: 4px 0; }}
        .btn {{ display: block; padding: 10px; background: #22c55e; color: white; text-decoration: none; border-radius: 5px; font-size: 13px; text-align: center; margin: 5px 0; }}
        .btn:hover {{ background: #16a34a; }}
        .instruction {{ background: rgba(255,215,0,0.1); border: 1px solid rgba(255,215,0,0.3); padding: 10px; border-radius: 5px; font-size: 11px; color: #ffd700; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>▶ {filename}</h1>
        <span style="color:#888;font-size:12px;">Formato: {ext.upper()}</span>
    </div>
    <div class="content">
        <div class="emulator-panel">
            <iframe src="https://nicofirst.github.io/web-zxspectrum/" allow="autoplay; fullscreen; gamepad"></iframe>
        </div>
        <div class="control-panel">
            <div class="card">
                <h3>📂 Archivo</h3>
                <p style="word-break:break-all;font-family:monospace;background:#111;padding:5px;border-radius:3px;">{filename}</p>
                <a href="{file_url}" download="{filename}" class="btn">⬇ Descargar archivo</a>
            </div>
            <div class="card">
                <h3>🎮 Instrucciones</h3>
                <div class="instruction">
                    <p><strong>1.</strong> Descarga el archivo</p>
                    <p><strong>2.</strong> En el emulador: File → Open</p>
                    <p><strong>3.</strong> {'LOAD "" (J + Ctrl+P×2 + ENTER)' if is_tape else 'Carga automática' if is_snapshot else 'Usar menú TR-DOS' if is_disk else 'Cargar manualmente'}</p>
                </div>
            </div>
            <div class="card">
                <h3>⌨️ Teclas</h3>
                <p>F1 - Menú | F2 - Guardar | F3 - Cargar</p>
            </div>
        </div>
    </div>
</body>
</html>'''
    return Response(html, mimetype='text/html')

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 ZX SPECTRUM TOSEC ORGANIZER")
    print("=" * 60)
    print(f"FE: {CONFIG['FE_PATH']}")
    print(f"TS: {CONFIG['TS_PATH']}/{CONFIG['TS_TOSEC_SUBPATH']}")
    print(f"TEMP: {CONFIG['TEMP_PATH']}")
    print(f"BACKUP: {CONFIG['BACKUP_PATH']}")
    print(f"\n🌐 http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
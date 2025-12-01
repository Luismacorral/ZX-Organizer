from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS
import os
import csv
import subprocess
import platform
import base64
import shutil
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
        elif platform.system() == 'Darwin':
            subprocess.call(['open', file_path])
        else:
            subprocess.call(['xdg-open', file_path])
        return jsonify({'success': True, 'message': f'Abriendo {os.path.basename(file_path)}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file-base64', methods=['POST'])
def get_file_base64():
    """Devuelve archivo en base64 para el emulador"""
    data = request.get_json()
    file_path = data.get('path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Archivo no encontrado'}), 404
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return jsonify({
            'success': True,
            'filename': os.path.basename(file_path),
            'extension': os.path.splitext(file_path)[1].lower(),
            'base64': base64.b64encode(content).decode('utf-8'),
            'size': len(content)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/serve-file')
def serve_file():
    """Sirve un archivo directamente para el emulador"""
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'Path no especificado'}), 400
    
    # Verificar que el archivo está en una ruta permitida
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(file_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed or not os.path.exists(file_path):
        return jsonify({'error': 'Acceso denegado o archivo no encontrado'}), 404
    
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=False)

# NUEVO: Copiar archivo entre colecciones (drag & drop)
@app.route('/api/copy-between', methods=['POST'])
def copy_between_collections():
    """Copia un archivo de una colección/ruta a otra"""
    data = request.get_json()
    source_path = data.get('source_path')
    dest_collection = data.get('dest_collection')
    dest_folder = data.get('dest_folder')
    
    if not source_path or not dest_collection or not os.path.exists(source_path):
        return jsonify({'error': 'Parámetros inválidos o archivo no existe'}), 400
    
    try:
        filename = os.path.basename(source_path)
        dest_base = get_collection_base_path(dest_collection)
        dest_full = os.path.join(dest_base, dest_folder, filename) if dest_folder else os.path.join(dest_base, filename)
        
        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        shutil.copy2(source_path, dest_full)
        
        cache['FE'] = None
        cache['TS'] = None
        
        return jsonify({
            'success': True,
            'message': f'Copiado: {filename}',
            'source': source_path,
            'destination': dest_full
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    try:
        fe_path = get_collection_base_path('FE')
        ts_path = get_collection_base_path('TS')
        stats = scanner.calculate_stats(fe_path, ts_path)
        return jsonify(stats)
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
        return jsonify({'error': 'No se proporcionó nombre de archivo'}), 400
    try:
        result = scanner.process_temp_file(filename, destinations)
        cache['FE'] = None
        cache['TS'] = None
        cache['TEMP'] = None
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rules/load')
def load_rules():
    rules_file = r'C:\ZX\SCRIPTS PYTHON\reglas.csv'
    if not os.path.exists(rules_file):
        return jsonify({'error': 'Archivo no encontrado', 'rules': []})
    try:
        rules = []
        with open(rules_file, mode='r', encoding='latin-1') as f:
            reader = csv.reader(f, delimiter=',')
            headers = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    files_str = row[0].strip()
                    files = [f.strip() for f in files_str.split('|') if f.strip()]
                    categories = [cat.strip() for cat in row[1:] if cat.strip()]
                    if files and categories:
                        rules.append({'files': files, 'categories': categories})
        return jsonify({'rules': rules, 'total': len(rules)})
    except Exception as e:
        return jsonify({'error': str(e), 'rules': []})

@app.route('/api/rules/save', methods=['POST'])
def save_rules():
    rules_file = r'C:\ZX\SCRIPTS PYTHON\reglas.csv'
    data = request.get_json()
    rules = data.get('rules', [])
    try:
        with open(rules_file, mode='w', encoding='latin-1', newline='') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['Archivos', 'Categoría 1', 'Categoría 2', 'Categoría 3', 'Categoría 4'])
            for rule in rules:
                files_str = '|'.join(rule.get('files', []))
                row = [files_str] + rule.get('categories', [])
                writer.writerow(row)
        return jsonify({'success': True, 'message': f'{len(rules)} reglas guardadas'})
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

@app.route('/api/compress', methods=['POST'])
def compress_collection():
    """Comprime una colección en volúmenes"""
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
    
    try:
        os.makedirs(dest_path, exist_ok=True)
        
        total_size = 0
        for root, dirs, files in os.walk(source_path):
            for f in files:
                total_size += os.path.getsize(os.path.join(root, f))
        
        archive_name = f"TOSEC_{collection}"
        
        if compress_format == '7z':
            cmd = f'7z a -v{volume_size_mb}m "{os.path.join(dest_path, archive_name)}.7z" "{source_path}\\*"'
        elif compress_format == 'rar':
            cmd = f'rar a -v{volume_size_mb}m "{os.path.join(dest_path, archive_name)}.rar" "{source_path}\\*"'
        else:
            cmd = f'7z a -tzip -v{volume_size_mb}m "{os.path.join(dest_path, archive_name)}.zip" "{source_path}\\*"'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            volumes = len([f for f in os.listdir(dest_path) if f.startswith(archive_name)])
            return jsonify({
                'success': True,
                'message': f'Compresión completada',
                'volumes': volumes,
                'total_size_mb': total_size / (1024*1024),
                'dest_path': dest_path
            })
        else:
            return jsonify({'error': f'Error en compresión: {result.stderr}'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup/list-files')
def list_backup_files():
    """Lista archivos de backup disponibles"""
    backup_path = CONFIG['BACKUP_PATH']
    if not os.path.exists(backup_path):
        os.makedirs(backup_path, exist_ok=True)
        return jsonify({'files': [], 'path': backup_path})
    
    try:
        files = []
        for f in os.listdir(backup_path):
            fp = os.path.join(backup_path, f)
            if os.path.isfile(fp):
                files.append({
                    'name': f,
                    'size': os.path.getsize(fp),
                    'modified': os.path.getmtime(fp)
                })
        files.sort(key=lambda x: x['name'])
        return jsonify({'files': files, 'path': backup_path})
    except Exception as e:
        return jsonify({'error': str(e), 'files': []})

@app.route('/api/backup/ftp-upload', methods=['POST'])
def ftp_upload():
    """Sube archivos de backup al NAS via FTP"""
    import ftplib
    
    data = request.get_json()
    password = data.get('password')
    files_to_upload = data.get('files', [])
    remote_path = data.get('remote_path', '/ZxTosec')  # Carpeta correcta en el NAS
    
    if not password:
        return jsonify({'error': 'Se requiere contraseña'}), 400
    
    backup_path = CONFIG['BACKUP_PATH']
    ftp_host = 'revisteo.synology.me'
    ftp_user = 'Flunky'
    
    results = {'success': [], 'failed': [], 'total': len(files_to_upload)}
    
    try:
        # Conexión FTP con TLS explícito
        ftp = ftplib.FTP_TLS()
        ftp.connect(ftp_host, 21)
        ftp.auth()
        ftp.prot_p()
        ftp.login(ftp_user, password)
        
        # Cambiar al directorio remoto
        try:
            ftp.cwd(remote_path)
        except ftplib.error_perm:
            # Intentar crear el directorio si no existe
            try:
                ftp.mkd(remote_path)
                ftp.cwd(remote_path)
            except:
                pass
        
        # Subir cada archivo
        for filename in files_to_upload:
            local_file = os.path.join(backup_path, filename)
            if os.path.exists(local_file):
                try:
                    with open(local_file, 'rb') as f:
                        ftp.storbinary(f'STOR {filename}', f)
                    results['success'].append(filename)
                except Exception as e:
                    results['failed'].append({'file': filename, 'error': str(e)})
            else:
                results['failed'].append({'file': filename, 'error': 'Archivo no encontrado'})
        
        ftp.quit()
        
        return jsonify({
            'success': len(results['failed']) == 0,
            'message': f"Subidos {len(results['success'])} de {results['total']} archivos",
            'results': results
        })
        
    except ftplib.error_perm as e:
        return jsonify({'error': f'Error de permisos FTP: {str(e)}'}), 403
    except Exception as e:
        return jsonify({'error': f'Error FTP: {str(e)}'}), 500

@app.route('/api/emulator-page')
def emulator_page():
    """Genera una página HTML con ZX-Dream embebido que soporta TAP, TZX, Z80, SNA, TRD, SCL, DSK"""
    file_path = request.args.get('path')
    
    if not file_path or not os.path.exists(file_path):
        return "Archivo no encontrado", 404
    
    # Verificar permisos
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(file_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed:
        return "Acceso denegado", 403
    
    filename = os.path.basename(file_path)
    file_url = f'/api/serve-file?path={file_path.replace(chr(92), "/")}'
    
    # Página HTML con instrucciones para cargar el archivo
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>ZX Spectrum - {filename}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); 
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            font-family: 'Segoe UI', sans-serif;
            color: white;
        }}
        h1 {{ 
            color: #00d4ff; 
            font-size: 18px; 
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .info {{
            background: rgba(0,0,0,0.3);
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 15px;
            text-align: center;
        }}
        .info p {{ margin: 5px 0; font-size: 14px; }}
        .info .hint {{ color: #ffd700; font-size: 12px; margin-top: 10px; }}
        .download-btn {{
            display: inline-block;
            background: #7b2cbf;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            text-decoration: none;
            margin: 10px 0;
            font-weight: bold;
        }}
        .download-btn:hover {{ background: #9d4edd; }}
        #emulator-frame {{
            border: 3px solid #7b2cbf;
            border-radius: 8px;
            width: 840px;
            height: 640px;
        }}
        .formats {{
            margin-top: 15px;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <h1>▶ {filename}</h1>
    <div class="info">
        <p>El emulador <strong>ZX-Dream</strong> soporta: TAP, TZX, Z80, SNA, TRD, SCL, DSK</p>
        <p class="hint">1. Descarga el archivo con el botón de abajo<br>
        2. Arrástralo al emulador o usa el menú File → Open</p>
        <a href="{file_url}" download="{filename}" class="download-btn">⬇ Descargar {filename}</a>
    </div>
    <iframe id="emulator-frame" src="https://zx.researcher.su/en/" allow="autoplay"></iframe>
    <p class="formats">Formatos soportados: .tap .tzx .z80 .sna .trd .scl .fdi .td0 .udi .dsk</p>
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
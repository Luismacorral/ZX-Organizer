from flask import Flask, jsonify, send_from_directory, request
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
    'TS_TOSEC_SUBPATH': 'TOSEC_v40.9'
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

@app.route('/api/serve-file/<path:filepath>')
def serve_file(filepath):
    """Sirve un archivo directamente para descarga/emulador"""
    # Verificar que el archivo está en una ruta permitida
    full_path = filepath
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    
    is_allowed = any(full_path.startswith(root) for root in allowed_roots)
    if not is_allowed or not os.path.exists(full_path):
        return jsonify({'error': 'Acceso denegado o archivo no encontrado'}), 404
    
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename, as_attachment=False)

# NUEVO: Copiar archivo entre colecciones (drag & drop)
@app.route('/api/copy-between', methods=['POST'])
def copy_between_collections():
    """Copia un archivo de una colección/ruta a otra"""
    data = request.get_json()
    source_path = data.get('source_path')  # Ruta completa del archivo origen
    dest_collection = data.get('dest_collection')  # 'FE' o 'TS'
    dest_folder = data.get('dest_folder')  # Ruta relativa de destino
    
    if not source_path or not dest_collection or not os.path.exists(source_path):
        return jsonify({'error': 'Parámetros inválidos o archivo no existe'}), 400
    
    try:
        filename = os.path.basename(source_path)
        dest_base = get_collection_base_path(dest_collection)
        dest_full = os.path.join(dest_base, dest_folder, filename) if dest_folder else os.path.join(dest_base, filename)
        
        # Crear directorio destino si no existe
        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        
        # Copiar archivo
        shutil.copy2(source_path, dest_full)
        
        # Limpiar caché
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
                    # Columna 0: archivos separados por |
                    files_str = row[0].strip()
                    files = [f.strip() for f in files_str.split('|') if f.strip()]
                    # Columna 1+: categorías (con prefijo FE: o TS:)
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

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 ZX SPECTRUM TOSEC ORGANIZER")
    print("=" * 60)
    print(f"FE: {CONFIG['FE_PATH']}")
    print(f"TS: {CONFIG['TS_PATH']}/{CONFIG['TS_TOSEC_SUBPATH']}")
    print(f"TEMP: {CONFIG['TEMP_PATH']}")
    print(f"\n🌐 http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
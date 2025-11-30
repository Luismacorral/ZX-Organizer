from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import os
import csv
import subprocess
import platform
from scanner import DirectoryScanner

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# Configuración de rutas
CONFIG = {
    'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
    'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
    'TEMP_PATH': r'c:\ZX\TEMP',
    'TS_TOSEC_SUBPATH': 'TOSEC_v40.9'
}

# Cache global
cache = {
    'FE': None,
    'TS': None,
    'TEMP': None,
    'stats': None
}

scanner = DirectoryScanner(CONFIG)

def get_collection_base_path(collection):
    """Obtiene la ruta base real para una colección"""
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
            'FE': {
                'name': 'Full Edition',
                'path': CONFIG['FE_PATH'],
                'exists': os.path.exists(CONFIG['FE_PATH'])
            },
            'TS': {
                'name': 'The Spectrum',
                'path': ts_full_path,
                'exists': os.path.exists(ts_full_path)
            }
        },
        'temp_path': CONFIG['TEMP_PATH'],
        'temp_exists': os.path.exists(CONFIG['TEMP_PATH'])
    })

@app.route('/api/scan/<collection>')
def scan_collection(collection):
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    
    if cache[collection]:
        return jsonify(cache[collection])
    
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
        return jsonify({'error': 'Ruta no encontrada'}), 404
    
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

# NUEVO: Endpoint para eliminar archivos de TEMP
@app.route('/api/temp/delete', methods=['POST'])
def delete_temp_file():
    """Elimina un archivo de la carpeta TEMP"""
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'error': 'No se proporcionó nombre de archivo'}), 400
    
    try:
        result = scanner.delete_temp_file(filename)
        if result['success']:
            cache['TEMP'] = None  # Limpiar caché
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# NUEVO: Endpoint para abrir archivos con aplicación predeterminada
@app.route('/api/open-file', methods=['POST'])
def open_file():
    """Abre un archivo con la aplicación predeterminada del sistema"""
    data = request.get_json()
    file_path = data.get('path')
    
    if not file_path:
        return jsonify({'error': 'No se proporcionó ruta de archivo'}), 400
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'El archivo no existe'}), 404
    
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

@app.route('/api/stats')
def get_stats():
    if cache['stats']:
        return jsonify(cache['stats'])
    
    try:
        fe_path = get_collection_base_path('FE')
        ts_path = get_collection_base_path('TS')
        stats = scanner.calculate_stats(fe_path, ts_path)
        cache['stats'] = stats
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/clear')
def clear_cache():
    global cache
    cache = {'FE': None, 'TS': None, 'TEMP': None, 'stats': None}
    return jsonify({'message': 'Caché limpiada correctamente'})

@app.route('/api/process-file', methods=['POST'])
def process_file():
    """Procesa un archivo de TEMP y lo copia a los destinos seleccionados"""
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
    """Carga las reglas desde el archivo CSV"""
    rules_file = r'C:\ZX\SCRIPTS PYTHON\reglas.csv'
    
    if not os.path.exists(rules_file):
        return jsonify({'error': 'Archivo de reglas no encontrado', 'rules': []})
    
    try:
        rules = []
        
        with open(rules_file, mode='r', encoding='latin-1') as f:
            reader = csv.reader(f, delimiter=',')
            headers = next(reader, None)
            
            for row in reader:
                if len(row) >= 2:
                    identifier = row[0].strip()
                    categories = [cat.strip() for cat in row[1:] if cat.strip()]
                    
                    if identifier and categories:
                        rules.append({
                            'identifier': identifier,
                            'categories': categories
                        })
        
        return jsonify({'rules': rules, 'total': len(rules)})
    except Exception as e:
        return jsonify({'error': str(e), 'rules': []})

@app.route('/api/rules/save', methods=['POST'])
def save_rules():
    """Guarda las reglas en el archivo CSV"""
    rules_file = r'C:\ZX\SCRIPTS PYTHON\reglas.csv'
    data = request.get_json()
    rules = data.get('rules', [])
    
    try:
        with open(rules_file, mode='w', encoding='latin-1', newline='') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['Identificador', 'Categoría 1', 'Categoría 2', 'Categoría 3'])
            
            for rule in rules:
                row = [rule['identifier']] + rule['categories']
                writer.writerow(row)
        
        return jsonify({'success': True, 'message': f'{len(rules)} reglas guardadas'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rules/delete/<int:index>', methods=['DELETE'])
def delete_rule(index):
    """Elimina una regla por su índice"""
    rules_file = r'C:\ZX\SCRIPTS PYTHON\reglas.csv'
    
    try:
        rules = []
        with open(rules_file, mode='r', encoding='latin-1') as f:
            reader = csv.reader(f, delimiter=',')
            headers = next(reader, None)
            rules = list(reader)
        
        if 0 <= index < len(rules):
            deleted = rules.pop(index)
            
            with open(rules_file, mode='w', encoding='latin-1', newline='') as f:
                writer = csv.writer(f, delimiter=',')
                writer.writerow(['Identificador', 'Categoría 1', 'Categoría 2', 'Categoría 3'])
                writer.writerows(rules)
            
            return jsonify({'success': True, 'deleted': deleted[0]})
        else:
            return jsonify({'error': 'Índice inválido'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse-folders/<collection>')
def browse_folders_for_rules(collection):
    """Navega carpetas para selección de reglas"""
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    
    base_path = get_collection_base_path(collection)
    
    try:
        folders = []
        for item in sorted(os.listdir(base_path)):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                folders.append({
                    'name': item,
                    'path': item,
                    'has_subfolders': scanner._has_subfolders(item_path)
                })
        
        return jsonify({'folders': folders, 'base': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse-folders/<collection>/<path:subpath>')
def browse_subfolders_for_rules(collection, subpath):
    """Navega subcarpetas para selección de reglas"""
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
                folders.append({
                    'name': item,
                    'path': os.path.join(subpath, item),
                    'has_subfolders': scanner._has_subfolders(item_path)
                })
        
        return jsonify({'folders': folders, 'base': subpath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 ZX SPECTRUM TOSEC ORGANIZER - Backend Server")
    print("=" * 60)
    print(f"\n📁 Rutas configuradas:")
    print(f"   FE: {CONFIG['FE_PATH']}")
    print(f"   TS: {CONFIG['TS_PATH']}/{CONFIG['TS_TOSEC_SUBPATH']}")
    print(f"   TEMP: {CONFIG['TEMP_PATH']}")
    print(f"\n🌐 Servidor iniciado en: http://localhost:5000")
    print(f"📡 API disponible en: http://localhost:5000/api/")
    print("\n⚠️  Presiona CTRL+C para detener el servidor\n")
    print("=" * 60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
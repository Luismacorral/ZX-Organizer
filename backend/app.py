from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS
from urllib.parse import quote
import os
import sys
import csv
import subprocess
import platform
import base64
import shutil
import time
import threading
from scanner import DirectoryScanner

# Determinar el directorio base (donde está app.py = backend/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Frontend está en ../frontend/
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend')

app = Flask(__name__)
CORS(app)

# Configuración - usa variables de entorno si están disponibles, sino valores por defecto
CONFIG = {
    'FE_PATH': os.environ.get('ZX_FE_PATH', r'c:\ZX\ZX_v41_FE'),
    'TS_PATH': os.environ.get('ZX_TS_PATH', r'c:\ZX\ZX_v41_TS'),
    'TEMP_PATH': os.environ.get('ZX_TEMP_PATH', r'c:\ZX\TEMP'),
    'TS_TOSEC_SUBPATH': os.environ.get('ZX_TS_TOSEC_SUBPATH', 'TOSEC_v41'),
    'BACKUP_PATH': os.environ.get('ZX_BACKUP_PATH', r'C:\ZX\Backups'),
    'UPDATES_TOSEC_PATH': os.environ.get('ZX_UPDATES_TOSEC_PATH', r'C:\ZX\UPDATES_TOSEC')
}

cache = {'FE': None, 'TS': None, 'TEMP': None, 'stats': None}
scanner = DirectoryScanner(CONFIG)

# Estado global para compresión
compress_status = {'running': False, 'progress': '', 'percent': 0, 'done': False, 'error': None}
compress_cancel_flag = False
compress_process = None

def get_collection_base_path(collection):
    if collection == 'FE':
        return CONFIG['FE_PATH']
    elif collection == 'TS':
        return os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH'])
    elif collection == 'UPD':
        return CONFIG.get('UPDATES_TOSEC_PATH', r'C:\ZX\UPDATES_TOSEC')
    return None

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

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

@app.route('/api/browse/<collection>')
def browse_root(collection):
    """Navegar la raíz de una colección"""
    if collection not in ['FE', 'TS']:
        return jsonify({'error': 'Colección inválida'}), 400
    base_path = get_collection_base_path(collection)
    if not os.path.exists(base_path):
        return jsonify({'error': f'Ruta base no encontrada'}), 404
    try:
        items = scanner.get_folder_contents(base_path, collection=collection)
        return jsonify(items)
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

@app.route('/api/temp/preview', methods=['POST'])
def preview_temp_copy():
    """
    Muestra vista previa de los destinos antes de copiar a FE/TS real.
    Solo procesa archivos TOSEC válidos (sin .zip, .rar, etc.)
    """
    data = request.get_json()
    target_collection = data.get('target_collection', 'TS')
    
    temp_path = CONFIG.get('TEMP_PATH', '')
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'success': False, 'error': 'Carpeta TEMP no existe'})
    
    files_preview = []
    
    for filename in os.listdir(temp_path):
        file_path = os.path.join(temp_path, filename)
        if not os.path.isfile(file_path):
            continue
        
        ext = os.path.splitext(filename)[1].lower()
        # Solo procesar archivos TOSEC válidos (sin .zip ni otros comprimidos)
        if ext not in scanner.TOSEC_EXTENSIONS:
            continue
        
        try:
            tosec_info = scanner._parse_tosec_filename(filename)
            suggested_paths = scanner._suggest_destination(tosec_info, ext, filename)
            paths_for_collection = suggested_paths.get(target_collection, [])
            
            files_preview.append({
                'filename': filename,
                'tosec_info': tosec_info,
                'dest_paths': paths_for_collection,
                'has_destinations': len(paths_for_collection) > 0
            })
        except Exception as e:
            files_preview.append({
                'filename': filename,
                'tosec_info': None,
                'dest_paths': [],
                'has_destinations': False,
                'error': str(e)
            })
    
    return jsonify({
        'success': True,
        'files': files_preview,
        'target_collection': target_collection,
        'total_files': len(files_preview)
    })

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

@app.route('/api/temp/copy', methods=['POST'])
def copy_temp_to_collection():
    """
    Copia archivos de TEMP a FE/TS usando las rutas sugeridas.
    Solo procesa archivos TOSEC válidos (sin .zip, .rar, etc.)
    """
    data = request.get_json()
    target_collection = data.get('target_collection', 'TS')
    
    temp_path = CONFIG.get('TEMP_PATH', '')
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'success': False, 'error': 'Carpeta TEMP no existe'})
    
    base_path = get_collection_base_path(target_collection)
    if not base_path:
        return jsonify({'success': False, 'error': f'Colección {target_collection} no configurada'})
    
    results = []
    
    for filename in os.listdir(temp_path):
        file_path = os.path.join(temp_path, filename)
        if not os.path.isfile(file_path):
            continue
        
        ext = os.path.splitext(filename)[1].lower()
        # Solo procesar archivos TOSEC válidos (sin .zip ni otros comprimidos)
        if ext not in scanner.TOSEC_EXTENSIONS:
            continue
        
        try:
            tosec_info = scanner._parse_tosec_filename(filename)
            suggested_paths = scanner._suggest_destination(tosec_info, ext, filename)
            paths_for_collection = suggested_paths.get(target_collection, [])
            
            if not paths_for_collection:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': 'Sin destinos sugeridos'
                })
                continue
            
            copied_to = []
            for dest_subpath in paths_for_collection:
                full_dest = os.path.join(base_path, dest_subpath)
                os.makedirs(os.path.dirname(full_dest), exist_ok=True)
                shutil.copy2(file_path, full_dest)
                copied_to.append(dest_subpath)
            
            results.append({
                'filename': filename,
                'success': True,
                'dest_paths': copied_to
            })
            
        except Exception as e:
            results.append({
                'filename': filename,
                'success': False,
                'error': str(e)
            })
    
    # Invalidar caches
    cache['FE'] = None
    cache['TS'] = None
    
    return jsonify({
        'success': True,
        'results': results,
        'total': len(results),
        'copied': sum(1 for r in results if r.get('success'))
    })

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

@app.route('/api/copy-folder', methods=['POST'])
def copy_folder_between_collections():
    """Copia una carpeta completa entre colecciones"""
    data = request.get_json()
    source_path = data.get('source_path')
    dest_collection = data.get('dest_collection')
    dest_folder = data.get('dest_folder', '')
    folder_name = data.get('folder_name')
    
    if not source_path or not dest_collection or not os.path.isdir(source_path):
        return jsonify({'error': 'Parámetros inválidos o carpeta no existe'}), 400
    
    try:
        dest_base = get_collection_base_path(dest_collection)
        if not dest_base:
            return jsonify({'error': f'Colección {dest_collection} no configurada'}), 400
        
        # Construir ruta destino
        if dest_folder:
            dest_full = os.path.join(dest_base, dest_folder, folder_name)
        else:
            dest_full = os.path.join(dest_base, folder_name)
        
        # Si ya existe, sobrescribir contenido
        if os.path.exists(dest_full):
            # Copiar sobrescribiendo archivos existentes
            files_copied = 0
            for root, dirs, files in os.walk(source_path):
                rel_path = os.path.relpath(root, source_path)
                dest_dir = os.path.join(dest_full, rel_path) if rel_path != '.' else dest_full
                os.makedirs(dest_dir, exist_ok=True)
                
                for file in files:
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(dest_dir, file)
                    shutil.copy2(src_file, dst_file)  # Siempre sobrescribe
                    files_copied += 1
        else:
            # Copiar carpeta completa
            shutil.copytree(source_path, dest_full)
            files_copied = sum(len(files) for _, _, files in os.walk(dest_full))
        
        cache['FE'] = None
        cache['TS'] = None
        
        return jsonify({
            'success': True, 
            'message': f'Carpeta copiada: {folder_name}',
            'files_copied': files_copied
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/multicopy/execute', methods=['POST'])
def multicopy_execute():
    data = request.get_json()
    files = data.get('files', [])  # list of source file paths (absolute or relative to TEMP)
    dest_collection = data.get('dest_collection')  # 'FE', 'TS' or 'UPD'
    dest_path = data.get('dest_path', '')  # subfolder relativo O ruta absoluta
    full_dest_path_param = data.get('full_dest_path')  # ruta absoluta directa (opcional)

    if not files or dest_collection not in ['FE', 'TS', 'UPD']:
        return jsonify({'error': 'Faltan archivos o colección destino inválida'}), 400

    print(f"[MULTICOPY] files={files}")
    print(f"[MULTICOPY] dest_collection={dest_collection}")
    print(f"[MULTICOPY] full_dest_path_param={full_dest_path_param}")

    # Si se proporciona full_dest_path, usarlo directamente
    # En Windows, verificamos si tiene letra de unidad (ej: c:\)
    is_absolute = full_dest_path_param and (os.path.isabs(full_dest_path_param) or (len(full_dest_path_param) > 2 and full_dest_path_param[1] == ':'))
    
    print(f"[MULTICOPY] is_absolute={is_absolute}")
    
    if is_absolute:
        full_dest_path = full_dest_path_param
        print(f"[MULTICOPY] Usando ruta absoluta: {full_dest_path}")
    else:
        base_path = get_collection_base_path(dest_collection)
        print(f"[MULTICOPY] base_path={base_path}, dest_path={dest_path}")
        if not base_path:
            return jsonify({'error': 'Colección destino no encontrada'}), 400
        full_dest_path = os.path.join(base_path, dest_path) if dest_path else base_path
        print(f"[MULTICOPY] Calculando ruta: {full_dest_path}")

    # Verificar que la ruta está dentro de las colecciones permitidas
    allowed_roots = [
        CONFIG['FE_PATH'], 
        os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH']),
        CONFIG.get('UPDATES_TOSEC_PATH', '')
    ]
    allowed_roots = [os.path.normpath(r).lower() for r in allowed_roots if r]  # Normalizar y filtrar
    full_dest_normalized = os.path.normpath(full_dest_path).lower()
    is_allowed = any(full_dest_normalized.startswith(root) for root in allowed_roots)
    if not is_allowed:
        return jsonify({'error': f'Ruta destino no permitida: {full_dest_path}'}), 403

    os.makedirs(full_dest_path, exist_ok=True)

    results = []
    success_count = 0
    for src in files:
        if not os.path.isabs(src):
            src = os.path.join(CONFIG['TEMP_PATH'], src)
        if not os.path.exists(src):
            results.append({'file': os.path.basename(src), 'status': 'error', 'message': 'Archivo no encontrado'})
            continue
        try:
            shutil.copy2(src, os.path.join(full_dest_path, os.path.basename(src)))
            results.append({'file': os.path.basename(src), 'status': 'ok'})
            success_count += 1
        except Exception as e:
            results.append({'file': os.path.basename(src), 'status': 'error', 'message': str(e)})

    # Invalidate caches for both collections
    cache['FE'] = None
    cache['TS'] = None

    return jsonify({
        'success': success_count > 0,
        'copied': success_count,
        'total': len(files),
        'details': results
    })

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
    
    # Obtener la ruta fuente y nombre del archivo
    if collection == 'FE':
        source_path = CONFIG['FE_PATH']
        # Nombre del archivo = nombre de la carpeta raíz (ej: ZX_v41_FE)
        archive_name = os.path.basename(source_path.rstrip('/\\'))
    else:  # TS
        # Para TS comprimimos la carpeta raíz TS, no la subcarpeta TOSEC
        source_path = CONFIG['TS_PATH']
        # Nombre del archivo = nombre de la carpeta raíz TS (ej: ZX_v41_TS)
        archive_name = os.path.basename(source_path.rstrip('/\\'))
    
    if not os.path.exists(source_path):
        return jsonify({'error': f'Ruta fuente no existe: {source_path}'}), 400
    
    # Reset status
    compress_status = {'running': True, 'progress': 'Iniciando...', 'percent': 0, 'done': False, 'error': None}
    
    def run_compression():
        global compress_status, compress_cancel_flag, compress_process
        compress_cancel_flag = False
        try:
            # Buscar 7-Zip
            seven_zip_paths = [
                r'C:\Program Files\7-Zip\7z.exe',
                r'C:\Program Files (x86)\7-Zip\7z.exe',
                '7z'
            ]
            seven_zip_path = None
            for p in seven_zip_paths:
                if os.path.exists(p) or p == '7z':
                    seven_zip_path = p
                    break
            
            if not seven_zip_path:
                compress_status['error'] = '7-Zip no encontrado'
                compress_status['running'] = False
                return
            
            # Calcular tamaño total
            compress_status['progress'] = 'Calculando tamaño...'
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(source_path):
                if compress_cancel_flag:
                    compress_status['error'] = 'Cancelado por el usuario'
                    compress_status['running'] = False
                    return
                for f in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                        file_count += 1
                    except:
                        pass
            
            size_gb = total_size / (1024 * 1024 * 1024)
            compress_status['progress'] = f'Total: {file_count:,} archivos ({size_gb:.2f} GB)'
            
            # Crear carpeta destino
            os.makedirs(dest_path, exist_ok=True)
            
            # Construir comando
            ext = 'zip' if compress_format == 'zip' else '7z'
            archive_file = os.path.join(dest_path, f'{archive_name}.{ext}')
            
            # Eliminar archivo existente si hay
            for old_file in os.listdir(dest_path):
                if old_file.startswith(archive_name) and (old_file.endswith('.zip') or old_file.endswith('.7z') or '.zip.' in old_file or '.7z.' in old_file):
                    try:
                        os.remove(os.path.join(dest_path, old_file))
                    except:
                        pass
            
            # Para incluir la carpeta raíz en el ZIP, ejecutamos desde el directorio padre
            # y comprimimos la carpeta por nombre
            parent_dir = os.path.dirname(source_path.rstrip('/\\'))
            folder_name = os.path.basename(source_path.rstrip('/\\'))
            
            if compress_format == 'zip':
                cmd = [seven_zip_path, 'a', '-tzip', f'-v{volume_size_mb}m', '-mx=5', '-bsp1', archive_file, folder_name]
            else:
                cmd = [seven_zip_path, 'a', '-t7z', f'-v{volume_size_mb}m', '-mx=5', '-bsp1', archive_file, folder_name]
            
            compress_status['progress'] = f'Comprimiendo {archive_name}...'
            
            # Ejecutar con captura de salida - desde el directorio padre para incluir carpeta raíz
            compress_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=parent_dir
            )
            
            # Parsear progreso
            for line in compress_process.stdout:
                if compress_cancel_flag:
                    compress_process.terminate()
                    compress_status['error'] = 'Cancelado por el usuario'
                    compress_status['running'] = False
                    compress_process = None
                    # Limpiar archivos temporales/parciales
                    try:
                        for tmp_file in os.listdir(dest_path):
                            if tmp_file.startswith(archive_name):
                                os.remove(os.path.join(dest_path, tmp_file))
                    except:
                        pass
                    return
                line = line.strip()
                if '%' in line:
                    try:
                        # Buscar porcentaje en la línea (ej: "45%")
                        import re
                        match = re.search(r'(\d+)%', line)
                        if match:
                            pct = int(match.group(1))
                            compress_status['percent'] = pct
                            compress_status['progress'] = f'Comprimiendo {archive_name}... {pct}%'
                    except:
                        pass
            
            compress_process.wait()
            
            if compress_cancel_flag:
                compress_status['error'] = 'Cancelado por el usuario'
                # Limpiar archivos temporales/parciales
                try:
                    for tmp_file in os.listdir(dest_path):
                        if tmp_file.startswith(archive_name):
                            os.remove(os.path.join(dest_path, tmp_file))
                except:
                    pass
            elif compress_process.returncode == 0:
                # Contar volúmenes creados
                volumes = [f for f in os.listdir(dest_path) if f.startswith(archive_name) and (f'.{ext}' in f)]
                compress_status['progress'] = f'¡Completado! {len(volumes)} volumen(es) de {archive_name}'
                compress_status['percent'] = 100
                compress_status['done'] = True
            else:
                compress_status['error'] = f'Error en 7-Zip (código {compress_process.returncode})'
        except Exception as e:
            compress_status['error'] = str(e)
        finally:
            compress_status['running'] = False
            compress_process = None
    
    # Ejecutar en thread separado
    thread = threading.Thread(target=run_compression)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': f'Compresión de {archive_name} iniciada'})

@app.route('/api/compress/status')
def compress_get_status():
    return jsonify(compress_status)

@app.route('/api/compress/cancel', methods=['POST'])
def compress_cancel():
    global compress_cancel_flag, compress_process, compress_status
    compress_cancel_flag = True
    if compress_process:
        try:
            compress_process.terminate()
        except:
            pass
    compress_status['progress'] = 'Cancelando...'
    return jsonify({'success': True, 'message': 'Cancelación solicitada'})

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
    full_path = data.get('full_path')  # Ruta completa directa
    force = data.get('force', False)
    
    # Si viene full_path, usarlo directamente
    if full_path and os.path.exists(full_path):
        target_path = full_path
    elif collection and path:
        base_path = get_collection_base_path(collection)
        if not base_path:
            return jsonify({'error': 'Colección inválida'}), 400
        target_path = os.path.join(base_path, path)
    else:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    if not os.path.exists(target_path):
        return jsonify({'error': 'Carpeta no encontrada'}), 404
    
    # Verificar que está dentro de las rutas permitidas
    allowed_roots = [CONFIG.get('FE_PATH', ''), CONFIG.get('TS_PATH', ''), CONFIG.get('TEMP_PATH', '')]
    is_allowed = any(os.path.normpath(target_path).lower().startswith(os.path.normpath(root).lower()) for root in allowed_roots if root)
    
    if not is_allowed:
        return jsonify({'error': 'Ruta no permitida'}), 403
    
    try:
        if force:
            shutil.rmtree(target_path)
        else:
            os.rmdir(target_path)
        cache['FE'] = None
        cache['TS'] = None
        return jsonify({'success': True, 'message': 'Carpeta eliminada'})
    except OSError as e:
        if 'not empty' in str(e).lower() or 'directory not empty' in str(e).lower():
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

@app.route('/api/files/rename', methods=['POST'])
def rename_file():
    """Renombrar archivo o carpeta"""
    data = request.get_json()
    old_path = data.get('old_path')
    new_name = data.get('new_name')
    
    if not old_path or not new_name:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    # Validar que la ruta está permitida
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(old_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed:
        return jsonify({'error': 'Ruta no permitida'}), 403
    
    if not os.path.exists(old_path):
        return jsonify({'error': 'Archivo no encontrado'}), 404
    
    # Sanitizar nuevo nombre
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        new_name = new_name.replace(char, '')
    new_name = new_name.strip()
    
    if not new_name:
        return jsonify({'error': 'Nombre inválido'}), 400
    
    # Construir nueva ruta
    dir_path = os.path.dirname(old_path)
    new_path = os.path.join(dir_path, new_name)
    
    if os.path.exists(new_path):
        return jsonify({'error': 'Ya existe un archivo con ese nombre'}), 400
    
    try:
        os.rename(old_path, new_path)
        cache['FE'] = None
        cache['TS'] = None
        cache['TEMP'] = None
        return jsonify({
            'success': True,
            'old_name': os.path.basename(old_path),
            'new_name': new_name,
            'new_path': new_path
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============== BÚSQUEDA UNIVERSAL ==============

@app.route('/api/search')
def search_files():
    """Búsqueda universal en FE y TS"""
    query = request.args.get('q', '').strip().lower()
    
    if len(query) < 2:
        return jsonify({'results': [], 'error': 'Búsqueda muy corta'})
    
    results = []
    max_results = 500
    
    # Buscar en FE
    if CONFIG.get('FE_PATH') and os.path.exists(CONFIG['FE_PATH']):
        for root, dirs, files in os.walk(CONFIG['FE_PATH']):
            for f in files:
                if query in f.lower():
                    rel_path = os.path.relpath(os.path.join(root, f), CONFIG['FE_PATH'])
                    results.append({
                        'name': f,
                        'collection': 'FE',
                        'relative_path': rel_path.replace('\\', '/'),
                        'full_path': os.path.join(root, f)
                    })
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
    
    # Buscar en TS
    ts_full_path = os.path.join(CONFIG.get('TS_PATH', ''), CONFIG.get('TS_TOSEC_SUBPATH', ''))
    if ts_full_path and os.path.exists(ts_full_path) and len(results) < max_results:
        for root, dirs, files in os.walk(ts_full_path):
            for f in files:
                if query in f.lower():
                    rel_path = os.path.relpath(os.path.join(root, f), ts_full_path)
                    results.append({
                        'name': f,
                        'collection': 'TS',
                        'relative_path': rel_path.replace('\\', '/'),
                        'full_path': os.path.join(root, f)
                    })
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
    
    return jsonify({'results': results, 'total': len(results)})

# ============== COPIAR A TEMP ==============

@app.route('/api/copy-to-temp', methods=['POST'])
def copy_to_temp():
    """Copia un archivo a la carpeta TEMP"""
    data = request.get_json()
    source_path = data.get('source_path', '')
    
    if not source_path or not os.path.exists(source_path):
        return jsonify({'success': False, 'error': 'Archivo no encontrado'})
    
    temp_path = CONFIG.get('TEMP_PATH', '')
    if not temp_path:
        return jsonify({'success': False, 'error': 'Carpeta TEMP no configurada'})
    
    try:
        os.makedirs(temp_path, exist_ok=True)
        filename = os.path.basename(source_path)
        dest_path = os.path.join(temp_path, filename)
        shutil.copy2(source_path, dest_path)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============== UPDATE PACKAGE ==============

@app.route('/api/update/generate', methods=['POST'])
def generate_update_package():
    """
    Copia archivos de TEMP a UPDATES_TOSEC usando la misma lógica que la pestaña TEMP.
    Solo procesa archivos TOSEC válidos (sin .zip, .rar, etc.)
    """
    data = request.get_json()
    target_collection = data.get('target_collection', 'TS')  # FE o TS
    
    # Verificar TEMP
    temp_path = CONFIG.get('TEMP_PATH', '')
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'success': False, 'error': 'Carpeta TEMP no existe'})
    
    # Verificar UPDATES_TOSEC
    updates_base = CONFIG.get('UPDATES_TOSEC_PATH', r'C:\ZX\UPDATES_TOSEC')
    if not os.path.exists(updates_base):
        return jsonify({'success': False, 'error': f'Carpeta UPDATES_TOSEC no existe: {updates_base}'})
    
    results = []
    total_success = 0
    total_errors = 0
    
    # Procesar cada archivo en TEMP (solo archivos TOSEC válidos)
    for filename in os.listdir(temp_path):
        file_path = os.path.join(temp_path, filename)
        if not os.path.isfile(file_path):
            continue
        
        ext = os.path.splitext(filename)[1].lower()
        # Solo procesar archivos TOSEC válidos (sin .zip ni otros comprimidos)
        if ext not in scanner.TOSEC_EXTENSIONS:
            continue
        
        try:
            # Obtener info TOSEC y rutas sugeridas (IGUAL que en scan_temp_files)
            tosec_info = scanner._parse_tosec_filename(filename)
            suggested_paths = scanner._suggest_destination(tosec_info, ext, filename)
            
            # Obtener las rutas para la colección seleccionada
            paths_for_collection = suggested_paths.get(target_collection, [])
            
            if not paths_for_collection:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': f'No hay rutas sugeridas para {target_collection}'
                })
                total_errors += 1
                continue
            
            # Copiar a UPDATES_TOSEC usando la función del scanner
            copy_result = scanner.copy_file_to_updates_tosec(
                file_path, 
                paths_for_collection, 
                target_collection, 
                updates_base
            )
            
            if copy_result['success']:
                results.append({
                    'filename': filename,
                    'success': True,
                    'dest_paths': copy_result['success']
                })
                total_success += 1
            else:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': '; '.join(copy_result['errors']) if copy_result['errors'] else 'Error desconocido'
                })
                total_errors += 1
                
        except Exception as e:
            results.append({
                'filename': filename,
                'success': False,
                'error': str(e)
            })
            total_errors += 1
    
    return jsonify({
        'success': True,
        'total_files': total_success,
        'total_errors': total_errors,
        'results': results,
        'target_collection': target_collection
    })


@app.route('/api/update/preview', methods=['POST'])
def preview_update_package():
    """
    Muestra vista previa de los destinos antes de copiar (igual que TEMP muestra suggested_paths).
    Solo procesa archivos TOSEC válidos (sin .zip, .rar, etc.)
    """
    data = request.get_json()
    target_collection = data.get('target_collection', 'TS')
    
    temp_path = CONFIG.get('TEMP_PATH', '')
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'success': False, 'error': 'Carpeta TEMP no existe'})
    
    updates_base = CONFIG.get('UPDATES_TOSEC_PATH', r'C:\ZX\UPDATES_TOSEC')
    if not os.path.exists(updates_base):
        return jsonify({'success': False, 'error': f'Carpeta UPDATES_TOSEC no existe: {updates_base}'})
    
    files_preview = []
    
    for filename in os.listdir(temp_path):
        file_path = os.path.join(temp_path, filename)
        if not os.path.isfile(file_path):
            continue
        
        ext = os.path.splitext(filename)[1].lower()
        # Solo procesar archivos TOSEC válidos (sin .zip ni otros comprimidos)
        if ext not in scanner.TOSEC_EXTENSIONS:
            continue
        
        try:
            tosec_info = scanner._parse_tosec_filename(filename)
            suggested_paths = scanner._suggest_destination(tosec_info, ext, filename)
            paths_for_collection = suggested_paths.get(target_collection, [])
            
            files_preview.append({
                'filename': filename,
                'tosec_info': tosec_info,
                'dest_paths': paths_for_collection,
                'has_destinations': len(paths_for_collection) > 0
            })
        except Exception as e:
            files_preview.append({
                'filename': filename,
                'tosec_info': None,
                'dest_paths': [],
                'has_destinations': False,
                'error': str(e)
            })
    
    return jsonify({
        'success': True,
        'files': files_preview,
        'target_collection': target_collection,
        'total_files': len(files_preview)
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

# ============== MULTICOPIA NAVEGACIÓN (NUEVO ENDPOINT) ==============

@app.route('/api/multicopy/browse')
@app.route('/api/multicopy/browse/<path:full_path>')
def multicopy_browse(full_path=None):
    ROOT_PATHS = [
        CONFIG['FE_PATH'],
        CONFIG['TS_PATH'],
        os.path.join(CONFIG['TS_PATH'], CONFIG['TS_TOSEC_SUBPATH']),
        CONFIG['TEMP_PATH'],
        CONFIG.get('UPDATES_TOSEC_PATH', '')
    ]
    # Filtrar paths vacíos
    ROOT_PATHS = [p for p in ROOT_PATHS if p]

    if full_path is None or full_path == 'ROOT':
        try:
            items = scanner.get_multicopy_roots()
            return jsonify(items)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    is_allowed = any(full_path.startswith(root) for root in ROOT_PATHS)
    
    if not is_allowed or not os.path.exists(full_path):
        return jsonify({'error': 'Ruta no permitida o no encontrada'}), 403

    try:
        if os.path.isdir(full_path):
            contents = scanner.get_folder_contents(full_path, fast_scan=True)
            return jsonify(contents)
        else:
            return jsonify({'error': 'No es un directorio'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/emulator')
def emulator_page():
    """Abre el archivo directamente en un emulador de Windows"""
    file_path = request.args.get('path')
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Archivo no encontrado'}), 404
    
    allowed_roots = [CONFIG['FE_PATH'], CONFIG['TS_PATH'], CONFIG['TEMP_PATH']]
    is_allowed = any(file_path.startswith(root) for root in allowed_roots)
    
    if not is_allowed:
        return jsonify({'error': 'Acceso denegado'}), 403
    
    # Intentar abrir con el programa predeterminado de Windows
    try:
        os.startfile(file_path)
        return jsonify({'success': True, 'message': f'Abriendo: {os.path.basename(file_path)}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
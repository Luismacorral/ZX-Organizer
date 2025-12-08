"""
File management routes for ZX Organizer
Handles folder creation, file deletion, and file renaming
"""

import os
import shutil
from flask import jsonify, request

def create_folder_route(app, CONFIG, cache):
    """Create folder route"""
    @app.route('/api/create-folder', methods=['POST'])
    def create_folder():
        data = request.get_json()
        collection = data.get('collection')
        path = data.get('path', '')
        folder_name = data.get('folder_name')
        
        if not collection or not folder_name:
            return jsonify({'error': 'Missing parameters'}), 400
            
        if collection not in ['FE', 'TS']:
            return jsonify({'error': 'Invalid collection'}), 400
            
        base_path = CONFIG['FE_PATH'] if collection == 'FE' else os.path.join(CONFIG['TS_PATH'], CONFIG.get('TS_TOSEC_SUBPATH', 'TOSEC_v40.9'))
        full_path = os.path.join(base_path, path, folder_name) if path else os.path.join(base_path, folder_name)
        
        try:
            os.makedirs(full_path, exist_ok=False)
            cache[collection] = None  # Invalidate cache
            return jsonify({'success': True, 'message': f'Carpeta "{folder_name}" creada'})
        except FileExistsError:
            return jsonify({'error': f'La carpeta "{folder_name}" ya existe'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


def delete_files_route(app, CONFIG, cache):
    """Delete files route"""
    @app.route('/api/delete-files', methods=['POST'])
    def delete_files():
        data = request.get_json()
        collection = data.get('collection')
        paths = data.get('paths', [])
        
        if not collection or not paths:
            return jsonify({'error': 'Missing parameters'}), 400
            
        if collection not in ['FE', 'TS']:
            return jsonify({'error': 'Invalid collection'}), 400
            
        results = []
        deleted_count = 0
        
        for file_path in paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    results.append({'path': file_path, 'success': True})
                    deleted_count += 1
                else:
                    results.append({'path': file_path, 'success': False, 'error': 'File not found'})
            except Exception as e:
                results.append({'path': file_path, 'success': False, 'error': str(e)})
        
        cache[collection] = None  # Invalidate cache
        return jsonify({'success': True, 'deleted': deleted_count, 'results': results})


def rename_file_route(app, CONFIG, cache):
    """Rename file route"""
    @app.route('/api/rename-file', methods=['POST'])
    def rename_file():
        data = request.get_json()
        collection = data.get('collection')
        old_path = data.get('old_path')
        new_name = data.get('new_name')
        
        if not collection or not old_path or not new_name:
            return jsonify({'error': 'Missing parameters'}), 400
            
        if collection not in ['FE', 'TS']:
            return jsonify({'error': 'Invalid collection'}), 400
        
        try:
            if not os.path.exists(old_path):
                return jsonify({'error': 'File not found'}), 404
                
            directory = os.path.dirname(old_path)
            new_path = os.path.join(directory, new_name)
            
            if os.path.exists(new_path):
                return jsonify({'error': f'File "{new_name}" already exists'}), 400
                
            os.rename(old_path, new_path)
            cache[collection] = None  # Invalidate cache
            return jsonify({'success': True, 'message': f'Renamed to "{new_name}"', 'new_path': new_path})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

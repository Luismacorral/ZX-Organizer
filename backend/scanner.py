import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
import shutil

class DirectoryScanner:
    """Clase para escanear y analizar la estructura de carpetas TOSEC"""
    
    # Extensiones válidas para archivos ZX Spectrum
    VALID_EXTENSIONS = {'.tap', '.tzx', '.z80', '.sna', '.dsk', '.trd', '.scl', '.img', '.zip'}
    
    # Extensiones de archivos comunes que se pueden abrir
    COMMON_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.txt', '.doc', '.docx', '.xls', '.xlsx'}
    
    # Todas las extensiones que mostramos en la interfaz
    ALL_DISPLAYABLE = VALID_EXTENSIONS | COMMON_EXTENSIONS
    
    # Tipos de archivo para clasificación
    FILE_TYPES = {
        '.tap': 'TAPs',
        '.tzx': 'TZXs',
        '.z80': 'Z80s',
        '.sna': 'SNAs',
        '.dsk': 'DISCOS',
        '.trd': 'DISCOS',
        '.scl': 'DISCOS',
        '.img': 'OTROS',
        '.zip': 'OTROS'
    }
    
    def __init__(self, config: Dict[str, str]):
        self.config = config
    
    def scan_root_folders(self, base_path: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Escanea las carpetas raíz de una colección (FE o TS)
        OPTIMIZADO: Conteo rápido con os.walk
        """
        if not os.path.exists(base_path):
            return {'error': f'La ruta {base_path} no existe', 'folders': []}
        
        try:
            folders = []
            total_files = 0
            
            for item in sorted(os.listdir(base_path)):
                item_path = os.path.join(base_path, item)
                
                if os.path.isdir(item_path):
                    file_count = self._count_files_fast(item_path)
                    
                    folders.append({
                        'name': item,
                        'path': item,
                        'type': 'folder',
                        'file_count': file_count,
                        'has_subfolders': self._has_subfolders(item_path)
                    })
                    
                    total_files += file_count
            
            return {
                'base_path': base_path,
                'folders': folders,
                'total_files': total_files,
                'folder_count': len(folders)
            }
        
        except Exception as e:
            return {'error': str(e), 'folders': []}
    
    def _count_files_fast(self, path: str) -> int:
        """Conteo RÁPIDO usando os.walk - cuenta TODOS los archivos relevantes"""
        count = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in self.ALL_DISPLAYABLE:
                        count += 1
        except (PermissionError, OSError):
            pass
        return count
    
    def get_folder_contents(self, folder_path: str, include_files: bool = True, collection: str = None) -> Dict[str, Any]:
        """
        Obtiene el contenido de una carpeta específica
        MEJORADO: Muestra archivos comunes (PDF, JPG, PNG) y permite abrirlos
        """
        if not os.path.exists(folder_path):
            return {'error': 'Carpeta no encontrada', 'items': []}
        
        try:
            items = []
            file_count = 0
            folder_count = 0
            
            is_ts_collection = collection == 'TS' or (self.config.get('TS_PATH', '') in folder_path)
            
            for item in sorted(os.listdir(folder_path)):
                item_path = os.path.join(folder_path, item)
                
                if os.path.isdir(item_path):
                    total_files = self._count_files_limited(item_path, max_depth=2)
                    direct_files = self._count_direct_files(item_path)
                    
                    if is_ts_collection:
                        near_limit = direct_files >= 200
                        at_limit = direct_files >= 230
                    else:
                        near_limit = False
                        at_limit = False
                    
                    is_range = self._is_range_folder(item)
                    
                    items.append({
                        'name': item,
                        'type': 'folder',
                        'file_count': total_files,
                        'direct_files': direct_files,
                        'near_limit': near_limit,
                        'at_limit': at_limit,
                        'is_range': is_range,
                        'path': item
                    })
                    folder_count += 1
                
                elif include_files:
                    ext = os.path.splitext(item)[1].lower()
                    
                    # Mostrar TODOS los archivos relevantes
                    if ext in self.ALL_DISPLAYABLE:
                        is_spectrum_file = ext in self.VALID_EXTENSIONS
                        is_common_file = ext in self.COMMON_EXTENSIONS
                        
                        file_info = self._parse_tosec_filename(item) if is_spectrum_file else None
                        
                        if is_spectrum_file:
                            file_type = self.FILE_TYPES.get(ext, 'OTROS')
                        else:
                            file_type = ext.upper().replace('.', '')
                        
                        items.append({
                            'name': item,
                            'type': 'file',
                            'extension': ext,
                            'file_type': file_type,
                            'size': os.path.getsize(item_path),
                            'tosec_info': file_info,
                            'is_spectrum': is_spectrum_file,
                            'is_common': is_common_file,
                            'can_open': is_common_file,
                            'full_path': item_path,
                            'path': item
                        })
                        file_count += 1
            
            return {
                'path': folder_path,
                'items': items,
                'file_count': file_count,
                'folder_count': folder_count,
                'total_items': len(items)
            }
        
        except Exception as e:
            return {'error': str(e), 'items': []}
    
    def scan_temp_files(self, temp_path: str) -> Dict[str, Any]:
        """Escanea archivos en TEMP - incluye todos los archivos"""
        if not os.path.exists(temp_path):
            return {'error': 'Carpeta TEMP no encontrada', 'files': []}
        
        try:
            files = []
            
            for item in os.listdir(temp_path):
                item_path = os.path.join(temp_path, item)
                
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    
                    if ext in self.VALID_EXTENSIONS:
                        tosec_info = self._parse_tosec_filename(item)
                        suggested_paths = self._suggest_destination(tosec_info, ext, item)
                        
                        files.append({
                            'name': item,
                            'extension': ext,
                            'file_type': self.FILE_TYPES.get(ext, 'OTROS'),
                            'size': os.path.getsize(item_path),
                            'tosec_info': tosec_info,
                            'suggested_paths': suggested_paths,
                            'is_spectrum': True,
                            'is_common': False,
                            'can_delete': True,
                            'status': 'pending'
                        })
                    
                    elif ext in self.COMMON_EXTENSIONS:
                        files.append({
                            'name': item,
                            'extension': ext,
                            'file_type': ext.upper().replace('.', ''),
                            'size': os.path.getsize(item_path),
                            'tosec_info': None,
                            'suggested_paths': {'FE': [], 'TS': []},
                            'is_spectrum': False,
                            'is_common': True,
                            'can_delete': True,
                            'can_open': True,
                            'full_path': item_path,
                            'status': 'other'
                        })
            
            return {
                'path': temp_path,
                'files': files,
                'total_files': len(files),
                'spectrum_files': len([f for f in files if f.get('is_spectrum')]),
                'common_files': len([f for f in files if f.get('is_common')])
            }
        
        except Exception as e:
            return {'error': str(e), 'files': []}
    
    def delete_temp_file(self, filename: str) -> Dict[str, Any]:
        """Elimina un archivo de la carpeta TEMP"""
        file_path = os.path.join(self.config['TEMP_PATH'], filename)
        
        if not os.path.exists(file_path):
            return {'success': False, 'error': 'Archivo no encontrado'}
        
        try:
            os.remove(file_path)
            return {'success': True, 'message': f'Archivo {filename} eliminado'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def calculate_stats(self, fe_path: str, ts_path: str) -> Dict[str, Any]:
        """Calcula estadísticas generales de ambas colecciones"""
        stats = {
            'FE': self._get_collection_stats(fe_path),
            'TS': self._get_collection_stats(ts_path),
            'comparison': {}
        }
        stats['comparison'] = {
            'difference': stats['FE']['total_files'] - stats['TS']['total_files']
        }
        return stats
    
    def copy_file_to_destinations(self, source_file: str, destinations: List[str], collection: str) -> Dict[str, Any]:
        """Copia un archivo desde TEMP a múltiples destinos"""
        results = {
            'success': [],
            'errors': [],
            'file': os.path.basename(source_file)
        }
        
        if not os.path.exists(source_file):
            results['errors'].append(f"Archivo origen no existe: {source_file}")
            return results
        
        base_path = self.config['FE_PATH'] if collection == 'FE' else self.config['TS_PATH']
        
        for dest_path in destinations:
            try:
                full_dest_path = os.path.join(base_path, dest_path)
                dest_dir = os.path.dirname(full_dest_path)
                
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(source_file, full_dest_path)
                results['success'].append(dest_path)
                
            except Exception as e:
                results['errors'].append(f"Error copiando a {dest_path}: {str(e)}")
        
        return results
    
    def process_temp_file(self, filename: str, selected_destinations: Dict[str, List[str]]) -> Dict[str, Any]:
        """Procesa un archivo de TEMP y lo copia a los destinos seleccionados"""
        source_file = os.path.join(self.config['TEMP_PATH'], filename)
        
        results = {
            'filename': filename,
            'FE': {'success': [], 'errors': []},
            'TS': {'success': [], 'errors': []},
            'overall_success': False
        }
        
        if 'FE' in selected_destinations and selected_destinations['FE']:
            fe_results = self.copy_file_to_destinations(source_file, selected_destinations['FE'], 'FE')
            results['FE'] = fe_results
        
        if 'TS' in selected_destinations and selected_destinations['TS']:
            ts_results = self.copy_file_to_destinations(source_file, selected_destinations['TS'], 'TS')
            results['TS'] = ts_results
        
        total_success = len(results['FE'].get('success', [])) + len(results['TS'].get('success', []))
        results['overall_success'] = total_success > 0
        
        return results
    
    def _count_files_limited(self, path: str, max_depth: int = 2, current_depth: int = 0) -> int:
        """Cuenta archivos con límite de profundidad"""
        if current_depth >= max_depth:
            return 0
        
        count = 0
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in self.ALL_DISPLAYABLE:
                        count += 1
                elif os.path.isdir(item_path):
                    count += self._count_files_limited(item_path, max_depth, current_depth + 1)
        except (PermissionError, OSError):
            pass
        
        return count
    
    def _count_direct_files(self, path: str) -> int:
        """Cuenta SOLO los archivos directos en una carpeta"""
        count = 0
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    if ext in self.ALL_DISPLAYABLE:
                        count += 1
        except (PermissionError, OSError):
            pass
        return count
    
    def _has_subfolders(self, path: str) -> bool:
        """Verifica si una carpeta tiene subcarpetas"""
        try:
            for item in os.listdir(path):
                if os.path.isdir(os.path.join(path, item)):
                    return True
        except (PermissionError, OSError):
            pass
        return False
    
    def _is_range_folder(self, folder_name: str) -> bool:
        """Detecta si una carpeta es un rango alfabético"""
        return bool(re.match(r'^[A-Z0-9].*\s*-\s*[A-Z0-9].*$', folder_name, re.IGNORECASE))
    
    def _parse_range_folder(self, folder_name: str) -> tuple:
        """Parsea una carpeta de rango"""
        parts = re.split(r'\s*-\s*', folder_name)
        if len(parts) >= 2:
            return (parts[0].strip().upper(), parts[1].strip().upper())
        return (folder_name.upper(), folder_name.upper())

    def _longest_common_prefix(self, s1: str, s2: str) -> str:
        """Calcula el prefijo común más largo entre dos cadenas"""
        min_len = min(len(s1), len(s2))
        for i in range(min_len):
            if s1[i] != s2[i]:
                return s1[:i]
        return s1[:min_len]

    def _find_range_folder(self, base_path: str, title: str) -> Optional[str]:
        """Busca la carpeta de rango correcta para un título dado con lógica LCP"""
        if not os.path.exists(base_path):
            return None
        
        try:
            subfolders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
            range_folders = [f for f in subfolders if self._is_range_folder(f)]
            
            if not range_folders:
                return None
            
            title_upper = title.upper()
            sorted_ranges = sorted(range_folders)
            
            first_start, _ = self._parse_range_folder(sorted_ranges[0])
            if title_upper < first_start:
                return sorted_ranges[0]
            
            for i in range(len(sorted_ranges)):
                current_folder = sorted_ranges[i]
                current_start, current_end = self._parse_range_folder(current_folder)
                
                if i == len(sorted_ranges) - 1:
                    return current_folder
                
                next_folder = sorted_ranges[i + 1]
                next_start, _ = self._parse_range_folder(next_folder)
                
                if title_upper >= current_start and title_upper < next_start:
                    if title_upper <= current_end:
                        return current_folder
                    
                    lcp_prev = len(self._longest_common_prefix(title_upper, current_end))
                    lcp_next = len(self._longest_common_prefix(title_upper, next_start))
                    
                    if lcp_next > lcp_prev:
                        return next_folder
                    else:
                        return current_folder
            
            return sorted_ranges[-1]
                    
        except (PermissionError, OSError):
            pass
        
        return None

    def _parse_tosec_filename(self, filename: str) -> Dict[str, Any]:
        """Parsea un nombre de archivo TOSEC"""
        pattern = r'^(?P<title>.*?)\s*\((?P<year>\d{4}(?:-\d{4})?|19xx|20xx)\)\((?P<publisher>.*?)\)'
        match = re.match(pattern, filename)
        
        if match:
            info = match.groupdict()
            year_str = info['year'].lower()
            
            if 'xx' in year_str:
                category = 'unknown'
                year_int = 0
                years = []
            else:
                years = []
                try:
                    if '-' in year_str:
                        parts = year_str.split('-')
                        start_year = int(parts[0])
                        end_year = int(parts[1])
                        years = [start_year, end_year]
                        year_int = start_year
                    else:
                        year_int = int(year_str)
                        years = [year_int]
                    
                    has_classic = any(1982 <= y <= 1993 for y in years)
                    has_homebrew = any(1994 <= y <= 2025 for y in years)
                    
                    if has_classic and has_homebrew:
                        category = 'both'
                    elif has_classic:
                        category = 'classic'
                    elif has_homebrew:
                        category = 'homebrew'
                    else:
                        category = 'unknown'
                except ValueError:
                    year_int = 0
                    category = 'unknown'
                    years = []
            
            return {
                'title': info['title'].strip(),
                'year': info['year'],
                'year_int': year_int,
                'years': years,
                'publisher': info['publisher'].strip(),
                'category': category,
                'is_tosec': True
            }
        
        return {
            'title': os.path.splitext(filename)[0],
            'year': 'unknown',
            'year_int': 0,
            'years': [],
            'publisher': 'unknown',
            'category': 'unknown',
            'is_tosec': False
        }

    def _create_game_folder_name(self, title: str) -> str:
        """Crea el nombre de la carpeta del juego"""
        clean = re.sub(r'\s+v\.?\s?\d+(\.\d+)*(\s?beta|\s?alpha)?$', '', title, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s+(?:[2-9]|I{2,3}|IV|V|VI|VII|VIII|IX|X|part\s+\d+|p\d+)$', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'[<>:"/\\|?*]', '_', clean)
        return clean.upper()

    def _suggest_destination(self, tosec_info: Dict[str, Any], extension: str, original_filename: str) -> Dict[str, List[str]]:
        """Sugiere rutas de destino"""
        title = tosec_info.get('title', '').strip()
        years = tosec_info.get('years', [])
        year_int = tosec_info.get('year_int', 0)
        file_type = self.FILE_TYPES.get(extension, 'OTROS')
        
        letter = self._get_initial_letter(title)
        game_folder = self._create_game_folder_name(title)
        filename = original_filename
        
        suggestions = {'FE': [], 'TS': []}
        
        if not years and year_int > 0:
            years = [year_int]
        
        # === DESTINOS FE ===
        suggestions['FE'].append(f"00 TOSEC ALL/ALFABETO TOSEC/{letter}/{filename}")
        suggestions['FE'].append(f"00 TOSEC ALL/CARPETAS/{letter}/{game_folder}/{filename}")
        suggestions['FE'].append(f"00 TOSEC ALL/TIPOS DE ARCHIVO/{file_type}/{letter}/{filename}")
        
        for year in years:
            if 1982 <= year <= 1993:
                suggestions['FE'].append(f"01 AÑOS/1982-1993 CLASICOS/{year}/{letter}/{filename}")
            elif 1994 <= year <= 2025:
                decade = self._get_decade_range(year)
                suggestions['FE'].append(f"01 AÑOS/1994-2025 HOMEBREW/{decade}/{year}/{filename}")
        
        if any(1982 <= y <= 1993 for y in years):
            fe_classic_path = os.path.join(self.config['FE_PATH'], "02 CLASICOS/ALFABETO CLASICOS", letter, file_type)
            range_folder = self._find_range_folder(fe_classic_path, title)
            if range_folder:
                suggestions['FE'].append(f"02 CLASICOS/ALFABETO CLASICOS/{letter}/{file_type}/{range_folder}/{filename}")
            else:
                suggestions['FE'].append(f"02 CLASICOS/ALFABETO CLASICOS/{letter}/{file_type}/{filename}")
        
        if any(1994 <= y <= 2025 for y in years):
            suggestions['FE'].append(f"03 HOMEBREW/ALFABETO HOMEBREW/{letter}/{filename}")
        
        # === DESTINOS TS ===
        ts_base = "TOSEC_v40.9"
        
        ts_carpetas_path = os.path.join(self.config['TS_PATH'], ts_base, "00 CARPETAS", letter)
        range_folder_carpetas = self._find_range_folder(ts_carpetas_path, title)
        if range_folder_carpetas:
            suggestions['TS'].append(f"{ts_base}/00 CARPETAS/{letter}/{range_folder_carpetas}/{filename}")
        else:
            suggestions['TS'].append(f"{ts_base}/00 CARPETAS/{letter}/{game_folder}/{filename}")
        
        for year in years:
            if 1982 <= year <= 1993:
                ts_year_path = os.path.join(self.config['TS_PATH'], ts_base, "01 AÑOS/1982-1993 CLASICOS", str(year), letter, file_type)
                range_folder = self._find_range_folder(ts_year_path, title)
                if range_folder:
                    suggestions['TS'].append(f"{ts_base}/01 AÑOS/1982-1993 CLASICOS/{year}/{letter}/{file_type}/{range_folder}/{filename}")
                else:
                    suggestions['TS'].append(f"{ts_base}/01 AÑOS/1982-1993 CLASICOS/{year}/{letter}/{file_type}/{filename}")
            elif 1994 <= year <= 2025:
                decade = self._get_decade_range(year)
                suggestions['TS'].append(f"{ts_base}/01 AÑOS/1994-2025 HOMEBREW/{decade}/{year}/{file_type}/{filename}")
        
        if any(1982 <= y <= 1993 for y in years):
            ts_classic_path = os.path.join(self.config['TS_PATH'], ts_base, "02 CLASICOS/ALFABETO CLASICOS", letter, file_type)
            range_folder = self._find_range_folder(ts_classic_path, title)
            if range_folder:
                suggestions['TS'].append(f"{ts_base}/02 CLASICOS/ALFABETO CLASICOS/{letter}/{file_type}/{range_folder}/{filename}")
            else:
                suggestions['TS'].append(f"{ts_base}/02 CLASICOS/ALFABETO CLASICOS/{letter}/{file_type}/{filename}")
        
        if any(1994 <= y <= 2025 for y in years):
            ts_homebrew_path = os.path.join(self.config['TS_PATH'], ts_base, "03 HOMEBREW/ALFABETO HOMEBREW", letter, file_type)
            range_folder = self._find_range_folder(ts_homebrew_path, title)
            if range_folder:
                suggestions['TS'].append(f"{ts_base}/03 HOMEBREW/ALFABETO HOMEBREW/{letter}/{file_type}/{range_folder}/{filename}")
            else:
                suggestions['TS'].append(f"{ts_base}/03 HOMEBREW/ALFABETO HOMEBREW/{letter}/{file_type}/{filename}")
        
        return suggestions
    
    def _get_initial_letter(self, title: str) -> str:
        """Obtiene la letra inicial limpia"""
        if not title:
            return '123'
        for char in title:
            if char.isalpha():
                return char.upper()
            elif char.isdigit():
                return '123'
        return '123'
    
    def _get_decade_range(self, year: int) -> str:
        """Calcula el rango de década"""
        if year < 1980:
            return "19XX"
        start = (year // 10) * 10
        end = start + 9
        return f"{start}-{end}"
    
    def _get_collection_stats(self, path: str) -> Dict[str, Any]:
        """Obtiene estadísticas de una colección"""
        if not os.path.exists(path):
            return {'total_files': 0, 'total_all': 0, 'by_type': {}, 'by_decade': {}}
        
        stats = {
            'total_files': 0,
            'total_all': 0,
            'by_type': defaultdict(int),
            'by_decade': defaultdict(int)
        }
        
        for root, dirs, files in os.walk(path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                
                if ext in self.ALL_DISPLAYABLE:
                    stats['total_all'] += 1
                
                if ext in self.VALID_EXTENSIONS:
                    stats['total_files'] += 1
                    file_type = self.FILE_TYPES.get(ext, 'OTROS')
                    stats['by_type'][file_type] += 1
                    
                    tosec_info = self._parse_tosec_filename(file)
                    if tosec_info['year_int'] > 0:
                        decade = self._get_decade_range(tosec_info['year_int'])
                        stats['by_decade'][decade] += 1
        
        stats['by_type'] = dict(stats['by_type'])
        stats['by_decade'] = dict(stats['by_decade'])
        
        return stats
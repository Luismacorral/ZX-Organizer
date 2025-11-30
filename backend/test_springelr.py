import os
import sys

# Añadir el directorio backend al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from scanner import DirectoryScanner

# Configuración de prueba
config = {
    'FE_PATH': r'c:\ZX\ZX_v40.9_FE',
    'TS_PATH': r'c:\ZX\ZX_v40.9_TS',
    'TEMP_PATH': r'c:\ZX\TEMP'
}

scanner = DirectoryScanner(config)

# Probar con el archivo Springelr
filename = "Springelr (1988-2025)(Microbyte).tap"
print(f"=== Probando: {filename} ===\n")

# Parsear el archivo
tosec_info = scanner._parse_tosec_filename(filename)
print(f"Título: {tosec_info['title']}")
print(f"Años: {tosec_info['years']}")
print(f"Categoría: {tosec_info['category']}\n")

# Obtener sugerencias
suggestions = scanner._suggest_destination(tosec_info, '.tap', filename)

print("=== DESTINOS TS ===")
for i, path in enumerate(suggestions['TS'], 1):
    print(f"{i}. {path}")

print("\n=== DESTINOS FE ===")
for i, path in enumerate(suggestions['FE'], 1):
    print(f"{i}. {path}")

# Verificar específicamente la ruta de CARPETAS
print("\n=== VERIFICACIÓN ===")
carpetas_path = [p for p in suggestions['TS'] if '00 CARPETAS' in p][0]
print(f"Ruta de CARPETAS: {carpetas_path}")

if 'SPEKKU - STAR CRYS' in carpetas_path:
    print("✅ CORRECTO: El archivo se copiará a la carpeta de rango 'SPEKKU - STAR CRYS'")
elif 'SPRINGELR' in carpetas_path and 'SPEKKU' not in carpetas_path:
    print("❌ INCORRECTO: El archivo se está copiando a una carpeta individual en lugar de a un rango")
    print("   Debería ir a: TOSEC_v40.9/00 CARPETAS/S/SPEKKU - STAR CRYS/")
else:
    print(f"⚠️  REVISAR: {carpetas_path}")

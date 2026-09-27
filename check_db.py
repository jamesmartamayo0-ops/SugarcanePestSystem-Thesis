import subprocess
import sys
import os

# Change to backend directory to avoid path issues
os.chdir('C:\\Dev\\SugarcanePestSystem\\backend')

# Try to connect to PostgreSQL and list databases
try:
    result = subprocess.run([
        'C:\\Program Files\\PostgreSQL\\17\\bin\\psql.exe',
        '-h', 'localhost',
        '-p', '5434',
        '-U', 'postgres',
        '-d', 'postgres',
        '-c', 'SELECT datname FROM pg_database WHERE datistemplate = false;'
    ], capture_output=True, text=True, timeout=15)
    
    print('Exit code:', result.returncode)
    print('Stdout:')
    print(result.stdout)
    print('Stderr:')
    print(result.stderr)
    
    # Check if sugarcane_pest_db exists
    if 'sugarcane_pest_db' in result.stdout:
        print('Database sugarcane_pest_db already exists')
        sys.exit(0)
    else:
        print('Database sugarcane_pest_db does not exist')
        sys.exit(1)
        
except subprocess.TimeoutExpired:
    print('Connection timed out')
    sys.exit(1)
except Exception as e:
    print('Error:', e)
    sys.exit(1)
"""
WSGI Configuration for PythonAnywhere
====================================
Username: BrasFactorySystem
Domain: BrasFactorySystem.pythonanywhere.com

Copy and paste the contents below into your PythonAnywhere WSGI configuration file:
/var/www/brasfactorysystem_pythonanywhere_com_wsgi.py
"""

import os
import sys

# 1. Project directory path on PythonAnywhere
path = '/home/BrasFactorySystem/Factory_project'
if path not in sys.path:
    sys.path.insert(0, path)

# 2. Virtualenv path (if using a virtual environment, e.g. .virtualenvs/myenv)
# sys.path.insert(0, '/home/BrasFactorySystem/.virtualenvs/myenv/lib/python3.10/site-packages')

# 3. Settings module
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

# 4. Initialize Django WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

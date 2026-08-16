"""
WSGI Configuration for PythonAnywhere
====================================
Username: megahd
Domain: megahd.pythonanywhere.com

Copy and paste the contents below into your PythonAnywhere WSGI configuration file:
/var/www/megahd_pythonanywhere_com_wsgi.py
"""

import os
import sys

# 1. Project directory path on PythonAnywhere
# (Replace 'BrasFactory' or 'Factory_project' with the exact folder name you cloned on PythonAnywhere)
path = '/home/megahd/BrasFactory'
if not os.path.exists(path):
    path = '/home/megahd/Factory_project'

if path not in sys.path:
    sys.path.insert(0, path)

# 2. Virtualenv path (if created, e.g., /home/megahd/.virtualenvs/myenv)
# virtualenv_path = '/home/megahd/.virtualenvs/myenv/lib/python3.10/site-packages'
# if os.path.exists(virtualenv_path) and virtualenv_path not in sys.path:
#     sys.path.insert(0, virtualenv_path)

# 3. Settings module
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

# 4. Initialize Django WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

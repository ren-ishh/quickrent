# config.py
# This file loads your secret credentials from .env
# python-dotenv reads the .env file and makes the values
# available via os.environ — a dictionary of environment variables

import os
from dotenv import load_dotenv

# load_dotenv() reads your .env file
load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-fallback-key')
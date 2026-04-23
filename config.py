import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-fallback-key')

# Admin email — must match the user you created in Supabase Auth
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@quickrent.in')
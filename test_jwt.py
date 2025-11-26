import os
import importlib.util
from pathlib import Path

# set test secret exactly (no surrounding whitespace/newlines)
os.environ['JWT_SECRET'] = 'a-string-secret-at-least-256-bits-long'

# Load app/utils/jwt.py as a standalone module to avoid importing app.__init__
jwt_path = Path(__file__).resolve().parent / 'app' / 'utils' / 'jwt.py'
spec = importlib.util.spec_from_file_location('jwt_utils', str(jwt_path))
jwt_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jwt_utils)

print('ENV repr ->', repr(os.getenv('JWT_SECRET')))

try:
    # create token with long expiry (minutes) to avoid immediate expiry during test
    token = jwt_utils.create_access_token('user_1', role='patient', expires_minutes=60*24)
    print('TOKEN repr ->', repr(token))
    decoded = jwt_utils.decode_token(token)
    print('DECODED ->', decoded)
except Exception as e:
    import traceback
    traceback.print_exc()
    print('Error:', e)

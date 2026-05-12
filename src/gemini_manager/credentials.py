import os
import sys
import requests
from .ui import cprint, NEON_RED, NEON_YELLOW, NEON_GREEN
from .settings import get_setting

def load_env_file(path):
    """Simple parsing of key=value env file."""
    if not os.path.exists(path):
        return {}
    env = {}
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                # simple unquote
                value = value.strip().strip("'").strip('"')
                env[key.strip()] = value
    except Exception:
        pass
    return env

def get_doppler_token():
    """
    Look for DOPPLER_TOKEN in:
    1. Environment Variables
    2. doppler.env
    3. .env
    """
    # 1. Environment
    token = os.environ.get("DOPPLER_TOKEN")
    if token:
        return token

    # 2. doppler.env
    d_env = load_env_file("doppler.env")
    if "DOPPLER_TOKEN" in d_env:
        return d_env["DOPPLER_TOKEN"]

    # 3. .env
    dot_env = load_env_file(".env")
    if "DOPPLER_TOKEN" in dot_env:
        return dot_env["DOPPLER_TOKEN"]
    
    return None

def fetch_doppler_secrets(token):
    """Fetch secrets from Doppler API using the token."""
    url = "https://api.doppler.com/v3/configs/config/secrets/download?format=json"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            # If we found a token but it failed, we might want to warn but fallback
            cprint(NEON_YELLOW, f"[WARN] Found DOPPLER_TOKEN but failed to fetch secrets (Status: {response.status_code}).")
    except Exception as e:
        cprint(NEON_YELLOW, f"[WARN] Found DOPPLER_TOKEN but failed to connect to Doppler: {e}")
    return None

def resolve_credentials(args, allow_fail=False):
    """
    Resolve B2 credentials (key_id, app_key, bucket_name) with the following priority:
    1. CLI Arguments
    2. Doppler (DOPPLER_TOKEN in Env -> doppler.env -> .env)
    3. Environment Variables (GEMINI_B2_...)
    4. .env file (GEMINI_B2_...)
    5. Persistent Settings (settings.py)
    """
    # 1. CLI Args (Immediate return if all present, otherwise use as overrides)
    # We start with what we have from CLI
    c_id = getattr(args, 'b2_id', None)
    c_key = getattr(args, 'b2_key', None)
    c_bucket = getattr(args, 'bucket', None)

    if c_id and c_key and c_bucket:
        return c_id, c_key, c_bucket

    # Helper to fill missing from a source dict/func
    def fill_from(source_dict, source_name=""):
        nonlocal c_id, c_key, c_bucket
        updated = False
        if not c_id and source_dict.get("GEMINI_B2_KEY_ID"):
            c_id = source_dict.get("GEMINI_B2_KEY_ID")
            updated = True
        if not c_key and source_dict.get("GEMINI_B2_APP_KEY"):
            c_key = source_dict.get("GEMINI_B2_APP_KEY")
            updated = True
        if not c_bucket and source_dict.get("GEMINI_B2_BUCKET"):
            c_bucket = source_dict.get("GEMINI_B2_BUCKET")
            updated = True
        return updated

    # 2. Doppler
    token = get_doppler_token()
    if token:
        secrets = fetch_doppler_secrets(token)
        if secrets:
            # Doppler might store them with the same keys or simple names?
            # Assuming user maps them as GEMINI_B2_... in Doppler, or maybe just B2_KEY_ID?
            # The prompt doesn't specify the key names IN Doppler.
            # Standardize on checking both GEMINI_B2_... and just B2_... or whatever is in the map.
            # Let's assume they are stored as GEMINI_B2_KEY_ID, etc. matching the env vars.
            fill_from(secrets, "Doppler")

            # If still missing, check if they stored them without prefix?
            # (Optional: User didn't specify, sticking to explicit names is safer)

    if c_id and c_key and c_bucket:
        return c_id, c_key, c_bucket

    # 3. Environment Variables
    fill_from(os.environ, "Environment")
    
    if c_id and c_key and c_bucket:
        return c_id, c_key, c_bucket

    # 4. .env File (Individual keys)
    # We parse .env again (it might have been parsed for token, but now we look for keys)
    # Optimization: reuse if loaded? It's small, reloading is fine.
    dot_env_data = load_env_file(".env")
    fill_from(dot_env_data, ".env File")

    if c_id and c_key and c_bucket:
        return c_id, c_key, c_bucket

    # 5. Persistent Settings (Legacy / Local Config)
    # This uses get_setting which loads from ~/.gemini-manager/config.json
    if not c_id: c_id = get_setting("b2_id")
    if not c_key: c_key = get_setting("b2_key")
    if not c_bucket: c_bucket = get_setting("bucket")

    if c_id and c_key and c_bucket:
        return c_id, c_key, c_bucket

    # 6. Fail
    if allow_fail:
        return None, None, None

    cprint(NEON_RED, "[ERROR] Missing B2 credentials or bucket name.")
    cprint(NEON_RED, "We checked: CLI args, Doppler, Environment Variables, .env file, and local config.")
    cprint(NEON_RED, "Please provide credentials via any of these methods:")
    cprint(NEON_RED, "  1. Doppler (DOPPLER_TOKEN in env/doppler.env/.env)")
    cprint(NEON_RED, "  2. Environment Variables (GEMINI_B2_KEY_ID, GEMINI_B2_APP_KEY, GEMINI_B2_BUCKET)")
    cprint(NEON_RED, "  3. .env file in current directory")
    cprint(NEON_RED, "  4. CLI flags (--b2-id, --b2-key, --bucket)")
    sys.exit(1)

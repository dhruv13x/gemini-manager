import os
import sys

# Standard library TOML support in 3.11+, fallback to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # If tomli is missing on old python, we just won't load toml config
        tomllib = None


def load_project_config(profile=None):
    """
    Load configuration from pyproject.toml or gemini-manager.toml (or profile specific) in the current directory.
    Returns a dictionary of {arg_name: value}.

    Priority:
    1. gemini-manager-<profile>.toml (if profile is set)
    2. gemini-manager.toml ([tool.gemini] or root)
    3. pyproject.toml ([tool.gemini])
    """
    if not tomllib:
        return {}

    # 0. Profile config
    if profile:
        profile_file = f"gemini-manager-{profile}.toml"
        if os.path.exists(profile_file):
            try:
                with open(profile_file, "rb") as f:
                    data = tomllib.load(f)
                    if "tool" in data and "gm" in data["tool"]:
                        return data["tool"]["gm"]
                    return data
            except Exception:
                pass

    # 1. gemini-manager.toml
    if os.path.exists("gemini-manager.toml"):
        try:
            with open("gemini-manager.toml", "rb") as f:
                data = tomllib.load(f)
                # Check if it has [tool.gemini] or just keys
                if "tool" in data and "gm" in data["tool"]:
                    return data["tool"]["gm"]
                return data  # Assume root keys if no [tool.gemini]
        except Exception:
            pass

    # 2. pyproject.toml
    if os.path.exists("pyproject.toml"):
        try:
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
                if "tool" in data and "gm" in data["tool"]:
                    return data["tool"]["gm"]
        except Exception:
            pass

    return {}


def normalize_config_keys(config):
    """
    Normalize config keys to match argparse dest names.
    TOML uses 'backup-dir', argparse uses 'backup_dir' (or we map it).
    """
    normalized = {}
    for k, v in config.items():
        # Convert kebab-case to snake_case
        key = k.replace("-", "_")
        normalized[key] = v
    return normalized

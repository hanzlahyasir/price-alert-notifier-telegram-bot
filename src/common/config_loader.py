import os
from configparser import ConfigParser

def load_config(config_file_path=None):
    if config_file_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_file_path = os.path.join(project_root, "config.ini")

    cp = ConfigParser()
    if os.path.exists(config_file_path):
        cp.read(config_file_path)
    else:
        print(f"⚠️  Warning: config file '{config_file_path}' not found. Falling back to environment variables.")
    return cp

import configparser
import os

def load_config(config_file_path='config.ini'):
    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print(f"Project root determined as: {project_root}")

    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"Configuration file '{config_file_path}' not found. Ensure it is in the project root.")

    config = configparser.ConfigParser()
    config.read(config_file_path)
    return config

if __name__ == '__main__':
    
    test_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.ini')
    if os.path.exists(test_config_path):
        cfg = load_config(test_config_path)
        print("Telegram Bot Token:", cfg['TELEGRAM']['BOT_TOKEN'])
        print("Email Sender:", cfg['EMAIL']['SENDER_EMAIL'])
    else:
        print(f"Test config file not found at {test_config_path}. Make sure config.ini is in the project root.")
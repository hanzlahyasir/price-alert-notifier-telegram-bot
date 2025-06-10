import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from src.common.config_loader import load_config 

def send_email_alert(sender_email: str, receiver_email: str, subject: str, body: str,
                     smtp_server: str, smtp_port: int, smtp_username: str, smtp_password: str):
    
    try:
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "html")) 

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"Email alert sent to {receiver_email}: \"{subject}\"")
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email alert: {e}")
        return False


def email_sender(subject, body):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, 'config.ini')

    if os.path.exists(config_path):
        config = load_config(config_path)
        SENDER = config['EMAIL']['SENDER_EMAIL']
        RECEIVER = config['EMAIL']['RECEIVER_EMAIL']
        SMTP_SERVER = config['EMAIL']['SMTP_SERVER']
        SMTP_PORT = int(config['EMAIL']['SMTP_PORT'])
        SMTP_USER = config['EMAIL']['SMTP_USERNAME']
        SMTP_PASS = config['EMAIL']['SMTP_PASSWORD']

        
        print("Attempting to send a alert email...")
        success = send_email_alert(SENDER, RECEIVER, subject, body, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS)
        if success:
            print("Alert Email sent successfully, check your inbox or spam.")
        else:
                print("Failed to send test email.")
    else:
        print(f"Config file not found at {config_path} for direct test.")


if __name__ == '__main__':
    import os
    from src.common.config_loader import load_config 

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, 'config.ini')

    if os.path.exists(config_path):
        config = load_config(config_path)
        SENDER = config['EMAIL']['SENDER_EMAIL']
        RECEIVER = config['EMAIL']['RECEIVER_EMAIL']
        SMTP_SERVER = config['EMAIL']['SMTP_SERVER']
        SMTP_PORT = int(config['EMAIL']['SMTP_PORT'])
        SMTP_USER = config['EMAIL']['SMTP_USERNAME']
        SMTP_PASS = config['EMAIL']['SMTP_PASSWORD']

        if SENDER == "your_sender_email@example.com" or SMTP_PASS == "your_smtp_password_or_app_password_here":
             print("Please update config.ini with your actual Email credentials.")
        else:
            print("Attempting to send a test email...")
            subject = "Price Tracker Bot - Test Email"
            body = "<h1>Test Email</h1><p>This is a test email from your Python Price Tracker Bot.</p>"
            success = send_email_alert(SENDER, RECEIVER, subject, body, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS)
            if success:
                print("Test email sent successfully (check your inbox).")
            else:
                print("Failed to send test email.")
    else:
        print(f"Config file not found at {config_path} for direct test.")
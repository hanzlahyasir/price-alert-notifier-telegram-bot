import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email_alert(
    sender_email: str,
    receiver_email: str,
    subject: str,
    body: str,
    smtp_server: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str
):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

        print(f"✅ Email sent to {receiver_email}: “{subject}”")
        return True
    except Exception as e:
        print(f"✗ Error sending email: {e}")
        return False

def email_sender(subject: str, body: str):
    """
    In production, read all settings from environment variables:
      EMAIL_SENDER, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT,
      SMTP_USERNAME, SMTP_PASSWORD
    Fall back to config.ini only if env var is missing (dev).
    """
    # 1) Try env vars first
    SENDER   = os.getenv("EMAIL_SENDER")
    RECEIVER = os.getenv("EMAIL_RECEIVER")
    SERVER   = os.getenv("SMTP_SERVER")
    PORT     = os.getenv("SMTP_PORT")
    USER     = os.getenv("SMTP_USERNAME")
    PASSWD   = os.getenv("SMTP_PASSWORD")

    # 2) If any are missing, fall back to config.ini for local dev
    if not all([SENDER, RECEIVER, SERVER, PORT, USER, PASSWD]):
        from src.common.config_loader import load_config
        cfg = load_config()  # no path → will warn if config.ini isn’t present
        try:
            SENDER   = SENDER   or cfg["EMAIL"]["SENDER_EMAIL"]
            RECEIVER = RECEIVER or cfg["EMAIL"]["RECEIVER_EMAIL"]
            SERVER   = SERVER   or cfg["EMAIL"]["SMTP_SERVER"]
            PORT     = PORT     or cfg["EMAIL"]["SMTP_PORT"]
            USER     = USER     or cfg["EMAIL"]["SMTP_USERNAME"]
            PASSWD   = PASSWD   or cfg["EMAIL"]["SMTP_PASSWORD"]
        except KeyError:
            print("⚠️  Email settings missing in environment and config.ini")
            return

    # Cast port to int
    try:
        PORT = int(PORT)
    except:
        print(f"✗ Invalid SMTP_PORT: {PORT}")
        return

    print("→ Sending alert email…")
    send_email_alert(
        SENDER, RECEIVER, subject, body,
        smtp_server=SERVER,
        smtp_port=PORT,
        smtp_username=USER,
        smtp_password=PASSWD
    )

# Optional test harness
if __name__ == "__main__":
    # Quick test message
    email_sender(
        subject="🚀 Test Alert",
        body="<h1>It Works!</h1><p>This is a test from deployed code.</p>"
    )

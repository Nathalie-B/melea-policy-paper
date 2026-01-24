import smtplib
from email.message import EmailMessage
from user_system_information import get_parent_email_for_username


#Obligations for Self-Harm Event:
def send_self_harm_alert(db_path: str, username: str, smtp_config: dict)-> str:
    notify_parent_via_email(db_path, username, smtp_config)
    return send_compassionate_message()

def send_compassionate_message() -> str:
    return "I'm really sorry to hear that you're feeling this way. " \
    "It's really important that you talk to someone who can help you, " \
    "like a mental health professional or a trusted person in your life."

def notify_parent_via_email(db_path: str, username: str, smtp_config: dict) -> None:
    parent_email = get_parent_email_for_username(db_path, username)
    if parent_email:
        _send_email(
            to_email=parent_email,
            subject="Notification",
            body=f"User '{username}' has triggered an event.",
            **smtp_config
        )

def _send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    smtp_server: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
):
    """
    Send an email via SMTP.

    Args:
        to_email: recipient email address
        subject: email subject
        body: email body (plain text)
        from_email: sender email address
        smtp_server: e.g. 'smtp.gmail.com'
        smtp_port: e.g. 587
        smtp_username: SMTP login username
        smtp_password: SMTP login password or app password
    """

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()           # encrypt connection
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
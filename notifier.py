"""Free email alerts via SMTP (e.g. a Gmail App Password — no paid service needed)."""

import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, body: str, attachments=None):
    smtp_server = os.environ["SMTP_SERVER"]
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_addr = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.set_content(body)

    for path in attachments or []:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype="image", subtype="png", filename=os.path.basename(path))

    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

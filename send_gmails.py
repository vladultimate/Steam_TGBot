import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

def send_email(subject, body, to_email):
    from_email = "######"
    password = "######"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

def process_email_input(message):
    email = message.text.strip()
    if re.match(r"[^@]+@[^@]+\.[^@]+", email):
        send_email(email)
        bot.send_message(message.chat.id, '✅ Ваш електронний лист надіслано!')
    else:
        bot.send_message(message.chat.id, '❌ Будь ласка, введіть дійсну електронну пошту.')
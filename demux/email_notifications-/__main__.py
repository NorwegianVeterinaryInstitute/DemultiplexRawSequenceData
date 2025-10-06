# demultiplex/email_notifications/__main__.py
from .notifier import send_notification

if __name__ == "__main__":
    send_notification("test@example.com", "Subject", "Body")

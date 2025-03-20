import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables (EMAIL_SENDER, EMAIL_PASSWORD, etc.)

# Get environment variables for SMTP
EMAIL_SENDER = os.getenv("MAIL_USERNAME")  # example: no-reply@company.com
EMAIL_PASSWORD = os.getenv("MAIL_PASSWORD")  # email password
SMTP_SERVER = os.getenv("MAIL_HOST")  # example: smtp.company.com
SMTP_PORT = int(587)  # SSL port: 465
SMTP_USE_SSL = os.getenv("MAIL_ENCRYPTION", "ssl").lower() == "ssl"

# Target email (company CS team) - customize as needed
COMPANY_EMAIL = os.getenv("MAIL_FROM_ADDRESS", "cs@company.com")


# Add better error handling and diagnostic information
def send_email(
    transcript: str, user_email: str, user_phone: str, html_transcript: str = None
):
    """
    Send an email containing conversation transcript + user contact info
    to COMPANY_EMAIL (set in environment).

    Args:
        transcript: Plain text transcript
        user_email: User's email address
        user_phone: User's phone number
        html_transcript: HTML formatted transcript (optional)
    """
    # Validate parameters
    if not transcript or not user_email or not user_phone:
        error_msg = "Missing required parameters for email"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Log SMTP settings for debugging (remove sensitive info in production)
    logger.info(f"Sending email using SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
    logger.info(f"Using SSL: {SMTP_USE_SSL}")
    logger.info(f"From: {EMAIL_SENDER}, To: {COMPANY_EMAIL}")

    # Validate SMTP settings
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT]):
        error_msg = "Missing SMTP configuration settings"
        logger.error(error_msg)
        raise ValueError(error_msg)

    subject = "Chat Transcript - Layanan Chatbot GITA"

    # Create message container
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_SENDER
    msg["To"] = COMPANY_EMAIL
    msg["Subject"] = subject

    # Create plain text version
    plain_body = (
        f"User Email   : {user_email}\n"
        f"User Phone   : {user_phone}\n"
        f"{'-'*40}\n\n"
        f"{transcript}"
    )

    # Attach plain text part
    msg.attach(MIMEText(plain_body, "plain"))

    # Attach HTML part if provided
    if html_transcript:
        # Create HTML version with basic styling
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
                .header {{ background-color: #007bff; color: white; padding: 15px; border-radius: 5px; }}
                .user-info {{ background-color: #f8f9fa; padding: 15px; margin: 20px 0; border-left: 5px solid #007bff; }}
                .transcript {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
                .user-message {{ background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                .bot-message {{ background-color: #f1f8e9; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>GITA Chatbot Transcript</h2>
            </div>
            <div class="user-info">
                <p><strong>User Email:</strong> {user_email}</p>
                <p><strong>User Phone:</strong> {user_phone}</p>
            </div>
            <div class="transcript">
                {html_transcript}
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_USE_SSL:
            logger.info("Establishing SSL connection...")
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        else:
            logger.info("Establishing standard connection...")
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
            server.starttls()  # Use TLS for security

        logger.info("Logging in to SMTP server...")
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        logger.info("Sending email...")
        server.send_message(msg)
        logger.info("Email sent successfully!")
        server.quit()

        logger.info(f"Transcript successfully sent to company email: {COMPANY_EMAIL}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Authentication failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

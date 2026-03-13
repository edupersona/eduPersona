"""
SMTP mail service for edupersona
Simplified version adapted from alarm app for sending notifications
"""
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import smtplib

from ng_loba.utils import logger
from services.settings import config


def _get_smtp_config() -> tuple[str, int, bool]:
    """Get SMTP configuration from settings"""
    smtp_server = config.get('smtp_server', 'localhost')
    smtp_port = config.get('smtp_port', 25)
    suppress_mail = config.get('suppress_mail', config.DTAP != 'prod')      # note, dev:25 not available
    return smtp_server, smtp_port, suppress_mail


def sendmail_sync(from_address: str, recipients: list | str, subject: str, body: str) -> bool:
    """Send email synchronously via SMTP

    Args:
        from_address: Sender email address
        recipients: Single email or list of email addresses
        subject: Email subject
        body: Email body (plain text)

    Returns:
        True if successful, False otherwise
    """
    smtp_server, smtp_port, suppress_mail = _get_smtp_config()

    logger.info(f"Sending email from {from_address} to {recipients}")

    if isinstance(recipients, str):
        recipients = [recipients]

    if suppress_mail:
        logger.info(f"Mail suppressed (DTAP={config.DTAP}), would send: {subject}")
        logger.debug(f"Body: {body}")
        return True

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            logger.debug(f"Connected to SMTP server {smtp_server}:{smtp_port}")

            for recipient in recipients:
                msg = MIMEMultipart()
                msg['From'] = from_address
                msg['To'] = recipient
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain'))

                try:
                    logger.info(f"Sending email to {recipient}")
                    server.sendmail(from_address, recipient, msg.as_string())
                except Exception as e:
                    logger.error(f"Failed to send email to {recipient}: {e}")
                    return False

            return True

    except Exception as e:
        logger.error(f"Failed to connect to SMTP server {smtp_server}:{smtp_port}: {e}")
        return False


async def sendmail_async(from_address: str, recipients: list | str, subject: str, body: str) -> bool:
    """Send email asynchronously via SMTP

    Args:
        from_address: Sender email address
        recipients: Single email or list of email addresses
        subject: Email subject
        body: Email body (plain text)

    Returns:
        True if successful, False otherwise
    """
    smtp_server, smtp_port, suppress_mail = _get_smtp_config()

    logger.info(f"Sending email from {from_address} to {recipients}")

    if isinstance(recipients, str):
        recipients = [recipients]

    if suppress_mail:
        logger.info(f"Mail suppressed (DTAP={config.DTAP}), would send: {subject}")
        logger.debug(f"Body: {body}")
        return True

    try:
        connection = aiosmtplib.SMTP(hostname=smtp_server, port=smtp_port)
        await connection.connect()
        logger.debug(f"Connected to SMTP server {smtp_server}:{smtp_port}")

        # Create the email message
        msg = MIMEMultipart()
        msg['From'] = from_address
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Send the email to all recipients
        await connection.sendmail(from_address, recipients, msg.as_string())
        await connection.quit()

        logger.info(f"Email successfully sent to {recipients}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {recipients}: {e}")
        return False

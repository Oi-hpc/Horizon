"""Email service for handling subscriptions and sending summaries."""

import email
import html
import imaplib
import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import List

try:
    import markdown
except ImportError:
    markdown = None

from ..models import EmailConfig

logger = logging.getLogger(__name__)


_ITEM_ANCHOR_RE = re.compile(r'<a id="(item-\d+)"></a>')
_DETAILS_RE = re.compile(
    r"<details><summary>(?P<title>.*?)</summary>\s*"
    r"<ul>\s*(?P<items>.*?)\s*</ul>\s*</details>",
    re.DOTALL,
)
_DETAILS_LINK_RE = re.compile(
    r'<li><a href="(?P<url>[^"]+)">(?P<title>.*?)</a></li>',
    re.DOTALL,
)
_EMAIL_ANCHOR_PARAGRAPH_RE = re.compile(
    r'<p>\s*<a id="(?P<anchor_id>item-\d+)" '
    r'name="(?P=anchor_id)"></a>\s*</p>\s*'
    r'(?P<heading><h[1-6][^>]*>)',
    re.IGNORECASE,
)
_EMAIL_ANCHOR_INLINE_RE = re.compile(
    r'<a id="(?P<anchor_id>item-\d+)" '
    r'name="(?P=anchor_id)"></a>\s*'
    r'(?P<heading><h[1-6][^>]*>)',
    re.IGNORECASE,
)


def _email_anchor_target(anchor_id: str) -> str:
    """Render a non-empty item anchor target for stricter email clients."""
    return (
        f'<a id="{anchor_id}" name="{anchor_id}" '
        'style="display:block;height:1px;line-height:1px;font-size:1px;'
        'overflow:hidden;color:transparent;text-decoration:none;">&#8203;</a>'
    )


def _details_to_markdown(match: re.Match) -> str:
    """Convert renderer-generated details blocks to email-safe Markdown."""
    title = html.unescape(match.group("title")).strip()
    lines = []
    for link in _DETAILS_LINK_RE.finditer(match.group("items")):
        link_title = html.unescape(link.group("title")).strip()
        url = link.group("url").strip()
        if link_title and url:
            lines.append(f"- [{link_title}]({url})")
    if not lines:
        return ""
    return f"**{title}**\n\n" + "\n".join(lines)


def _prepare_markdown_for_email(summary_md: str) -> str:
    """Escape arbitrary raw HTML while keeping Horizon item anchors usable."""
    prepared = _DETAILS_RE.sub(_details_to_markdown, summary_md)
    anchors: dict[str, str] = {}

    def protect_anchor(match: re.Match) -> str:
        token = f"@@HORIZON_EMAIL_ANCHOR_{len(anchors)}@@"
        anchor_id = match.group(1)
        anchors[token] = f'<a id="{anchor_id}" name="{anchor_id}"></a>'
        return token

    prepared = _ITEM_ANCHOR_RE.sub(protect_anchor, prepared)
    prepared = prepared.replace("<", "&lt;")
    for token, anchor in anchors.items():
        prepared = prepared.replace(token, anchor)
    return prepared


def _stabilize_email_anchors(html_content: str) -> str:
    """Move item anchors into headings and make them non-empty.

    Some desktop email clients ignore empty anchors, especially when Markdown
    wraps them in their own paragraph. Keeping the target inside the heading
    makes in-message TOC links work in more clients.
    """

    def replace(match: re.Match) -> str:
        anchor_id = match.group("anchor_id")
        heading = match.group("heading")
        return f"{heading}{_email_anchor_target(anchor_id)}"

    html_content = _EMAIL_ANCHOR_PARAGRAPH_RE.sub(replace, html_content)
    return _EMAIL_ANCHOR_INLINE_RE.sub(replace, html_content)


class EmailManager:
    """Manages email subscriptions and sending summaries."""

    def __init__(self, config: EmailConfig, console=None):
        self.config = config
        self.pwd = os.getenv(self.config.password_env)
        if console is None:
            try:
                from rich.console import Console

                self.console = Console()
            except ImportError:

                class DummyConsole:
                    def print(self, *args, **kwargs):
                        print(*args, **kwargs)

                self.console = DummyConsole()
        else:
            self.console = console

        if not self.pwd and self.config.enabled:
            logger.warning(
                f"Environment variable {self.config.password_env} not set. Email features may fail."
            )
            self.console.print(
                f"[yellow]Warning: Environment variable {self.config.password_env} not set. Email features may fail.[/yellow]"
            )

    def check_subscriptions(self, storage_manager):
        """Checks inbox for subscription requests and updates subscriber list."""
        if not self.config.enabled or not self.config.imap_enabled:
            return

        try:
            mail = imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port)
            mail.login(self.config.email_address, self.pwd)
            mail.select("INBOX")

            keyword = self.config.subscribe_keyword
            search_crit = f'(UNSEEN SUBJECT "{keyword}")'

            status, messages = mail.search(None, search_crit)

            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                subscribers = storage_manager.load_subscribers()

                for e_id in email_ids:
                    _, msg_data = mail.fetch(e_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])

                            subject = str(msg.get("Subject") or "").strip()
                            if subject.upper() != keyword.upper():
                                continue

                            sender = msg.get("From")

                            if sender:
                                _, email_addr = parseaddr(sender)
                                if email_addr and "@" in email_addr:
                                    if (
                                        "noreply" in email_addr.lower()
                                        or "no-reply" in email_addr.lower()
                                    ):
                                        continue

                                    if email_addr not in subscribers:
                                        storage_manager.add_subscriber(email_addr)
                                        subscribers = storage_manager.load_subscribers()
                                        self._send_reply(
                                            email_addr,
                                            "Subscribed to Horizon",
                                            "You have been successfully subscribed to Horizon daily summaries.",
                                        )
                                        logger.info(f"Added subscriber: {email_addr}")
                                    else:
                                        logger.info(f"Already subscribed: {email_addr}")

            unsub_keyword = self.config.unsubscribe_keyword
            search_crit_unsub = f'(UNSEEN SUBJECT "{unsub_keyword}")'

            status, messages = mail.search(None, search_crit_unsub)

            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                subscribers = storage_manager.load_subscribers()

                for e_id in email_ids:
                    _, msg_data = mail.fetch(e_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])

                            subject = str(msg.get("Subject") or "").strip()
                            if subject.upper() != unsub_keyword.upper():
                                continue

                            sender = msg.get("From")

                            if sender:
                                _, email_addr = parseaddr(sender)
                                if email_addr and "@" in email_addr:
                                    if (
                                        "noreply" in email_addr.lower()
                                        or "no-reply" in email_addr.lower()
                                    ):
                                        continue

                                    if email_addr in subscribers:
                                        storage_manager.remove_subscriber(email_addr)
                                        subscribers = storage_manager.load_subscribers()
                                        self._send_reply(
                                            email_addr,
                                            "Unsubscribed from Horizon",
                                            "You have been successfully unsubscribed from Horizon daily summaries.",
                                        )
                                        logger.info(f"Removed subscriber: {email_addr}")
                                    else:
                                        logger.info(f"Not subscribed: {email_addr}")

            mail.close()
            mail.logout()

        except Exception as e:
            logger.error(f"Error checking subscriptions: {e}")

    def send_daily_summary(self, summary_md: str, subject: str, subscribers: List[str]):
        """Sends the daily summary to all subscribers."""
        if not self.config.enabled or not subscribers:
            return

        safe_summary_md = _prepare_markdown_for_email(summary_md)
        html_content = (
            _stabilize_email_anchors(markdown.markdown(safe_summary_md))
            if markdown
            else f"<pre>{html.escape(summary_md)}</pre>"
        )

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
                h1, h2, h3 {{ color: #2c3e50; }}
                code {{ background-color: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; }}
                pre {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                blockquote {{ border-left: 4px solid #ddd; padding-left: 15px; color: #777; }}
                .footer {{ margin-top: 40px; font-size: 12px; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
            </style>
        </head>
        <body>
            {html_content}
            <div class="footer">
                <p>Sent by {self.config.sender_name}</p>
                <p>To unsubscribe, please reply with "{self.config.unsubscribe_keyword}"</p>
            </div>
        </body>
        </html>
        """

        try:
            with smtplib.SMTP_SSL(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.login(
                    self.config.smtp_username or self.config.email_address, self.pwd
                )

                for subscriber in subscribers:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = (
                        f"{self.config.sender_name} <{self.config.email_address}>"
                    )
                    msg["To"] = subscriber

                    text_part = MIMEText(summary_md, "plain")
                    html_part = MIMEText(html_body, "html")

                    msg.attach(text_part)
                    msg.attach(html_part)

                    try:
                        server.send_message(msg)
                        logger.info(f"Sent summary to {subscriber}")
                    except Exception as e:
                        logger.error(f"Failed to send to {subscriber}: {e}")

        except Exception as e:
            logger.error(f"SMTP Error: {e}")

    def _send_reply(self, to_email: str, subject: str, body: str):
        """Helper to send a simple reply."""
        try:
            with smtplib.SMTP_SSL(
                self.config.smtp_server, self.config.smtp_port
            ) as server:
                server.login(
                    self.config.smtp_username or self.config.email_address, self.pwd
                )

                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = f"{self.config.sender_name} <{self.config.email_address}>"
                msg["To"] = to_email

                server.send_message(msg)
        except Exception as e:
            logger.error(f"Failed to send reply to {to_email}: {e}")

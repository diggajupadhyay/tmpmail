#!/usr/bin/env python3
"""
tmpmail - A temporary email right from your terminal

A command line utility that allows you to create a temporary email address
and receive emails. It uses 1secmail's API to receive emails.
"""

import argparse
import os
import random
import re
import string
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

VERSION = "1.2.3"
API_URL = "https://api.mail.tm/"

# Default browser for rendering HTML emails
DEFAULT_BROWSER = "w3m"

# Default command for copying to clipboard
DEFAULT_CLIPBOARD_CMD = "xclip -selection c"

# Headers for API requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class TmpMail:
    """Main class for tmpmail functionality."""

    def __init__(self):
        self.tmpmail_dir = Path(tempfile.gettempdir()) / "tmpmail"
        self.email_file = self.tmpmail_dir / "email_address"
        self.password_file = self.tmpmail_dir / "password"
        self.token_file = self.tmpmail_dir / "token"
        self.html_file = self.tmpmail_dir / "tmpmail.html"
        self.browser = DEFAULT_BROWSER
        self.clipboard_cmd = DEFAULT_CLIPBOARD_CMD
        self.raw_text = False
        self.email_address = None
        self.username = None
        self.domain = None
        self.password = None
        self.token = None

        # Create tmpmail directory if it doesn't exist
        self.tmpmail_dir.mkdir(parents=True, exist_ok=True)

    def _get_token(self):
        """Get or create JWT token for API authentication."""
        if self.token_file.exists() and self.token_file.stat().st_size > 0:
            self.token = self.token_file.read_text().strip()
            return self.token

        # Need to authenticate
        self.get_email_address()
        self._authenticate()
        return self.token

    def _authenticate(self):
        """Authenticate and get JWT token."""
        try:
            response = requests.post(
                f"{API_URL}token",
                json={"address": self.email_address, "password": self.password},
                headers=HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            self.token = data.get("token")
            if self.token:
                self.token_file.write_text(self.token)
        except requests.RequestException as e:
            print(f"Error authenticating: {e}", file=sys.stderr)
            sys.exit(1)

    def get_email_address(self):
        """Get or generate email address."""
        if not self.email_file.exists() or self.email_file.stat().st_size == 0:
            self.generate_email_address()

        self.email_address = self.email_file.read_text().strip()
        self.username = self.email_address.split("@")[0]
        self.domain = self.email_address.split("@")[1]

        # Load password if exists
        if self.password_file.exists():
            self.password = self.password_file.read_text().strip()

        return self.email_address

    def get_domains(self):
        """Get list of available domains from mail.tm API."""
        try:
            response = requests.get(f"{API_URL}domains", headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            domains = [d.get("domain") for d in data.get("hydra:member", [])]
            if not domains:
                print("Error: mail.tm API error for getting domains list", file=sys.stderr)
                sys.exit(1)
            return domains
        except requests.RequestException as e:
            print(f"Error fetching domains: {e}", file=sys.stderr)
            sys.exit(1)

    def generate_email_address(self, custom_address=None):
        """Generate a random or custom email address."""
        blacklisted = ["abuse", "webmaster", "contact", "postmaster", "hostmaster", "admin"]
        domains = self.get_domains()
        domain_regex = "|".join(re.escape(d) for d in domains)
        valid_email_regex = re.compile(rf"^[a-z0-9]+@({domain_regex})$")
        blacklisted_regex = re.compile(rf"^({'|'.join(blacklisted)})$")

        # Generate random password
        self.password = "".join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=16))

        if custom_address:
            email_address = custom_address
            username = email_address.split("@")[0]

            if blacklisted_regex.match(username):
                print(
                    f"Error: For security reasons, that username cannot be used. "
                    f"Blacklisted: {', '.join(blacklisted)}",
                    file=sys.stderr,
                )
                sys.exit(1)

            if not valid_email_regex.match(email_address):
                print(f"Error: Provided email is invalid. Must match pattern: [a-z0-9]+@({domain_regex})", file=sys.stderr)
                sys.exit(1)
        else:
            # Generate random username
            username = "".join(random.choices(string.ascii_lowercase + string.digits, k=11))
            domain = random.choice(domains)
            email_address = f"{username}@{domain}"

        # Create account on mail.tm
        try:
            response = requests.post(
                f"{API_URL}accounts",
                json={"address": email_address, "password": self.password},
                headers=HEADERS,
                timeout=10,
            )
            if response.status_code not in [200, 201]:
                print(f"Error creating account: {response.text}", file=sys.stderr)
                sys.exit(1)
        except requests.RequestException as e:
            print(f"Error creating account: {e}", file=sys.stderr)
            sys.exit(1)

        self.email_file.write_text(email_address)
        self.password_file.write_text(self.password)
        return email_address

    def list_emails(self):
        """List all received emails."""
        self.get_email_address()
        self._get_token()

        try:
            headers = HEADERS.copy()
            headers["Authorization"] = f"Bearer {self.token}"
            response = requests.get(
                f"{API_URL}messages",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            emails = data.get("hydra:member", [])
        except requests.RequestException as e:
            print(f"Error fetching emails: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"[ Inbox for {self.email_address} ]\n")

        if not emails:
            print("No new mail")
            return

        # Print emails in a formatted table
        print(f"{'ID':<40} {'From':<40} {'Subject'}")
        print("-" * 100)
        for email in emails:
            email_id = email.get("id", "")
            from_addr = email.get("from", {}).get("address", "") if isinstance(email.get("from"), dict) else ""
            subject = email.get("subject", "")
            # Truncate long fields for display
            from_addr = from_addr[:38] + ".." if len(from_addr) > 40 else from_addr
            subject = subject[:50] + ".." if len(subject) > 50 else subject
            print(f"{email_id:<40} {from_addr:<40} {subject}")

    def view_email(self, email_id):
        """View a specific email by ID."""
        self.get_email_address()
        self._get_token()

        try:
            headers = HEADERS.copy()
            headers["Authorization"] = f"Bearer {self.token}"
            response = requests.get(
                f"{API_URL}messages/{email_id}",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error fetching email: {e}", file=sys.stderr)
            sys.exit(1)

        if not data.get("id"):
            print("Error: Message not found", file=sys.stderr)
            sys.exit(1)

        from_dict = data.get("from", {})
        from_addr = from_dict.get("address", "") if isinstance(from_dict, dict) else ""
        subject = data.get("subject", "")
        html_body = data.get("html", "")
        text_body = data.get("text", "")
        attachments = data.get("attachments", [])

        # Use textBody if htmlBody is empty
        if not html_body:
            html_body = f"<pre>{text_body}</pre>"

        # Build HTML content
        html_content = f"""<pre><b>To: </b>{self.email_address}
<b>From: </b>{from_addr}
<b>Subject: </b>{subject}</pre>
{html_body}
"""

        # Handle attachments
        if attachments:
            html_content += "<br><b>[Attachments]</b><br>"
            for attachment in attachments:
                filename = attachment.get("name", "") if isinstance(attachment, dict) else str(attachment)
                download_url = f"{API_URL}messages/{email_id}/html"

                if self.raw_text:
                    html_content += f"{download_url}  [{filename}]<br>"
                else:
                    html_content += f'<a href="{download_url}" download="{filename}">{filename}</a><br>'

        # Save to file
        self.html_file.write_text(html_content)

        if self.raw_text:
            # Convert HTML to text using w3m or beautifulsoup
            self._print_text_version()
        else:
            # Open with browser
            try:
                subprocess.run([self.browser, str(self.html_file)], check=True)
            except FileNotFoundError:
                print(f"Error: Browser '{self.browser}' not found", file=sys.stderr)
                sys.exit(1)
            except subprocess.CalledProcessError as e:
                print(f"Error opening browser: {e}", file=sys.stderr)
                sys.exit(1)

    def _print_text_version(self):
        """Print text version of email using w3m -dump or BeautifulSoup."""
        try:
            result = subprocess.run(
                ["w3m", "-dump", str(self.html_file)],
                capture_output=True,
                text=True,
                check=True,
            )
            print(result.stdout)
        except FileNotFoundError:
            # Fallback to BeautifulSoup if w3m is not available
            soup = BeautifulSoup(self.html_file.read_text(), "html.parser")
            print(soup.get_text())
        except subprocess.CalledProcessError as e:
            print(f"Error converting to text: {e}", file=sys.stderr)
            sys.exit(1)

    def view_recent_email(self):
        """View the most recent email."""
        self.get_email_address()
        self._get_token()

        try:
            headers = HEADERS.copy()
            headers["Authorization"] = f"Bearer {self.token}"
            response = requests.get(
                f"{API_URL}messages",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            emails = data.get("hydra:member", [])
        except requests.RequestException as e:
            print(f"Error fetching emails: {e}", file=sys.stderr)
            sys.exit(1)

        if not emails:
            print("No new mail")
            return

        # Get the most recent email (first in the list)
        recent_email_id = emails[0].get("id")
        self.view_email(recent_email_id)

    def copy_to_clipboard(self):
        """Copy email address to clipboard."""
        self.get_email_address()

        try:
            # Parse the clipboard command
            cmd_parts = self.clipboard_cmd.split()
            process = subprocess.Popen(
                cmd_parts,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            process.communicate(input=self.email_address.encode())
            print(f"Email address '{self.email_address}' copied to clipboard")
        except FileNotFoundError:
            print(f"Error: Clipboard command '{self.clipboard_cmd}' not found", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error copying to clipboard: {e}", file=sys.stderr)
            sys.exit(1)

    def show_domains(self):
        """Show list of available domains."""
        domains = self.get_domains()
        print("List of available domains:")
        for domain in domains:
            print(f"  - {domain}")


def check_dependencies(browser, clipboard_cmd):
    """Check if required dependencies are installed."""
    missing = []

    # Check for w3m (or custom browser)
    if not check_command(browser):
        missing.append(browser)

    # Check for clipboard command
    clipboard_base = clipboard_cmd.split()[0]
    if not check_command(clipboard_base):
        missing.append(clipboard_base)

    if missing:
        print(f"Error: Could not find the following dependencies: {' '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def check_command(cmd):
    """Check if a command exists."""
    return subprocess.run(
        ["which", cmd],
        capture_output=True,
        check=False,
    ).returncode == 0


def main():
    """Main entry point for tmpmail."""
    parser = argparse.ArgumentParser(
        prog="tmpmail",
        description="A temporary email right from your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tmpmail --generate              Create random email
  tmpmail -g myemail@domain.com   Create custom email
  tmpmail                         View the inbox
  tmpmail 12345                   View email by ID
  tmpmail -r                      View most recent email
  tmpmail -t 12345                View email as raw text
  tmpmail -c                      Copy email address to clipboard
  tmpmail -d                      Show available domains
        """,
    )

    parser.add_argument(
        "-g",
        "--generate",
        nargs="?",
        const="__random__",
        metavar="ADDRESS",
        help="Generate a new email address, either randomly or with specified ADDRESS",
    )
    parser.add_argument(
        "-b",
        "--browser",
        metavar="BROWSER",
        default=DEFAULT_BROWSER,
        help=f"Specify browser to render HTML (default: {DEFAULT_BROWSER})",
    )
    parser.add_argument(
        "-t",
        "--text",
        action="store_true",
        help="View email as raw text (remove HTML tags)",
    )
    parser.add_argument(
        "-r",
        "--recent",
        action="store_true",
        help="View the most recent email message",
    )
    parser.add_argument(
        "-c",
        "--copy",
        action="store_true",
        help="Copy the email address to clipboard",
    )
    parser.add_argument(
        "-d",
        "--domains",
        action="store_true",
        help="Show list of available domains",
    )
    parser.add_argument(
        "--clipboard-cmd",
        metavar="COMMAND",
        default=DEFAULT_CLIPBOARD_CMD,
        help=f"Command for copying to clipboard (default: {DEFAULT_CLIPBOARD_CMD})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "email_id",
        nargs="?",
        metavar="ID",
        help="View email message with specified ID",
    )

    args = parser.parse_args()

    tmpmail = TmpMail()
    tmpmail.browser = args.browser
    tmpmail.clipboard_cmd = args.clipboard_cmd
    tmpmail.raw_text = args.text

    # Handle --domains and --version first (don't require dependencies)
    if args.domains:
        tmpmail.show_domains()
        sys.exit(0)

    # Handle --generate (don't require browser/clipboard dependencies)
    if args.generate is not None:
        if args.generate == "__random__":
            email = tmpmail.generate_email_address()
        else:
            email = tmpmail.generate_email_address(args.generate)
        print(email)
        sys.exit(0)

    # For other operations, check dependencies as needed
    # Check dependencies for operations that need them
    if args.recent or args.email_id:
        check_dependencies(args.browser, args.clipboard_cmd)

    # Handle --copy
    if args.copy:
        check_dependencies(args.browser, args.clipboard_cmd)
        tmpmail.copy_to_clipboard()
        sys.exit(0)

    # Handle --recent
    if args.recent:
        tmpmail.view_recent_email()
        sys.exit(0)

    # Handle email ID argument
    if args.email_id:
        tmpmail.view_email(args.email_id)
        sys.exit(0)

    # Default: list emails (no dependencies needed)
    tmpmail.list_emails()


if __name__ == "__main__":
    main()

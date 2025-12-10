import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional


# -------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------

URL_TO_SCRAPE = "https://ipocentral.in/ipo-discussion/"

# Will use env vars if present (for GitHub Actions),
# otherwise ask interactively (for local testing)
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or input("Sender email: ")).strip()
SENDER_PASSWORD = (os.getenv("SENDER_PASSWORD") or input("Email password/App Password: ")).strip()

raw_receivers = (
    os.getenv("RECIPIENT_EMAILS")
    or input("Recipient emails (comma separated): ")
)
RECIPIENT_EMAILS = [r.strip() for r in raw_receivers.split(",") if r.strip()]

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# -------------------------------------------------------
# GMP TABLE PARSER
# -------------------------------------------------------

def parse_gmp_rows(rows) -> Dict[str, List[dict]]:
    """
    Parse a sequence of <tr> elements like the one you pasted into:
    {
      "Mainboard IPO": [ {row}, ... ],
      "SME IPO": [ {row}, ... ]
    }
    """
    sections: Dict[str, List[dict]] = {}
    current_section: Optional[str] = None

    for row in rows:
        # Header row (Mainboard IPO / SME IPO)
        th_cells = row.find_all("th")
        if th_cells:
            header_text = th_cells[0].get_text(strip=True)
            if header_text:  # e.g. "Mainboard IPO" or "SME IPO"
                current_section = header_text
                sections.setdefault(current_section, [])
            continue

        # Data row
        td_cells = row.find_all("td")
        if not td_cells or current_section is None:
            continue

        # Column 1: IPO name + bidding window in brackets
        first_td = td_cells[0]
        # Example: "ICICI Prudential AMC\n(12 - 16 Dec)"
        parts = list(first_td.stripped_strings)
        name = parts[0] if parts else ""
        window = parts[1] if len(parts) > 1 else ""

        price = td_cells[1].get_text(strip=True)       # Price*
        gmp = td_cells[2].get_text(strip=True)         # IPO GMP
        gmp_pct = td_cells[3].get_text(strip=True)     # GMP %
        subject_to = td_cells[4].get_text(strip=True)  # Subject to

        row_data = {
            "section": current_section,
            "name": name,
            "window": window,
            "price": price,
            "gmp": gmp,
            "gmp_percent": gmp_pct,
            "subject_to": subject_to,
        }

        sections[current_section].append(row_data)

    return sections


# -------------------------------------------------------
# SCRAPER
# -------------------------------------------------------

def scrape_site() -> str:
    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://ipocentral.in/",
        "Connection": "keep-alive",
    }

    response = session.get(URL_TO_SCRAPE, headers=headers, timeout=20)

    if response.status_code == 403:
        print("Got 403 Forbidden from the server.")
        return (
            "<p>Scraping blocked by the website (HTTP 403 Forbidden). "
            "They may be blocking bots / scripts.</p>"
        )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Grab ALL table rows on the page from any table
    rows = soup.select("table tr")

    # Parse into structured sections
    sections = parse_gmp_rows(rows)

    if not sections:
        return "<p>No GMP table data could be parsed from the page.</p>"

    # Build an HTML body with tables
    html: List[str] = []
    html.append("<html><body>")
    html.append("<h2>IPO GMP Summary</h2>")
    # html.append(
    #     f"<p>Source: <a href='{URL_TO_SCRAPE}'>{URL_TO_SCRAPE}</a></p>"
    # )

    for section_name, ipos in sections.items():
        html.append(f"<h3>{section_name}</h3>")

        if not ipos:
            html.append("<p>No rows</p>")
            continue

        # Table header
        html.append("""
        <table border="1" cellpadding="6" cellspacing="0"
               style="border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px;">
            <tr style="background-color:#f2f2f2; font-weight:bold;">
                <th>IPO Name</th>
                <th>Bidding Window</th>
                <th>Price</th>
                <th>GMP</th>
                <th>GMP %</th>
                <th>Subject To</th>
            </tr>
        """)

        # Table rows
        for ipo in ipos:
            html.append(f"""
            <tr>
                <td>{ipo['name']}</td>
                <td>{ipo['window']}</td>
                <td>{ipo['price']}</td>
                <td>{ipo['gmp']}</td>
                <td>{ipo['gmp_percent']}</td>
                <td>{ipo['subject_to']}</td>
            </tr>
            """)

        html.append("</table><br/>")

    html.append("</body></html>")

    return "\n".join(html)


# -------------------------------------------------------
# EMAIL SENDER
# -------------------------------------------------------

def send_email(subject: str, body_html: str):
    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENT_EMAILS)
    msg["Subject"] = subject

    # Optional: plain-text fallback (very simple)
    plain_fallback = "Your email client does not support HTML. Please open in a modern email app."
    msg.attach(MIMEText(plain_fallback, "plain"))

    # HTML part with table
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, msg.as_string())


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------

def main():
    print("Scraping site...")
    content_html = scrape_site()
    print("Scrape OK, sending email...")

    send_email("Daily IPO GMP Summary", content_html)
    print("Email sent to:")
    for r in RECIPIENT_EMAILS:
        print(" -", r)


if __name__ == "__main__":
    main()

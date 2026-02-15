import argparse
import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


def _hostname_from_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    # allow WP_BASE_URL without scheme
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    host = p.netloc or p.path
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _today_human() -> str:
    s = date.today().strftime("%d %B %Y")
    return s[1:] if s.startswith("0") else s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=".env", help="Path to the .env file for this site")
    ap.add_argument("--out", default="drafts_legal", help="Output directory for draft JSONs")
    args = ap.parse_args()

    # Load site-specific env
    load_dotenv(dotenv_path=args.env, override=True)

    city = os.getenv("CITY", "").strip()
    wp_base = os.getenv("WP_BASE_URL", "").strip()
    domain = _hostname_from_url(wp_base) or "example.com"

    # Optional env overrides (nice to add, but not required)
    site_name = (os.getenv("SITE_NAME") or "").strip() or (f"Apartments in {city}" if city else domain)
    contact_email = (os.getenv("CONTACT_EMAIL") or "").strip() or f"contact@{domain}"
    last_updated = (os.getenv("LEGAL_LAST_UPDATED") or "").strip() or _today_human()

    site_key = (os.getenv("SITE_KEY") or "").strip() or "site"
    default_lang = (os.getenv("DEFAULT_LANGUAGE") or "").strip() or "en"

    out_dir = Path(args.out) / site_key / default_lang
    out_dir.mkdir(parents=True, exist_ok=True)


    # Add <!-- AB:CTA --> as a comment so publish_wp.py doesn't warn about missing markers.
    privacy_html = f"""<h2>Overview</h2>
<p>This Privacy Policy explains how <strong>{site_name}</strong> (“we”, “us”) handles personal data when you use <strong>{domain}</strong>.</p>
<p><strong>Last updated:</strong> {last_updated}</p>

<h2>Who we are</h2>
<p><strong>Site:</strong> {domain}<br>
<strong>Contact:</strong> {contact_email}</p>

<h2>What data we collect</h2>
<ul>
  <li><strong>Messages you send us:</strong> if you email us, we receive your email address and the contents of your message.</li>
  <li><strong>Basic technical data:</strong> IP address, device/browser info, pages visited, and referral source (typical server and analytics data).</li>
  <li><strong>Cookies:</strong> used for site functionality and, if enabled, analytics.</li>
</ul>

<h2>How we use your data</h2>
<ul>
  <li>To respond to messages and support requests.</li>
  <li>To operate, maintain, and improve the site (performance, debugging, security).</li>
  <li>To understand what content is useful (site analytics, if enabled).</li>
</ul>

<h2>Affiliate links and referrals</h2>
<p>Some pages include links to third-party services. If you click those links, the third party may set cookies or collect data under their own policies. We may earn a commission if you complete a purchase or booking after clicking a link.</p>

<h2>Cookies</h2>
<p>You can control cookies via your browser settings. If a cookie banner/consent tool is enabled, you can manage preferences there.</p>

<h2>Data retention</h2>
<p>We keep personal data only as long as needed for the purposes above. Emails you send may be retained for support and record-keeping, then deleted periodically.</p>

<h2>Your rights</h2>
<p>Depending on your location, you may have rights to access, correct, delete, or restrict processing of your personal data, and to object to certain processing. To make a request, contact us at <strong>{contact_email}</strong>.</p>

<h2>Contact</h2>
<p>Questions about privacy? Email <strong>{contact_email}</strong>.</p>

<!-- AB:CTA -->"""

    terms_html = f"""<h2>Overview</h2>
<p>These Terms and Conditions govern your use of <strong>{domain}</strong> (the “site”), operated by <strong>{site_name}</strong> (“we”, “us”). By using the site, you agree to these terms.</p>
<p><strong>Last updated:</strong> {last_updated}</p>

<h2>What this site is</h2>
<p>The site provides informational guides. We do not own or manage rental inventory and we are not an agent or broker.</p>

<h2>External links</h2>
<p>The site may link to third-party websites. We do not control those sites and are not responsible for their content, policies, or services. Your use of third-party sites is at your own risk and subject to their terms.</p>

<h2>Affiliate disclosure</h2>
<p>Some links may be affiliate links. If you click a link and later make a purchase or booking, we may earn a commission at no extra cost to you.</p>

<h2>Accuracy of information</h2>
<p>We aim to keep content up to date, but information may change. Content is provided “as is” without warranties of any kind.</p>

<h2>Acceptable use</h2>
<ul>
  <li>Do not misuse the site, attempt to disrupt it, or access it unlawfully.</li>
  <li>Do not copy, scrape, or republish substantial portions of content without permission.</li>
  <li>Do not upload or transmit malware or harmful code.</li>
</ul>

<h2>Limitation of liability</h2>
<p>To the maximum extent permitted by law, we are not liable for any loss or damage arising from your use of the site or reliance on its content, including losses resulting from third-party services you choose to use.</p>

<h2>Changes</h2>
<p>We may update the site and these terms at any time. We do not guarantee uninterrupted availability.</p>

<h2>Contact</h2>
<p>Questions about these terms? Email <strong>{contact_email}</strong>.</p>

<!-- AB:CTA -->"""

    contact_html = f"""<h2>Get in touch</h2>
<p>If you have questions, spot an error, or want to discuss a partnership, contact us:</p>
<ul>
  <li><strong>Email:</strong> <a href="mailto:{contact_email}">{contact_email}</a></li>
</ul>

<h2>What to include</h2>
<ul>
  <li>The page URL you’re referring to (if relevant)</li>
  <li>A short description of what you need</li>
  <li>Any supporting links or screenshots</li>
</ul>

<h2>Note</h2>
<p>We can’t provide legal or financial advice. For bookings, payments, and account issues, please contact the platform you booked with directly.</p>

<!-- AB:CTA -->"""

    disclaimer_html = f"""<h2>General information</h2>
<p>The content on <strong>{domain}</strong> is provided for general informational purposes only. While we try to keep information accurate and current, we make no representations or warranties about completeness, reliability, or suitability.</p>
<p><strong>Last updated:</strong> {last_updated}</p>

<h2>No professional advice</h2>
<p>Nothing on this site constitutes legal, financial, or professional advice. You should verify details independently and seek professional advice where appropriate.</p>

<h2>Affiliate links</h2>
<p>Some links on this site are affiliate links. If you click a link and later make a purchase or booking, we may receive a commission at no extra cost to you.</p>

<h2>External websites</h2>
<p>The site includes links to third-party websites. We do not control those websites and are not responsible for their content, privacy practices, or services.</p>

<h2>Limitation of liability</h2>
<p>To the maximum extent permitted by law, we are not liable for any loss or damage arising from your use of the site, reliance on its content, or your interactions with third-party services.</p>

<h2>Contact</h2>
<p>If you have questions about this disclaimer, email <strong>{contact_email}</strong>.</p>

<!-- AB:CTA -->"""

    drafts = [
        {
            "slug": "privacy-policy",
            "title": "Privacy Policy",
            "meta_description": f"How {site_name} collects and uses data, cookies, analytics, affiliate links, and how to contact us.",
            "primary_key_word": "privacy policy",
            "html": privacy_html,
        },
        {
            "slug": "terms",
            "title": "Terms and Conditions",
            "meta_description": f"Terms for using {domain}: content, external links, acceptable use, and limitations of liability.",
            "primary_key_word": "terms and conditions",
            "html": terms_html,
        },
        {
            "slug": "contact",
            "title": "Contact",
            "meta_description": f"Contact {site_name} for questions, corrections, or partnership enquiries.",
            "primary_key_word": "contact",
            "html": contact_html,
        },
        {
            "slug": "disclaimer",
            "title": "Disclaimer",
            "meta_description": f"Important disclaimers for {domain}: informational content, affiliate links, external sites, and liability.",
            "primary_key_word": "disclaimer",
            "html": disclaimer_html,
        },
    ]

    for d in drafts:
        path = out_dir / f"{d['slug']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(drafts)} legal drafts to: {out_dir}")


if __name__ == "__main__":
    main()

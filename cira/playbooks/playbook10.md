# Playbook 10: Website & Infrastructure Attack

**Categories Covered:** Website Defacement, Website Hacking

---

## 1. Immediate Steps (Stop the Damage & Recover Fast)

1. **Take the website offline or put it in maintenance mode immediately** if defacement/malicious content is visible to visitors — this limits reputational damage and prevents visitors from being exposed to malicious redirects/content.
2. **Do not panic-delete or "fix" content immediately** — first take screenshots/backups of the defaced state for evidence, then proceed to remediation.
3. **Change all admin credentials** — CMS admin (WordPress/Joomla/etc.), hosting panel (cPanel/Plesk), FTP/SFTP, and database passwords — from a separate secure device.
4. **Check for backdoors/malicious files** — defacement attacks often leave hidden shells/backdoors for repeated access. Scan the file system for recently modified/added files (especially .php, .asp, .jsp files in unusual locations).
5. **Restore from a clean, known-good backup** taken **before** the attack — but only after identifying and patching the vulnerability that allowed access (otherwise the attacker can simply re-exploit it).
6. **Update all software/plugins/CMS core** to the latest patched versions — most defacements exploit known, unpatched vulnerabilities.
7. **Contact your hosting provider immediately** — they can help identify the attack vector via server logs and may have built-in malware scanning/cleanup tools.
8. **Check if your site has been blacklisted** by Google Safe Browsing or other security services post-attack, and request a review once cleaned.
9. **If sensitive user data (passwords, payment info) might be exposed**, force a password reset for all users and notify them per breach disclosure requirements.

---

## 2. Evidence Storage (What to Save & Why)

| Evidence Type | What to Capture |
|---|---|
| **Screenshots of defaced page** | Full page screenshot with URL and timestamp visible, including any message left by the attacker |
| **Server access/error logs** | Web server logs (Apache/Nginx), CMS logs, FTP logs — covering the period before and during the attack |
| **File modification timestamps** | List of recently modified/created files on the server (use `find` command or hosting panel's file manager sort-by-date) |
| **Malicious files/backdoors found** | Preserve copies (in an isolated location, do not execute) of any shell scripts or backdoor files discovered |
| **Database changes** | If content/user data was altered, note what changed compared to your last backup |
| **DNS/domain records** | Screenshot current DNS settings — attackers sometimes alter these too, redirecting traffic elsewhere |
| **Attacker's IP address(es)** | From server logs, note IPs associated with the unauthorized access/upload activity |
| **Timeline log** | When the defacement was discovered, when the site was taken offline, when each remediation step was completed |

**Tip:** Always back up the **compromised state** before cleaning anything — this is your primary evidence and also helps identify exactly how the attacker got in (helpful to prevent recurrence).

---

## 3. Reporting (In Priority Order)

### Step 1 — Take the Site Offline / Contact Hosting Provider Immediately
- Most hosting providers have a security/abuse team that can assist with immediate containment and log analysis.

### Step 2 — Report to CERT-In (Mandatory for Many Organizations)
- **[cert-in.org.in](https://www.cert-in.org.in)** — Email: incident@cert-in.org.in. Website defacement/hacking incidents fall under CERT-In's mandatory reporting categories (within 6 hours of detection for applicable entities). CERT-In also tracks defacement trends and can offer guidance.

### Step 3 — File a Complaint on the National Cyber Crime Reporting Portal
- **[cybercrime.gov.in](https://cybercrime.gov.in)** — File under "Report Other Cyber Crime" for website hacking/defacement. Include logs, screenshots, and timeline.

### Step 4 — Notify Affected Users (if applicable)
- If user data/credentials may have been exposed, notify your users to change passwords and monitor for suspicious activity on accounts that used the same credentials elsewhere.

### Step 5 — Request Blacklist Review (after cleanup)
- **Google Search Console / Safe Browsing:** [search.google.com/search-console](https://search.google.com/search-console) — request a malware review once the site is cleaned, to restore search visibility and remove "This site may be hacked" warnings.

### Step 6 — File FIR at Local Police Cyber Cell
- Recommended for significant business/reputational damage, or if the defacement involved politically/communally sensitive content (which may also need reporting to platform/authorities for content removal urgency).

---

## 4. Helpful Resources

| Need | Resource |
|---|---|
| **Check if your site is blacklisted** | [Google Safe Browsing Transparency Report](https://transparencyreport.google.com/safe-browsing/search) — check your domain's status |
| **Request malware review after cleanup** | [Google Search Console](https://search.google.com/search-console) — Security Issues section |
| **CMS-specific hardening guides** | WordPress: [wordpress.org/support/article/hardening-wordpress](https://wordpress.org/support/article/hardening-wordpress/); similar official hardening guides exist for Joomla, Drupal, etc. |
| **CERT-In security advisories** | [cert-in.org.in](https://www.cert-in.org.in) — published vulnerability advisories relevant to your CMS/server stack |
| **Web Application Firewall (WAF) services** | Cloudflare, Sucuri — can help block future attacks and offer malware cleanup services for compromised sites |

---

## 5. Quick Checklist Summary

1. ✅ Take the site offline/maintenance mode immediately
2. ✅ Screenshot the defaced page and preserve logs BEFORE cleanup
3. ✅ Change all admin/hosting/FTP/database credentials
4. ✅ Scan for and remove backdoors/malicious files
5. ✅ Patch the vulnerability, THEN restore from clean backup
6. ✅ Report to CERT-In (mandatory, within 6 hours for applicable entities)
7. ✅ File complaint on cybercrime.gov.in
8. ✅ Request blacklist/malware review via Google Search Console after cleanup
9. ✅ Notify users if their data/credentials may be exposed
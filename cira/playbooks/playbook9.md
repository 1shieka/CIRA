# Playbook 9: System Intrusion & Data Breach

**Categories Covered:** Unauthorized Access, System Damage, Source Code Tampering

---

## 1. Immediate Steps (Stop the Damage & Recover Fast)

1. **Isolate the affected system immediately** — disconnect it from the network (unplug Ethernet/disable Wi-Fi) to stop further data exfiltration or spread, but **do NOT power it off** (this can destroy forensic evidence in memory). Just disconnect network access.
2. **Do not attempt to "clean up" or delete anything yourself** — this can destroy evidence needed for investigation and legal action. Preserve the system in its compromised state for forensic review.
3. **Identify the scope** — which systems, accounts, or source code repositories were accessed? Check access logs for unusual login times/locations/IPs.
4. **Change all admin/root credentials immediately** for systems NOT yet confirmed compromised, using a separate secure device/network.
5. **Revoke API keys, tokens, and SSH keys** that may have been exposed, and rotate all secrets/credentials stored in the affected system.
6. **For source code tampering**: Compare against your last known-good backup/version control history (git log/diff) to identify exactly what was changed, when, and by which credentials.
7. **Notify your internal IT/security team or incident response provider immediately** — if you don't have one, this is the point to engage a professional cybersecurity firm for forensic investigation.
8. **If customer/user data was potentially exposed**, begin preparing for mandatory breach notification (see Reporting section) — many regulations require notification within strict time limits (e.g., 6 hours under India's CERT-In rules).
9. **Restore from clean backups** only after the vulnerability that allowed access has been identified and patched — restoring without fixing the entry point means the attacker can return.

---

## 2. Evidence Storage (What to Save & Why)

| Evidence Type | What to Capture |
|---|---|
| **System logs** | Server access logs, authentication logs, firewall logs — covering at least 30 days before the detected incident |
| **Network traffic logs** | Any unusual outbound traffic (data exfiltration indicators), connections to unknown IPs |
| **Memory/disk snapshot** | If possible, take a forensic image of the affected system before any changes (consult a forensic expert for proper imaging tools) |
| **Source code diff/version history** | Git commit history, diffs showing exactly what was tampered with, timestamps, and committer credentials used |
| **Account activity logs** | List of accounts that accessed the system, especially any new/unrecognized admin accounts created |
| **Malware/tool samples** | If malicious scripts/tools were left behind, preserve copies (in an isolated environment) for analysis — do not run them |
| **Screenshots of damage** | Any visible system damage, deleted files list, ransom notes, defacement messages |
| **Timeline log** | Exact discovery time, isolation time, who was notified and when — critical for regulatory reporting deadlines |

**Tip:** Engage a digital forensics expert before making major changes if the breach is significant — improper handling of evidence can compromise both recovery and any legal case.

---

## 3. Reporting (In Priority Order)

### Step 1 — Internal Escalation (Immediate)
- Notify your CISO/IT security team or engage an external incident response firm immediately — internal containment must happen in parallel with external reporting.

### Step 2 — Report to CERT-In (Mandatory & Time-Sensitive for Organizations)
- **[cert-in.org.in](https://www.cert-in.org.in)** — Email: incident@cert-in.org.in. Under India's CERT-In directions, organizations **must report specific categories of cyber incidents within 6 hours of detection**, including unauthorized access, data breaches, and source code tampering. This is a legal/regulatory requirement, not optional, for many entities.

### Step 3 — Dial 1930 / File on National Cyber Crime Reporting Portal
- **[cybercrime.gov.in](https://cybercrime.gov.in)** — File under "Report Other Cyber Crime" for unauthorized access/system damage. Include all logs and timeline evidence.

### Step 4 — Notify Affected Users/Customers (if personal data was breached)
- If user/customer data was exposed, you are generally required to notify affected individuals — check applicable data protection law requirements (e.g., India's Digital Personal Data Protection Act) for notification timelines and content requirements.

### Step 5 — File FIR at Local Police Cyber Cell
- Important for legal proceedings, insurance claims, and especially if source code/intellectual property theft occurred (covered under IT Act Sections 43, 66 and IPC/BNS provisions).

### Step 6 — Sector-Specific Regulator (if applicable)
- **RBI** (for banks/NBFCs), **SEBI** (for stock market entities), **IRDAI** (for insurance) — many sectors have additional mandatory breach reporting obligations to their specific regulator.

---

## 4. Helpful Resources

| Need | Resource |
|---|---|
| **CERT-In incident reporting guidelines** | [cert-in.org.in](https://www.cert-in.org.in) — detailed format for what to include in your incident report |
| **Digital forensics support** | Engage CERT-In empanelled security auditors (list available on CERT-In's website) for professional forensic investigation |
| **Data breach notification requirements** | Refer to India's [Digital Personal Data Protection Act, 2023](https://www.meity.gov.in) guidelines via Ministry of Electronics & IT |
| **Vulnerability disclosure/patching guidance** | [cert-in.org.in](https://www.cert-in.org.in) publishes advisories on known vulnerabilities being actively exploited |
| **Source code integrity verification** | Use Git's built-in commit signing (GPG) going forward to prevent/detect future tampering |

---

## 5. Quick Checklist Summary

1. ✅ Disconnect affected systems from network (don't power off)
2. ✅ Preserve logs, disk image, and source code diffs — don't "clean up" yet
3. ✅ Change all credentials/rotate keys for unaffected systems
4. ✅ Notify internal security team / engage incident response immediately
5. ✅ Report to CERT-In within 6 hours (mandatory for many organizations)
6. ✅ File complaint on cybercrime.gov.in / dial 1930
7. ✅ Notify affected users if personal data was exposed
8. ✅ File FIR + notify sector regulator (RBI/SEBI/IRDAI) if applicable
9. ✅ Patch the vulnerability BEFORE restoring from backup
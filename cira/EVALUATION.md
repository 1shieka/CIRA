## This file contains all the evaluation critera needs to be paased from the User responses and evidence.

# Cybercrime Evidence Mapping Matrix

## Purpose

For each identified cybercrime category, determine:

1. Required evidence
2. Optional evidence
3. Missing evidence
4. Evidence completeness score

The assistant must compare collected evidence against the expected evidence list for that category.

---

# 1. UPI Fraud

## Required Evidence

* UTR Number
* Transaction ID
* Bank account involved
* Date and time of transaction
* Amount transferred
* Screenshot of transaction
* Beneficiary account details (if visible)

## Optional Evidence

* Fraudster phone number
* WhatsApp chats
* Call recordings
* SMS alerts

## Critical Missing Flags

* No UTR
* No transaction screenshot
* No amount information

---

# 2. Banking Fraud

## Required Evidence

* Bank name
* Account number (masked)
* Transaction IDs
* SMS alerts
* Debit notifications
* Date and time of unauthorized transaction

## Optional Evidence

* Login alerts
* Email notifications
* Call recordings

## Critical Missing Flags

* No transaction proof
* No bank details
* No transaction timeline

---

# 3. SIM Swap Fraud

## Required Evidence

* Mobile number affected
* Loss of network screenshot
* SMS from telecom operator
* Date and time service stopped

## Optional Evidence

* Telecom complaint number
* Call records
* Device screenshots

## Critical Missing Flags

* No telecom messages
* No affected number
* No timeline

---

# 4. WhatsApp Account Hijack

## Required Evidence

* Affected phone number
* WhatsApp login alert
* Screenshot of logout
* Unauthorized messages

## Optional Evidence

* Linked device screenshots
* Fraudster messages

## Critical Missing Flags

* No screenshots
* No account identifier

---

# 5. Social Media Account Takeover

## Required Evidence

* Platform name
* Username/profile URL
* Login alert emails
* Recovery emails
* Unauthorized posts/messages

## Optional Evidence

* Device history
* Session logs

## Critical Missing Flags

* No profile information
* No login evidence

---

# 6. Phishing Scam

## Required Evidence

* URL clicked
* Screenshot of website
* Phishing email/message
* Date and time interaction occurred

## Optional Evidence

* Browser history
* Email headers

## Critical Missing Flags

* No URL
* No phishing message

---

# 7. QR Code Scam

## Required Evidence

* QR code image
* Payment screenshot
* UTR number
* Transaction amount

## Optional Evidence

* Chat history
* Merchant information

## Critical Missing Flags

* No QR screenshot
* No transaction evidence

---

# 8. Remote Access Scam

## Required Evidence

* Application installed
* App name
* Installation time
* Screenshots of permissions granted
* Transaction history (if money loss occurred)

## Optional Evidence

* APK file
* Call recordings

## Critical Missing Flags

* Unknown app
* No device evidence

---

# 9. Mobile Phone Hacking / Malware

## Required Evidence

* Device type
* OS version
* Suspicious application name
* APK file (if available)
* Screenshots of suspicious behavior

## Optional Evidence

* Antivirus reports
* Accessibility permissions
* Device logs

## Critical Missing Flags

* Unknown suspicious app
* No screenshots

---

# 10. Investment Scam

## Required Evidence

* Platform name
* Website URL
* Wallet/account details
* Transaction records
* Deposit screenshots

## Optional Evidence

* Telegram chats
* Account manager details

## Critical Missing Flags

* No transaction proof
* No platform information

---

# 11. Job Scam

## Required Evidence

* Job posting
* Company name
* Communication screenshots
* Payment request evidence
* Email addresses used

## Optional Evidence

* Offer letter
* Contract

## Critical Missing Flags

* No communication evidence
* No payment proof

---

# 12. E-Commerce / Shopping Fraud

## Required Evidence

* Order ID
* Seller profile
* Payment receipt
* Product listing

## Optional Evidence

* Tracking information
* Chat conversations

## Critical Missing Flags

* No order details
* No payment proof

---

# 13. Sextortion

## Required Evidence

* Threat messages
* Usernames
* Payment demands
* Wallet/account details used by attacker

## Optional Evidence

* Images/videos shared
* Social media profiles

## Critical Missing Flags

* No threat evidence
* No account identifiers

---

# 14. Cyber Bullying / Harassment

## Required Evidence

* Messages/posts
* URLs
* Usernames
* Dates and timestamps

## Optional Evidence

* Witness statements

## Critical Missing Flags

* No screenshots
* No offender identifier

---

# 15. Identity Theft

## Required Evidence

* Misused document details
* Fraudulent account details
* Emails/messages showing misuse

## Optional Evidence

* Credit reports
* Complaint references

## Critical Missing Flags

* No proof of misuse
* No affected identity document

---

# Evidence Completeness Formula

For each category:

Evidence Completeness (%) =
(Number of Required Evidence Collected /
Total Required Evidence) × 100

Example:

UPI Fraud

Collected:
✓ UTR
✓ Amount
✓ Screenshot
✗ Beneficiary Details
✓ Date/Time

4 / 5 = 80%

Evidence Completeness = 80%

---

# Evaluation Rule

If Evidence Completeness < 70%

Verdict:
NEEDS_MORE_INFORMATION

If Evidence Completeness ≥ 90%

Verdict:
REPORT_READY

If any Critical Missing Flag exists

Verdict:
NEEDS_MORE_INFORMATION regardless of score.



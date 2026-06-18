# Cybercrime Evidence Mapping Matrix

## Purpose

This file defines the evaluation logic for an AI agent that reviews evidence a user has submitted for a cybercrime report. For each identified cybercrime category, the agent must:

1. Identify the correct category (or categories) for the complaint.
2. Compare submitted evidence against that category's **Required Evidence** list.
3. Calculate an **Evidence Completeness Score**.
4. Check for **Critical Missing Flags**.
5. Output a **Verdict** with a clear, user-facing explanation of what is missing.

Evidence is scored on presence only (collected / not collected). Quality of evidence (e.g. blurry vs. clear screenshot) is not scored, but if an item is present yet clearly unusable as evidence (e.g. a screenshot with no visible data), treat it as **not collected**.

Optional Evidence is never scored. It is shown to the user as "nice to have" only and does not affect the score in either direction.

---

## How to Use This Matrix (Agent Instructions)

For every user submission:

1. **Classify.** Match the complaint to one category below using its description and required-evidence pattern. If the complaint clearly spans more than one category (e.g. a Remote Access Scam that led to a UPI Fraud), evaluate it against **each** relevant category separately and report both. If no category fits, use the **Uncategorized / Other Cybercrime** fallback at the end of this file rather than forcing a poor match.
2. **Extract.** Go through everything the user has provided (text description, uploaded files, screenshots, IDs, dates) and map each piece to a Required or Optional Evidence item for the matched category. Do not credit an item unless it is clearly present and intelligible.
3. **Score.** Apply the Evidence Completeness Formula below using only the Required Evidence list for that category.
4. **Flag.** Check the category's Critical Missing Flags. These can force a `NEEDS_MORE_INFORMATION` verdict even at a high score.
5. **Verdict.** Apply the Evaluation Rule to produce one of the three verdicts.
6. **Explain.** Always list which specific Required Evidence items are missing, in plain language, so the user knows exactly what to provide next. Never just output a score with no explanation.

---

# 1. UPI Fraud

## Required Evidence (7)

* UTR Number
* Transaction ID
* Bank account involved
* Date and time of transaction
* Amount transferred
* Screenshot of transaction
* Beneficiary account details (if visible to the victim)

## Optional Evidence

* Fraudster phone number
* WhatsApp chats
* Call recordings
* SMS alerts

## Critical Missing Flags

* No UTR Number
* No transaction screenshot
* No amount information

---

# 2. Banking Fraud

## Required Evidence (6)

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

* No transaction proof (no Transaction IDs, SMS alerts, or Debit notifications)
* No bank details (no Bank name or Account number)
* No transaction timeline (no Date and time)

---

# 3. SIM Swap Fraud

## Required Evidence (4)

* Mobile number affected
* Loss-of-network screenshot
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

## Required Evidence (4)

* Affected phone number
* WhatsApp login alert
* Screenshot of logout
* Unauthorized messages sent from the account

## Optional Evidence

* Linked-device screenshots
* Fraudster messages received by the victim

## Critical Missing Flags

* No screenshots (neither login alert nor logout screenshot)
* No account identifier (no affected phone number)

---

# 5. Social Media Account Takeover

## Required Evidence (5)

* Platform name
* Username / profile URL
* Login alert emails
* Recovery emails
* Unauthorized posts/messages

## Optional Evidence

* Device history
* Session logs

## Critical Missing Flags

* No profile information (no Platform name or Username/profile URL)
* No login evidence (no Login alert emails or Recovery emails)

---

# 6. Phishing Scam

## Required Evidence (4)

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

## Required Evidence (4)

* QR code image
* Payment screenshot
* UTR number
* Transaction amount

## Optional Evidence

* Chat history
* Merchant information

## Critical Missing Flags

* No QR code screenshot
* No transaction evidence (no Payment screenshot and no UTR number)

---

# 8. Remote Access Scam

## Required Evidence (5)

* Application installed
* App name
* Installation time
* Screenshots of permissions granted
* Transaction history (only required if money loss occurred; see note below)

## Optional Evidence

* APK file
* Call recordings

## Critical Missing Flags

* Unknown app (no App name)
* No device evidence (no Screenshots of permissions granted)

**Note:** If the user reports no financial loss, "Transaction history" is excluded from both the required count and the denominator in the completeness formula for this case.

---

# 9. Mobile Phone Hacking / Malware

## Required Evidence (5)

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

* Unknown suspicious app (no Suspicious application name)
* No screenshots

---

# 10. Investment Scam

## Required Evidence (5)

* Platform name
* Website URL
* Wallet/account details
* Transaction records
* Deposit screenshots

## Optional Evidence

* Telegram/chat group history
* Account manager details

## Critical Missing Flags

* No transaction proof (no Transaction records and no Deposit screenshots)
* No platform information (no Platform name or Website URL)

---

# 11. Job Scam

## Required Evidence (5)

* Job posting
* Company name
* Communication screenshots
* Payment request evidence
* Email addresses used

## Optional Evidence

* Offer letter
* Contract

## Critical Missing Flags

* No communication evidence (no Communication screenshots)
* No payment proof (no Payment request evidence) — only applies if the user reports a financial loss

---

# 12. E-Commerce / Shopping Fraud

## Required Evidence (4)

* Order ID
* Seller profile
* Payment receipt
* Product listing

## Optional Evidence

* Tracking information
* Chat conversations with seller

## Critical Missing Flags

* No order details (no Order ID)
* No payment proof (no Payment receipt)

---

# 13. Sextortion

## Required Evidence (4)

* Threat messages
* Usernames/handles of attacker
* Payment demands
* Wallet/account details used by attacker (only if payment was demanded via a specific account/wallet)

## Optional Evidence

* Images/videos shared (handle per platform sensitive-content policy; never require upload, accept confirmation of existence instead)
* Social media profiles of attacker

## Critical Missing Flags

* No threat evidence (no Threat messages)
* No account identifiers (no Usernames/handles)

**Note:** Do not require the victim to upload sensitive images/videos as evidence. Their existence and description are sufficient; flag this item as collected based on the victim's confirmation alone.

---

# 14. Cyber Bullying / Harassment

## Required Evidence (4)

* Messages/posts
* URLs (where the content is hosted)
* Usernames of offender(s)
* Dates and timestamps

## Optional Evidence

* Witness statements

## Critical Missing Flags

* No screenshots (no Messages/posts)
* No offender identifier (no Usernames)

---

# 15. Identity Theft

## Required Evidence (3)

* Misused document details (e.g. which ID — Aadhaar, PAN, passport — was misused)
* Fraudulent account/transaction details created using the identity
* Emails/messages/notices showing the misuse

## Optional Evidence

* Credit reports
* Prior complaint reference numbers

## Critical Missing Flags

* No proof of misuse (no Fraudulent account/transaction details and no Emails/messages showing misuse)
* No affected identity document specified

---

# 16. Uncategorized / Other Cybercrime (Fallback)

Use this category only when the complaint does not reasonably match any of categories 1–15.

## Required Evidence (4)

* Clear description of what happened, including platform/channel involved
* Date and time of incident
* Any screenshots, messages, or files related to the incident
* Identifier of the other party (username, phone number, account, or URL), if known

## Optional Evidence

* Witness statements
* Any financial records, if money was involved

## Critical Missing Flags

* No incident description
* No timeline
* No supporting evidence of any kind

**Note:** If a submission scored under this fallback category later turns out to match a specific category once more detail is provided, re-classify and re-score under that category instead.

---

# Evidence Completeness Formula

For each matched category:

```
Evidence Completeness (%) = (Required Evidence Items Collected / Total Applicable Required Evidence Items) × 100
```

"Total Applicable Required Evidence Items" excludes any item marked conditional in that category's notes (e.g. "only if money loss occurred") when the condition does not apply to this case. Round to the nearest whole number.

### Worked Example — UPI Fraud

Collected:
* UTR Number — ✓
* Transaction ID — ✓
* Bank account involved — ✓
* Date and time of transaction — ✓
* Amount transferred — ✓
* Screenshot of transaction — ✓
* Beneficiary account details — ✗ (not visible to victim, but item is still applicable since visibility is about availability to the platform, not a valid exemption)

6 / 7 = 86%

Evidence Completeness = 86%

This also illustrates the Evaluation Rule below: 86% falls in the 70–89% band, and since no Critical Missing Flag is triggered (UTR, screenshot, and amount are all present), the verdict is `NEEDS_MORE_INFORMATION` rather than `REPORT_READY`, because completeness is below the 90% threshold — even though no flag fired. The agent should tell the user specifically that beneficiary account details are still needed if available.

---

# Evaluation Rule

Apply in this order:

1. **If any Critical Missing Flag for the matched category is triggered → Verdict: `NEEDS_MORE_INFORMATION`**, regardless of completeness score. State which flag(s) triggered.
2. **Else if Evidence Completeness < 70% → Verdict: `NEEDS_MORE_INFORMATION`.**
3. **Else if 70% ≤ Evidence Completeness < 90% → Verdict: `NEEDS_MORE_INFORMATION`.** The submission is on track but not yet sufficient; list the specific missing items.
4. **Else if Evidence Completeness ≥ 90% → Verdict: `REPORT_READY`.**

There is no separate passing band between "needs more information" and "report ready" — anything below 90%, or with a critical flag, is not report-ready. This removes the ambiguity in scores between 70–89% that the original rule left undefined.

## Output Format

For every evaluation, the agent should output:

* Matched category (or categories, if more than one applies)
* Evidence Completeness Score (%)
* List of Required Evidence items: collected vs. missing
* Any Critical Missing Flags triggered
* Final Verdict
* A short, plain-language note to the user listing exactly what additional evidence would move the case forward

Do not output the score alone without the missing-items explanation — the user needs actionable next steps, not just a number.
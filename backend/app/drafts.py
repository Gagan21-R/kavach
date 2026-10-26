"""Editable request drafts (data access, deletion, consent withdrawal, objection).

Drafts are text for the user to review, edit and send themselves. Consent Court has no code path that sends
email. The wording asks rather than asserts legal entitlement, because which rights apply depends on law and
circumstances we have not established.
"""
from app.models import PolicySnapshot, PolicySource, WatchEvent

SUBJECTS = {
    "access": "Request for a copy of my personal data",
    "deletion": "Request to delete my personal data",
    "withdraw_consent": "Withdrawal of consent for a new data use",
    "objection": "Objection to a change in how my data is used",
}
ASKS = {
    "access": "Please send me a copy of the personal data you hold about me, the purposes you use it for, and the "
              "recipients or categories of recipients you have shared it with.",
    "deletion": "Please delete the personal data you hold about me and confirm in writing once this is done, including "
                "whether any copies held by partners or in backups will also be deleted.",
    "withdraw_consent": "I do not agree to the use described above. Please treat this message as withdrawal of any consent "
                        "I may have given for it, and stop using my data for this purpose.",
    "objection": "I object to my data being used in the way described above. Please stop, and tell me what options I have "
                 "if you believe you can continue.",
}


def draft(policy: PolicySource, snapshot: PolicySnapshot, request_type: str, *, event: WatchEvent | None = None,
          sender_name: str = "", account_email: str = "") -> dict:
    lines = ["Hello,", ""]
    lines.append(f"I am a user of {policy.name} ({policy.domain})" + (f", registered with {account_email}" if account_email else "") + ".")
    changed = []
    if event is not None:
        changed = [c for c in event.output.get("changes", []) if c["classification"] in ("POTENTIALLY_MATERIAL", "AMBIGUOUS")]
    if changed:
        lines += ["", f"I noticed that your privacy policy changed (version {event.from_version} to {event.to_version}). It now says:"]
        for c in changed[:3]:
            if c["new_text"]:
                lines.append(f'  "{c["new_text"]}"')
    lines += ["", ASKS[request_type], ""]
    lines.append("If you need anything further to verify my identity, please tell me what is required.")
    lines += ["", "Thank you,", sender_name or "[your name]"]
    return {
        "request_type": request_type,
        "subject": SUBJECTS[request_type],
        "to_hint": f"privacy contact for {policy.domain} (check the policy's contact section)",
        "body": "\n".join(lines),
        "sent": False,
        "disclaimer": "This is a draft for you to edit and send yourself. Consent Court never sends it. Whether the "
                      "company must comply depends on the law where you live and other circumstances; this is not legal advice.",
        "based_on_version": snapshot.version,
    }

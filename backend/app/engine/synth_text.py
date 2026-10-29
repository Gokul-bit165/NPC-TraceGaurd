"""Deterministic synthetic email-text corpus used to bootstrap the bundled text model.

IMPORTANT: this is template text written by the team, not real mail. A model trained on it proves the
plumbing works and gives plausible term attributions; it says nothing about real-world accuracy.
Retrain on the Kaggle phishing-email dataset with scripts/train_text_model.py and publish those metrics.
Hard negatives (legitimate mail that uses urgency, passwords and links) are included on purpose so the
model cannot rely on a single keyword.
"""
from __future__ import annotations

import random

SERVICES = ["Office 365", "campus portal", "student email", "library account", "payroll portal", "VPN access", "Canvas", "university SSO", "cloud storage"]
NAMES = ["Priya", "Rahul", "Ananya", "Vikram", "Meera", "Arjun", "Sana", "Karthik", "Neha", "Ishaan"]
TOPICS = ["machine learning", "renewable energy", "data ethics", "robotics", "quantum computing", "public health", "urban design", "cybersecurity"]
DEPTS = ["Computer Science", "Mechanical Engineering", "Commerce", "Physics", "Library Services", "Student Affairs", "Placement Cell", "Registrar"]

# (family, text). Each family is a distinct template; the held-out split is by family, not by random row.
PHISH = [
    ("expire", "Your {svc} password will expire in {n} hours. Verify your account now to keep access. Click here to sign in and confirm your password: {url}"),
    ("unusual", "Unusual sign-in activity was detected on your {svc}. Confirm your identity immediately or your account will be suspended. Sign in here: {url}"),
    ("mailbox", "Your mailbox is almost full and incoming mail will be blocked. Validate your mailbox within 24 hours to avoid deactivation: {url}"),
    ("payment", "A payment of ${amt} is pending approval on your {svc}. If you did not authorise this, log in to cancel it immediately: {url}"),
    ("doc", "{name} shared a confidential document with you. Sign in with your campus credentials to view the secure file: {url}"),
    ("refund", "Your scholarship refund of ${amt} is ready. Confirm your bank details and student login to receive the transfer: {url}"),
    ("hr", "HR has updated the salary revision letter for staff. Open the attached portal and re-enter your password to download: {url}"),
    ("suspend", "Final notice: your {svc} has been suspended due to a policy violation. Update your credentials to restore access today: {url}"),
    ("gift", "Congratulations {name}, you were selected for a campus rewards gift card. Claim now, offer expires today. Login required: {url}"),
    ("ceo", "Are you available? I need a quick favour, it is urgent and confidential. Reply with your phone number and buy gift cards for me, {name}."),
]
LEGIT = [
    ("library", "Reminder from {dept}: library books borrowed on your card are due next {day}. Renew them on the library page or at the desk."),
    ("lecture", "{dept} invites you to a guest lecture on {topic} this {day} at 3 PM in the main auditorium. Registration is optional, refreshments provided."),
    ("timetable", "Your timetable for next week has been updated. Please check the notice board or the department page for room changes. Regards, {dept}."),
    ("minutes", "Please find the minutes of the {dept} committee meeting attached. Action items are due by {day}. Let me know if anything is missing."),
    ("deadline", "Deadline reminder: assignment submissions close tomorrow at 5 PM. Late submissions will lose marks. Submit through the course page you normally use."),
    ("fees", "Fee payment due date reminder: the second instalment is due on {day}. Pay only through the official campus payment page; the accounts office never asks for your password."),
    ("pwdit", "IT notice: your campus password will expire in {n} days. Change it at the usual single sign-on page when convenient. Never share it with anyone."),
    ("exam", "The exam seating arrangement for {dept} has been published. Carry your ID card and arrive 20 minutes early. Good luck, {name}."),
    ("newsletter", "This week at campus: {topic} seminar, sports trials on {day}, and the placement cell workshop. Read the full newsletter on the campus website."),
    ("hostel", "Water supply maintenance is planned in the hostel blocks on {day} between 10 AM and 1 PM. Please store water in advance."),
    ("reg", "Semester registration opens on {day}. Select your electives from the registrar page and confirm with your advisor. Many links below for each department list."),
    ("receipt", "Thank you {name}. Your order for the {topic} workshop is confirmed. Your receipt is attached. This is an automated message, do not reply."),
]


def _fill(tpl: str, r: random.Random, bad_url: bool) -> str:
    urls_bad = ["http://kestrel-edu-login.top/verify", "http://secure-office365-signin.xyz/auth", "http://bit.ly/3xYz9Q", "http://192.0.2.44/login", "https://kestre1.edu.verify-account.click/s"]
    return tpl.format(
        svc=r.choice(SERVICES), n=r.choice([2, 6, 12, 24, 48]), amt=r.choice([120, 480, 950, 2300]), name=r.choice(NAMES),
        url=r.choice(urls_bad) if bad_url else "https://portal.kestrel.edu", dept=r.choice(DEPTS), topic=r.choice(TOPICS),
        day=r.choice(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]))


def _noise(text: str, r: random.Random) -> str:
    prefixes = ["", "Dear user, ", "Hello, ", "Hi, ", "Attention: ", "Notice: "]
    suffixes = ["", " Thank you.", " Regards, IT Support", " Do not reply to this message.", " Have a good day."]
    return r.choice(prefixes) + text + r.choice(suffixes)


def build(n_per_class: int = 1500, seed: int = 7, held_out_families: tuple[str, ...] = ("gift", "refund", "newsletter", "receipt")):
    """Return (train_texts, train_labels, test_texts, test_labels). Held-out families never appear in training."""
    r = random.Random(seed)
    train_x, train_y, test_x, test_y = [], [], [], []
    for _ in range(n_per_class):
        fam, tpl = r.choice(PHISH)
        t = _noise(_fill(tpl, r, True), r)
        (test_x if fam in held_out_families else train_x).append(t)
        (test_y if fam in held_out_families else train_y).append(1)
        fam, tpl = r.choice(LEGIT)
        t = _noise(_fill(tpl, r, False), r)
        (test_x if fam in held_out_families else train_x).append(t)
        (test_y if fam in held_out_families else train_y).append(0)
    return train_x, train_y, test_x, test_y

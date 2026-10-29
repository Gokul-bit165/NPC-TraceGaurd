"""Populate the database with a synthetic campus: ~1,000 ordinary emails, ~2,500 logins, two phishing
waves and the scripted scenarios. Everything here is fictional and generated; nothing is real data.

Run:  python -m app.seed --reset
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import scenarios as sc
from . import services
from .db import SessionLocal, init_db, reset_db
from .engine import synth_text
from .engine.bulk import score_stream
from .engine.email_parse import parse_eml
from .engine.types import LoginEvent
from .models import AuditRow

FIRST = ["Aarav", "Diya", "Kabir", "Ishita", "Reyansh", "Tara", "Advait", "Myra", "Vihaan", "Anika", "Arnav", "Kiara", "Dhruv", "Navya", "Yash", "Riya",
         "Samar", "Pooja", "Harsh", "Zoya", "Tejas", "Aditi", "Rudra", "Sneha", "Manav", "Ira", "Veer", "Pari", "Neel", "Anvi", "Om", "Saanvi"]
LAST = ["Sharma", "Verma", "Gupta", "Reddy", "Nair", "Menon", "Patel", "Singh", "Das", "Bose", "Kulkarni", "Chopra", "Banerjee", "Pillai", "Desai", "Iyer"]
CITIES = [("Pune", "IN"), ("Mumbai", "IN"), ("Delhi", "IN"), ("Bengaluru", "IN"), ("Chennai", "IN"), ("Hyderabad", "IN"), ("Kolkata", "IN"), ("Coimbatore", "IN"), ("Jaipur", "IN")]
DEVICES = ["windows|chrome", "windows|edge", "macos|safari", "android|chrome mobile", "ios|safari", "windows|firefox", "linux|chrome"]
DEPTS = ["Computer Science", "Mechanical Engineering", "Commerce", "Physics", "Civil Engineering", "Electronics", "Law", "Arts"]
SENDERS = [("Library Services", "library"), ("Registrar", "registrar"), ("Placement Cell", "placement"), ("Student Affairs", "affairs"),
           ("IT Service Desk", "itdesk"), ("Hostel Office", "hostel"), ("Department Office", "dept"), ("Sports Council", "sports")]


def _persons(n: int, rnd: random.Random) -> list[sc.Person]:
    out, used = [], set()
    while len(out) < n:
        f, l = rnd.choice(FIRST), rnd.choice(LAST)
        if (f, l) in used:
            continue
        used.add((f, l))
        city, country = rnd.choice(CITIES)
        devs = tuple(rnd.sample(DEVICES, rnd.choice([1, 2])))
        out.append(sc.Person(id=f"u-{f.lower()}-{l.lower()}", name=f"{f} {l}", email=f"{f.lower()}.{l.lower()}@{sc.CAMPUS}", dept=rnd.choice(DEPTS),
                             role="staff" if rnd.random() < 0.15 else "student", city=city, country=country, devices=devs))
    return out


def _legit_mail(p: sc.Person, when: datetime, rnd: random.Random, i: int):
    name, local = rnd.choice(SENDERS)
    fam, tpl = rnd.choice(synth_text.LEGIT)
    body = synth_text._fill(tpl, rnd, False)
    links = ""
    if rnd.random() < 0.35:
        links = "".join(f'<li><a href="https://portal.{sc.CAMPUS}/{local}/{k}">{k.title()}</a></li>' for k in rnd.sample(["notice", "form", "calendar", "faq", "help", "map"], 3))
    html = f"<p>{body}</p>" + (f"<ul>{links}</ul>" if links else "")
    raw = sc.eml(from_name=name, from_addr=f"{local}@{sc.CAMPUS}", to=p.email, subject=f"{name}: {fam.title()} update {i}", html=html, when=when,
                 dkim_d=sc.CAMPUS, mailfrom=sc.CAMPUS)
    return parse_eml(raw, p.id, when, f"m-bg-{i}")


def _marketing(p: sc.Person, when: datetime, rnd: random.Random, i: int):
    """Real vendor blasts look a bit like phishing: urgency, shorteners, many links. They authenticate correctly."""
    brand = rnd.choice(["campusbooks.example.com", "laptopdeals.example.in", "examprep.example.org"])
    links = "".join(f'<li><a href="http://bit.ly/{rnd.randint(10**5, 10**6)}">Deal {k}</a></li>' for k in range(rnd.randint(3, 6)))
    html = f"<p>Last chance! Sale ends today. Grab your student discount now.</p><ul>{links}</ul>"
    raw = sc.eml(from_name="Student Deals", from_addr=f"offers@{brand}", to=p.email, subject=f"Last chance: student discount {i}", html=html, when=when,
                 dkim_d=brand, mailfrom=brand)
    return parse_eml(raw, p.id, when, f"m-mkt-{i}")


def _wave(p: sc.Person, when: datetime, wave: int, i: int):
    if wave == 1:                       # same campaign as scenarios 1 and 2
        return sc._phish(p, when, f"m-w1-{i}")
    raw = sc.eml(from_name="Payroll Office", from_addr="payroll@kestrel-payroll.top", to=p.email, subject="Salary revision letter: action needed",
                 html='<p>HR has updated your salary revision letter. Open the secure portal and re-enter your password to download: '
                      '<a href="http://kestrel-payroll.top/letter">https://payroll.kestrel.edu/letter</a></p>', when=when,
                 reply_to="payroll.kestrel@outlook.com", spf="fail", dkim="none", dmarc="fail")
    return parse_eml(raw, p.id, when, f"m-w2-{i}")


def seed(db: Session, now: Optional[datetime] = None, n_background: int = 60, n_legit_emails: int = 960, rng_seed: int = 42, verbose: bool = True) -> dict:
    rnd = random.Random(rng_seed)
    now = now or datetime.now(timezone.utc)
    A = sc.anchor_time(now)
    scenarios = sc.build_all(now)

    # ---- people
    people: dict[str, sc.Person] = {s.person.id: s.person for s in scenarios}
    for s in scenarios:                                    # extra accounts that exist only inside scenarios (stuffing victims, lab PCs)
        for ev in s.others:
            if ev.user_id not in people:
                people[ev.user_id] = sc.Person(id=ev.user_id, name=ev.user_id.replace("u-", "").replace("stuffed", "Stuffed ").replace("lab", "Lab ").title(),
                                               email=f"{ev.user_id}@{sc.CAMPUS}", dept="Various")
    background = _persons(n_background, rnd)
    for p in background:
        people[p.id] = p
    for p in people.values():
        services.upsert_user(db, p.id, p.name, p.email, p.dept, p.role)

    # ---- logins: history + scenario events + background noise
    events: list[LoginEvent] = []
    for s in scenarios:
        events += s.logins + s.others
    for p in background:
        events += sc.history(p, A, n=rnd.randint(18, 34), ips=2, device_mix=p.devices)
    noise_users = rnd.sample(background, min(24, len(background)))
    for k, p in enumerate(noise_users):                    # benign recent behaviour, some of it a little odd
        t = A - timedelta(hours=rnd.randint(1, 20), minutes=rnd.randint(0, 59))
        dev, ip = rnd.choice(p.devices), sc._ip(p.id, 0)
        kind = k % 8
        if kind in (0, 1, 2):                              # ordinary login
            events.append(LoginEvent(p.id, t, ip, p.country, p.city, device=dev))
        elif kind == 3:                                    # new phone at home
            events.append(LoginEvent(p.id, t, ip, p.country, p.city, device=rnd.choice([d for d in DEVICES if d not in p.devices])))
        elif kind == 4:                                    # forgot password: 3 typos then success on the usual device
            for j in range(3):
                events.append(LoginEvent(p.id, t + timedelta(seconds=25 * j), ip, p.country, p.city, device=dev, success=False))
            events.append(LoginEvent(p.id, t + timedelta(seconds=110), ip, p.country, p.city, device=dev))
        elif kind == 5:                                    # visiting another Indian city
            events.append(LoginEvent(p.id, t, sc._ip(p.id, 5, "106.51"), "IN", rnd.choice([c for c, _ in CITIES if c != p.city]), device=dev))
        elif kind == 6:                                    # abroad on a new phone (Medium: ask, don't lock)
            events.append(LoginEvent(p.id, t, "203.0.113.%d" % rnd.randint(2, 250), "SG", "Singapore", device=rnd.choice([d for d in DEVICES if d not in p.devices])))
        else:                                              # bot-like failures from an unknown IP, no success
            for j in range(6):
                events.append(LoginEvent(p.id, t + timedelta(seconds=30 * j), "198.51.100.%d" % rnd.randint(2, 250), "IN", "Mumbai", device="linux|chrome", success=False))

    rows = 0
    for ev, risk, band, flags, _thin in score_stream(events):
        services.add_login(db, ev, risk, band, flags)
        rows += 1
    db.flush()

    # ---- emails: ordinary traffic, vendor blasts, two phishing waves, scenario mail
    cfg_emails = 0
    i = 0
    all_people = list(people.values())
    for _ in range(n_legit_emails):
        p = rnd.choice(background)
        services.add_email(db, _legit_mail(p, A - timedelta(minutes=rnd.randint(30, 60 * 40)), rnd, i)); i += 1; cfg_emails += 1
    for j in range(14):
        services.add_email(db, _marketing(rnd.choice(background), A - timedelta(minutes=rnd.randint(30, 60 * 30)), rnd, j)); cfg_emails += 1
    w1 = rnd.sample(background, min(7, len(background)))
    for j, p in enumerate(w1):
        services.add_email(db, _wave(p, A - timedelta(hours=3, minutes=rnd.randint(-20, 20)), 1, j)); cfg_emails += 1
    rest = [p for p in background if p not in w1]
    w2 = rnd.sample(rest, min(5, len(rest)))
    for j, p in enumerate(w2):
        services.add_email(db, _wave(p, A - timedelta(hours=9, minutes=rnd.randint(-30, 30)), 2, j)); cfg_emails += 1
    for s in scenarios:
        for em in s.emails:
            services.add_email(db, em); cfg_emails += 1
    db.flush()

    # ---- analyse every user with something recent, scenario users first so their case ids are stable
    order = [s.person.id for s in scenarios] + [p.id for p in noise_users] + [p.id for p in w1 + w2]
    seen, cases = set(), 0
    scen_by_user = {s.person.id: s.key for s in scenarios}
    for uid in order:
        if uid in seen:
            continue
        seen.add(uid)
        c = services.reanalyze_user(db, uid, actor="system", scenario_key=scen_by_user.get(uid), as_of=A)
        cases += 1 if c else 0
    for j in range(5):                                      # co-victims of the stuffing run and the lab students get scored too
        for uid in (f"u-stuffed{j}",):
            if uid not in seen:
                seen.add(uid)
                cases += 1 if services.reanalyze_user(db, uid, as_of=A) else 0
    db.commit()
    out = {"users": len(people), "logins": rows, "emails": cfg_emails, "cases": cases, "anchor": A.isoformat()}
    if verbose:
        print("seeded:", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    args = ap.parse_args()
    reset_db() if args.reset else init_db()
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    main()

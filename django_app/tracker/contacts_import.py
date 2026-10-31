"""Read an attendee or contacts export (e.g. a CSV from Wix) and match each person to an existing student."""
import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

MAX_BYTES = 2_000_000
MAX_ROWS = 5000

NAME_HEADERS = ("name", "full name", "client name", "contact name", "attendee", "attendee name", "customer name",
                "guest name", "participant", "participant name")
FIRST_HEADERS = ("first name", "firstname", "given name")
LAST_HEADERS = ("last name", "lastname", "surname", "family name")
BOOKED_HEADERS = ("service", "service name", "class", "course", "event", "event name", "session", "booking",
                  "title", "product", "product name")


@dataclass
class Person:
    name: str
    email: str = ""
    phone: str = ""
    booked: list = field(default_factory=list)
    student: object = None  # the student this person is thought to be
    candidates: list = field(default_factory=list)  # possible matches when it isn't certain
    action: str = "new"  # "new", "skip" or a student pk
    rename: bool = False  # replace a first-name-only record with the full name from the export
    reason: str = ""


def _norm(name: str) -> str:
    return " ".join(name.split()).lower()


def _clean_email(value: str) -> str:
    value = (value or "").strip()
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def read_people(data: bytes) -> list[Person]:
    """One Person per email address (or per name when there's no email), however many bookings they appear in."""
    if len(data) > MAX_BYTES:
        raise ValueError("That file is too big – export just the attendees you need (under 2 MB).")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}

    def pick(names):
        return next((headers[n] for n in names if n in headers), None)

    def containing(*words):
        return next((original for low, original in headers.items() if any(w in low for w in words)), None)

    full, first, last = pick(NAME_HEADERS), pick(FIRST_HEADERS), pick(LAST_HEADERS)
    email, phone, booked = containing("email", "e-mail"), containing("phone", "mobile"), pick(BOOKED_HEADERS)
    if not (full or first):
        raise ValueError("Couldn't find a name column. The file needs a “Name” or “First name” column.")

    people = {}
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        name = (row.get(full) or "") if full else ""
        if not name.strip() and first:
            name = f"{row.get(first) or ''} {(row.get(last) or '') if last else ''}"
        name = " ".join(name.split())
        if not name:
            continue
        address = _clean_email(row.get(email) if email else "")
        key = address.lower() or _norm(name)
        person = people.get(key)
        if person is None:
            person = people[key] = Person(name=name, email=address)
        if phone and not person.phone:
            person.phone = " ".join((row.get(phone) or "").split())
        service = " ".join((row.get(booked) or "").split()) if booked else ""
        if service and service not in person.booked:
            person.booked.append(service)
    return list(people.values())


def match(people, students):
    """Pick a likely student for each person; anything uncertain is left for Liz to choose on the preview."""
    students = list(students)
    by_email = {s.email.lower(): s for s in students if s.email}
    by_name, by_first = defaultdict(list), defaultdict(list)
    for s in students:
        by_name[_norm(s.name)].append(s)
        if len(s.name.split()) == 1:
            by_first[_norm(s.name)].append(s)
    for person in people:
        exact = by_name.get(_norm(person.name), [])
        first_only = by_first.get(_norm(person.name.split()[0]), []) if len(person.name.split()) > 1 else []
        if person.email.lower() in by_email:
            person.student, person.reason = by_email[person.email.lower()], "Same email"
        elif len(exact) == 1:
            person.student, person.reason = exact[0], "Same name"
        elif exact or first_only:
            person.candidates = exact or first_only
            person.action, person.reason = "skip", "More than one possible match – choose who this is"
            if len(person.candidates) == 1:
                person.student, person.reason = person.candidates[0], "First name matches – check it’s the same person"
        else:
            person.reason = "No match – will be added as a new student"
        if person.student:
            person.action = str(person.student.pk)
            person.rename = _norm(person.student.name) != _norm(person.name) and len(person.student.name.split()) == 1
        if person.student and person.student not in person.candidates:
            person.candidates = [person.student, *person.candidates]
    return people

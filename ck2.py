#!/usr/bin/env python3
# ------------------------------------------------------------------
# Benötigte externe Pakete (per pip installieren):
#   pip install requests beautifulsoup4 python-dateutil icalendar
#
# Idee: DO7OO
# Phrasen: DO7OO
# Durchführung: ChatGPT Lizenziert
# ------------------------------------------------------------------
"""
Script to scrape DARC CT contest dates from the online calendar,
extract contest rows by detecting links in contest cells,
inherit dates from header rows (<strong>) including ranges,
and show a preview of
events filtered by month(s) and mode(s) parameters (SQL-like 'like' matching),
sorted and without duplicates, only for the current year.

Adds optional ICS calendar export with debug, robust file creation,
calendar name including selected modes, and purge option to cancel all events.

Usage:
  python ck.py [-m MONAT]... [-d MODE]... [-o ICS_FILE] [-p]
Options:
  -m, --month    Monat 1-12 für spezifischen Monat (mehrfach möglich; leer = alle)
  -d, --mode     Filter für das Mode-Feld im SQL LIKE Stil (case-insensitive, Leerzeichen ignoriert; mehrfach möglich)
  -o, --ics      Pfad zur Ausgabedatei im ICS-Format (optional)
  -p, --purge    Setze alle Conteste im ICS auf METHOD:CANCEL mit STATUS:CANCELLED
"""
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from dateutil import parser
import uuid
import os
try:
    from icalendar import Calendar, Event
except ImportError:
    raise ImportError("Module 'icalendar' nicht gefunden. Bitte installieren mit 'pip install icalendar'.")

URL = "https://www.darc.de/der-club/referate/conteste/ct-kalender/terminuebersicht/"


def scrape_all_contests():
    """Scrapes and returns all contest events for the current year."""
    current_year = date.today().year
    resp = requests.get(URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tbody tr")
    events = []
    current_start_date = None
    current_end_date = None

    for row in rows:
        tds = row.find_all("td")
        if not tds:
            continue
        strong = tds[0].find("strong")
        if strong:
            txt = strong.get_text(strip=True).replace(u"\u00A0", " ")
            parts = txt.split('-', 1)
            # parse start date
            first = parts[0].strip()
            parts1 = first.split('.', 1)
            date_part1 = parts1[1] if len(parts1) > 1 else parts1[0]
            if date_part1.count('.') < 2 and len(parts) > 1:
                year = parts[1].strip().split('.')[-1]
                date_part1 = f"{date_part1}.{year}"
            try:
                d1 = parser.parse(date_part1, dayfirst=True).date()
                current_start_date = d1.replace(year=current_year)
            except Exception:
                current_start_date = None
            # parse end date if present
            if len(parts) > 1:
                second = parts[1].strip()
                parts2 = second.split('.', 1)
                date_part2 = parts2[1] if len(parts2) > 1 else parts2[0]
                if date_part2.count('.') < 2:
                    year2 = parts[1].strip().split('.')[-1]
                    date_part2 = f"{date_part2}.{year2}"
                try:
                    d2 = parser.parse(date_part2, dayfirst=True).date()
                    current_end_date = d2.replace(year=current_year)
                except Exception:
                    current_end_date = current_start_date
            else:
                current_end_date = current_start_date
            continue
        link = tds[0].find('a')
        if link and current_start_date:
            title = link.get_text(strip=True)
            time_txt = tds[1].get_text(strip=True).replace(u"\u00A0", " ") if len(tds) > 1 else ''
            start_str, _, end_str = [s.strip() for s in time_txt.partition('-')]
            mode = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            note = tds[3].get_text(strip=True) if len(tds) > 3 else ''
            start_dt = None
            end_dt = None
            try:
                if start_str:
                    t1 = parser.parse(start_str).time()
                    start_dt = datetime.combine(current_start_date, t1)
                if end_str:
                    t2 = parser.parse(end_str).time()
                    dt_end_date = current_end_date or current_start_date
                    end_dt = datetime.combine(dt_end_date, t2)
            except Exception:
                pass
            if start_dt:
                events.append({
                    'title': title,
                    'start_dt': start_dt,
                    'end_dt': end_dt,
                    'mode': mode,
                    'note': note,
                })
    return events


def filter_events(events, months=None, modes=None):
    """Applies month and mode filters to the event list."""
    current_year = date.today().year
    pats = [m.lower().replace(' ', '') for m in modes] if modes else None
    out = []
    for e in events:
        if e['start_dt'].year != current_year and (not e['end_dt'] or e['end_dt'].year != current_year):
            continue
        if months:
            sm = e['start_dt'].month
            em = e['end_dt'].month if e['end_dt'] else None
            if sm not in months and (em not in months if em else True):
                continue
        if pats:
            mval = e['mode'].lower().replace(' ', '')
            if not any(pat in mval or mval in pat for pat in pats):
                continue
        out.append(e)
    return out


def export_to_ics(events, filename, calname=None, purge=False):
    """Exports given events to an ICS file, ensuring directory creation and setting calendar name.
    If purge=True, sets METHOD:CANCEL and each event's status to CANCELLED."""
    out_dir = os.path.dirname(os.path.abspath(filename))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    cal = Calendar()
    cal.add('prodid', '-//DARC CT Contest Calendar//darc.de//')
    cal.add('version', '2.0')
    if calname:
        cal.add('X-WR-CALNAME', calname)
    if purge:
        cal.add('METHOD', 'CANCEL')
    now = datetime.utcnow()
    for e in events:
        ev = Event()
        ev.add('uid', f"{uuid.uuid4()}@darc.de")
        ev.add('dtstamp', now)
        ev.add('dtstart', e['start_dt'])
        if e['end_dt']:
            ev.add('dtend', e['end_dt'])
        ev.add('summary', e['title'])
        desc = f"Mode: {e['mode']}"
        if e['note']:
            desc += f"\nNotiz: {e['note']}"
        ev.add('description', desc)
        if purge:
            ev.add('status', 'CANCELLED')
        cal.add_component(ev)
    try:
        with open(filename, 'wb') as f:
            f.write(cal.to_ical())
        mode = ' (PURGE: METHOD=CANCEL, STATUS=CANCELLED)' if purge else ''
        print(f"ICS-Datei '{filename}' erfolgreich erstellt{mode}.")
    except Exception as e:
        print(f"Fehler beim Schreiben der ICS-Datei: {e}")


def format_and_print_events(events):
    """Prints the events with neatly aligned columns, independent of shell tab width."""
    headers = [
        "Contest",
        "Startdatum",
        "Startzeit",
        "Enddatum",
        "Endzeit",
        "Mode",
        "Notiz",
    ]

    # Prepare rows once so we can both measure widths and print
    rows = []
    for e in events:
        sd = e['start_dt'].strftime('%d.%m.%Y')
        st = e['start_dt'].strftime('%H:%M')
        ed = e['end_dt'].strftime('%d.%m.%Y') if e['end_dt'] else ''
        et = e['end_dt'].strftime('%H:%M') if e['end_dt'] else ''
        rows.append([
            e['title'],
            sd,
            st,
            ed,
            et,
            e['mode'],
            e['note'],
        ])

    # Compute column widths (at least as wide as the header)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)

    # Print header
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))

    # Print rows
    if not rows:
        print("keine Einträge")
    else:
        for row in rows:
            print(fmt.format(*row))


def main():
    parser_args = argparse.ArgumentParser(description="DARC CT Contest CLI mit ICS-Export und Purge")
    parser_args.add_argument('-m', '--month', type=int, choices=range(1,13), action='append',
                             help='Monat 1-12 (mehrfach; leer = alle)')
    parser_args.add_argument('-d', '--mode', action='append',
                             help='Mode-Filter LIKE-Stil (mehrfach; Leerzeichen ok)')
    parser_args.add_argument('-o', '--ics', metavar='ICS_FILE',
                             help='Pfad zur Ausgabedatei im ICS-Format (optional)')
    parser_args.add_argument('-p', '--purge', action='store_true',
                             help='Setze alle Conteste im ICS auf METHOD:CANCEL mit STATUS:CANCELLED')
    args = parser_args.parse_args()

    events = scrape_all_contests()

    # De-duplicate
    seen = set()
    unique = []
    for e in events:
        key = (e['title'], e['start_dt'])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Filter & sort
    filtered = filter_events(unique, months=args.month, modes=args.mode)
    filtered.sort(key=lambda e: e['start_dt'])

    # Header line (kept for backward compatibility)
    base_title = "Contests"
    header_line = base_title
    if args.month:
        header_line += " MONATE=" + ",".join(str(m) for m in args.month)
    if args.mode:
        header_line += " MODE~'" + ",".join(args.mode) + "'"
    if args.purge:
        header_line += " - PURGE"
    print(header_line)

    # Aligned table print
    format_and_print_events(filtered)

    # Optional ICS export
    if args.ics:
        if not filtered:
            print("Warnung: Keine Events gefiltert, erstelle leere ICS-Datei.")
        cal_name = base_title
        if args.mode:
            cal_name += " - " + ",".join(args.mode)
        export_to_ics(filtered, args.ics, cal_name, purge=args.purge)


if __name__ == '__main__':
    main()


import argparse
import datetime
from pathlib import Path
from urllib.parse import urlparse
import re
import sys
import warnings

import icalendar
import requests
import pandas as pd
from bs4 import BeautifulSoup


ALL_VARIANTS = set(('shogi', 'xiangqi', 'janggi', 'makruk'))
FESA_URL = 'https://fesashogi.eu/calendar/'
DXB_URL = 'http://chinaschach.de/blog/events/list/?ical=1'
FFS_URL = 'https://shogi.fr/events/liste/?ical=1'
SNK_URL = 'https://shogi.es/calendario/lista/?ical=1'
TOURNEY_MOMENTUMS_URL = 'https://tourney-momentums.eu/tournaments/category/english/list/?ical=1'
SHOGIBOND_URL = 'https://shogibond.nl/toernooien/'

DUTCH_MONTHS = {
    'jan': 1,
    'januari': 1,
    'feb': 2,
    'februari': 2,
    'mrt': 3,
    'maart': 3,
    'mar': 3,
    'march': 3,
    'apr': 4,
    'april': 4,
    'mei': 5,
    'jun': 6,
    'juni': 6,
    'jul': 7,
    'juli': 7,
    'aug': 8,
    'augustus': 8,
    'sep': 9,
    'sept': 9,
    'september': 9,
    'okt': 10,
    'oktober': 10,
    'nov': 11,
    'november': 11,
    'dec': 12,
    'december': 12,
}


def get_content(target, params=None):
    response = requests.get(target, params=params)
    response.raise_for_status()
    return response.content


def get_variant(title, variants):
    assert ALL_VARIANTS.intersection(variants)
    words = set(title.lower().split())
    found = words.intersection(variants)
    if len(found) == 1:
        return found.pop().capitalize()
    else:
        return variants[0].capitalize()


def render_link(url):
    return "<a href='{}'>{}</a>".format(url, urlparse(url).netloc)


def get_ics_calendar(url, columns, variants):
    tournaments = []
    ics = get_content(url)
    if ics:
        gcal = icalendar.Calendar.from_ical(ics)
        for component in gcal.walk():
            if component.name == "VEVENT":
                tournament_url = component.get('url') or url
                dtend = component.decoded('dtend')
                # iCalendar uses exclusive end dates for all-day (DATE) events,
                # so subtract one day to get the actual inclusive last day.
                if type(dtend) is datetime.date:
                    dtend = dtend - datetime.timedelta(days=1)
                tournaments.append([
                    component.decoded('dtstart').strftime('%Y-%m-%d'),
                    dtend.strftime('%Y-%m-%d'),
                    get_variant(component.get('summary'), variants),
                    component.get('location'),
                    component.get('summary'),
                    render_link(tournament_url)
                ])
    else:
        warnings.warn(f'{url} does not return events')
    return pd.DataFrame(tournaments, columns=columns)


def get_html_calendar(url, columns):
    html = get_content(url)
    soup = BeautifulSoup(html, 'lxml')

    # Locate the container for upcoming tournaments
    container = soup.find('div', {'id': 'brxe-rxlvcv'})
    if not container:
        raise ValueError(f"No calendar data found on the page at {url}")

    # Extract rows for each tournament
    rows = container.find_all('div', class_='brxe-jbzoch')
    data = []

    for row in rows:
        # Extract start and end dates
        start_date_elem = row.find('div', class_='brxe-tbyczs')
        end_date_elem = row.find('div', class_='brxe-lvnbjn')
        
        # Get text content or empty string if element not found
        start_date = start_date_elem.text.strip() if start_date_elem else ''
        end_date = end_date_elem.text.strip() if end_date_elem else ''

        # Skip rows with missing start dates
        if not start_date:
            continue

        # Extract event name
        event_name_elem = row.find('div', class_='brxe-vzpxtn')
        event_name = event_name_elem.text.strip() if event_name_elem else ''

        # Extract location
        location_elem = row.find('div', class_='brxe-tdutfx')
        location = location_elem.text.strip() if location_elem else ''

        # Format dates
        try:
            start = datetime.datetime.strptime(start_date, '%d.%m.%Y').strftime('%Y-%m-%d')
        except ValueError:
            # Skip rows with invalid start date format
            continue
            
        # If end_date is missing or empty, treat as single-day event
        if not end_date:
            end = start
        else:
            try:
                end = datetime.datetime.strptime(end_date, '%d.%m.%Y').strftime('%Y-%m-%d')
            except ValueError:
                # If end_date format is invalid, treat as single-day event
                end = start

        # Append the extracted data
        data.append([start, end, 'Shogi', location, event_name, render_link(url)])

    # Create DataFrame
    df = pd.DataFrame(data, columns=columns)
    return df


def parse_dutch_date_cell(value, year):
    clean = value.replace('\xa0', ' ').strip().lower()
    clean = clean.replace('–', '-').replace('—', '-')
    clean = re.sub(r'\s+', ' ', clean)

    def month_of(name):
        key = name.strip().strip('.').lower()
        return DUTCH_MONTHS.get(key)

    def build_date(y, month, day):
        return datetime.date(y, month, day)

    parsed = None
    same_month_slash = re.match(r'^(\d{1,2})\s*/\s*(\d{1,2})\s+([a-z.]+)$', clean)
    same_month_dash = re.match(r'^(\d{1,2})\s*-\s*(\d{1,2})\s+([a-z.]+)$', clean)
    explicit_month_range = re.match(r'^(\d{1,2})\s+([a-z.]+)\s*-\s*(\d{1,2})\s+([a-z.]+)$', clean)
    single_day = re.match(r'^(\d{1,2})\s+([a-z.]+)$', clean)

    try:
        if same_month_slash:
            day1, day2, month_name = same_month_slash.groups()
            month = month_of(month_name)
            if month:
                parsed = (
                    build_date(year, month, int(day1)),
                    build_date(year, month, int(day2)),
                )
        elif same_month_dash:
            day1, day2, month_name = same_month_dash.groups()
            month = month_of(month_name)
            if month:
                parsed = (
                    build_date(year, month, int(day1)),
                    build_date(year, month, int(day2)),
                )
        elif explicit_month_range:
            day1, month1_name, day2, month2_name = explicit_month_range.groups()
            month1 = month_of(month1_name)
            month2 = month_of(month2_name)
            if month1 and month2:
                start = build_date(year, month1, int(day1))
                end = build_date(year, month2, int(day2))
                if end < start:
                    end = build_date(year + 1, month2, int(day2))
                parsed = (start, end)
        elif single_day:
            day, month_name = single_day.groups()
            month = month_of(month_name)
            if month:
                day_date = build_date(year, month, int(day))
                parsed = (day_date, day_date)
    except ValueError:
        parsed = None

    if parsed:
        return parsed[0].strftime('%Y-%m-%d'), parsed[1].strftime('%Y-%m-%d')
    return None


def get_shogibond_calendar(url, columns):
    html = get_content(url)
    soup = BeautifulSoup(html, 'lxml')
    tournaments = []

    for heading in soup.find_all('h3'):
        heading_text = heading.get_text(' ', strip=True)
        year_match = re.search(r'\b(20\d{2})\b', heading_text)
        if not year_match:
            continue
        year = int(year_match.group(1))
        table = heading.find_next('table')
        if not table:
            continue

        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 3:
                continue

            parsed_dates = parse_dutch_date_cell(cells[0].get_text(' ', strip=True), year)
            if not parsed_dates:
                date_text = cells[0].get_text(' ', strip=True)
                # TablePress sometimes contains month-only separator rows (e.g. "Okt").
                # Ignore those instead of warning.
                if date_text and date_text.strip().strip('.').lower() in DUTCH_MONTHS:
                    continue
                warnings.warn(f'Unparsed Dutch date in {url}: {date_text!r}')
                continue

            info_url = url
            if len(cells) >= 4:
                info_link = cells[3].find('a', href=True)
                if info_link:
                    info_url = info_link.get('href')

            tournaments.append([
                parsed_dates[0],
                parsed_dates[1],
                'Shogi',
                cells[2].get_text(' ', strip=True),
                cells[1].get_text(' ', strip=True),
                render_link(info_url)
            ])

    return pd.DataFrame(tournaments, columns=columns)


def prettify_location(locations):
    # street names
    locations.replace(to_replace=r'[^, ][^,]* \d+', value='', regex=True, inplace=True)
    # strip zip code from city
    locations.replace(to_replace=r'\d{4,6}|\d+\-\d+', value=r'', regex=True, inplace=True)
    # lengthy names
    locations.replace(to_replace='[^,]{30,}', value='', regex=True, inplace=True)
    # clean up by removing redundance and consolidating whitespacing
    return locations.apply(lambda x: ", ".join(dict.fromkeys(s.strip() for s in str(x or '-').split(',') if s.strip())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dry-run', action='store_true', help='Only print, do not write to file')
    parser.add_argument('-o', '--offline', action='store_true', help='Skip fetching new data')
    parser.add_argument('-u', '--unfiltered', action='store_true', help='Skip filtering')
    args = parser.parse_args()
    tsv_path = str((Path(__file__).absolute().parent.parent / '_data' / 'tournaments.tsv').resolve())
    current = pd.read_csv(tsv_path, sep='\t', header=0)
    calendars = [
        current
    ]
    if not args.offline:
        calendars.extend([
            #get_ics_calendar(TOURNEY_MOMENTUMS_URL, current.columns, ('shogi', 'xiangqi', 'janggi', 'makruk')),
            get_ics_calendar(DXB_URL, current.columns, ('xiangqi',)),
            get_ics_calendar(FFS_URL, current.columns, ('shogi',)),
            get_ics_calendar(SNK_URL, current.columns, ('shogi',)),
            get_html_calendar(FESA_URL, current.columns),
            get_shogibond_calendar(SHOGIBOND_URL, current.columns),
        ])
    merged = pd.concat(calendars)
    # try to remove street names, zip codes, and redundancy in location
    merged['location'] = prettify_location(merged['location'])
    # filter past and duplicate events
    if not args.unfiltered:
        merged = merged[merged['end-date'] >= datetime.datetime.today().strftime('%Y-%m-%d')]
        merged.drop_duplicates(subset=('start-date', 'variant', 'tournament'), keep='last', inplace=True)
        # do some more fuzzy matching
        merged['location2'] = merged['location'].apply(lambda s: re.match(r'^\w*', s).group())
        merged.drop_duplicates(subset=('start-date', 'end-date', 'variant', 'location2'), keep='last', inplace=True)
        merged = merged.drop(columns=['location2'])
    merged = merged.sort_values(by=['start-date', 'end-date', 'variant', 'location', 'tournament'])
    merged.to_csv(sys.stdout if args.dry_run else tsv_path, sep='\t', index=False)

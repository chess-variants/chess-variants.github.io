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
                tournaments.append([
                    component.decoded('dtstart').strftime('%Y-%m-%d'),
                    component.decoded('dtend').strftime('%Y-%m-%d'),
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
        start_date = row.find('div', class_='brxe-tbyczs').text.strip()
        end_date = row.find('div', class_='brxe-lvnbjn').text.strip()

        # Extract event name
        event_name = row.find('div', class_='brxe-vzpxtn').text.strip()

        # Extract location
        location = row.find('div', class_='brxe-tdutfx').text.strip()

        # Format dates
        start = datetime.datetime.strptime(start_date, '%d.%m.%Y').strftime('%Y-%m-%d')
        end = datetime.datetime.strptime(end_date, '%d.%m.%Y').strftime('%Y-%m-%d')

        # Append the extracted data
        data.append([start, end, 'Shogi', location, event_name, render_link(url)])

    # Create DataFrame
    df = pd.DataFrame(data, columns=columns)
    return df


def prettify_location(locations):
    # street names
    locations.replace(to_replace='[^, ][^,]* \d+', value='', regex=True, inplace=True)
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
            get_ics_calendar(TOURNEY_MOMENTUMS_URL, current.columns, ('shogi', 'xiangqi', 'janggi', 'makruk')),
            get_ics_calendar(DXB_URL, current.columns, ('xiangqi',)),
            get_ics_calendar(FFS_URL, current.columns, ('shogi',)),
            get_ics_calendar(SNK_URL, current.columns, ('shogi',)),
            get_html_calendar(FESA_URL, current.columns),
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

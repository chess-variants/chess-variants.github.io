import argparse
import datetime
from pathlib import Path
from urllib.parse import urlparse
import re
import sys

import icalendar
import requests
import pandas as pd


ALL_VARIANTS = set(('shogi', 'xiangqi', 'janggi', 'makruk'))
FESA_URL = 'http://fesashogi.eu/index.php?mid=2'
DXB_URL = 'http://chinaschach.de/blog/events/list/?ical=1'
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
    ics = get_content(url)
    gcal = icalendar.Calendar.from_ical(ics)
    tournaments = []
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
    return pd.DataFrame(tournaments, columns=columns)


def get_html_calendar(url, columns):
    html = get_content(url)
    df_list = pd.read_html(html, flavor='lxml')
    assert len(df_list) == 1
    df = df_list[-1]
    df.columns = ['Date', 'Event', 'Place', 'Info']
    # add year
    year_rows = df[df.Date.str.contains('^\d+$', regex=True, na=False)]
    years = tuple((row['Date'], index) for index, row in year_rows.iterrows())
    df['Year'] = years[0][0]
    for year, i in years:
        df['Year'][i:] = year
    df = df.drop(year_rows.index, axis=0)
    # reformat date
    df = df[df['Date'] != 'Date']
    df = df[df['Date'].notna()]
    df[['Start', 'End']] = df['Date'].str.split('-', expand=True)
    df['End'] = df.End.combine_first(df.Start)
    def reformat_date(row, col):
        return datetime.datetime.strptime(row[col].strip(), '%d %b').replace(year=int(row['Year'])).strftime('%Y-%m-%d')
    df['Start'] = df.apply(lambda r: reformat_date(r, 'Start'), axis=1)
    df['End'] = df.apply(lambda r: reformat_date(r, 'End'), axis=1)
    # add additional info
    df['Source'] = render_link(url)
    df['Variant'] = 'Shogi'
    df = df[['Start', 'End', 'Variant', 'Place', 'Event', 'Source']]
    df.columns = columns
    return df


def prettify_location(locations):
    # street names
    locations.replace(to_replace='[^, ][^,]* \d+', value='', regex=True, inplace=True)
    # strip zip code from city
    locations.replace(to_replace=r'\d{4,6}|\d+\-\d+', value=r'', regex=True, inplace=True)
    # clean up by removing redundance and consolidating whitespacing
    return locations.apply(lambda x: ", ".join(dict.fromkeys(s.strip() for s in x.split(',') if s.strip())))


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

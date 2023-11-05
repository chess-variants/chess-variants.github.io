import datetime
from pathlib import Path

import requests
import pandas as pd


def get_html(target, params=None):
    response = requests.get(target, params=params)
    response.raise_for_status()
    return response.content


def get_fesa_tourneys():
    URL = 'http://fesashogi.eu/index.php?mid=2'
    html = get_html(URL)
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
    df['End'] = df.Start.combine_first(df.End)
    def reformat_date(row, col):
        return datetime.datetime.strptime(row[col].strip(), '%d %b').replace(year=int(row['Year'])).strftime('%Y-%m-%d')
    df['Start'] = df.apply(lambda r: reformat_date(r, 'Start'), axis=1)
    df['End'] = df.apply(lambda r: reformat_date(r, 'End'), axis=1)
    # try to remove street names and zip codes in location
    df['Place'].replace(to_replace='[^, ][^,]* \d+,\s*', value='', regex=True, inplace=True)
    df['Place'].replace(to_replace='\d+(-\d+)? (\w+)', value=r'\2', regex=True, inplace=True)
    # add additional info
    df['Source'] = "<a href='{}'>fesashogi.eu</a>".format(URL)
    df['Variant'] = 'Shogi'
    return df[['Start', 'End', 'Variant', 'Place', 'Event', 'Source']]


def merge(current, new):
    new.columns = current.columns
    return pd.concat([
        current[current['tournament'].isin(new['tournament']) == False],
        new,
    ]).sort_values(by=['start-date'])


if __name__ == '__main__':
    tsv_path = str((Path(__file__).absolute().parent.parent / '_data' / 'tournaments.tsv').resolve())
    current = pd.read_csv(tsv_path, sep='\t', header=0)
    new = get_fesa_tourneys()
    merged = merge(current, new)
    # filter past events
    merged = merged[merged['end-date'] >= datetime.datetime.today().strftime('%Y-%m-%d')]
    merged.to_csv(tsv_path, sep='\t', index=False)

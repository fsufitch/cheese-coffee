from argparse import ArgumentParser
from contextlib import redirect_stderr, redirect_stdout
import csv
from itertools import chain, combinations
import logging
import shutil
import sqlite3
import sys
from emojis import count
import emojis
import requests
import progressbar
from dataclasses import dataclass
from typing import Any, Collection, Container, FrozenSet, Iterable, List, Mapping, Optional, Set
from emojis.db import Emoji, get_emoji_by_code

from alive_progress import alive_bar, alive_it

logging.basicConfig(level=logging.INFO)

EMOJI_KITCHEN_URL = 'https://tenor.googleapis.com/v2/featured?key=AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ&collection=emoji_kitchen_v5&q={}'
ALLOWED_CATEGORIES = {'Animals & Nature', 'Objects', 'Food & Drink',
                      'Smileys & Emotion', 'Symbols', 'Travel & Places', 'People & Body'}

# ALLOWED_CATEGORIES = {'Animals & Nature', 'Objects', 'Flags', 'Food & Drink',
#                       'Smileys & Emotion', 'Symbols', 'Activities', 'Travel & Places', 'People & Body'}


@dataclass(frozen=True)
class EmojiKitchenSticker:
    id: str
    symbols: FrozenSet[str]
    url: str
    created_time: int

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, EmojiKitchenSticker) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


def read_emoji_csv(path: str) -> List[str]:
    logging.info("Reading supported emoji CSV: %s", path)
    symbols: Set[str] = set()
    with open(path) as f:
        reader = csv.reader(f)
        for line in reader:
            symbol = line[0][0]
            symbols.add(symbol)

    emoji_map: Mapping[str, Emoji] = {}
    for symbol in symbols:
        emoji: Optional[Emoji] = get_emoji_by_code(symbol)
        if emoji:
            emoji_map[symbol] = emoji

    filtered_emojis = [symbol for symbol, emoji in emoji_map.items(
    ) if emoji.category in ALLOWED_CATEGORIES]

    logging.info("Found %d supported emojis", len(filtered_emojis))
    return filtered_emojis


def emoji_kitchen_build_queries(symbols: Collection[str]) -> List[str]:
    logging.info("Building search URLs for %d symbols", len(symbols))
    queries: List[str] = []

    # Search for the symbol by itself
    queries.extend(symbol for symbol in symbols)

    # Search for the symbol together with itself
    queries.extend(f"{symbol}_{symbol}" for symbol in symbols)

    for s1, s2 in combinations(symbols, 2):
        queries.append(f"{s1}_{s2}")
        queries.append(f"{s2}_{s1}")

    queries.sort()
    logging.info("%s symbols => %s queries", len(symbols), len(queries))
    return queries

def emoji_kitchen_progress_bar(queries: Collection[str]) -> Iterable[str]:
    bar = alive_it(queries, length=25, force_tty=True)
    for item in bar:
        bar.text(item)
        yield item

def emoji_kitchen_query(query: str) -> Iterable[EmojiKitchenSticker]:
    url = EMOJI_KITCHEN_URL.format(query)
    data = requests.get(url).json()

    assert (not data.get('error')) or (
        data.get('error', {}).get('code') == 404)

    count = 0
    for result in data.get("results", []):
        id = result.get('id')
        assert id and isinstance(id, str)

        url = result.get('url')
        assert url and isinstance(url, str)

        created_time = result.get('created')
        assert created_time and isinstance(created_time, int)

        tags: List[str] = result.get('tags')
        assert tags and isinstance(tags, list) and all(
            isinstance(tag, str) for tag in tags)

        symbols = frozenset(tag[0] for tag in tags)

        yield EmojiKitchenSticker(id, symbols, url, created_time)
        count += 1


def init_db_schema(db: sqlite3.Connection):
    logging.info("Init result database schema")
    db.execute(
        "CREATE TABLE IF NOT EXISTS stickers (id TEXT, symbols TEXT, url TEXT, created_time INTEGER)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_stickers ON stickers (id)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS sticker_lookup (symbol1 TEXT, symbol2 TEXT, sticker_id TEXT)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sticker_lookup ON sticker_lookup (symbol1, symbol2)")


def db_write_sticker(db: sqlite3.Connection, sticker: EmojiKitchenSticker):
    db.execute("INSERT INTO stickers VALUES (?, ?, ?, ?)", (sticker.id,
               ''.join(sticker.symbols), sticker.url, sticker.created_time))

    symbols = [*sticker.symbols]
    if not symbols:
        return
    if len(symbols) == 1:
        # Special case of comboing with itself
        single_symbol = next(iter(symbols))
        symbols = [single_symbol, single_symbol]

    pairs = combinations(symbols, 2)

    for symbol1, symbol2 in pairs:
        db.execute("INSERT INTO sticker_lookup VALUES (?, ?, ?)",
                   (symbol1, symbol2, sticker.id))


def cli():
    parser = ArgumentParser(
        description="Scan the online emoji kitchen database")
    parser.add_argument('emojis_csv', type=str,
                        help="concatenated CSVs from the GBoard APK, listing supported emojis")
    parser.add_argument('output_db', type=str,
                        help="destination file to write the SQLite3 database to")
    return parser.parse_args()


def main():
    cli_namespace = cli()
    csv_input: str = cli_namespace.emojis_csv
    sqlite_output: str = cli_namespace.output_db

    supported_emojis = read_emoji_csv(csv_input)
    queries = emoji_kitchen_build_queries(supported_emojis)

    stickers: Set[EmojiKitchenSticker] = set()
    for query in emoji_kitchen_progress_bar(queries):
        stickers.update(emoji_kitchen_query(query))

    logging.info("Finished indexing sticker API. Stickers: %d", len(stickers))
    logging.info("Actual supported emoji: %s", ''.join(
        frozenset(chain(*(sticker.symbols for sticker in stickers)))))

    with sqlite3.connect(sqlite_output) as db:
        init_db_schema(db)

        logging.info("Writing %d stickers to db", len(stickers))
        for sticker in stickers:
            db_write_sticker(db, sticker)

    logging.info("Emoji Kitchen scan complete")


if __name__ == '__main__':
    main()

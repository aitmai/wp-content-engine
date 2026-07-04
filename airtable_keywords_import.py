"""
airtable_keywords_import.py

Pushes docs/keyword-research-airdoctor.csv into the Airtable "Keywords" table
(see docs/airtable-schema.md for the expected field schema).

Usage:
    python airtable_keywords_import.py --csv docs/keyword-research-airdoctor.csv

Requires .env (see .env.example) with:
    AIRTABLE_BASE_ID
    AIRTABLE_PERSONAL_ACCESS_TOKEN

Set AIRTABLE_KEYWORDS_TABLE_NAME below or via env var if it differs from "Keywords".
"""

import argparse
import csv
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_PERSONAL_ACCESS_TOKEN")
KEYWORDS_TABLE = os.environ.get("AIRTABLE_KEYWORDS_TABLE_NAME", "Keywords")

API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{KEYWORDS_TABLE}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}

# Airtable REST API accepts max 10 records per batch create
BATCH_SIZE = 10


def load_rows(csv_path: str) -> list:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            fields = {
                "Keyword": row["Keyword"],
                "Intent": row["Intent"],
                "Priority": row["Priority"],
                "SourceNote": row["SourceNote"],
                "Status": row["Status"],
                "DateAdded": row["DateAdded"],
            }
            # Only include numeric fields if populated (avoid sending empty strings
            # to Airtable number fields, which will error)
            if row.get("SearchVolume"):
                fields["SearchVolume"] = float(row["SearchVolume"])
            if row.get("KeywordDifficulty"):
                fields["KeywordDifficulty"] = float(row["KeywordDifficulty"])
            rows.append({"fields": fields})
    return rows


def push_batch(records: list) -> dict:
    resp = requests.post(API_URL, headers=HEADERS, json={"records": records}, timeout=30)
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Import keyword CSV into Airtable")
    parser.add_argument("--csv", required=True, help="Path to keyword research CSV")
    args = parser.parse_args()

    if not (AIRTABLE_BASE_ID and AIRTABLE_TOKEN):
        sys.exit("Missing AIRTABLE_BASE_ID / AIRTABLE_PERSONAL_ACCESS_TOKEN in .env")

    all_rows = load_rows(args.csv)
    print(f"Loaded {len(all_rows)} keyword rows from {args.csv}")

    created = 0
    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i : i + BATCH_SIZE]
        result = push_batch(batch)
        created += len(result.get("records", []))
        print(f"  Pushed batch {i // BATCH_SIZE + 1}: {len(batch)} records")
        time.sleep(0.25)  # stay well under Airtable's rate limit

    print(f"Done. {created} keyword records created in Airtable table '{KEYWORDS_TABLE}'.")


if __name__ == "__main__":
    main()

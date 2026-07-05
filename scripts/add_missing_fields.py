"""
add_missing_fields.py

Your Sites, ContentPipeline, and Keywords tables already exist (created
manually in the Airtable UI) but are missing most fields, including the
link fields that connect them. This script adds everything that's missing
via Airtable's Metadata API — it's idempotent, so re-running it is safe:
existing fields are left untouched, only missing ones are added.

Order matters: Sites' fields are added first, then ContentPipeline's
(including its link to Sites), then Keywords' (including its links to
both Sites and ContentPipeline) — because a link field needs its target
table to already exist and be known before it can be created.

Requires .env (see .env.example) with:
    AIRTABLE_BASE_ID
    AIRTABLE_PERSONAL_ACCESS_TOKEN   (needs schema.bases:write + schema.bases:read scopes)

Usage:
    python add_missing_fields.py
"""

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_PERSONAL_ACCESS_TOKEN")

META_BASE = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json",
}


def get_tables() -> list:
    resp = requests.get(f"{META_BASE}/tables", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()["tables"]


def find_table(tables: list, name: str) -> dict:
    for t in tables:
        if t["name"] == name:
            return t
    sys.exit(f"Table '{name}' not found in base. Create it in the Airtable UI first.")


def existing_field_names(table: dict) -> set:
    return {f["name"] for f in table["fields"]}


def create_field(table_id: str, field_def: dict):
    resp = requests.post(
        f"{META_BASE}/tables/{table_id}/fields", headers=HEADERS, json=field_def, timeout=30
    )
    if resp.status_code not in (200, 201):
        print(f"  FAILED to create '{field_def['name']}': {resp.status_code} {resp.text}")
        return
    print(f"  + created field: {field_def['name']}")
    time.sleep(0.3)


def rename_field(table_id: str, field_id: str, new_name: str):
    resp = requests.patch(
        f"{META_BASE}/tables/{table_id}/fields/{field_id}",
        headers=HEADERS,
        json={"name": new_name},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"  FAILED to rename field to '{new_name}': {resp.status_code} {resp.text}")
        return
    print(f"  ~ renamed field to: {new_name}")
    time.sleep(0.3)


def add_missing(table: dict, field_defs: list):
    have = existing_field_names(table)
    print(f"\n{table['name']}: {len(have)} existing field(s)")
    for field_def in field_defs:
        if field_def["name"] in have:
            print(f"  = already exists, skipping: {field_def['name']}")
            continue
        create_field(table["id"], field_def)


def sites_fields() -> list:
    return [
        {"name": "WPBaseURL", "type": "url"},
        {"name": "WPUsername", "type": "singleLineText"},
        {"name": "WPAppPassword", "type": "singleLineText"},
        {"name": "ContentVoicePrompt", "type": "multilineText"},
        {"name": "DefaultCategories", "type": "multilineText"},
        {"name": "Niche", "type": "singleLineText"},
        {"name": "Active", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
    ]


def content_pipeline_fields(sites_table_id: str) -> list:
    return [
        {"name": "PostTitle", "type": "singleLineText"},
        {
            "name": "SiteId",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": sites_table_id, "prefersSingleRecordLink": True},
        },
        {
            "name": "PostType",
            "type": "singleSelect",
            "options": {"choices": [{"name": "New"}, {"name": "Refresh"}]},
        },
        {
            "name": "Category",
            "type": "singleSelect",
            "options": {"choices": [{"name": "Uncategorized"}]},
        },
        {
            "name": "LastUpdated",
            "type": "dateTime",
            "options": {
                "dateFormat": {"name": "us"},
                "timeFormat": {"name": "12hour"},
                "timeZone": "client",
            },
        },
        {"name": "ModelsChecked", "type": "multilineText"},
        {
            "name": "Status",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "Pending Review"},
                    {"name": "Approved"},
                    {"name": "Published"},
                    {"name": "Needs Revision"},
                ]
            },
        },
        {"name": "WPEditLink", "type": "url"},
        {"name": "ReviewerNotes", "type": "multilineText"},
        {"name": "PriceLastChecked", "type": "date", "options": {"dateFormat": {"name": "us"}}},
        {"name": "BrokenLinksFound", "type": "number", "options": {"precision": 0}},
    ]


def keywords_fields(sites_table_id: str, content_pipeline_table_id: str) -> list:
    return [
        {
            "name": "SiteId",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": sites_table_id, "prefersSingleRecordLink": True},
        },
        {
            "name": "Intent",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "Comparison"},
                    {"name": "Cost-of-ownership"},
                    {"name": "Model-selection"},
                    {"name": "Seasonal/Problem"},
                    {"name": "Transactional"},
                    {"name": "Broad/Competitive"},
                ]
            },
        },
        {
            "name": "Priority",
            "type": "singleSelect",
            "options": {"choices": [{"name": "High"}, {"name": "Medium"}, {"name": "Low"}]},
        },
        {"name": "SearchVolume", "type": "number", "options": {"precision": 0}},
        {"name": "KeywordDifficulty", "type": "number", "options": {"precision": 0}},
        {"name": "SourceNote", "type": "multilineText"},
        {
            "name": "LinkedPost",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": content_pipeline_table_id, "prefersSingleRecordLink": True},
        },
        {
            "name": "Status",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "Researched"},
                    {"name": "Assigned"},
                    {"name": "In Content"},
                    {"name": "Live"},
                ]
            },
        },
        {"name": "DateAdded", "type": "date", "options": {"dateFormat": {"name": "us"}}},
    ]


def main():
    if not (AIRTABLE_BASE_ID and AIRTABLE_TOKEN):
        sys.exit("Missing AIRTABLE_BASE_ID / AIRTABLE_PERSONAL_ACCESS_TOKEN in .env")

    tables = get_tables()
    sites = find_table(tables, "Sites")
    content_pipeline = find_table(tables, "ContentPipeline")
    keywords = find_table(tables, "Keywords")

    # 1. Sites — no dependencies
    add_missing(sites, sites_fields())

    # 2. ContentPipeline — links to Sites
    add_missing(content_pipeline, content_pipeline_fields(sites_table_id=sites["id"]))

    # 3. Keywords — links to Sites and ContentPipeline
    #    Also rename the default 'Name' primary field to 'Keyword' if present.
    keyword_field_names = existing_field_names(keywords)
    if "Name" in keyword_field_names and "Keyword" not in keyword_field_names:
        name_field = next(f for f in keywords["fields"] if f["name"] == "Name")
        print(f"\n{keywords['name']}: renaming primary field")
        rename_field(keywords["id"], name_field["id"], "Keyword")
        # refresh local copy so add_missing doesn't try to re-add 'Keyword'
        keywords["fields"] = [
            f if f["id"] != name_field["id"] else {**f, "name": "Keyword"}
            for f in keywords["fields"]
        ]

    add_missing(
        keywords,
        keywords_fields(
            sites_table_id=sites["id"], content_pipeline_table_id=content_pipeline["id"]
        ),
    )

    print("\nDone. Re-run anytime — already-existing fields are skipped automatically.")
    print("Next: add at least one row to Sites, then link ContentPipeline/Keywords rows to it.")


if __name__ == "__main__":
    main()

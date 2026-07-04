# wp-content-engine

A reusable automated content pipeline for **any WordPress site**: researches keywords, drafts posts using Claude in that site's own voice, and publishes with a human-approval gate before anything goes live.

Originally built for [indoorbreathing.com](https://indoorbreathing.com) (AirDoctor comparison content), now generalized to run any number of WordPress sites off the same infrastructure.

## What this does

```
n8n (cron)
  → Airtable "Sites" table: pull all Active sites
  → For each site: Airtable "Keywords" table: pull keywords marked "Assigned"
  → For each keyword: fetch product/topic data (Amazon PA-API, or your own source)
  → Claude API via Cloudflare Worker: generate draft, using that SITE's own voice prompt
  → WordPress REST API (that site's own credentials): push as DRAFT
  → Airtable "ContentPipeline" table: log entry, linked to the Site, Status: Pending Review
  → [human approval in Airtable]
  → n8n webhook: publish trigger → Cloudflare Worker → that site's WordPress → publish
```

**What makes it multi-site:** WordPress credentials, content voice, and niche context all live as *data* in the Airtable `Sites` table, not hardcoded in the Worker or n8n workflow. Adding a new site means adding a row to `Sites` — no code changes.

## Repo structure

```
wp-content-engine/
├── n8n/
│   └── content-pipeline-workflow.json   # Multi-site workflow: loops over Sites, then Keywords per site
├── worker/
│   └── cloudflare-worker.js             # Site-agnostic proxy: Claude gen + WP draft/publish, creds passed per-request
├── scripts/
│   ├── wordpress_publish.py             # Manual WP draft/publish/link-check, works against any site via CLI flags
│   └── airtable_keywords_import.py      # Bulk-import keyword research CSVs into the Keywords table
├── docs/
│   ├── airtable-schema.md               # Sites, ContentPipeline, and Keywords table schemas
│   └── keyword-research-airdoctor.csv   # Example keyword research (IndoorBreathing/AirDoctor)
├── .env.example
├── .gitignore
└── LICENSE
```

## Installation

### Prerequisites
- Node.js + npm (for Cloudflare Wrangler CLI)
- Python 3.9+ (for the helper scripts)
- An Airtable account
- A Cloudflare account (free tier is fine)
- An n8n instance (self-hosted or n8n Cloud)
- At least one WordPress site with admin access

---

### Step 1: Set up Airtable

1. Create a new base — name it `WP Content Engine`
2. Build three tables per `docs/airtable-schema.md`:
   - **`Sites`** — SiteName, WPBaseURL, WPUsername, WPAppPassword, ContentVoicePrompt, DefaultCategories, Niche, Active (checkbox)
   - **`ContentPipeline`** — Site (link), PostID, PostTitle, PostType, Category, LastUpdated, ModelsChecked, Status, WPEditLink, ReviewerNotes, PriceLastChecked, BrokenLinksFound
   - **`Keywords`** — Site (link), Keyword, Intent, Priority, SearchVolume, KeywordDifficulty, SourceNote, LinkedPost (link), Status, DateAdded
3. Add one row to `Sites` for your first WordPress site (leave WP credentials blank for now — fill in after Step 2)
4. Get your **Base ID**: open the base → Help → API documentation (URL starts with `app...`)
5. Get a **Personal Access Token**: account icon → Developer Hub → Personal access tokens → Create token (scopes: `data.records:read`, `data.records:write`, `schema.bases:read` on this base)

**Build order matters:** create `Sites` first, then `ContentPipeline` and `Keywords` — the "Link to another record" fields need `Sites` to already exist to link against.

**Field types reference:**

**`Sites`**

| Field | Type |
|---|---|
| `SiteName` | Single line text (primary field) |
| `WPBaseURL` | URL |
| `WPUsername` | Single line text |
| `WPAppPassword` | Single line text |
| `ContentVoicePrompt` | Long text |
| `DefaultCategories` | Long text |
| `Niche` | Single line text |
| `Active` | Checkbox |

**`ContentPipeline`**

| Field | Type |
|---|---|
| `SiteId` | Link to another record (→ `Sites`) |
| `PostID` | Number |
| `PostTitle` | Single line text |
| `PostType` | Single select (`New`, `Refresh`) |
| `Category` | Single select (options per niche) |
| `LastUpdated` | Date (with time) |
| `ModelsChecked` | Long text |
| `Status` | Single select (`Pending Review`, `Approved`, `Published`, `Needs Revision`) |
| `WPEditLink` | URL |
| `ReviewerNotes` | Long text |
| `PriceLastChecked` | Date |
| `BrokenLinksFound` | Number |

**`Keywords`**

| Field | Type |
|---|---|
| `SiteId` | Link to another record (→ `Sites`) |
| `Keyword` | Single line text (primary field) |
| `Intent` | Single select (`Comparison`, `Cost-of-ownership`, `Model-selection`, `Seasonal/Problem`, `Transactional`, `Broad/Competitive`) |
| `Priority` | Single select (`High`, `Medium`, `Low`) |
| `SearchVolume` | Number |
| `KeywordDifficulty` | Number |
| `SourceNote` | Long text |
| `LinkedPost` | Link to another record (→ `ContentPipeline`) |
| `Status` | Single select (`Researched`, `Assigned`, `In Content`, `Live`) |
| `DateAdded` | Date |

---

### Step 2: Set up WordPress

1. On your site's admin dashboard, go to **Users → Profile**
2. Scroll to **Application Passwords**, enter a name (e.g. "wp-content-engine"), click **Add New Application Password**
3. Copy the generated password immediately — it's shown only once
4. Confirm the REST API responds: visit `https://yoursite.com/wp-json/wp/v2/posts` in a browser
5. Go back to your `Sites` row in Airtable and fill in: `WPBaseURL`, `WPUsername`, `WPAppPassword`

---

### Step 3: Deploy the Cloudflare Worker

```bash
npm install -g wrangler
wrangler login
```

1. Create a new Worker project locally, copy `worker/cloudflare-worker.js` in as the main script
2. Set secrets:
```bash
wrangler secret put ANTHROPIC_API_KEY
wrangler secret put N8N_WEBHOOK_SECRET
```
3. Deploy:
```bash
wrangler deploy
```
4. Note the deployed URL (e.g. `https://wp-content-engine.yoursubdomain.workers.dev`)

---

### Step 4: Configure environment variables

1. Copy `.env.example` to `.env`
2. Fill in:
   - `ANTHROPIC_API_KEY`
   - `AIRTABLE_BASE_ID`, `AIRTABLE_PERSONAL_ACCESS_TOKEN`
   - `CLOUDFLARE_WORKER_URL` (from Step 3)
   - `N8N_WEBHOOK_SECRET` (same value used in Step 3)
   - Leave `WP_*` vars blank or as local-dev fallback only — real credentials live in Airtable

---

### Step 5: Install Python script dependencies

```bash
pip install requests python-dotenv --break-system-packages
```

Test the connection manually before wiring up n8n:
```bash
python scripts/wordpress_publish.py draft \
  --title "Test Post" \
  --content-file test.html \
  --wp-base-url https://yoursite.com \
  --wp-username your_username \
  --wp-app-password "xxxx xxxx xxxx xxxx"
```
Confirm it creates a draft in WordPress before moving on.

---

### Step 6: Import keyword research (optional, if starting with the AirDoctor example)

```bash
python scripts/airtable_keywords_import.py --csv docs/keyword-research-airdoctor.csv
```
Or import the CSV directly through Airtable's UI (Add or import → CSV).

---

### Step 7: Set up n8n

1. Open your n8n instance → Workflows → Import from File
2. Select `n8n/content-pipeline-workflow.json`
3. Configure credentials inside n8n:
   - Airtable Personal Access Token
   - HTTP Header Auth (if using Amazon PA-API or another product-data source)
4. Set environment variables n8n needs access to: `AIRTABLE_BASE_ID`, `CLOUDFLARE_WORKER_URL`, `N8N_WEBHOOK_SECRET`
5. Adjust the cron schedule if you don't want the default (weekly, Mondays 9am)
6. **Do not activate yet** — test with a manual execution first

---

### Step 8: Set up the Airtable approval automation

1. In Airtable, go to **Automations** on the `ContentPipeline` table
2. Trigger: `Status` field updates to `Approved`
3. Action: Send webhook → your n8n publish-webhook URL, payload: `{ "post_id": "{{PostID}}", "site_id": "{{SiteId}}" }`
4. This requires a second, smaller n8n workflow (webhook trigger → look up Site credentials → call Worker's `/wp/publish`) — **not yet included** in `n8n/content-pipeline-workflow.json`, so build this one manually in n8n's editor for now

---

### Step 9: Test end-to-end

1. Add a test keyword to `Keywords`, mark it `Assigned`, link it to your site
2. Manually execute the n8n workflow
3. Check WordPress for a new draft, and Airtable's `ContentPipeline` for the log entry
4. Flip `Status` to `Approved` in Airtable, confirm the post goes live on WordPress
5. Once confirmed working, activate the n8n workflow on its schedule

## Human-in-the-loop by design

Posts are pushed to WordPress as **drafts only**. Nothing publishes without a status flip in Airtable triggering the n8n publish webhook. This holds true per-site — fully autonomous publishing on any monetized content site is a real SEO and trust risk.

## Adding a new site

1. Add a row to the `Sites` table: URL, WP credentials, voice prompt, niche
2. Research keywords for that niche (manually via Google Keyword Planner, or via the automated Google Ads API service once built) and import into `Keywords`, linked to the new site
3. The next scheduled n8n run picks up the new site automatically

## Roadmap

- **Phase 1 (done):** Single-site content pipeline (IndoorBreathing/AirDoctor) — draft → review → publish loop
- **Phase 2 (done):** Generalized to multi-site — Sites table, site-agnostic Worker, per-site voice/credentials
- **Phase 2.5 (not yet built):** Publish-webhook n8n workflow — webhook trigger → look up Site credentials in Airtable → call Worker's `/wp/publish`. Referenced in Installation Step 8; needs to be built manually in n8n until it's added to this repo.
- **Phase 3:** Automated keyword research service — Flask/Render service calling the Google Ads API (Keyword Planner) on a schedule, feeding new/trending keywords into the `Keywords` table automatically, with YoY-spike alerting
- **Phase 4:** Broken/dead affiliate link scanner (scheduled n8n job, per site)
- **Phase 5:** Interactive tools (e.g. cost-of-ownership calculators) — React, Vercel-hosted, embedded via iframe per site

---
MIT © 2026 aitmai

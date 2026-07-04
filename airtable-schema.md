# Airtable Schema — wp-content-engine (Multi-Site)

Base name suggestion: `WP Content Engine`

This base has **three tables**. `Sites` is new — it's what makes the rest of the pipeline reusable across any WordPress site instead of hardcoded to one.

---

## Table 1: `Sites`

One row per WordPress site the engine manages. Everything else (`ContentPipeline`, `Keywords`) links back to a row here.

| Field name | Type | Notes |
|---|---|---|
| `SiteName` | Single line text | Primary field, e.g. "IndoorBreathing", "Old Man's Ride Blog" |
| `WPBaseURL` | URL | e.g. `https://indoorbreathing.com` — no trailing slash |
| `WPUsername` | Single line text | WordPress admin username with an Application Password |
| `WPAppPassword` | Single line text | ⚠️ See security note below |
| `ContentVoicePrompt` | Long text | The site's voice/style instructions — passed as Claude's system prompt. This is what lets the same engine write in IndoorBreathing's review-site voice for one site and, say, Old Man's Ride's "posh BBC narrator" voice for another |
| `DefaultCategories` | Long text | Comma-separated WP category IDs to default new drafts into |
| `Niche` | Single line text | e.g. "Air quality / HVAC products", "Motorcycle culture" — gives context to keyword research and content prompts |
| `Active` | Checkbox | Toggle a site on/off without deleting its config |

**⚠️ Security note:** Airtable is not a secrets vault. Storing `WPAppPassword` here is convenient but means anyone with base access can see it. For a solo operation this is a reasonable tradeoff, but if you ever add collaborators, move credentials to a proper secrets manager (Cloudflare Worker secrets, Doppler, 1Password Connect, etc.) and have this field just reference which secret to look up instead of holding the raw value.

---

## Table 2: `ContentPipeline`

| Field name | Type | Notes |
|---|---|---|
| `SiteId` | Link to another record | → `Sites` table. **New** — every post now belongs to a site |
| `PostID` | Number | WordPress post ID (unique per site, not globally) |
| `PostTitle` | Single line text | |
| `PostType` | Single select | `New`, `Refresh` |
| `Category` | Single select | Expand per-niche as needed, e.g. `AirDoctor Comparison`, `Filter Cost` for IndoorBreathing; different categories for other sites |
| `LastUpdated` | Date (with time) | Timestamp of last automated draft push |
| `ModelsChecked` | Long text | Audit trail of what was verified (products, specs, facts) |
| `Status` | Single select | `Pending Review` → `Approved` → `Published` → `Needs Revision` |
| `WPEditLink` | URL | Direct link to WP editor for the draft |
| `ReviewerNotes` | Long text | Manual notes from human review pass |
| `PriceLastChecked` | Date | For product-review sites — track price-refresh cadence separately from content updates |
| `BrokenLinksFound` | Number | Populated by the link-checker job |

### Automation (Airtable side)

- **Trigger:** `Status` field updates to `Approved`
- **Action:** Send a webhook to your n8n publish-webhook URL with `{ "post_id": "{{PostID}}", "site_id": "{{SiteId}}" }` — n8n uses `site_id` to look up that site's WP credentials from the `Sites` table before calling the Worker's `/wp/publish` route.

### Views to set up

- **Pending Review** — filter `Status = Pending Review`, grouped by `Site`, sorted by `LastUpdated`
- **Stale Content** — filter `LastUpdated` older than 6 months, grouped by `Site`
- **Published Log** — filter `Status = Published` — audit trail / content calendar history per site

---

## Table 3: `Keywords`

| Field name | Type | Notes |
|---|---|---|
| `SiteId` | Link to another record | → `Sites` table. **New** — keyword research is now scoped per site/niche |
| `Keyword` | Single line text | Primary field |
| `Intent` | Single select | `Comparison`, `Cost-of-ownership`, `Model-selection`, `Seasonal/Problem`, `Transactional`, `Broad/Competitive` — adjust options per niche as needed |
| `Priority` | Single select | `High`, `Medium`, `Low` |
| `SearchVolume` | Number | From Keyword Planner/Ahrefs/Ubersuggest |
| `KeywordDifficulty` | Number | From your SEO tool of choice |
| `SourceNote` | Long text | Why this keyword made the list / what data backs it |
| `LinkedPost` | Link to another record | → `ContentPipeline`, once a post is drafted for this keyword |
| `Status` | Single select | `Researched`, `Assigned`, `In Content`, `Live` |
| `DateAdded` | Date | |

A starter CSV for IndoorBreathing (`docs/keyword-research-airdoctor.csv`) is included as an example — import it, then link each row to the IndoorBreathing record in `Sites`. For additional sites, create a new `Sites` row first, then run keyword research scoped to that site's niche.

---

## Setting up a new site

1. Add a row to `Sites` with WP credentials, voice prompt, and niche
2. Run keyword research for that niche (manually via Keyword Planner, or via the automated service once built) and import into `Keywords`, linked to the new `Sites` row
3. n8n workflow picks up the new site automatically on its next scheduled run — no code changes needed, since site config is now data, not hardcoded values

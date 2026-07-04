/**
 * wp-content-engine — Cloudflare Worker Proxy
 *
 * Site-agnostic proxy between n8n and (1) the Anthropic API and (2) any
 * WordPress site's REST API. Site-specific credentials (WP URL, app password)
 * are passed per-request from n8n — which reads them from the Airtable
 * "Sites" table — rather than hardcoded here. This lets one Worker deployment
 * serve any number of WordPress sites.
 *
 * Routes:
 *   POST /generate   -> calls Claude API to draft/update post content
 *   POST /wp/draft    -> creates a WordPress draft post on a given site
 *   POST /wp/publish  -> flips an existing WP post to "publish" status on a given site
 *
 * Secrets (set via `wrangler secret put <NAME>`):
 *   ANTHROPIC_API_KEY
 *   N8N_WEBHOOK_SECRET   (shared secret to authenticate incoming n8n requests)
 *
 * No WP_BASE_URL / WP_USERNAME / WP_APP_PASSWORD here anymore — those travel
 * in the request body per-call, sourced from the Airtable "Sites" table.
 */

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return corsResponse(new Response(null, { status: 204 }));
    }

    const auth = request.headers.get("x-pipeline-secret");
    if (auth !== env.N8N_WEBHOOK_SECRET) {
      return corsResponse(
        new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })
      );
    }

    const url = new URL(request.url);

    try {
      if (url.pathname === "/generate" && request.method === "POST") {
        return corsResponse(await handleGenerate(request, env));
      }
      if (url.pathname === "/wp/draft" && request.method === "POST") {
        return corsResponse(await handleWpDraft(request));
      }
      if (url.pathname === "/wp/publish" && request.method === "POST") {
        return corsResponse(await handleWpPublish(request));
      }
      return corsResponse(
        new Response(JSON.stringify({ error: "not found" }), { status: 404 })
      );
    } catch (err) {
      return corsResponse(
        new Response(JSON.stringify({ error: err.message }), { status: 500 })
      );
    }
  },
};

// --- Claude API: generate/update post content ---
async function handleGenerate(request, env) {
  const body = await request.json();
  // Expected body: { system_prompt, user_prompt, max_tokens? }
  // system_prompt should carry the SITE's own voice/style, passed in by n8n
  // from the Airtable "Sites" table (ContentVoicePrompt field) — this is what
  // makes content generation site-aware without hardcoding any one site's voice here.

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: body.max_tokens || 4000,
      system: body.system_prompt || "",
      messages: [{ role: "user", content: body.user_prompt }],
    }),
  });

  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
}

// --- WordPress: create draft (site-agnostic) ---
async function handleWpDraft(request) {
  const body = await request.json();
  // Expected body: {
  //   wp_base_url, wp_username, wp_app_password,   <- from Sites table
  //   title, content, excerpt?, categories?, tags?, meta?
  // }
  requireSiteCredentials(body);

  const wpAuth = basicAuth(body.wp_username, body.wp_app_password);

  const resp = await fetch(`${body.wp_base_url.replace(/\/$/, "")}/wp-json/wp/v2/posts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Basic ${wpAuth}`,
    },
    body: JSON.stringify({
      title: body.title,
      content: body.content,
      excerpt: body.excerpt || "",
      status: "draft",
      categories: body.categories || [],
      tags: body.tags || [],
      meta: body.meta || {},
    }),
  });

  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
}

// --- WordPress: flip draft -> publish (site-agnostic, called after human approval) ---
async function handleWpPublish(request) {
  const body = await request.json();
  // Expected body: { wp_base_url, wp_username, wp_app_password, post_id }
  requireSiteCredentials(body);

  const wpAuth = basicAuth(body.wp_username, body.wp_app_password);

  const resp = await fetch(
    `${body.wp_base_url.replace(/\/$/, "")}/wp-json/wp/v2/posts/${body.post_id}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Basic ${wpAuth}`,
      },
      body: JSON.stringify({ status: "publish" }),
    }
  );

  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
}

function requireSiteCredentials(body) {
  const missing = ["wp_base_url", "wp_username", "wp_app_password"].filter(
    (k) => !body[k]
  );
  if (missing.length) {
    throw new Error(`Missing site credentials in request: ${missing.join(", ")}`);
  }
}

function basicAuth(username, appPassword) {
  return btoa(`${username}:${appPassword}`);
}

function corsResponse(response) {
  const newResponse = new Response(response.body, response);
  newResponse.headers.set("Access-Control-Allow-Origin", "*");
  newResponse.headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  newResponse.headers.set(
    "Access-Control-Allow-Headers",
    "Content-Type, x-pipeline-secret"
  );
  return newResponse;
}


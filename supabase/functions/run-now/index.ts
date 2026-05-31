/**
 * run-now — Supabase Edge Function
 *
 * Receives a POST from the stock monitoring dashboard and fires the
 * GitHub Actions price_refresh.yml workflow via the repository dispatch API.
 *
 * Environment variables (set in Supabase Dashboard → Edge Functions → Secrets):
 *   DISPATCH_TOKEN  — GitHub personal access token with `repo` + `workflow` scopes
 *   TRIGGER_SECRET  — Simple shared secret to prevent random callers (optional but recommended)
 */

const REPO = "Terrence314/stock-monitoring-tool";
const WORKFLOW = "price_refresh.yml";
const GITHUB_API = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",   // GitHub Pages origin
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-trigger-key, content-type",
};

Deno.serve(async (req: Request) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // Optional trigger key check (add X-Trigger-Key header from dashboard)
  const triggerSecret = Deno.env.get("TRIGGER_SECRET");
  if (triggerSecret) {
    const provided = req.headers.get("x-trigger-key");
    if (provided !== triggerSecret) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
  }

  const dispatchToken = Deno.env.get("DISPATCH_TOKEN");
  if (!dispatchToken) {
    return new Response(JSON.stringify({ error: "DISPATCH_TOKEN not configured" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  // Fire the workflow
  const resp = await fetch(GITHUB_API, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${dispatchToken}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });

  if (resp.status === 204) {
    // 204 No Content = GitHub accepted the dispatch
    return new Response(JSON.stringify({ ok: true, message: "Pipeline triggered" }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const body = await resp.text();
  return new Response(JSON.stringify({ ok: false, github_status: resp.status, detail: body }), {
    status: 502,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});

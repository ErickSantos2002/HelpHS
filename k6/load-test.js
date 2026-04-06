/**
 * HelpHS — Load Test (k6)
 *
 * Stages:
 *   smoke  : 1 VU, 30s   — sanity check, all endpoints respond 2xx
 *   load   : ramp to 20 VUs over 1m, sustain 2m, ramp down 30s
 *
 * Run:
 *   k6 run k6/load-test.js
 *   k6 run --env STAGE=smoke k6/load-test.js
 *
 * Requirements:
 *   Backend running at http://localhost:8001
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

// ── Custom metrics ────────────────────────────────────────────

const errorRate = new Rate("error_rate");
const loginDuration = new Trend("login_duration", true);
const ticketListDuration = new Trend("ticket_list_duration", true);
const ticketCreateDuration = new Trend("ticket_create_duration", true);
const dashboardDuration = new Trend("dashboard_duration", true);

// ── Configuration ─────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8001/api/v1";
const ADMIN_EMAIL = __ENV.ADMIN_EMAIL || "admin@healthsafety.com";
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || "Admin@123456";

const stage = __ENV.STAGE || "load";

const STAGES = {
  smoke: [{ duration: "30s", target: 1 }],
  load: [
    { duration: "30s", target: 5 },   // ramp up
    { duration: "1m",  target: 20 },  // sustain
    { duration: "1m",  target: 20 },  // sustain
    { duration: "30s", target: 0 },   // ramp down
  ],
};

// ── Thresholds ────────────────────────────────────────────────
// Dev thresholds are lenient (local DB + ORM overhead).
// Set ENV=prod for strict production targets.

const isProd = __ENV.ENV === "prod";

export const options = {
  stages: STAGES[stage] || STAGES.load,
  thresholds: {
    // prod: p95<500ms | dev: p95<2000ms
    http_req_duration: [isProd ? "p(95)<500" : "p(95)<2000"],
    // Error rate must stay below 1% in all environments
    error_rate: ["rate<0.01"],
    // Login p95
    login_duration: [isProd ? "p(95)<1000" : "p(95)<3000"],
    // Ticket list p95
    ticket_list_duration: [isProd ? "p(95)<500" : "p(95)<2000"],
    // Dashboard p95
    dashboard_duration: [isProd ? "p(95)<800" : "p(95)<2000"],
  },
};

// ── Auth helper ───────────────────────────────────────────────

function login() {
  const start = Date.now();
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    { headers: { "Content-Type": "application/json" } },
  );
  loginDuration.add(Date.now() - start);

  const ok = check(res, {
    "login 200": (r) => r.status === 200,
    "login has access_token": (r) => {
      try {
        return JSON.parse(r.body).access_token !== undefined;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!ok);
  if (!ok) return null;

  return JSON.parse(res.body).access_token;
}

function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  };
}

// ── Main virtual user scenario ────────────────────────────────

export default function () {
  const token = login();
  if (!token) {
    sleep(1);
    return;
  }

  const headers = authHeaders(token);

  // ── Health check ───────────────────────────────────────────
  group("health", () => {
    const res = http.get(`${BASE_URL}/health`);
    const ok = check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(!ok);
  });

  sleep(0.5);

  // ── Tickets list ───────────────────────────────────────────
  group("tickets", () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/tickets?limit=20&offset=0`, headers);
    ticketListDuration.add(Date.now() - start);

    const ok = check(res, {
      "tickets list 200": (r) => r.status === 200,
      "tickets list has items": (r) => {
        try {
          return Array.isArray(JSON.parse(r.body).items);
        } catch {
          return false;
        }
      },
    });
    errorRate.add(!ok);

    sleep(0.5);

    // Create a ticket
    const createStart = Date.now();
    const createRes = http.post(
      `${BASE_URL}/tickets`,
      JSON.stringify({
        title: `k6 load test ${Date.now()}`,
        description: "Ticket criado por teste de carga k6.",
        priority: "medium",
        category: "software",
      }),
      headers,
    );
    ticketCreateDuration.add(Date.now() - createStart);

    const createOk = check(createRes, {
      "ticket created 201": (r) => r.status === 201,
    });
    errorRate.add(!createOk);
  });

  sleep(0.5);

  // ── Dashboard ──────────────────────────────────────────────
  group("dashboard", () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/dashboard/stats`, headers);
    dashboardDuration.add(Date.now() - start);

    const ok = check(res, {
      "dashboard stats 200": (r) => r.status === 200,
      "dashboard has tickets key": (r) => {
        try {
          return JSON.parse(r.body).tickets !== undefined;
        } catch {
          return false;
        }
      },
    });
    errorRate.add(!ok);
  });

  sleep(0.5);

  // ── Knowledge Base ─────────────────────────────────────────
  group("kb", () => {
    const res = http.get(`${BASE_URL}/kb/articles?limit=10`, headers);
    const ok = check(res, { "kb articles 200": (r) => r.status === 200 });
    errorRate.add(!ok);
  });

  sleep(0.5);

  // ── Notifications ──────────────────────────────────────────
  group("notifications", () => {
    const res = http.get(`${BASE_URL}/notifications?limit=10`, headers);
    const ok = check(res, { "notifications 200": (r) => r.status === 200 });
    errorRate.add(!ok);
  });

  sleep(1);
}

// ── Summary handler ───────────────────────────────────────────

export function handleSummary(data) {
  return {
    "k6/results/load-test-summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
  };
}

// Inline text summary (avoids needing k6/x/summary extension)
function textSummary(data, opts = {}) {
  const indent = opts.indent || "";
  const lines = [`\n${indent}=== HelpHS Load Test Summary ===`];

  const metrics = data.metrics || {};
  const checks = metrics.checks;
  if (checks) {
    const passed = checks.values.passes || 0;
    const failed = checks.values.fails || 0;
    const total = passed + failed;
    lines.push(
      `${indent}Checks : ${passed}/${total} passed (${total > 0 ? ((passed / total) * 100).toFixed(1) : 0}%)`,
    );
  }

  const dur = metrics.http_req_duration;
  if (dur) {
    lines.push(
      `${indent}Latency: avg=${dur.values.avg?.toFixed(0)}ms  p90=${dur.values["p(90)"]?.toFixed(0)}ms  p95=${dur.values["p(95)"]?.toFixed(0)}ms  max=${dur.values.max?.toFixed(0)}ms`,
    );
  }

  const reqs = metrics.http_reqs;
  if (reqs) {
    lines.push(
      `${indent}Requests: ${reqs.values.count} total  ${reqs.values.rate?.toFixed(1)} req/s`,
    );
  }

  const err = metrics.error_rate;
  if (err) {
    lines.push(`${indent}Error rate: ${(err.values.rate * 100).toFixed(2)}%`);
  }

  // Threshold results
  lines.push(`${indent}\nThresholds:`);
  for (const [name, threshold] of Object.entries(data.root_group?.checks || {})) {
    lines.push(`${indent}  ${name}: ${threshold.passes > 0 ? "✓" : "✗"}`);
  }

  return lines.join("\n") + "\n";
}

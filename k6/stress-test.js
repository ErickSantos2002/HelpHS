/**
 * HelpHS — Stress Test (k6)
 *
 * Stages:
 *   stress : ramp to 50 VUs, sustain, spike to 100, recover
 *   soak   : 10 VUs for 10 minutes (long-running stability)
 *
 * Run:
 *   k6 run k6/stress-test.js
 *   k6 run --env STAGE=soak k6/stress-test.js
 *
 * Goal: find the breaking point and verify the API recovers gracefully.
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ── Custom metrics ────────────────────────────────────────────

const errorRate = new Rate("error_rate");
const httpErrors5xx = new Counter("http_errors_5xx");
const httpErrors4xx = new Counter("http_errors_4xx");
const p95Duration = new Trend("p95_response_time", true);

// ── Configuration ─────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8001/api/v1";
const ADMIN_EMAIL = __ENV.ADMIN_EMAIL || "admin@healthsafety.com";
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || "Admin@123456";

const stage = __ENV.STAGE || "stress";

const STAGES = {
  stress: [
    { duration: "30s", target: 10 },   // warm up
    { duration: "1m",  target: 50 },   // ramp to stress load
    { duration: "1m",  target: 50 },   // sustain stress
    { duration: "30s", target: 100 },  // spike
    { duration: "30s", target: 50 },   // recover from spike
    { duration: "30s", target: 0 },    // ramp down
  ],
  soak: [
    { duration: "30s", target: 10 },
    { duration: "10m", target: 10 },   // soak: sustained load
    { duration: "30s", target: 0 },
  ],
};

// ── Thresholds ────────────────────────────────────────────────
// Dev thresholds are lenient (local DB + ORM overhead).
// Set ENV=prod for strict production targets.

const isProd = __ENV.ENV === "prod";

export const options = {
  stages: STAGES[stage] || STAGES.stress,
  thresholds: {
    // prod: p95<1s | dev: p95<3s
    http_req_duration: [isProd ? "p(95)<1000" : "p(95)<3000"],
    // Error rate must stay below 5% under stress
    error_rate: ["rate<0.05"],
    // No more than 50 server errors total
    http_errors_5xx: ["count<50"],
  },
};

// ── Shared token pool (one login per VU) ──────────────────────

let cachedToken = null;

function getToken() {
  if (cachedToken) return cachedToken;

  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    { headers: { "Content-Type": "application/json" } },
  );

  if (res.status !== 200) return null;

  try {
    cachedToken = JSON.parse(res.body).access_token;
    return cachedToken;
  } catch {
    return null;
  }
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
  const token = getToken();
  if (!token) {
    errorRate.add(1);
    sleep(1);
    return;
  }

  const headers = authHeaders(token);

  // ── Read-heavy scenario (most realistic) ──────────────────

  group("read_scenario", () => {
    // Ticket list with filters
    const ticketRes = http.get(
      `${BASE_URL}/tickets?limit=20&status=open`,
      headers,
    );
    p95Duration.add(ticketRes.timings.duration);

    if (ticketRes.status >= 500) httpErrors5xx.add(1);
    if (ticketRes.status >= 400 && ticketRes.status < 500) httpErrors4xx.add(1);

    const ticketOk = check(ticketRes, {
      "tickets list not 5xx": (r) => r.status < 500,
      "tickets list has body": (r) => r.body && r.body.length > 0,
    });
    errorRate.add(!ticketOk);

    sleep(0.3);

    // Dashboard stats
    const dashRes = http.get(`${BASE_URL}/dashboard/stats`, headers);
    p95Duration.add(dashRes.timings.duration);

    if (dashRes.status >= 500) httpErrors5xx.add(1);
    const dashOk = check(dashRes, {
      "dashboard not 5xx": (r) => r.status < 500,
    });
    errorRate.add(!dashOk);

    sleep(0.3);

    // KB articles
    const kbRes = http.get(`${BASE_URL}/kb/articles?limit=10`, headers);
    if (kbRes.status >= 500) httpErrors5xx.add(1);
    check(kbRes, { "kb not 5xx": (r) => r.status < 500 });
  });

  sleep(0.5);

  // ── Write scenario (every 3rd VU iteration creates a ticket) ─

  if (__ITER % 3 === 0) {
    group("write_scenario", () => {
      const createRes = http.post(
        `${BASE_URL}/tickets`,
        JSON.stringify({
          title: `stress test ${__VU}-${__ITER}`,
          description: "Ticket de teste de stress. Pode ser ignorado.",
          priority: "low",
          category: "other",
        }),
        headers,
      );
      p95Duration.add(createRes.timings.duration);

      if (createRes.status >= 500) httpErrors5xx.add(1);
      const createOk = check(createRes, {
        "ticket create not 5xx": (r) => r.status < 500,
      });
      errorRate.add(!createOk);
    });

    sleep(0.3);
  }

  // ── Auth endpoint (verify token refresh path) ─────────────

  if (__ITER % 10 === 0) {
    group("auth_scenario", () => {
      const meRes = http.get(`${BASE_URL}/users/me`, headers);
      if (meRes.status >= 500) httpErrors5xx.add(1);
      check(meRes, { "me not 5xx": (r) => r.status < 500 });
    });
  }

  sleep(0.5);
}

// ── Setup: verify the API is reachable before the test starts ─

export function setup() {
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    throw new Error(
      `API not reachable at ${BASE_URL}/health — got ${res.status}. Start the backend first.`,
    );
  }
  console.log(`✓ API reachable at ${BASE_URL} (status ${res.status})`);
  return {};
}

// ── Summary handler ───────────────────────────────────────────

export function handleSummary(data) {
  return {
    "k6/results/stress-test-summary.json": JSON.stringify(data, null, 2),
  };
}

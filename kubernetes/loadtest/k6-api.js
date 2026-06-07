// k6 load test — LyonFlowFull FastAPI
//
// Lance localement :
//   K6_API_BASE=https://api-dev.lyonflow.fr \
//   K6_API_KEY=secret \
//   k6 run --vus 100 --duration 5m kubernetes/loadtest/k6-api.js
//
// Lance dans le cluster (Job ephemere) :
//   kubectl -n lyonflow run k6 --rm -i --tty --restart=Never \
//     --image=grafana/k6:0.50.0 -- run -<k6-api.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const apiLatency = new Trend('api_latency_ms');

const BASE = __ENV.K6_API_BASE || 'http://fastapi.lyonflow.svc:8000';
const API_KEY = __ENV.K6_API_KEY || 'dev-key-change-me';

export const options = {
  stages: [
    { duration: '1m',  target: 20 },   // warm-up
    { duration: '3m',  target: 100 },  // load
    { duration: '1m',  target: 200 },  // stress
    { duration: '1m',  target: 0 },    // cooldown
  ],
  thresholds: {
    http_req_failed:        ['rate<0.05'],          // < 5% erreurs
    http_req_duration:      ['p(95)<1000'],         // p95 < 1s
    'api_latency_ms{path:predict}': ['p(95)<800'],
    'api_latency_ms{path:route}':   ['p(95)<1500'],
  },
};

const headers = {
  'X-API-Key': API_KEY,
  'Content-Type': 'application/json',
};

export default function () {
  group('health', () => {
    const r = http.get(`${BASE}/health`);
    check(r, { 'health 200': res => res.status === 200 });
    apiLatency.add(r.timings.duration, { path: 'health' });
    errorRate.add(r.status !== 200);
  });

  group('predict traffic', () => {
    const payload = JSON.stringify({
      node_idx: Math.floor(Math.random() * 1500),
      horizon: '15min',
    });
    const r = http.post(`${BASE}/predict/traffic`, payload, { headers });
    check(r, { 'predict 200': res => res.status === 200 });
    apiLatency.add(r.timings.duration, { path: 'predict' });
    errorRate.add(r.status >= 400);
  });

  group('route', () => {
    const payload = JSON.stringify({
      origin:      { lat: 45.7640, lon: 4.8357 },
      destination: { lat: 45.7800, lon: 4.8500 },
      modes:       ['car', 'bus', 'velov', 'walk'],
    });
    const r = http.post(`${BASE}/route`, payload, { headers });
    check(r, { 'route 200': res => res.status === 200 });
    apiLatency.add(r.timings.duration, { path: 'route' });
    errorRate.add(r.status >= 400);
  });

  sleep(Math.random() * 2 + 0.5);
}

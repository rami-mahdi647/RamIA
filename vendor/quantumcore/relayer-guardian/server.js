import express from 'express';
import fetch from 'node-fetch';
import { RateLimiterMemory } from 'rate-limiter-flexible';
import pino from 'pino';

const TARGET = process.env.GUARDIAN_TARGET || 'http://localhost:8545';
const RATE_RPM = Number(process.env.GUARDIAN_RATE_RPM || 120);
const ERR_THRESH = Number(process.env.GUARDIAN_CIRCUIT_THRESHOLD_ERRORS || 20);
const WINDOW = Number(process.env.GUARDIAN_CIRCUIT_WINDOW_SEC || 60);

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const app = express();
app.use(express.json({ limit: '2mb' }));

const limiter = new RateLimiterMemory({ points: RATE_RPM, duration: 60 });
let errorWindow = [];
let breakerOpen = false;
let breakerUntil = 0;

function nowSec() { return Math.floor(Date.now() / 1000); }

app.use(async (req, res, next) => {
  const ip = req.headers['x-forwarded-for']?.toString().split(',')[0].trim() || req.ip;
  try {
    await limiter.consume(ip || 'anon', 1);
    return next();
  } catch {
    return res.status(429).json({ error: 'rate_limited' });
  }
});

app.post('/', async (req, res) => {
  // Circuit breaker window prune
  const t = nowSec();
  errorWindow = errorWindow.filter(ts => ts > t - WINDOW);
  if (breakerOpen && t < breakerUntil) {
    return res.status(503).json({ error: 'circuit_open' });
  } else if (breakerOpen && t >= breakerUntil) {
    breakerOpen = false;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);

  try {
    const r = await fetch(TARGET, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(req.body),
      signal: controller.signal
    });
    clearTimeout(timeout);
    const text = await r.text();
    if (!r.ok) {
      errorWindow.push(nowSec());
      if (errorWindow.length >= ERR_THRESH) {
        breakerOpen = true;
        breakerUntil = nowSec() + WINDOW;
        logger.warn({ count: errorWindow.length }, 'breaker_open');
      }
      return res.status(r.status).send(text);
    }
    return res.status(200).send(text);
  } catch (e) {
    clearTimeout(timeout);
    errorWindow.push(nowSec());
    if (errorWindow.length >= ERR_THRESH) {
      breakerOpen = true;
      breakerUntil = nowSec() + WINDOW;
      logger.warn({ count: errorWindow.length }, 'breaker_open');
    }
    logger.error({ error: e?.message }, 'proxy_error');
    return res.status(502).json({ error: 'upstream_error' });
  }
});

const port = Number(process.env.PORT || 8787);
app.listen(port, () => logger.info({ port, target: TARGET }, 'guardian up'));

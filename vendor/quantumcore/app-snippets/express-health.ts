import express from 'express';
import { env } from './env';
import pino from 'pino';
import { v4 as uuidv4 } from 'uuid';

const app = express();
const logger = pino({ level: env.LOG_LEVEL });

// request id
app.use((req, res, next) => {
  req.headers['x-request-id'] = req.headers['x-request-id'] || uuidv4();
  res.setHeader('x-request-id', String(req.headers['x-request-id']));
  next();
});

app.get('/healthz', (_req, res) => res.status(200).json({ ok: true }));

async function pingRPC(): Promise<boolean> {
  if (!env.RPC_URL) return true; // opcional
  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 1500);
    const r = await fetch(env.RPC_URL, { method: 'POST', body: '{}', signal: controller.signal });
    clearTimeout(t);
    return r.ok;
  } catch {
    return false;
  }
}

app.get('/readyz', async (_req, res) => {
  const deps = { rpc: await pingRPC() };
  const ready = Object.values(deps).every(Boolean);
  res.status(ready ? 200 : 503).json({ ready, deps });
});

const port = Number(env.PORT || 3000);
app.listen(port, () => logger.info({ port }, 'service up'));

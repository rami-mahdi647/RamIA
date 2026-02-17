import { cleanEnv, str, url, num } from 'envalid';

export const env = cleanEnv(process.env, {
  NODE_ENV: str({ choices: ['development','staging','production'] }),
  PORT: str({ default: '3000' }),
  ORIGIN: url({ default: 'https://tu-dominio.com' }),

  RPC_URL: url({ default: 'http://localhost:8545' }),
  AA_BUNDLER_URL: url({ default: 'http://localhost:3001' }),
  PAYMASTER_URL: url({ default: 'http://localhost:3002' }),

  OTEL_EXPORTER_OTLP_ENDPOINT: url({ default: 'http://localhost:4318' }),
  LOG_LEVEL: str({ default: 'info' }),

  // Guardian (opcional)
  GUARDIAN_TARGET: str({ default: 'http://localhost:8545' }),
  GUARDIAN_RATE_RPM: num({ default: 120 }),
  GUARDIAN_CIRCUIT_THRESHOLD_ERRORS: num({ default: 20 }),
  GUARDIAN_CIRCUIT_WINDOW_SEC: num({ default: 60 }),
});

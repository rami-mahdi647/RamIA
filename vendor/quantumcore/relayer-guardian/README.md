# Relayer Guardian (opcional)

Proxy ligero para proteger tus endpoints AA/RPC sin cambiar tu app/contratos.
- Limita peticiones por minuto.
- Circuit breaker si aumenta la tasa de errores.
- **No realiza bloqueo por país ni geo-IP** (respeta tu enfoque de privacidad).

## Variables
- GUARDIAN_TARGET: URL del RPC/bundler a proteger
- GUARDIAN_RATE_RPM: Requests por minuto permitidas (por IP)
- GUARDIAN_CIRCUIT_THRESHOLD_ERRORS: Nº de errores (5xx/timeouts) en ventana para abrir el breaker
- GUARDIAN_CIRCUIT_WINDOW_SEC: Duración de la ventana en segundos

## Uso
npm install
npm run dev
# o build + docker

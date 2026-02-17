# Runbook: Incidente en Producción

## Señales para iniciar
- 5xx > 2% por 5 minutos
- p95 > SLO por 10 minutos
- Falla de userOps/tx anómala por cadena
- Ausencia de logs > 2 min (dead man's switch)

## Pasos
1. **Pausar canary** o revertir a versión estable (rollback por tag).
2. **Activar circuit breaker** en el Relayer Guardian si los errores vienen de AA/RPC.
3. Reducir tasa (`limit_req`) temporalmente en el proxy si hay abuso.
4. Revisar métricas (latencia/error) y logs con `X-Request-ID`.
5. Crear postmortem con causa raíz y acción correctiva.

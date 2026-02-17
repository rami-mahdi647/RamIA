# Production Safety Belt (Drop-in Kit)

Este paquete te permite ejecutar tu experimento **tal cual está**, pero con
controles mínimos de producción: contenedores reproducibles, proxy TLS con
rate limiting, health checks, CI, y plantillas de despliegue. **No incluye
bloqueo por país/geo-IP**; respeta tu enfoque de privacidad y fraud-detection
basado en TensorFlow/Keras.

## ¿Cómo integrar?
1. Copia las carpetas de este paquete en la raíz de tu repo (no sobrescribe tu código).
2. Revisa `proxy/default.conf` para ajustar CORS/CSP/ORIGIN.
3. Exporta variables de entorno según `app-snippets/env.ts` y `.env.example`.
4. Construye y prueba localmente con `compose/docker-compose.yml`.
5. Configura `REGISTRY` e `IMAGE_NAME` en `.github/workflows/ci.yml`.
6. Despliega en Kubernetes con el Helm chart de `k8s/helm/` (staging → prod).
7. Opcional: Ejecuta el **Relayer Guardian** como proxy para AA/RPC con límites y circuit breaker.

> Sugerencia: empieza por staging (idéntico a prod) y canary 1–5% antes de 100%.

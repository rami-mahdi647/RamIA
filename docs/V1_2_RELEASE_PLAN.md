# RamIA v1.2 — Plan de estabilización y lanzamiento

Este documento convierte las ideas estratégicas en un plan ejecutable para publicar una versión **v1.2** más estable, segura y fácil de validar.

## Objetivo de v1.2

Entregar una versión enfocada en:

- estabilidad del nodo y del flujo de minado/transacciones,
- validación rigurosa (unitaria + integración),
- mayor protección criptográfica y operativa,
- documentación orientada a usuarios y colaboradores,
- reglas de recompensa adaptativa más predecibles,
- preparación de testnet antes de cualquier adopción más amplia.

---

## Alcance funcional (qué debe estar sólido)

Para considerar v1.2 como “lista”, los siguientes bloques deben funcionar de forma consistente:

1. **Cadena base** (`aichain.py`): creación de bloques, persistencia y consulta.
2. **Nodo CLI** (`ramia_node.py`): `init`, `mine`, `send`, `chain`, y manejo de configuración.
3. **Guardian IA** (`ramia_ai_guardian.py`): scoring determinista y acciones de política repetibles.
4. **Recompensas** (`ramia_reward_policy.py` + `ramia_rewards_ledger.py`): cálculo auditable, topes, trazabilidad en ledger hash-encadenado.
5. **Cripto y wallet** (`crypto_backend.py`, `ramia_wallet_secure.py`): firma/verificación y resguardo de material sensible.

---

## Checklist de release

## 1) Estabilización del código

- [ ] Eliminar duplicados obsoletos (`*.pyx`, `*.pyxx`, variantes legacy sin uso) o marcarlos explícitamente como archivados.
- [ ] Definir “rutas oficiales” de ejecución (scripts y entrypoints soportados).
- [ ] Estandarizar estructura de configuración en `ramia_config.json`.
- [ ] Asegurar compatibilidad con Termux/Linux para el flujo principal.

## 2) Pruebas rigurosas

- [ ] Mantener pruebas unitarias para tokenomics, guardian y firma segura.
- [ ] Añadir pruebas de integración para:
  - [ ] minar + registrar recompensa + verificar ledger,
  - [ ] enviar transacción válida e inválida,
  - [ ] comportamiento de rechazo del guardian en escenarios de riesgo.
- [ ] Definir comando único de validación (por ejemplo `pytest -q`).

## 3) Seguridad de claves y transacciones

- [ ] Verificar que no existan secretos versionados (tokens, claves privadas, backups sensibles).
- [ ] Endurecer defaults de permisos de archivos de wallet/config.
- [ ] Revisar parámetros criptográficos vigentes en `docs/CRYPTO_SPEC.md`.
- [ ] Añadir checklist mínima de hardening operativo para nodos.

## 4) Documentación clara

- [ ] Actualizar `README.md` con:
  - [ ] instalación,
  - [ ] quickstart reproducible,
  - [ ] flujo de minado/transacciones,
  - [ ] auditoría de recompensas.
- [ ] Vincular documentos de producto/amenazas/cripto en una “guía de lectura”.
- [ ] Añadir notas de troubleshooting comunes (Termux, rutas, permisos).

## 5) IA adaptativa mejorada

Definir métrica y pesos explícitos para la función de recompensa:

- [ ] `network_congestion`
- [ ] `active_nodes`
- [ ] `latency_ms`
- [ ] `guardian_risk_score`
- [ ] `work_units`

Y validar propiedades clave:

- [ ] **Predictibilidad**: cambios suaves y acotados (sin saltos inesperados).
- [ ] **Equidad**: sin sesgos extremos por ruido temporal.
- [ ] **Auditabilidad**: cada recompensa explica factores y límites aplicados.

## 6) Comunidad/Testnet

- [ ] Publicar perfil de testnet (config separada, faucet simple si aplica).
- [ ] Definir periodo de pruebas y criterios de éxito.
- [ ] Abrir canal de feedback (issues/discussions) con plantilla de reporte.

## 7) Roadmap y versión

- [ ] Publicar changelog de v1.2 respecto a v1.1.
- [ ] Etiquetar alcance “in” y “out” para evitar creep.
- [ ] Preparar notas de release con riesgos conocidos.

## 8) Ruta alternativa (token en red existente)

Si la operación de red propia resulta costosa para esta etapa:

- [ ] evaluar despliegue como token en BSC/Polygon,
- [ ] mantener lógica diferenciadora (IA anti-spam/recompensa adaptativa) fuera de consenso base,
- [ ] usar esta ruta como acelerador de adopción temprana.

---

## Criterios de salida (Definition of Done)

v1.2 se considera lista cuando:

1. Suite de pruebas principal en verde.
2. Flujo `init -> mine -> send -> audit ledger` reproducible en entorno limpio.
3. Sin secretos en repo y con guía de seguridad operativa publicada.
4. README y documentos enlazados, coherentes y actualizados.
5. Testnet ejecutada con feedback incorporado en al menos una iteración.

---

## Entregables sugeridos para la release

- `CHANGELOG_v1.2.md`
- `docs/V1_2_RELEASE_PLAN.md` (este documento)
- Actualización de `README.md`
- Tag de versión (`v1.2.0-rc1` -> `v1.2.0`)

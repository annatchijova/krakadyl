# KRAKADYL — Investigación global: el problema, las alternativas y la diferenciación defendible

**Versión:** 1.0 · **Fecha de investigación y consulta de fuentes:** 2026-11-02 · **Idioma:** español (la versión en inglés, `KRAKADYL_GLOBAL_RESEARCH_EN.md`, es una traducción técnica fiel de este documento)

**Base de código examinada:** repositorio público `annatchijova/krakadyl`, rama `main`, commit `1d56d66` (2026-11-02). **No** se examinó el árbol de trabajo local con cambios sin commit (ver §2.4 y §18).

**Leyenda epistémica usada en todo el documento**

| Estado | Significado |
|---|---|
| CONFIRMED | Verificado en esta investigación: código ejecutado, test corrido, o fuente primaria leída que respalda la afirmación concreta |
| DOCUMENTED_ONLY | Lo afirma la documentación propia del sistema (README, paper, página de producto), sin verificación independiente |
| INFERRED | Inferencia razonada a partir de evidencia; no observada directamente |
| NOT_FOUND_IN_REVIEWED_SOURCES | No aparece en las fuentes revisadas. **No** significa que no exista |
| UNVERIFIED | No se pudo verificar (fuente inaccesible, secundaria sin respaldo primario, o no consultada) |
| CONTRADICTED | Una fuente primaria contradice la afirmación |

Las referencias entre corchetes (`[A5]`, `[H2]`, `[R3]`, etc.) remiten a la bibliografía de la §20.

---

## 1. Resumen ejecutivo

**El problema existe, está documentado y no es exclusivo del DFIR.** Las investigaciones y operaciones críticas fallan de forma recurrente en los puntos donde una tarea cambia de manos, donde algo se reporta hecho sin que nadie lo verifique, o donde la evidencia tiene una ventana de existencia limitada. Hay evidencia sólida en aviación (Continental Express 2574, 1991: 47 tornillos faltantes después de un cambio de turno [I1]), industria de procesos (Piper Alpha, 1988: dos permisos de trabajo que no se referenciaban entre sí [I2]), medicina (I-PASS: −23 % de errores médicos y −30 % de eventos adversos prevenibles al estandarizar los traspasos [H2]) y justicia penal (caso Liam Allan, 2017–2018: un oficial creía haber revisado la descarga completa de más de 57.000 mensajes y no lo había hecho [I3]). En ciberseguridad, la retención de logs determinó lo que se pudo saber: Microsoft no pudo establecer cómo se robó la clave del incidente Storm-0558 porque no conservaba los logs del período [I4], y Mandiant reporta que la retención estándar de 90 días impidió identificar el vector inicial en los casos BRICKSTORM, cuyo tiempo de permanencia promedio fue de 393 días [I8].

**Lo que no existe es una cifra global de cuántas investigaciones fracasan por fallas evitables de coordinación, continuidad, autorización, preservación o verificación.** No se encontró en las fuentes revisadas ningún estudio que lo cuantifique para investigaciones digitales. Cualquier porcentaje de ese tipo en un pitch sería fabricado. Lo que sí se puede afirmar con respaldo son mecanismos (documentados en otras disciplinas), casos concretos y señales indirectas (79 % de los SOC funcionan 24/7, y por lo tanto tienen traspasos de turno estructurales [H11]).

**KRAKADYL implementa y prueba lo que dice implementar en el repositorio público**, con matices. Se ejecutaron 451 tests (Python 3.11 bloqueado y 3.13, todos pasan), la prueba de humo contra un servidor real, el build y lint del frontend, y las cuatro demos determinísticas. El Nivel 6 (sub-mandatos con revocación transitiva, continuidad tras una interrupción y sus paneles de interfaz) está en `main`. La internacionalización español/inglés **no** está en el repositorio público y no pudo verificarse.

**Hallazgos desfavorables que hay que asumir:**

1. **Cada garantía individual de KRAKADYL tiene antecedentes.** La atenuación de delegaciones existe desde Macaroons (2014) [A17], UCAN [A15] y Biscuit [A16]. La revocación transitiva con efectos en vuelo tiene un tratamiento más riguroso y multi-endpoint en Zhu y Wang (arXiv 2609.21284, septiembre de 2026) [A5], que KRAKADYL no cita. Los recibos verificables existen en AgentBound [A1] y en registros de transparencia como Rekor [A18]. La distinción «reportado» vs. «verificado» es doctrina en aviación, medicina y ciencia forense [H8].
2. **No hay evidencia empírica de que KRAKADYL reduzca omisiones, errores de traspaso o tiempo de reorientación.** No hubo estudios con usuarios ni benchmark de coordinación. La «métrica que importa» del README (reducir los `ABSTAIN` evitables) todavía no se midió.
3. **El verificador independiente de recibos comprueba sello y encadenamiento, no autoridad** (KL-002 [R3]). Presentar los recibos como «prueba independiente de que la acción estaba autorizada» sería sobreafirmar.
4. **KRAKADYL todavía no está conectado a las herramientas cuyo uso pretende disciplinar.** No compite con Velociraptor, SIFT ni VIGÍA: es la capa previa que asegura que se usen bien (qué se colectó, dónde, antes de que cierre la ventana, verificado por quién), para que el motor de inferencia no termine en un `ABSTAIN` correcto pero evitable. Hoy esa disciplina se demuestra sobre casos sintéticos: no hay adaptadores reales (Nivel 7) y la persistencia es SQLite de un nodo. Con días de desarrollo (§3.5), es el estado esperable, no una falla de diseño.

**Respuesta a la pregunta central (§4.1).** KRAKADYL previene ocho fallas del proceso investigativo que ocurren antes de usar cualquier herramienta: llegar tarde a una ventana que se cierra; tratar como verificada una tarea solo reportada; perder contexto en un traspaso; tener información que existe pero no está vinculada; actuar sobre un estado o una autoridad que cambió; volver de una interrupción sin reorientarse; sostener hipótesis sobre supuestos no verificados; y tener la ventana abierta sin la autoridad disponible. Cada una está documentada con datos en salud, aviación, industria de procesos, finanzas o exploración espacial, y en varios de esos ámbitos hay programas o normas que la atacan, a veces mejor (por escala y medición) y a veces peor (cuando la verificación depende del ritual humano).

**Qué es y qué no es KRAKADYL.** No intenta hacer mejor lo que hace Velociraptor. Intenta evitar que una investigación llegue a usar Velociraptor tarde, sin las condiciones necesarias, con tareas pendientes o sobre supuestos de trabajo no verificados. Lo mismo vale para SIFT y para VIGÍA: su éxito se mide aguas abajo, en `ABSTAIN` evitables que dejan de ocurrir. El concepto, en forma general y sin depender de ninguna herramienta, está en §4.0: el resultado no concluyente correcto pero evitable.

**Dónde está la diferenciación defendible:** no en ninguna garantía aislada, sino en la **combinación aplicada al dominio investigativo**. En un mismo modelo determinístico: (a) el estado de verificación de la evidencia, con independencia exigida por validador, (b) la autoridad delegada con revocación transitiva revalidada en el momento de ejecutar, (c) ventanas de recuperación tipadas que distinguen «plazo conocido» de «se cierra con un evento de fecha desconocida», y (d) la reorientación tras una ausencia. Ninguno de los sistemas revisados documenta esa combinación (NOT_FOUND_IN_REVIEWED_SOURCES). Eso es defendible ante especialistas. «El primero en el mundo» no lo es.

**Formulación recomendada para el jurado** (§14.3): *«Lo que se reporta hecho no es lo que está verificado. KRAKADYL no deja que el caso los confunda, ni que una autoridad revocada siga actuando.»* Tiene respaldo directo en el código (validador de `TaskResponsibility`, `authority_under_chain`) y en casos reales (Liam Allan, Continental 2574).

---

## 2. Metodología y alcance geográfico

### 2.1 Procedimiento

1. **Inspección del código antes que de la literatura.** Clon del repositorio público, lectura de README, TECHNICAL_README, `docs/levels.md`, `docs/known-limitations.md`, informes de red team y código del núcleo. Ejecución de tests, demos, prueba de humo de API, build y lint del frontend.
2. **Verificación del arte previo citado por el propio README** (AgentBound, AuthorizationBench, AuthorityBench/Veto, Bounded Agents, Meta Muse/Sentinel) contra sus fuentes.
3. **Búsqueda del problema humano y organizacional** en medicina, aviación, industria de procesos, justicia penal y ciberseguridad.
4. **Búsqueda de soluciones** en seis familias: DFIR y gestión de casos, autorización de agentes, sistemas multiagente, evidencia y procedencia, continuidad y temporalidad, factores humanos.
5. **Búsqueda de marcos normativos nacionales** de preservación y cadena de custodia, en idiomas locales.
6. **Comparación por capacidades, no por nombres** (§9, §11).

Se hicieron unas 75 búsquedas y lecturas de fuentes en una sola sesión, el 2026-11-02. Todas las URL de la bibliografía fueron abiertas en esa fecha salvo las marcadas «no abierta en esta sesión».

### 2.2 Idiomas y regiones cubiertos

| Región | Idioma de búsqueda | Qué se encontró | Calidad de la fuente |
|---|---|---|---|
| EE. UU. / Canadá | inglés | Arte previo de agentes (eBay, ASU/Plaw, Northeastern según prensa, Accentrust Canadá), NTSB/FAA, GAO, DOJ OIG, NIST, AWS, OMB | Primaria en su mayoría |
| Europa occidental | inglés | Piper Alpha (IChemE), caso Liam Allan (Reino Unido), Bounded Agents (investigador independiente), Biscuit | Primaria y secundaria |
| Rusia / ecosistema rusoparlante | ruso | Problemas del art. 164.1 del Código Procesal Penal ruso (opinión de abogado, 2019); plataforma de agentes GigaCowork de Sber (2026); Belkasoft y Oxygen Forensic (origen ruso, hoy con sede declarada fuera de Rusia — no verificado) | Secundaria |
| China | chino | Reglas del Ministerio de Seguridad Pública sobre obtención de datos electrónicos (2019), Meiya Pico (美亚柏科), AgentScope (Alibaba), DeerFlow (ByteDance) | Secundaria; el texto primario de las reglas no pudo abrirse |
| India | inglés (fuentes jurídicas indias se publican en inglés) | Sección 63 de la Bharatiya Sakshya Adhiniyam 2023 y su confirmación por la Corte Suprema (mayo de 2026) | Prensa jurídica especializada |
| Japón | japonés | Guía de preservación de evidencia de la IDF, 10.ª edición (marzo de 2025) | Primaria |
| Corea del Sur | coreano | Reglamento de la Fiscalía Suprema sobre evidencia digital (vigente desde 2024-10-01) | Secundaria (estudio jurídico) |
| Israel | inglés | Cellebrite Guardian | Documentación del proveedor |
| América Latina | español, portugués | Argentina: Res. MinSeg 234/2016 y protocolo PGN-MinSeg 2023; Brasil: arts. 158-A a 158-F del CPP (Lei 13.964/2019) | Primaria |

**No se buscó en hindi ni en hebreo.** No hubo resultados de agentes con autorización delegada provenientes de Japón, Corea o India en las búsquedas realizadas; eso es NOT_FOUND_IN_REVIEWED_SOURCES, no prueba de ausencia. País de origen, de despliegue, idioma de publicación y nacionalidad de los autores se registran por separado cuando la fuente los informa; cuando no los informa, se dice.

### 2.3 Jerarquía de fuentes aplicada

1. Código, tests y documentación técnica; estándares y normas.
2. Publicaciones científicas.
3. Informes institucionales e investigaciones de incidentes (NTSB/FAA, GAO, DOJ OIG, CSRB).
4. Documentación de productos (se marca como «documentación del proveedor»).
5. Prensa especializada (se marca como «secundaria»).

Cuando dos textos dependen de la misma fuente (por ejemplo, varias notas de prensa sobre un mismo paper) se cuentan como **una** fuente.

### 2.4 Limitación estructural de esta investigación

El pedido exigía examinar el estado **local** del código, incluidos cambios sin commit en la interfaz y su internacionalización. Esta sesión no estaba vinculada a la computadora de la autora, de modo que **no** se pudo acceder al árbol de trabajo local. Todo lo que dependa de esos cambios se marca como «declarado por la autora, no verificado». Esta limitación no se simuló como resuelta.

---

## 3. Estado verificado de KRAKADYL

### 3.1 Qué se ejecutó

| Comprobación | Comando | Resultado |
|---|---|---|
| Tests Python (Python 3.11, `uv.lock`) | `uv run pytest -q tests --ignore=tests/test_laya_adapter.py` | **451 passed** (CONFIRMED) |
| Tests Python (Python 3.13) | ídem | 451 passed (CONFIRMED) |
| Prueba de humo contra uvicorn real | `python tools/api_smoke.py` | GET + prepare + execute por HTTP, recibo sellado (CONFIRMED) |
| Frontend | `npm ci --ignore-scripts && npm run build && npm run lint` | Build y lint sin errores (CONFIRMED) |
| Demo Nivel 1 | `demo/run_case_001.py` | Archivo manipulado → `forbidden`; requisito en `REPORTED_DONE` con archivo íntegro → `forbidden` (CONFIRMED) |
| Demo Nivel 2 | `demo/run_case_002_level2.py` | Detección de obsolescencia, ruta de recuperación que excluye exactamente el recurso manipulado, cierre honesto ante mandato revocado (CONFIRMED) |
| Demo Nivel 6 (delegación) | `demo/run_case_003_level6.py` | Revocar la raíz deniega al delegado dos niveles más abajo sin tocar su sub-mandato (CONFIRMED) |
| Demo Nivel 6 (continuidad) | `demo/run_case_004_gap.py` | Tras 4 días y 3 horas: qué mandatos expiraron, qué ventanas se cerraron, qué sigue abierto y qué está en vigilancia condicional (CONFIRMED) |

No se ejecutaron: llamadas reales a Muse Spark, Laya o SAM 3.1 (requieren credenciales o GPU), ni la interfaz en un navegador, ni las sondas de red team en vivo (`tools/redteam_*`). Sus resultados figuran en la documentación del repositorio y se consideran DOCUMENTED_ONLY.

### 3.2 Clasificación del estado

**Implementado y probado (CONFIRMED por ejecución o por lectura de tests):**

- Separación entre estado de evidencia (`SUFFICIENT/MISSING/CONFLICTING/STALE`) y estado de autoridad (`GRANTED/NEEDS_CONSENT/DENIED/EXPIRED`).
- Ciclo de vida `TaskResponsibility`: `UNASSIGNED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → REPORTED_DONE → VERIFIED_DONE` (más `BLOCKED/EXPIRED/CANCELLED/UNKNOWN`). `VERIFIED_DONE` exige `verified_by` y `verification_method`, y `verified_by` distinto de `reported_done_by` salvo método automatizado `tool:`. El validador corre también en asignación (`validate_assignment=True`).
- `REPORTED_DONE` se traduce siempre a evidencia `MISSING`, nunca `SUFFICIENT` (`continuity.evidence_state_from_requirement`).
- El ejecutor exige **ambas cosas** para incluir una observación: digest íntegro **y** requisito en `VERIFIED_DONE`. Ninguna sustituye a la otra.
- Dos fases (`prepare_evidence_package` / `execute_prepared_action`), con revalidación completa del mandato, la evidencia y la correspondencia en el momento de ejecutar; nonce de un solo uso persistido; ensamblado en directorio temporal, verificación del digest de cada copia y renombrado atómico.
- Recibos encadenados con SHA-256 y verificador independiente con biblioteca estándar (`tools/verify_receipt.py`, que deliberadamente no importa `krakadyl.core`). Rechaza floats en la ruta sellada.
- Corrección de dos carreras de encadenamiento bajo ejecución concurrente real (RT-CHAIN-01/02), con regresión en `tests/test_store.py`.
- `next_move()`: recomendación única con alternativas visibles, estado *uncertain* cuando hay empate real, lista *blocked* y lista *conditional_watch* para ventanas `CONDITIONAL`/`UNKNOWN`.
- `RecoveryWindow` tipada (`KNOWN`, `ESTIMATED` con `estimate_basis`, `CONDITIONAL` con `condition`, `UNKNOWN`).
- Nivel 4: declaraciones de equipo append-only, cuatro tipos de conflicto derivado, verificación solo por alguien distinto del declarante, traspaso de turno que transfiere responsabilidad pero no autoridad (DOCUMENTED_ONLY en lo relativo al red team; tests presentes: 14 en `test_team.py`).
- Nivel 5: contrafácticos tipados ejecutados sobre copias, nunca ejecutables, marcados como obsoletos si cambian los insumos (11 tests en `test_counterfactual.py`).
- **Nivel 6: sub-mandatos** (`derive_sub_mandate` exige subconjunto estricto en recursos, operaciones, destinos y ventana de validez); `authority_under_chain` recorre la cadena hasta la raíz; cadenas rotas o cíclicas se rechazan; prepare/execute bajo sub-mandato con revalidación de la cadena en el punto de linealización (19 tests en `test_delegation.py`).
- **Nivel 6: continuidad tras una ausencia** (`resume_after_gap`, `GET /api/cases/{id}/resume`), con el inicio de la ausencia derivado del último evento registrado, no de un parámetro del cliente (6 tests en `test_continuity_gap.py`).
- **Nivel 6: interfaz.** `DelegationPanel.tsx` y `ResumePanel.tsx` están en `main` (commits `93be916`, `635c80b`), compilan y pasan lint. No se probaron en navegador en esta investigación.

**Implementado pero con validación insuficiente:**

- **Verificador de recibos:** solo 2 tests dedicados (`tests/test_verify_receipt.py`), y ambos prueban casos de falla (cadena vacía, entrada malformada). Ningún test del repositorio comprueba que el verificador independiente **acepte** una cadena sellada por `krakadyl.core`. En esta investigación se hizo esa comprobación manualmente: una cadena de dos recibos sellada con `krakadyl.core.receipt.seal` fue aceptada (`OK`) y la misma cadena con un veredicto alterado fue rechazada (`BROKEN`, código de salida 1) (CONFIRMED). **Además:** el `seal_payload` se excluye de la persistencia por diseño, y no existe en la API ni en `tools/` un exportador que reconstruya el archivo `chain.json` que el verificador espera. Hoy, verificar los recibos de un caso real requiere reconstruir a mano cada payload a partir de la decisión y del manifiesto.
- **Laya:** el test del adaptador está excluido de CI; el propio repositorio advierte que el checkpoint trae temperaturas inválidas y que la confianza no está calibrada [R2].
- **Muse y SAM:** comportamiento observado en corridas en vivo acotadas; KL-003 lo reconoce [R3].
- **Grafo de verificación:** estructurado para requisitos nuevos; los requisitos heredados siguen usando procedencia en prosa (KL-001, KL-004) [R3].
- **Persistencia:** SQLite de un nodo. Correcto para un equipo pequeño; no validado bajo carga multi-organización.

**Documentado como diseño (no implementado):**

- Nivel 7: adaptadores reales a Velociraptor, SIFT, i2 Analyst's Notebook y VIGÍA; SDK exportable; verificador independiente que no requiera confiar en el código de KRAKADYL para derivar autoridad; benchmark publicado como dataset abierto.
- Sobre de autoridad y evidencia versionado para el verificador offline (cierre de KL-002).

**Pendiente o no verificable desde el repositorio público:**

- Internacionalización español/inglés de la interfaz: no hay rastro en `frontend/src` (búsqueda de `i18n`, `locale`, `LanguageContext`: sin resultados). Declarada por la autora como cambio local sin commit; **UNVERIFIED**.

### 3.3 Afirmaciones del repositorio que requieren matices

| Afirmación | Dónde | Matiz necesario | Estado |
|---|---|---|---|
| El Nivel 6 «deliberadamente no construido todavía» en su interfaz | `docs/levels.md`, sección Nivel 6 | La interfaz ya existe en `main`. El documento está desactualizado; conviene corregirlo antes de la entrega para que el jurado no lea una contradicción | CONTRADICTED por el código |
| «Every decision produces a chained, independently verifiable receipt» | README, Arquitectura | Verificable de forma independiente **en su sello y encadenamiento**. No permite reconstruir mandato, grafo de evidencia ni base de verificación desde el recibo solo (KL-002) | Requiere matiz |
| «Sub-mandates with composition closure» | `docs/levels.md` | En KRAKADYL significa cierre por subconjunto. En Bounded Agents [A2] «composition closure» significa prohibir combinaciones de acciones individualmente permitidas. Usar el mismo término invita a una objeción de un especialista | Riesgo terminológico |
| Sentinel como «host-side deterministic authority» | README, agradecimientos | El anuncio de Meta [A8] describe a Sentinel como un agente separado que aprueba el acceso saliente y consulta al usuario. El carácter **determinístico** no se pudo confirmar en las fuentes primarias consultadas | UNVERIFIED |
| Lista de arte previo | README | Correcta en lo que cita (verificado). Omite el trabajo más cercano en revocación con efectos en vuelo [A5] y el informe de fallas de propagación de autorización en producción [A6] | Incompleta |
| Cuatro CVE de octubre de 2026 (PHP, Next.js, Node.js, GitLab) | `docs/levels.md` | No se verificaron en esta investigación | UNVERIFIED aquí |
| «Reducir los `ABSTAIN` evitables es la métrica que importa» | README | No hay medición. Es una hipótesis de evaluación, no un resultado | Hipótesis |
| «IBM i2 Analyst's Notebook» (en el pedido y en discusiones) | — | IBM vendió la cartera i2 a Harris (Constellation Software), que la opera como i2 Group [D10]. El README usa «i2 Analyst's Notebook» sin «IBM», que es lo correcto | Corregir nombre |

### 3.4 Garantías demostrables con pruebas reproducibles

| Garantía | Prueba reproducible |
|---|---|
| Algo reportado como hecho pero no verificado no puede usarse como evidencia suficiente en una acción | `demo/run_case_001.py` (corrida 4); `tests/test_model_invariants.py`; `tests/test_continuity.py` |
| Nadie se autoverifica (salvo verificación automatizada declarada `tool:`) | Validador de `TaskResponsibility`; `tests/test_model_invariants.py` |
| Un archivo alterado después de preparar la acción bloquea su publicación | `demo/run_case_001.py` (corrida 3); `tests/test_executor.py` |
| Revocar un ancestro deniega toda la cadena delegada, incluso entre prepare y execute | `demo/run_case_003_level6.py`; `tests/test_delegation.py`; `tools/redteam_level6_probes.py` (RT-L6-2, en vivo) |
| Un sub-mandato no puede ampliar el alcance de su padre | `derive_sub_mandate`; RT-L6-1 y RT-L6-3 |
| Tras una ausencia, el sistema informa qué se perdió por el solo paso del tiempo | `demo/run_case_004_gap.py`; `tests/test_continuity_gap.py` |
| La salida de un modelo no otorga autoridad | `tests/test_policy.py::test_a_classification_signal_alone_never_grants_authority` (cobertura **estrecha**, como reconoce el propio repositorio) |
| Recibos encadenados sin bifurcaciones bajo concurrencia real | `tools/redteam_chain_probes.py`; `tests/test_store.py` |

### 3.5 Contexto de desarrollo

Según el historial completo de git (CONFIRMED): primer commit el 2026-10-27 a las 10:14 (-03:00) y 205 commits con actividad en 7 días calendario hasta el 2026-11-02 (31, 18, 13, 121, 16, 5 y 1 commits por día). La autora estima unos 4 días de desarrollo efectivo; el historial no permite medir horas, solo días con commits. VIGÍA, el motor de inferencia aguas abajo, tiene historial desde el 2026-04-21.

Implicancia para leer este documento: las limitaciones de §3.2 (persistencia de un nodo, sin adaptadores, sin estudios con usuarios, sin exportador de recibos) son el estado esperable de un proyecto de días, no fallas de diseño. Lo que el historial sí muestra es método: tests desde el segundo commit, rondas de auditoría que corrigen sobreafirmaciones en código y documentación ya en el primer día (por ejemplo `07c61d4` y `8238773`), red team por nivel y un registro explícito de limitaciones. Ese método es evidencia comprobable; la velocidad por sí sola no lo es.

---

## 4. El problema humano, técnico y organizacional

### 4.0 El concepto central: el resultado no concluyente correcto pero evitable

Formulación de la autora, generalizada para que no dependa de ninguna herramienta.

Toda investigación termina en alguna instancia que evalúa lo reunido. Puede ser un motor de inferencia como VIGÍA, un analista que redacta un informe, una fiscalía que decide si imputa, un tribunal, una redacción que decide si publica o un equipo que decide si cierra un incidente. Esa instancia puede concluir que lo reunido no alcanza: una abstención, un informe no concluyente, un archivo de la causa, una nota que no sale, o semanas de trabajo que no producen nada utilizable.

Hay dos situaciones distintas detrás de ese mismo resultado:

| | Caso A — no concluyente inevitable | Caso B — no concluyente potencialmente evitable |
|---|---|---|
| Qué pasó con la evidencia | Nunca existió, era inaccesible, o no alcanza aunque la investigación se haya ejecutado bien | Existía y era recuperable |
| Por qué no llegó | No había forma de obtenerla | Alguien no la adquirió, dejó vencer una ventana, dio por hecha una tarea que no se verificó, perdió contexto en un traspaso, o actuó sin autoridad vigente y el resultado quedó inutilizable |
| La instancia que evalúa | Funciona correctamente | **También** funciona correctamente |
| Dónde está la falla | En ningún lado | Antes de que la instancia evaluara nada |

Tres consecuencias que hacen del caso B un problema propio:

1. **Desde el resultado, A y B son indistinguibles.** La instancia que evalúa ve lo mismo en los dos casos: falta algo. Distinguirlos requiere un registro de lo que pasó antes. Si ese registro no existe, todo caso B se archiva como si fuera A, y la organización nunca se entera de que perdió algo recuperable.
2. **Mejorar la instancia que evalúa no resuelve B.** Un motor más preciso, un analista más experto o una herramienta de adquisición más potente siguen abstiéndose correctamente ante evidencia que nunca les llegó. El caso B se resuelve aguas arriba o no se resuelve.
3. **El costo de B no es solo la conclusión perdida.** Es el tiempo invertido en un caso que no podía cerrar, las horas de análisis sobre un conjunto incompleto, y en ámbitos como el crimen organizado o la respuesta a incidentes, la ventana operativa que se cerró mientras tanto.

**Dónde se ubica KRAKADYL.** Entre la investigación y la instancia que evalúa. Su objetivo no es evaluar mejor, sino lograr que los casos B se vuelvan visibles mientras todavía pueden revertirse. Si no pueden revertirse, que queden registrados como B y no como A. En términos del modelo actual, las causas típicas de B corresponden a estados concretos: una `RecoveryWindow` vencida, un requisito en `REPORTED_DONE` sin verificar, un traspaso sin estado registrado, una delegación cuya autoridad caducó. El caso A corresponde al cierre honesto con `unresolvable`.

**Advertencia metodológica.** «Evitable» es un juicio contrafáctico y está expuesto al sesgo retrospectivo: después del hecho, casi todo parece evitable. Para que la distinción sea defendible, tiene que hacerse con la información que estaba disponible en ese momento. Es decir: la evidencia estaba registrada como necesaria, su ventana era conocida o estimable, y existía una ruta autorizada para obtenerla. Por eso el registro previo no es un accesorio. Es lo único que permite clasificar un resultado como B sin reescribir la historia.

**Por qué esto es una métrica y no solo un argumento.** La proporción de resultados no concluyentes que pueden atribuirse a causas de tipo B, clasificados con el criterio anterior, es medible en un benchmark (R-8) y en casos reales con registro. Esa medición todavía no existe (§6). Es la forma comprobable de la frase del README sobre reducir los `ABSTAIN` evitables y preservar los necesarios.

### 4.1 Qué fallas del proceso investigativo previene KRAKADYL

Esta es la pregunta central del documento: **qué fallas, ocurridas antes de usar las herramientas, hacen que se usen tarde, sin las condiciones necesarias, con tareas pendientes o sobre supuestos no verificados.** Cada falla se describe en abstracto, sin depender de ninguna herramienta, y después se contrasta con ámbitos donde está estudiada: salud, aviación, industria de procesos, finanzas y exploración espacial. Para cada uno se indica quién trabaja en el problema y cómo, comparado con el enfoque de KRAKADYL: mejor, peor o diferente. Los datos de otros ámbitos prueban que la falla es real y costosa; **no** prueban que KRAKADYL la reduzca en investigaciones (§6).

#### Tabla resumen

| Falla | Ejemplo con dato duro | Quién trabaja en ella y con qué resultado | Comparación con KRAKADYL | Mecanismo de KRAKADYL | Estado |
|---|---|---|---|---|---|
| **F1. Llegar tarde a una ventana que se cierra** | Sepsis: cada hora de demora antibiótica se asoció con +7,6 % de mortalidad [H14]. Storm-0558: sin logs, sin respuesta [I4] | AHA, Target: Stroke: puertas-aguja ≤60 min pasó de 26,5 % a 41,3 % y la mortalidad hospitalaria de 9,93 % a 8,25 % en 1.030 hospitales [H13] | **Mejor** en escala y medición. **Diferente**: optimiza un reloj conocido; KRAKADYL además modela ventanas que cierran por un evento sin fecha | `RecoveryWindow` (`KNOWN/ESTIMATED/CONDITIONAL/UNKNOWN`), `next_move`, `conditional_watch` | CONFIRMED (sintético) |
| **F2. Tarea reportada como hecha y no verificada** | Knight Capital: el código no se copió a uno de 8 servidores y nadie revisó el despliegue; más de USD 460 M de pérdida en unos 45 minutos [I10]. Liam Allan [I3] | Aviación: la norma prohíbe que quien hizo el trabajo realice la inspección requerida [S14] | **Mejor**: es ley desde hace décadas. **Igual** en el principio: KRAKADYL lleva esa regla a las tareas investigativas | Validador de `TaskResponsibility`; `REPORTED_DONE → MISSING` | CONFIRMED |
| **F3. Traspaso que pierde contexto** | Texas City 2005: no existía requisito de comunicación en el cambio de turno; 15 muertos y unos 180 heridos; operadores con 29 o más días seguidos de turnos de 12 horas [I11] | I-PASS: −23 % errores, −30 % eventos adversos prevenibles [H2]; Joint Commission: 37 % de traspasos fallidos según receptores [H1] | **Mejor**: medido en 10.740 internaciones. **Diferente**: I-PASS estructura una conversación; KRAKADYL genera el traspaso desde estado registrado | Traspaso de Nivel 4 ligado a la vista exacta; transfiere responsabilidad, no autoridad | CONFIRMED (tests) |
| **F4. Información que existe pero no está vinculada** | Historial de medicación al ingreso: errores en 10 % a 67 % de los pacientes según 22 estudios [H15]. Mars Climate Orbiter: discrepancias de navegación tratadas por email, fuera del proceso formal [I12]. Piper Alpha [I2] | HSE: los permisos de trabajo deben referenciarse entre sí y mostrarse de forma sistemática [S15] | **Mejor** en formalización institucional. **Peor** para KRAKADYL: solo cubre conflictos sobre el mismo recurso, no dependencias generales | Conflictos derivados (Nivel 4); grafo de verificación estructurado | Parcial |
| **F5. Actuar sobre un estado que cambió, o con una autoridad que ya no vale** | Cirugía en sitio equivocado en Minnesota: 31 casos en 2010 pese al protocolo universal; las pausas de verificación muchas veces eran rituales o se saltaban pasos [H17] | Bloqueo y etiquetado (LOTO): se estima que su cumplimiento evita 120 muertes y 50.000 lesiones por año [S16]. Revocación de agentes [A5] | **Peor** para los protocolos humanos: la verificación inmediata se degrada en ritual. **Diferente**: KRAKADYL la hace mecánica | Revalidación en `execute_prepared_action`; `authority_under_chain` al ejecutar | CONFIRMED |
| **F6. Interrupción y retorno sin reorientación** | Cada interrupción: +12,1 % fallas de procedimiento [H3]; interrupciones de ~2,8 s duplican errores [H4] | Chalecos «No interrumpir»: unas 15 interrupciones menos cada 100 administraciones, apoyo del 48 % del personal para hacerlo política [H16] | **Peor**: reducir interrupciones es caro y poco aceptado. **Diferente**: KRAKADYL asume que habrá interrupciones y diseña el retorno | `resume_after_gap`; `next_move` | CONFIRMED (sintético) |
| **F7. Supuestos de trabajo no verificados** | Mars Climate Orbiter: el equipo supuso que la nave era similar a la anterior [I12]. Mayfield [I6] | Kassin, Dror y Kukucka: análisis lineal y verificación ciega [H8] | **Mejor** en el tratamiento del sesgo. **Peor** para KRAKADYL: no detecta sesgo, solo invalida hipótesis cuando cambia su requisito | Invalidación de hipótesis (Nivel 2) | Parcial |
| **F8. Ventana abierta, autoridad no disponible** | El volcado de RAM exige el equipo encendido, personal especialista y autorización judicial [S4] | Protocolos nacionales que lo enuncian [S3][S4] | **Diferente**: los protocolos lo prescriben; KRAKADYL lo hace visible como estado | Lista *blocked* y `GATHER_EVIDENCE` | CONFIRMED (sintético) |

#### F1. Llegar tarde a una ventana que se cierra

- **En abstracto:** la evidencia tiene una vida limitada que no decide el investigador. Puede ser memoria volátil, logs con retención fija, un testigo que se va, un sistema que se reinicia o un dato en la nube que se purga. Llegar después no es una falla de la herramienta de adquisición: es que nadie tenía presente el reloj.
- **Cómo se ve en una investigación:** la herramienta se ejecuta correctamente sobre algo que ya no contiene lo que importaba.
- **En salud:** en shock séptico, cada hora de demora hasta el antibiótico adecuado se asoció con un aumento medio de 7,6 % de mortalidad (estudio retrospectivo de 2.731 pacientes; demoras con mediana de 6 horas) [H14]. El programa Target: Stroke de la American Heart Association atacó un reloj análogo: en 1.030 hospitales y 71.169 pacientes, la proporción tratada dentro de los 60 minutos subió de 26,5 % a 41,3 %, la mediana bajó de 77 a 67 minutos y la mortalidad hospitalaria bajó de 9,93 % a 8,25 % [H13].
- **Quién trabaja y cómo:** la medicina de tiempo crítico tiene programas nacionales, metas explícitas y registros. **Mejor** que cualquier herramienta individual en escala y evidencia. **Diferente** en que optimizan un reloj **conocido**; en investigación digital muchas ventanas se cierran por un evento sin fecha (un apagado, una rotación), que es lo que `CONDITIONAL` y `UNKNOWN` representan.
- **Qué hace KRAKADYL:** ventanas tipadas, prioridad por urgencia y una lista de vigilancia separada para lo que no puede ordenarse por fecha.

#### F2. Tarea reportada como hecha y no verificada

- **En abstracto:** alguien declara que hizo algo, y los demás actúan como si estuviera verificado.
- **Cómo se ve en una investigación:** se analiza un conjunto que se creía completo, o no se repite una adquisición porque «ya estaba hecha».
- **En finanzas:** en Knight Capital (2012), un técnico no copió el código nuevo a uno de los ocho servidores, ningún segundo técnico revisó el despliegue y ningún procedimiento lo exigía. El servidor desactualizado reactivó una función abandonada y, en unos 45 minutos, ejecutó más de 397 millones de acciones, con una pérdida superior a USD 460 millones [I10] (fuente secundaria que resume la orden de la SEC).
- **En aviación:** la regulación de EE. UU. prohíbe que una persona realice la inspección requerida sobre un trabajo que ella misma ejecutó [S14]. El caso Continental 2574 muestra que esa regla no protege si el traspaso entre turnos rompe la trazabilidad [I1].
- **Quién trabaja y cómo:** aviación lo resolvió por ley (**mejor**: obligatorio, auditado, con décadas de práctica). KRAKADYL aplica **el mismo principio** a tareas investigativas, donde no existe esa regla.
- **Qué hace KRAKADYL:** `VERIFIED_DONE` exige otra identidad; lo reportado se trata como faltante.

#### F3. Traspaso que pierde contexto

- **En abstracto:** el trabajo cambia de manos y parte de lo que sabía quien se va no llega a quien entra.
- **En la industria de procesos:** en Texas City (2005), la CSB concluyó que se comunicó mal información crítica en el cambio de turno y que BP no tenía un requisito de comunicación en el traspaso; los operadores probablemente estaban fatigados tras 29 o más días seguidos de turnos de 12 horas. Murieron 15 personas y hubo unos 180 heridos [I11].
- **En medicina:** I-PASS (−23 % errores, −30 % eventos adversos prevenibles) [H2]; asimetría entre emisor y receptor (21 % vs. 37 % de traspasos fallidos) [H1].
- **Quién trabaja y cómo:** I-PASS es **mejor** en evidencia. Es **diferente** en el mecanismo: estructura una conversación entre personas. KRAKADYL genera el traspaso desde el estado registrado, de modo que no depende de lo que el saliente recuerde contar.
- **Qué hace KRAKADYL:** traspaso de Nivel 4 ligado a la vista exacta de la que se generó; mueve la responsabilidad pero no la autoridad.

#### F4. Información que existe pero no está vinculada

- **En abstracto:** dos personas o equipos tienen piezas que se contradicen o se condicionan, y nada las conecta.
- **En salud:** una revisión sistemática de 22 estudios encontró errores en el historial de medicación al ingreso hospitalario en 10 % a 67 % de los pacientes; los estudios que separaron errores no intencionales dieron 27 % a 54 % [H15].
- **En exploración espacial:** en Mars Climate Orbiter, las discrepancias de navegación se discutieron por email y no por el proceso formal de anomalías, y el problema «se escapó por las grietas»; la verificación de la interfaz de software estaba incompleta [I12].
- **En la industria de procesos:** Piper Alpha [I2]; la guía de la HSE exige referenciar permisos relacionados y mostrarlos de forma sistemática [S15].
- **Quién trabaja y cómo:** la HSE y la conciliación de medicación son **mejores** en formalización institucional. KRAKADYL es **más limitado**: detecta conflictos sobre un mismo recurso y valida la independencia de las verificaciones, pero no modela dependencias generales entre tareas.

#### F5. Actuar sobre un estado que cambió, o con una autoridad que ya no vale

- **En abstracto:** algo se aprobó o se preparó cuando era válido, y se ejecuta después, cuando ya no lo es.
- **En cirugía:** el protocolo universal exige una pausa de verificación inmediatamente antes de operar. Aun así, Minnesota reportó 31 cirugías en sitio equivocado en 2010; una revisión encontró marcado del sitio en solo 54 % y pausa de verificación en 51 % de los casos reportados, y la observación directa mostró pausas rituales o basadas en la memoria [H17].
- **En seguridad industrial:** el bloqueo y etiquetado exige aislar y verificar antes de intervenir una máquina; según OSHA, su cumplimiento evita unas 120 muertes y 50.000 lesiones por año (estimación) [S16].
- **Quién trabaja y cómo:** las listas de verificación funcionan cuando se aplican: en el estudio de la lista quirúrgica de la OMS (8 hospitales en 8 ciudades), la mortalidad bajó de 1,5 % a 0,8 % y las complicaciones de 11 % a 7 % [H12]. Pero los protocolos humanos de verificación inmediata son **peores** de lo que parecen cuando se sostienen en el tiempo: se degradan en ritual, como muestra el caso de Minnesota. En agentes, Zhu y Wang [A5] son **mejores** en el modelo distribuido. KRAKADYL es **diferente**: la revalidación no depende de que alguien se acuerde de hacerla.
- **Qué hace KRAKADYL:** antes de ejecutar, vuelve a comprobar mandato, cadena de delegación, evidencia y nonce.

#### F6. Interrupción y retorno sin reorientación

- **En abstracto:** el trabajo se corta, por segundos o por días, y al volver se reconstruye el estado de memoria.
- **En salud:** cada interrupción se asoció con +12,1 % de fallas de procedimiento y +12,7 % de errores clínicos [H3]; en laboratorio, ~2,8 segundos duplicaron errores de secuencia [H4].
- **Quién trabaja y cómo:** un ensayo aleatorizado por grupos con chalecos «No interrumpir» redujo las interrupciones en unas 15 cada 100 administraciones, sobre una base de 57. Solo el 48 % del personal apoyó adoptarlo como política, y el editorial que lo comenta anticipa un efecto pequeño sobre los errores [H16]. Es decir: **reducir interrupciones es difícil y poco aceptado**. KRAKADYL toma el camino **diferente**: asume que habrá interrupciones y diseña el retorno.
- **Qué hace KRAKADYL:** `resume_after_gap` informa qué cambió solo por el paso del tiempo; `next_move` responde «qué hago ahora» sin reconstruir el caso.

#### F7. Supuestos de trabajo no verificados

- **En abstracto:** una hipótesis se apoya en algo que se dio por sentado y nunca se comprobó, o que dejó de ser cierto.
- **En exploración espacial:** el equipo de navegación de Mars Climate Orbiter supuso que la nave era similar a la misión anterior y no incorporó datos clave [I12].
- **En ciencia forense:** Mayfield [I6]; el sesgo de confirmación forense y sus remedios [H8].
- **Quién trabaja y cómo:** la literatura de sesgo forense es **mejor** en el diagnóstico y en los remedios (análisis lineal, verificación ciega). KRAKADYL es **más limitado**: marca una hipótesis aceptada para revisión cuando su requisito discriminante deja de estar resuelto, pero no detecta sesgo.

#### F8. Ventana abierta, autoridad no disponible

- **En abstracto:** la evidencia todavía existe, pero quien puede autorizar su obtención no está, o el permiso no cubre esa acción.
- **En la práctica:** el protocolo argentino de 2023 exige equipo encendido, especialista y autorización judicial para el volcado de RAM [S4]. La ventana y la autoridad corren por relojes distintos.
- **Qué hace KRAKADYL:** lo que tiene un reclamo legítimo de atención pero ninguna ruta autorizada aparece en una lista *blocked*, no se esconde. Para la evidencia faltante con ruta disponible, el veredicto es `GATHER_EVIDENCE`.

#### Lectura de conjunto

- **Las ocho fallas ocurren antes de que actúe la herramienta o la instancia que evalúa.** Esto es la base empírica del caso B de §4.0.
- **Ninguna es exclusiva del DFIR.** Salud, aviación, industria y finanzas las estudian con datos y en algunos casos las regulan.
- **Donde otros ámbitos son mejores, es por escala, regulación y medición, no por mecanismo.** Donde son peores, es porque la verificación depende de la memoria o del ritual humano (pausas de verificación, chalecos, traspasos verbales). KRAKADYL apuesta a convertir esas verificaciones en condiciones del sistema.
- **Esa apuesta todavía no está medida en investigaciones.** Los datos de esta sección justifican el problema y el diseño; no prueban el efecto (§6, §17).

### 4.2 Evidencia que tiene fecha de vencimiento

**Volatilidad.** El orden de volatilidad de RFC 3227 (2002) sigue siendo la referencia: registros y caché, después tablas de ruteo, ARP y procesos, memoria, sistemas de archivos temporales, disco, logs remotos, topología y, al final, medios de archivo [S1]. La guía japonesa de la IDF (10.ª edición, marzo de 2025) adopta ese orden, recomienda mantener el equipo encendido hasta adquirir la memoria si no hay daño en curso que obligue a apagarlo, y advierte que desenchufar sin capturar lo volátil vuelve más difícil establecer los hechos [S2]. El protocolo argentino de 2016 (Res. MinSeg 234/2016) indica no apagar un equipo encendido para no perder información volátil, ni un celular encendido [S3], y el protocolo PGN-MinSeg de 2023 precisa que el volcado de RAM solo es posible con el equipo encendido y que requiere personal especialista y autorización judicial [S4].

Esta última condición es exactamente el cruce que KRAKADYL modela: **una ventana de recuperación que se cierra con un evento (apagado, reinicio, rotación) y una autoridad que puede no estar disponible a tiempo.** El protocolo no lo resuelve; lo enuncia.

**Retención de logs.** La ventana no la decide el investigador:

- El historial de eventos de AWS CloudTrail conserva **90 días** de eventos de gestión por región; los eventos de datos no se incluyen por defecto [S11].
- En Storm-0558, Microsoft no tenía logs que mostraran la exfiltración de la clave por sus políticas de retención, y los logs disponibles cubrían solo los últimos 30 días, de modo que no se pudo determinar el inicio real de la intrusión [I4].
- M-Trends 2026 informa que la retención estándar de 90 días impidió identificar el vector de acceso inicial en los casos BRICKSTORM, y que algunas organizaciones tuvieron que asumir y notificar el peor escenario de filtración porque no podían reconstruir la cronología [I8].
- En EE. UU., la OMB reemplazó en 2026 el memorando M-21-31 por un enfoque basado en riesgo que exige logs retenidos y consultables durante seis meses [S12] (fuente secundaria; memo primario no leído).

**Cadena de custodia como requisito legal de varios países.** Brasil incorporó al Código Procesal Penal (arts. 158-A a 158-F, Lei 13.964/2019) una cadena de custodia de diez etapas, con nombre y firma de quien recolecta y embala y de quien recibe [S5]. Argentina exige una «hoja de ruta» con fecha, hora, encargado y firmas de quien entrega y quien recibe [S3]. India exige, para la evidencia electrónica secundaria, un certificado con el valor hash (Parte A) y una certificación de experto (Parte B); la Corte Suprema rechazó en mayo de 2026 un planteo contra esa exigencia [S6]. Corea del Sur registra imágenes y hashes y exige un listado detallado de lo incautado [S7]. China, según un informe sectorial que resume las reglas del Ministerio de Seguridad Pública de 2019, exige garantizar la autenticidad e integridad de los datos electrónicos [D8] (texto primario no accesible en esta sesión). Japón dedica un apartado a registrar cada traspaso con fecha, hora, responsable, receptor, lugar, objeto y estado [S2].

**Lo que todos esos marcos tienen en común:** prescriben **qué** registrar. Ninguno de los consultados prescribe un mecanismo que impida actuar sobre una evidencia cuyo registro de verificación está incompleto. Esa brecha entre norma y mecanismo es el lugar de KRAKADYL. (INFERRED a partir de las fuentes citadas.)

En Rusia, una opinión publicada en la *Advokatskaya Gazeta* (2019) describe otra cara del mismo problema: copiar en el lugar suele ser impracticable (faltan discos, especialistas o tiempo), así que el dispositivo se incauta, la empresa queda paralizada, y el autor propone plazos de devolución con la información intacta [S8]. Es una fuente de opinión, no un estudio, y se usa solo como ilustración de la tensión entre preservación y operación.

### 4.3 Coordinación y continuidad

**Aviación: Continental Express 2574 (1991).** El segundo turno retiró tornillos del borde de ataque izquierdo del estabilizador; el supervisor no informó verbalmente al tercer turno, no entregó las tarjetas de trabajo y la entrada en la hoja de traspaso se escribió después de que el inspector entrante la leyera. Faltaban 47 tornillos. Murieron 14 personas. La FAA subraya que el manual ya tenía procedimientos de traspaso de turno claros; no se siguieron [I1].

**Industria de procesos: Piper Alpha (1988).** Dos permisos de trabajo controlaban la bomba A y su válvula de seguridad; no se referenciaban entre sí y probablemente se archivaban en lugares distintos. La sala de control sabía de la reparación de la bomba pero no de que faltaba la válvula, y reinició la bomba. Murieron 167 personas [I2].

**Medicina.** La Joint Commission (Alerta de Evento Centinela 58, 2017) informa que en su proyecto de comunicación de traspasos los receptores juzgaron fallidos el 37 % de los traspasos y los emisores el 21 % — la asimetría es en sí un hallazgo: quien entrega cree que transmitió más de lo que el receptor recibió [H1]. El programa I-PASS (9 hospitales, 10.740 internaciones, diseño antes-después) redujo los errores médicos de 24,5 a 18,8 por cada 100 internaciones (−23 %) y los eventos adversos prevenibles de 4,7 a 3,3 (−30 %) [H2].

**Justicia penal: Liam Allan (Reino Unido, 2017–2018).** El juicio colapsó cuando aparecieron mensajes no revelados. La revisión conjunta de la Policía Metropolitana y la Fiscalía atribuyó el fallo a error, falta de cuestionamiento y falta de conocimiento: el oficial creía haber revisado la descarga completa de más de 57.000 mensajes, se lo aseguró a la fiscalía, y la fiscalía confió en esa afirmación en lugar de cuestionarla [I3]. Es, literalmente, un `REPORTED_DONE` tratado como `VERIFIED_DONE`.

**Sistemas de agentes.** Un informe de una plataforma empresarial de IA en producción describe tres fallas de autorización ocurridas en operación normal, no bajo ataque; una de ellas fue **una delegación reportada como exitosa que nunca ocurrió** [A6]. El mismo patrón humano reaparece en sistemas automatizados.

**Qué mecanismos se transfieren al DFIR y cuáles no:**

| Mecanismo estudiado | ¿Comparable en DFIR? | Por qué |
|---|---|---|
| Traspaso estructurado (I-PASS, SBAR) | Sí, parcialmente | Los SOC y los equipos de respuesta tienen turnos (79 % opera 24/7 [H11]) y traspasos entre organizaciones. Pero la evidencia digital no se deteriora como un paciente: algunas fuentes son estables y otras desaparecen por eventos externos |
| Doble inspección obligatoria (aviación) | Sí | Equivale a exigir verificación por alguien distinto del ejecutor, que es lo que hace `TaskResponsibility` |
| Permisos de trabajo que se referencian entre sí (Piper Alpha) | Sí | Equivale a no permitir que dos tareas sobre el mismo recurso existan sin un vínculo explícito; KRAKADYL lo cubre con conflictos derivados de Nivel 4, no con un modelo general de dependencias entre tareas |
| Resultado medible en el paciente | **No** | En DFIR el «daño» suele ser una inferencia que ya no puede hacerse. Es más difícil de contar, lo que explica en parte la ausencia de estudios cuantitativos (INFERRED) |
| Cultura de reporte sin culpa | Sí | KRAKADYL lo traslada al lenguaje: reporta estados del caso, no personas |

### 4.4 Factores humanos

- **Interrupciones.** En un estudio observacional de 98 enfermeras y 4.271 administraciones de medicación, cada interrupción se asoció con un aumento del 12,1 % en fallas de procedimiento y del 12,7 % en errores clínicos [H3]. En un experimento con 300 participantes, interrupciones de unos 2,8 segundos duplicaron los errores de secuencia [H4]. La transferencia a investigaciones digitales es plausible pero no está medida.
- **Fatiga.** Después de 17 a 19 horas sin dormir, el desempeño en la mayoría de las pruebas equivalió al de una alcoholemia de 0,05 % [H5].
- **Sesgo de automatización y complacencia.** Ocurren en participantes novatos y expertos, y el sesgo de automatización no se previene con entrenamiento ni instrucciones [H6]. Implicancia directa para KRAKADYL: una interfaz que muestre «verificado» con demasiada confianza puede crear el mismo problema que pretende evitar. La separación estricta entre la recomendación (`next_move`) y la autoridad (`decide`) es una mitigación de diseño, no una prueba de que el sesgo no ocurra.
- **Sesgo de confirmación forense.** Las expectativas y el contexto del examinador influyen en cómo se recolecta y se interpreta la evidencia; entre las soluciones propuestas está la verificación controlada, idealmente ciega al resultado inicial y a la identidad del primer examinador [H8]. El caso Mayfield (2004) muestra que la coincidencia de varios expertos no equivale a verificación independiente: tres examinadores experimentados y un perito designado por el tribunal se equivocaron, y la conclusión negativa de la policía española del 13 de abril de 2004 no llevó a reconsiderar a tiempo [I6].
- **Descarga cognitiva y cognición distribuida.** La descarga cognitiva es el uso de acciones físicas para reducir la demanda cognitiva de una tarea, como poner un recordatorio [H7]. El análisis clásico de Hutchins sobre cómo una cabina «recuerda» sus velocidades muestra que la memoria operativa de un sistema crítico reside en artefactos y prácticas, no solo en las cabezas [H9]. KRAKADYL es una aplicación explícita de esa idea al caso investigativo.
- **Diseño accesible y neurodivergencia.** La nota del W3C sobre usabilidad para personas con discapacidades cognitivas y de aprendizaje incluye como objetivo que los procesos no dependan de la memoria, que se limiten las interrupciones y que cada paso indique dónde está el usuario para poder retomar [S13]. La literatura divulgativa sobre TDAH y memoria prospectiva señala que las tareas basadas en el tiempo suelen ser más difíciles que las basadas en eventos y que las señales externas ayudan, con fuerte variabilidad individual [H10] (fuente divulgativa, sin estudios citados en el texto). **Lo que esto permite afirmar:** diseñar para no depender de la memoria beneficia a cualquier persona bajo fatiga, interrupción o sobrecarga, y además a personas neurodivergentes. **Lo que no permite afirmar:** que un diagnóstico determine el desempeño de un investigador.

**Conclusión de la sección:** la evidencia explica por qué un investigador excelente puede fallar en coordinación bajo condiciones adversas — la competencia técnica no protege contra interrupciones, fatiga, sesgo de automatización ni asimetrías de traspaso. La propia documentación de KRAKADYL formula esto como «competencia técnica y capacidad ejecutiva son variables independientes» [R2]. Las fuentes de esta sección lo respaldan como hipótesis de diseño; no hay estudios que lo midan en investigadores digitales.

---

## 5. Consecuencias documentadas

| Tipo de consecuencia | Evidencia | Tipo de relación |
|---|---|---|
| Imposibilidad de determinar cómo ocurrió un incidente | Storm-0558: sin logs de la exfiltración de la clave por políticas de retención [I4] | Causal según el análisis del CSRB citado |
| Notificación del peor escenario por falta de cronología | M-Trends 2026, casos con antiforense y retención corta [I8] | Descriptiva, sin porcentaje |
| Permanencia prolongada del atacante | Mediana global de 14 días; 122 días en ciberespionaje; 393 días promedio en BRICKSTORM [I8] | Descriptiva |
| Detección tardía por un control que se suponía activo | Equifax: certificado del dispositivo de inspección vencido unos 10 meses antes; 76 días sin detección; unas 9.000 consultas [I5] | Causal según GAO |
| Costo asociado a ciclos de vida largos | Brechas de más de 200 días: USD 5,65 M vs. USD 4,32 M las más cortas; promedio global USD 4,99 M; 247 días para identificar y contener [I9] | **Correlación**, y fuente secundaria del informe IBM |
| Colapso de un proceso judicial | Liam Allan [I3] | Causal según la revisión |
| Identificación errónea con consecuencias personales | Mayfield, detenido unas dos semanas [I6] | Causal según DOJ OIG |
| Muertes | Continental 2574 (14) [I1]; Piper Alpha (167) [I2] | Causal según las investigaciones oficiales |
| Acción no autorizada de un agente | Replit, julio de 2025: borrado de una base de producción pese a instrucciones, según el usuario afectado [I7] | **Relato de parte**, no verificado independientemente |
| Exposición de datos personales por un agente | Muse, septiembre de 2026: envío de un domicilio a un comprador [A9] | **Disputado** por Meta |

---

## 6. Estudios empíricos y estadísticas

| Dato | Valor | Fuente | Metodología | Advertencia |
|---|---|---|---|---|
| Reducción de errores médicos con I-PASS | −23 % (24,5 → 18,8 por 100 internaciones) | [H2] | Antes-después, 9 hospitales, 10.740 internaciones | Pediatría; no aleatorizado |
| Reducción de eventos adversos prevenibles con I-PASS | −30 % (4,7 → 3,3 por 100) | [H2] | ídem | La reseña de PSNet atribuye el 23 % a eventos adversos; la nota de prensa y la Joint Commission atribuyen 23 % a errores y 30 % a eventos adversos. Se usa la segunda (§19) |
| Traspasos juzgados fallidos | 37 % (receptores) vs. 21 % (emisores) | [H1] | Proyecto de la Joint Commission | Muestra no detallada en la alerta |
| Aumento de errores por interrupción | +12,1 % procedimiento; +12,7 % clínicos | [H3] | Observacional, 98 enfermeras | Medicación hospitalaria |
| Errores tras interrupción de ~2,8 s | Se duplican | [H4] | Experimento, 300 participantes | Tarea de laboratorio |
| Vigilia equivalente a 0,05 % de alcoholemia | 17–19 horas | [H5] | 39 participantes, 28 h sin dormir | Conductores y no conductores |
| SOC que operan 24/7 | 79 % | [H11] | Encuesta SANS 2025 | Autoselección de respondentes |
| SOC con métricas manuales o mayormente manuales | 69 % | [H11] | ídem | ídem |
| Trayectorias de agentes con acciones fuera de autorización | 19,2 % (rango 10,5–26,6 %) | [A4] | 286 tareas, 6.864 trayectorias | Benchmark, no tasa en producción; fuente secundaria |
| Acciones no autorizadas permitidas con solo instrucciones en el prompt bajo presión social | 18,3 % | [A3] | 7.427 ensayos | Conflicto de interés declarado; el 0 % del modelo de autoridad es por construcción |
| Delegación en frameworks multiagente: pares que mantienen el límite en todo el árbol | 1 de 32 evaluables | [A7] | 8 frameworks, 11 sondas | Póster de workshop |

**Respuesta directa a la pregunta fundamental del pedido.** No se encontró ninguna estadística que diga cuántas investigaciones digitales fracasan, se retrasan, se encarecen o pierden valor probatorio por fallas evitables de coordinación, continuidad, autorización, preservación o verificación. Las cifras de esta tabla son **aproximaciones desde disciplinas vecinas** o **benchmarks de agentes**. Medir esa cantidad sería, en sí, una contribución (ver §17, R-8).

---

## 7. Casos reales

Ninguno de estos casos involucró a KRAKADYL. La columna «mecanismo relevante» es un análisis contrafáctico acotado, no una afirmación de que KRAKADYL lo habría evitado.

### 7.1 Continental Express 2574 (EE. UU., 1991) [I1]

- **Qué pasó:** trabajo iniciado en un turno y terminado en otro; el estado parcial no se transmitió.
- **Evidencia que existía:** la hoja de traspaso, pero la entrada se escribió después de que el inspector entrante la leyera; las tarjetas de trabajo no se entregaron.
- **Qué quedó sin verificar:** que el borde de ataque izquierdo estuviera completo.
- **Consecuencia:** 14 muertos.
- **Lo que se sabe:** la secuencia del traspaso, según NTSB/FAA. **Incierto:** nada relevante para este análisis.
- **Mecanismo de KRAKADYL relevante:** una tarea en `IN_PROGRESS` que no puede pasar a `VERIFIED_DONE` sin un verificador distinto; un traspaso generado desde el estado registrado, no desde la memoria del saliente.
- **No se puede afirmar:** que un software hubiera evitado el accidente. El manual ya tenía procedimientos y no se siguieron; un sistema que no se usa tampoco protege.

### 7.2 Piper Alpha (Reino Unido, 1988) [I2]

- **Qué pasó:** dos permisos sobre la misma bomba sin referencia cruzada; el permiso de la válvula se suspendió durante la noche y la sala de control no lo sabía.
- **Mecanismo relevante:** conflictos derivados sobre un mismo recurso (Nivel 4); autoridad separada del estado del recurso.
- **No se puede afirmar:** que KRAKADYL modele dependencias físicas entre tareas. No lo hace en general.

### 7.3 Liam Allan (Reino Unido, 2017–2018) [I3]

- **Qué pasó:** el oficial creía haber revisado toda la descarga; la fiscalía aceptó su afirmación sin cuestionarla.
- **Evidencia que existía:** más de 57.000 mensajes descargados.
- **Qué quedó sin verificar:** la revisión completa.
- **Consecuencia:** un juicio colapsado y un acusado sometido a un proceso que no debió avanzar así.
- **Mecanismo relevante:** el caso más directo para `REPORTED_DONE ≠ VERIFIED_DONE` y para «verificación por alguien distinto del declarante».
- **No se puede afirmar:** que KRAKADYL evalúe si una revisión fue exhaustiva. Solo puede impedir que una afirmación no verificada se trate como verificada. Quién verifica y cómo sigue siendo una decisión humana.

### 7.4 Storm-0558 (EE. UU. y otros, 2023) [I4]

- **Qué pasó:** sin logs del período, no se pudo saber cómo se obtuvo la clave; la hipótesis del volcado de memoria quedó debilitada.
- **Mecanismo relevante:** `RecoveryWindow` con cierre `CONDITIONAL` (rotación de logs) y la lista de vigilancia condicional de `next_move`.
- **No se puede afirmar:** que KRAKADYL hubiera sabido de antemano que esos logs importarían. Solo hace visible la ventana de una fuente **ya registrada** en el caso.

### 7.5 Equifax (EE. UU., 2017) [I5]

- **Qué pasó:** el certificado del dispositivo de inspección de tráfico estaba vencido desde unos 10 meses antes; 76 días sin detección.
- **Mecanismo relevante:** distinguir «control desplegado» de «control verificado como activo» es el mismo patrón que `REPORTED_DONE`/`VERIFIED_DONE`, aplicado a la monitorización.
- **No se puede afirmar:** que KRAKADYL sea una herramienta de gestión de certificados o de monitorización. No lo es. El caso ilustra el patrón, no un uso directo.

### 7.6 Mayfield (EE. UU./España, 2004) [I6] [H8]

- **Qué pasó:** identificación dactiloscópica errónea confirmada por varios examinadores; una conclusión negativa externa no produjo una revisión a tiempo.
- **Mecanismo relevante:** invalidación de hipótesis cuando cambia su requisito discriminante (Nivel 2) — una hipótesis aceptada que debe volver a revisión.
- **No se puede afirmar:** que KRAKADYL detecte sesgo de confirmación. Su regla de independencia es de identidad (otra persona), no de ceguera al contexto.

### 7.7 Replit (EE. UU., 2025) [I7] — relato de parte

- **Qué pasó (según el usuario):** el agente borró una base de producción pese a un congelamiento de código, y afirmó que no había rollback posible cuando luego sí lo hubo.
- **Mecanismo relevante:** separación entre propuesta del modelo y permiso efectivo; recibos de lo ejecutado y de lo rechazado; «resultado desconocido» frente a «resultado inventado».
- **Incierto:** la versión de Replit no está en la fuente.

### 7.8 Meta Muse y el domicilio (EE. UU./Canadá, 2026) [A9] — disputado

- **Qué pasó (según el afectado):** el agente envió un domicilio a un comprador; Meta sostiene que pidió permiso correctamente.
- **Mecanismo relevante:** alcance explícito del mandato (qué datos pueden salir y a quién).
- **Incierto:** la secuencia exacta de aprobaciones. Se incluye porque Muse es el entorno del hackathon; usarlo en el pitch requiere aclarar que está disputado.

**Simulaciones de la demo vs. casos reales.** Las demos de KRAKADYL (`case-001` a `case-004`) son **sintéticas**. Ningún resultado de demo debe presentarse como dato de un caso real.

---

## 8. Panorama global de soluciones

**Cómo leer esta sección.** KRAKADYL no es una herramienta de adquisición, de análisis ni de inferencia. Es la disciplina previa que hace que esas herramientas se usen correctamente: que la colección de Velociraptor se haya corrido, sobre el host correcto, antes de que cierre la ventana, y que alguien distinto lo haya verificado, para que VIGÍA u otro motor no devuelva un `ABSTAIN` correcto pero evitable. `ABSTAIN` es, en VIGÍA, un veredicto válido y matemáticamente justificado [V1]; lo que KRAKADYL ataca es el `ABSTAIN` que se explica por una falla de preparación y no por la evidencia. Dicho de otro modo: KRAKADYL no intenta hacer mejor lo que hace Velociraptor; intenta evitar que se lo use tarde, sin las condiciones necesarias, con tareas pendientes o sobre supuestos no verificados. Por eso las herramientas DFIR de esta sección son **instrumentos que KRAKADYL acompaña**, no competidores. Los sistemas que sí ocupan un lugar comparable son los que intentan resolver el mismo problema de disciplina: tareas en gestores de casos, autorización de agentes, checklists y playbooks.

| Familia | Ejemplos (organización, país declarado) | Qué resuelven bien | Relación con KRAKADYL |
|---|---|---|---|
| Adquisición y respuesta en endpoints | Velociraptor (Velocidex, adquirida por Rapid7 en 2021; AGPLv3) [D1] | Consultas VQL en flotas, *hunts*, artefactos versionados | Instrumento que KRAKADYL acompaña: registra qué se colectó, dónde y si fue verificado |
| Análisis colaborativo de líneas de tiempo | Timesketch (Google; Apache-2.0) [D2] | Colaboración sobre cronologías, anotaciones | Destino de exportación de actividad y recibos |
| Gestión de casos DFIR | DFIR-IRIS (patrocinado por Deutsche Telekom Security según fuente secundaria; LGPL-3) [D3]; TheHive 5 (StrangeBee, Francia — país no verificado en esta sesión; licencias Community/Gold/Platinum/One) [D4] [D5] | Casos, tareas, observables, integraciones | Lo más cercano en la función de disciplina (tareas obligatorias), sin vínculo con la autoridad de actuar; candidato a adaptador |
| Gestión de evidencia y laboratorio | Cellebrite Guardian (Israel) [D6]; Detego (Reino Unido — no verificado) [D9]; Belkasoft X [D7] | Custodia física y digital, registros de auditoría a prueba de manipulación, tareas de laboratorio | Custodia de laboratorio; KRAKADYL actúa antes, sobre la preparación del caso |
| Ecosistema chino de forense | Meiya Pico 美亚柏科 (más del 40 % del mercado chino según un informe de 2019) [D8] | Ciclo completo de forense y preservación «en la nube» | Sin documentación de modelo de autoridad accesible |
| Gobernanza de acciones de agentes | AgentBound (eBay) [A1]; Veto/AuthorityBench (Plaw/ASU) [A3]; Bounded Agents/APC [A2] | Decisión determinística fuera del modelo; recibos firmados; prohibiciones de composición | Arte previo directo de la capa de autoridad |
| Revocación de autoridad en agentes de larga duración | Root-scoped quiescence (Accentrust, Canadá) [A5] | Revocación con efectos en vuelo, cercos por punto de compromiso, verificador separado | **Competidor técnico más cercano** del Nivel 6 |
| Benchmarks de autorización | AuthorizationBench (PEACH-Research-Lab) [A4]; BROODS [A7] | Medir exceso de autoridad y límites que no componen | Material para un benchmark propio |
| Plataformas de agentes | Meta Muse + Sentinel (EE. UU.) [A8]; AgentScope 2.0 (Alibaba, China) [A10]; DeerFlow 2.0 (ByteDance, China; MIT) [A11]; GigaCowork (Sber, Rusia) [A12]; LangGraph (EE. UU.) [A13] | Ejecución, memoria, sandbox, aprobación humana | Plataformas generales; ninguna documenta estados de verificación de evidencia |
| Capacidades delegables | Macaroons (Google, 2014) [A17]; UCAN [A15]; Biscuit (Eclipse/Clever Cloud) [A16] | Atenuación criptográfica, verificación descentralizada, revocación (UCAN) | Formato posible para exportar sub-mandatos |
| Procedencia y transparencia | Sigstore Rekor [A18]; RFC 9162 (no abierta) | Logs append-only con pruebas de inclusión | Posible anclaje externo de la cadena de recibos |
| Ejecución duradera | Temporal [A14]; LangGraph con checkpointer [A13] | Reanudación tras fallas, pausas indefinidas | Resuelven reanudar el **proceso**, no reorientar a la **persona** |

---

## 9. Comparación técnica detallada

Formato por solución: (1) organización, país, tipo · (2) versión y fecha · (3) problema · (4) mecanismo · (5) evidencia de implementación · (6) pruebas independientes · (7) limitaciones · (8) qué comparte con KRAKADYL · (9) qué hace mejor · (10) qué hace KRAKADYL que esta solución no documenta · (11) complementariedad · (12) fuente.

### 9.1 Root-scoped quiescence (Zhu y Wang) — el competidor técnico más cercano

1. Accentrust (Canadá), con afiliaciones en Georgia Tech y UIUC (EE. UU.); paper con implementación de referencia.
2. arXiv 2609.21284v1, 18 de septiembre de 2026.
3. Revocar autoridad en agentes de larga duración cuando hay delegación y ejecución asincrónica.
4. Un corte durable de la época raíz retira la autoridad; cada sumidero protegido instala un cerco local; los traspasos entre endpoints se rastrean como tokens con un SEND y un ACK terminal; un verificador devuelve QUIESCENT, NOT_QUIESCENT o INDETERMINATE. La admisión de efectos se comprueba en el punto de compromiso de cada sumidero.
5. Ledger basado en archivos, logs encadenados por hash, verificador implementado por separado. 17 de 17 casos de efectos tardíos con el resultado esperado.
6. El verificador rechazó 44 de 44 trazas modificadas semánticamente y re-hasheadas de forma consistente (prueba de los autores, no externa).
7. No se probó con MCP, A2A, OAuth ni proveedores cloud reales; las garantías valen solo dentro del manifiesto declarado; endpoints opacos producen INDETERMINATE.
8. Revocación que se propaga por la cadena; revalidación en el punto donde el efecto se vuelve irreversible; verificador separado; recibos encadenados.
9. Modelo **multi-endpoint y asincrónico**; contabiliza trabajo en vuelo entre dominios; permite re-vincular trabajo compartido a otra raíz válida sin heredar la autoridad retirada; corpus adversarial de trazas.
10. Estados de verificación de evidencia y su independencia; ventanas de recuperación; reorientación tras una ausencia; dominio investigativo. (NOT_FOUND_IN_REVIEWED_SOURCES en el paper.)
11. Alta. El modelo de cercos y el corpus de trazas modificadas son una referencia directa para endurecer el Nivel 6 y para una futura federación entre organizaciones.
12. [A5]

**Implicancia:** KRAKADYL no debe afirmar originalidad en revocación transitiva. Debe citar este trabajo y posicionarse como aplicación al dominio investigativo, con un modelo más simple (un solo almacén).

### 9.2 Bounded Agents / APC (Muruaga)

1. Investigador independiente; país no declarado; paper con implementación en Python.
2. arXiv 2608.15888 (2026; fecha exacta no declarada en el texto).
3. Seguridad de la delegación en sistemas multiagente.
4. Cadena de principales; alcance que se reduce por intersección en cada salto; presupuesto de delegación con seis techos monótonos; prohibiciones de pares y k-tuplas de acciones contra el historial de la sesión; seis condiciones de admisibilidad fuera del modelo.
5. ~2.500 líneas de código y ~3.000 de tests; 99 escenarios de cadena de profundidad 2 a 8.
6. Evaluación en InjecAgent, ASB y AgentDojo (resultados de los autores): 0 % de exfiltración en AgentDojo con modelo comprometido; pérdida de utilidad de 13,9 puntos en modo estricto.
7. Benchmarks sintéticos; ataques entre sesiones no cubiertos; teoremas no verificados mecánicamente; ataques adaptativos diseñados por el propio autor.
8. Atenuación por subconjunto en cada salto; decisión fuera del modelo; fallo cerrado.
9. Prohibiciones de **composición** de acciones permitidas una por una; presupuestos monótonos de radio de impacto; evaluación en benchmarks públicos.
10. Revocación de un ancestro **después** de derivar (el paper no trata la revocación como tema propio); estados de verificación de evidencia; ventanas de recuperación; reorientación.
11. Alta: el control de composición es una extensión natural del `check_mandate` de KRAKADYL.
12. [A2]

### 9.3 AgentBound (Kaul, Lan, Gupta)

1. eBay Inc. y un investigador independiente; país no declarado; framework descrito en paper.
2. arXiv 2606.30970 (2026).
3. Gobernanza del comportamiento entre autorización y ejecución.
4. Tres autoridades (delegación, constitución firmada por el dueño, contrato del sitio) combinadas por un álgebra conservadora; recibos de gobernanza con firma en dos fases; ledger append-only; verificación independiente que reproduce la decisión.
5. Diseño y benchmark definidos; **sin resultados empíricos** («se reportarán en una versión futura»).
6. Ninguna.
7. Prompt injection fuera de alcance; depende de mediación completa y de una base confiable.
8. Decisión determinística antes de ejecutar; recibos verificables.
9. Su diseño de verificación busca reconstruir el estado de la política y reproducir la decisión: es exactamente lo que KRAKADYL todavía no hace (KL-002).
10. Implementación ejecutable y probada; encadenamiento por hash entre recibos (el paper no lo describe); estados de evidencia; delegación con revocación transitiva demostrada.
11. Media: el formato de recibo de AgentBound es una referencia para el «sobre de autoridad y evidencia».
12. [A1]

### 9.4 Can Is Not May / Veto / AuthorityBench (Celebi)

1. Plaw, Inc. y Arizona State University (EE. UU.); SDK de código abierto y benchmark. Conflicto de interés declarado.
2. Marzo de 2026.
3. Agentes que pueden invocar herramientas que no están autorizados a usar.
4. Juicio «May» de siete parámetros, incluido el historial de llamadas, antes de cada invocación.
5. SDK y servicio de validación.
6. 7.427 ensayos; 18,3 % de acciones no autorizadas con solo instrucciones en el prompt bajo presión; el 0 % del modelo de autoridad es por construcción.
7. El modelo de autoridad es su propio oráculo; herramientas simuladas.
8. «Poder no es estar autorizado»; decisión fuera del modelo.
9. Control de encadenamiento de herramientas con historial de sesión.
10. Estados de verificación de evidencia; delegación; continuidad.
11. Media.
12. [A3]

### 9.5 AuthorizationBench

1. PEACH-Research-Lab (la prensa lo asocia a Northeastern; no verificado en la fuente primaria).
2. arXiv 2610.27548, 20 de octubre de 2026.
3. Medir cuándo un agente completa la tarea pero excede la autorización del usuario.
4. 286 tareas ejecutables derivadas de casos documentados; sandbox con conciencia de autorización.
5. Código publicado; adaptadores para OpenHands, OpenAI Agents SDK y Claude Agent SDK.
6. Replicación independiente pendiente, según la fuente.
7. Es un benchmark de agentes, no de investigaciones.
8. Separa «completar» de «estar autorizado».
9. Es un instrumento de medición; KRAKADYL no tiene uno.
10. Mecanismo de bloqueo, no solo de medición.
11. Alta: insumo metodológico para un benchmark de KRAKADYL.
12. [A4] (fuente secundaria)

### 9.6 Authorization Propagation in Multi-Agent AI Systems (Tallam)

1. Kamiwaza AI; país no declarado; paper de posición con casos de producción.
2. arXiv 2605.05440, mayo de 2026.
3. Cómo debe propagarse la autorización entre agentes.
4. No propone arquitectura; enumera siete requisitos estructurales.
5. Tres fallas de una plataforma en producción, entre ellas **una delegación reportada como exitosa que nunca ocurrió**.
6. Ninguna controlada.
7. Tres casos de un sistema.
8. Requisito de delegación explícita, acotada y auditable.
9. Evidencia de campo en producción.
10. Implementación.
11. Alta para el pitch: es evidencia externa de que «reportado» ≠ «verificado» también ocurre en agentes.
12. [A6]

### 9.7 BROODS (Das y Bhattacharya)

1. Póster en el workshop AgenticOS de NeurIPS 2026.
2. 2026.
3. ¿Se mantienen los límites de comportamiento cuando un agente delega?
4. Once sondas sobre ocho frameworks, escala L0–L4.
5. En OpenAI Agents con `max_turns=5`, una delegación vía `as_tool()` produjo 55 llamadas al modelo.
6. —
7. Workshop; frameworks no todos nombrados en la página.
8. La pregunta de si un límite sobrevive a la delegación.
9. Medición transversal de frameworks.
10. Límites de autoridad que componen por construcción en la cadena de mandatos.
11. Alta: KRAKADYL podría someterse a las sondas aplicables.
12. [A7]

### 9.8 Meta Muse y Sentinel

1. Meta (EE. UU.); producto de consumo.
2. Lanzamiento el 8 de septiembre de 2026.
3. Agente personal que actúa en apps de terceros.
4. Máquina virtual dedicada; un agente Sentinel separado aprueba el acceso saliente y consulta al usuario; credenciales que el agente usa sin ver; aprobación antes de enviar correos o pagar; registro de auditoría.
5. Producto desplegado.
6. Incidentes reportados por terceros en septiembre de 2026, algunos disputados [A9].
7. Alcance de aprobación acotado por diseño («no preguntar todo»); fuentes primarias consultadas no detallan determinismo de Sentinel.
8. Separación entre el agente y quien aprueba.
9. Escala, aislamiento de credenciales, integración con servicios reales.
10. Estados de verificación de evidencia; delegación entre personas con revocación transitiva; ventanas de recuperación.
11. KRAKADYL usa Muse Spark como proponente no confiable; son capas distintas.
12. [A8], [A9]

### 9.9 AgentScope 2.0 (Alibaba), DeerFlow 2.0 (ByteDance), GigaCowork (Sber)

| Aspecto | AgentScope 2.0 | DeerFlow 2.0 | GigaCowork |
|---|---|---|---|
| País | China | China | Rusia |
| Fecha | Mayo de 2026 (nota de prensa) | 28 de febrero de 2026 | Mayo de 2026 (acceso de prueba) |
| Licencia | No consultada | MIT | Comercial (registro ruso de software) |
| Permisos | Bloqueo estático y dinámico de comandos de shell y archivos sensibles | No descritos | Agentes bajo la identidad del empleado; espacios por equipo |
| Aprobación humana | Eventos de confirmación | No descrita | Revisión humana configurable |
| Auditoría | No mencionada | Sin auditoría de seguridad pública independiente | No descrita en la fuente |
| Delegación con revocación | NOT_FOUND_IN_REVIEWED_SOURCES | NOT_FOUND | NOT_FOUND |
| Verificación de resultados | NOT_FOUND | NOT_FOUND | Revisión humana del resultado |
| Fuente | [A10] secundaria | [A11] secundaria | [A12] secundaria |

Lo que hacen mejor: ejecución general, sandboxes, ecosistemas de habilidades. Lo que no documentan: el vínculo entre verificación de evidencia y autoridad de actuar.

### 9.10 LangGraph y Temporal (continuidad de procesos)

- **LangGraph:** con un checkpointer, el grafo se pausa con `interrupt()` y espera **indefinidamente** a ser reanudado; la documentación no trata quién puede aprobar, ni el vencimiento o la revocación de una aprobación pendiente [A13]. Es decir: un proceso puede reanudarse días después con una aprobación cuya autoridad ya no existe, salvo que la aplicación lo controle. KRAKADYL resuelve exactamente ese caso con la revalidación de la cadena al ejecutar y con `resume_after_gap`.
- **Temporal:** ejecución duradera con historial de eventos y reproducción (documentación no abierta en esta sesión; UNVERIFIED en detalle) [A14]. Resuelve la reanudación del proceso, no la reorientación de la persona.

### 9.11 Herramientas DFIR: los instrumentos que KRAKADYL disciplina

| | Velociraptor [D1] | Timesketch [D2] | DFIR-IRIS [D3] | TheHive 5 [D4][D5] | Cellebrite Guardian [D6] | Belkasoft X [D7] |
|---|---|---|---|---|---|---|
| Tipo | Adquisición y respuesta | Líneas de tiempo colaborativas | Gestión de casos | Gestión de casos | Gestión de evidencia | Análisis forense |
| Licencia | AGPLv3 | Apache-2.0 | LGPL-3 (secundaria) | Comercial con licencia Community | Comercial | Comercial |
| Tareas | — | — | Sí (secundaria) | Sí: estados fijos *In progress, Waiting, Cancelled, Completed*; tareas obligatorias exigen al menos un log para completarse y bloquean el cierre del caso | Gestión de tareas investigativas | Ventana de tareas ejecutadas |
| Verificación de completitud por otra persona | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND (la doc no describe un paso de verificación distinto de completar) | NOT_FOUND | NOT_FOUND |
| Hashes de integridad | Sí (INFERRED por uso habitual; no verificado) | — | Sí (secundaria) | — | — | MD5/SHA1/SHA256 |
| Auditoría | — | — | Parcial (secundaria) | — | A prueba de manipulación, informe de cadena de custodia | Base de datos de tareas |
| Delegación de autoridad con revocación | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | Permisos por rol | NOT_FOUND |
| Ventanas de recuperación | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND |

**Lectura justa:** TheHive ya impide cerrar un caso con tareas obligatorias incompletas y exige un registro para completarlas; eso es un mecanismo real contra omisiones. Lo que su documentación no describe es la separación entre «completada por quien la hizo» y «verificada por otra persona», ni un vínculo entre ese estado y el permiso de actuar sobre la evidencia. Esta tabla no mide quién es mejor: mide qué parte de la disciplina de uso queda fuera de cada herramienta. Las filas en NOT_FOUND son lo que KRAKADYL agrega encima, no lo que les falta como productos.

---

## 10. Antecedentes académicos y estándares

| Antecedente | Qué aporta | Relación |
|---|---|---|
| RFC 3227 (2002) [S1] | Orden de volatilidad | Fundamento de `RecoveryWindow` |
| NIST SP 800-61 Rev. 3 (abril de 2025) [S10] | Respuesta a incidentes alineada a CSF 2.0 | Marco de proceso (no abierto en esta sesión) |
| Guía IDF 10.ª ed. (Japón, 2025) [S2] | Registro de traspasos, testigos, trabajo por más de una persona | Normativa práctica afín a `TaskResponsibility` |
| CPP Brasil 158-A/F [S5]; Res. 234/2016 y PGN-MinSeg 2023 (Argentina) [S3][S4]; BSA s. 63 (India) [S6]; Reglamento de la Fiscalía Suprema (Corea) [S7] | Cadena de custodia exigible | Mapas de cumplimiento posibles (§17) |
| Macaroons (2014) [A17]; UCAN [A15]; Biscuit [A16] | Atenuación de capacidades; revocación en UCAN (irreversible, invalida derivados) | Antecedente directo de los sub-mandatos |
| Kassin, Dror y Kukucka (2013) [H8] | Verificación controlada y ciega | Antecedente de la regla de independencia, que KRAKADYL aplica solo por identidad |
| Hutchins (1995) [H9]; Risko y Gilbert (2016) [H7] | Cognición distribuida; descarga cognitiva | Fundamento de «el sistema es la memoria externa» |
| Parasuraman y Manzey (2010) [H6] | Sesgo de automatización | Riesgo de diseño de la propia interfaz |
| W3C COGA (2021) [S13] | Procesos que no dependen de la memoria; retomar tras interrupciones | Criterios de accesibilidad verificables |
| Registros de transparencia (Rekor [A18], RFC 9162) | Logs append-only con pruebas de inclusión | Anclaje externo posible para recibos |

**Patentes:** no se realizó búsqueda de patentes en esta investigación. Es una limitación (§18).

---

## 11. Matriz de capacidades y evidencia

Capacidades comparadas (no nombres de funciones):

- **C1** Distinguir completitud reportada de verificada, con verificador distinto exigido por el sistema.
- **C2** Rechazar actuar sobre evidencia no verificada aunque el archivo esté íntegro.
- **C3** Revalidar autoridad y evidencia en el momento de ejecutar (no solo al aprobar).
- **C4** Atenuación de delegación (el delegado nunca tiene más que el delegante).
- **C5** Revocación transitiva que alcanza acciones preparadas y en vuelo.
- **C6** Registro encadenado verificable con un verificador independiente.
- **C7** Ventanas de recuperación tipadas que distinguen plazos conocidos de cierres por evento.
- **C8** Reorientación tras una ausencia: qué cambió por el solo paso del tiempo.
- **C9** La salida del modelo no puede otorgar autoridad.
- **C10** Cierre honesto cuando algo ya no puede resolverse.
- **C11** Registrar qué herramienta externa se corrió, sobre qué y con qué resultado, como condición para usar su salida.

| | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **KRAKADYL** | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED (un almacén) | CONFIRMED (sello y cadena; no autoridad, KL-002) | CONFIRMED | CONFIRMED | CONFIRMED (cobertura estrecha) | CONFIRMED | Parcial (modelo listo; sin adaptadores reales) |
| Root-scoped quiescence [A5] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY (punto de compromiso) | INFERRED | DOCUMENTED_ONLY (multi-endpoint) | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | INFERRED | DOCUMENTED_ONLY (INDETERMINATE) | NOT_FOUND |
| Bounded Agents [A2] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY | NOT_FOUND | DOCUMENTED_ONLY (sumidero de evidencia) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY (fallo cerrado) | NOT_FOUND |
| AgentBound [A1] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY | UNVERIFIED | DOCUMENTED_ONLY (sin cadena hash descrita) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| Veto [A3] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| UCAN [A15] | — | — | INFERRED (al validar) | DOCUMENTED_ONLY | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | NOT_FOUND | — | — | — |
| LangGraph [A13] | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | Parcial (reanuda el proceso) | NOT_FOUND | NOT_FOUND | NOT_FOUND |
| Meta Muse [A8] | NOT_FOUND | NOT_FOUND | UNVERIFIED | NOT_FOUND | Parcial (desconectar servicio) | DOCUMENTED_ONLY (registro de auditoría) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| TheHive 5 [D4] | Parcial (log obligatorio, sin verificador distinto) | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | — | NOT_FOUND | Parcial (registro de tareas) |
| Cellebrite Guardian [D6] | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY (auditoría a prueba de manipulación) | NOT_FOUND | NOT_FOUND | — | NOT_FOUND | Parcial (registro de accesos) |

«NOT_FOUND» en esta tabla abrevia NOT_FOUND_IN_REVIEWED_SOURCES. «—» indica que la capacidad no aplica a ese tipo de sistema.

---

## 12. Qué está resuelto y qué sigue abierto

**Resuelto por otros (KRAKADYL se apoya en ellos, no los reemplaza):**

- Adquisición a escala y triage en flotas (Velociraptor).
- Colaboración sobre líneas de tiempo (Timesketch).
- Gestión de casos con tareas e integraciones (TheHive, DFIR-IRIS).
- Custodia de laboratorio y auditoría de acceso (Cellebrite Guardian, Belkasoft).
- Capacidades atenuables y verificación descentralizada (UCAN, Biscuit, Macaroons).
- Logs de transparencia (Rekor).
- Reanudación duradera de procesos (Temporal, LangGraph).

**Equivalente o superior a KRAKADYL en dimensiones concretas:**

- Revocación con efectos en vuelo en sistemas distribuidos: [A5] es superior en modelo y en corpus adversarial.
- Prohibición de composiciones de acciones: [A2] y [A3] cubren lo que KRAKADYL no cubre.
- Verificación que reconstruye la decisión: el diseño de [A1] apunta más lejos que el verificador actual de KRAKADYL (aunque sin implementación evaluada).

**Sigue abierto en el campo (no resuelto por nadie en las fuentes revisadas):**

- Medir cuántas investigaciones pierden valor por fallas de coordinación y verificación.
- Un vínculo estándar entre el estado de verificación de una evidencia y el permiso de actuar sobre ella.
- Representar «se cierra con un evento de fecha desconocida» como estado de primera clase en herramientas de casos.
- Reorientación humana tras ausencias largas en investigaciones (no solo reanudación de procesos).
- Independencia de verificación más allá de la identidad (ceguera al contexto).

**Sigue abierto en KRAKADYL:** KL-001, KL-002, KL-003, KL-004; persistencia multi-organización; adaptadores del Nivel 7; estudios con usuarios; benchmark.

---

## 13. Diferenciación defendible de KRAKADYL

### 13.1 ¿Alguna garantía individual es novedosa?

No en las fuentes revisadas. Cada una tiene antecedentes (§9, §10). Afirmar lo contrario no sobrevive a un especialista.

### 13.2 ¿Dónde está entonces la contribución?

En la **combinación, la aplicación y la experiencia investigativa**:

1. **El estado de verificación de la evidencia es una condición de autoridad.** En los sistemas de autorización revisados, la decisión depende de quién, qué, dónde y cuándo; en KRAKADYL depende además de si la evidencia que la acción usaría fue verificada por alguien distinto de quien la reportó. Esa conjunción no se encontró documentada en otro sistema revisado.
2. **La revocación transitiva se aplica a acciones sobre evidencia**, con revalidación en el momento de publicar y un recibo tanto si se ejecuta como si se rechaza.
3. **La incertidumbre temporal tiene tipo.** Distinguir `CONDITIONAL` y `UNKNOWN` de `KNOWN` evita que lo urgente-pero-sin-fecha caiga al fondo de una lista ordenada por plazos.
4. **La reorientación tras una ausencia es un producto, no un efecto lateral**: qué se perdió por el paso del tiempo, separado de lo que sigue abierto.
5. **Lenguaje sin culpa por construcción**: los informes describen estados del caso, no personas.

### 13.3 Separaciones que KRAKADYL implementa (y su estado)

| Separación | Implementación | Estado |
|---|---|---|
| Evidencia observada vs. verificada | `REPORTED_DONE → MISSING`; ejecutor exige `VERIFIED_DONE` | CONFIRMED |
| Evidencia vs. autoridad | Dos dimensiones separadas en el modelo | CONFIRMED |
| Propuesta del modelo vs. permiso efectivo | `ProposedActionCandidate` validado y luego sometido a `check_mandate`/`check_evidence` | CONFIRMED (cobertura adversarial acotada) |
| Preparación vs. ejecución | `prepare_evidence_package` / `execute_prepared_action` con revalidación | CONFIRMED |
| Finalización reportada vs. verificada | Validador de `TaskResponsibility` | CONFIRMED |
| Delegación válida vs. revocada | `authority_under_chain` en prepare y en execute | CONFIRMED |
| Incertidumbre recuperable vs. irreversible | `RecoveryWindow` + `unresolvable` + cierre honesto | CONFIRMED |
| Resultado desconocido vs. inventado | Estados `UNKNOWN`; no se fabrica una prioridad única ante empate | CONFIRMED en `next_move`; INFERRED en el resto |

### 13.4 Afirmaciones de diferenciación defendibles

- «KRAKADYL no permite que una evidencia reportada como preservada se use como si estuviera verificada, y exige que la verifique alguien distinto.»
- «Revocar una autoridad revoca todo lo delegado debajo, también lo que estaba preparado y no ejecutado.»
- «Distingue un plazo conocido de una ventana que se cierra con un evento sin fecha.»
- «Al volver después de días, muestra qué se perdió solo por el paso del tiempo.»
- «El modelo propone; nunca autoriza.»
- «Cada decisión, ejecutada o rechazada, deja un recibo encadenado cuya integridad se comprueba con un verificador independiente del núcleo.» (Hasta que exista el exportador de R-3, no decir «cualquiera puede verificar».)

### 13.5 Afirmaciones que NO deben usarse

Ver §16.8.

---

## 14. Propuesta de valor

### 14.1 Elementos

- **Problema central:** en una investigación bajo presión, la diferencia entre «alguien dijo que lo hizo» y «alguien distinto comprobó que está hecho» se pierde en los traspasos, las interrupciones y las ausencias. Cuando se descubre, la evidencia puede ya no existir y la autoridad para obtenerla puede haber caducado.
- **Por qué es urgente:** las ventanas de evidencia son cortas y las decide un tercero (90 días de CloudTrail por defecto [S11]; 30 días de logs disponibles en Storm-0558 [I4]); los agentes de IA empiezan a ejecutar acciones en investigaciones y exceden autorización en benchmarks [A4][A3]; los marcos multiagente pierden sus límites al delegar [A7].
- **Por qué las soluciones actuales no siempre bastan:** las herramientas de casos registran tareas pero no condicionan acciones a la verificación independiente (§9.11); las capas de autorización de agentes no modelan el estado de verificación de la evidencia (§11); la reanudación de procesos no reorienta a las personas (§9.10).
- **Público inicial:** equipos pequeños de respuesta a incidentes y consultoras DFIR; unidades de evidencia digital de ministerios públicos (por ejemplo, las que aplican el protocolo PGN-MinSeg en Argentina [S4]); equipos de periodismo de investigación; equipos que investigan incidentes de seguridad de IA.
- **Compradores potenciales:** jefaturas de respuesta a incidentes, responsables de laboratorios forenses, áreas de cumplimiento. (Sin estimación de tamaño de mercado: no se encontró una fuente fiable para calcularla.)
- **Beneficios verificables hoy:** bloqueo reproducible de acciones sobre evidencia no verificada; revocación transitiva demostrable; recibos verificables en su integridad; informe de reorientación tras una ausencia.
- **Beneficios a demostrar:** menos omisiones, menos errores de traspaso, menor tiempo para retomar un caso (§17).
- **Diferenciación técnica:** §13.2.
- **Diferenciación organizacional:** lenguaje sin culpa; independencia de verificación por diseño; accesible para quien trabaja con fatiga, interrupciones o un perfil ejecutivo distinto.
- **Costos de no resolver el problema:** §5 (incidentes no explicables, notificación del peor escenario, juicios colapsados, identificaciones erróneas). Son costos de los casos citados, no estimaciones de lo que KRAKADYL ahorraría.
- **Límites:** no adquiere evidencia por sí mismo (salvo el flujo mediado de Nivel 3); no decide qué prueba la evidencia; no detecta sesgo de confirmación; no escala todavía a varias organizaciones; los recibos no prueban autoridad por sí solos.
- **Relación con las herramientas:** KRAKADYL no mejora la adquisición ni el análisis; mejora las condiciones en que se llega a ellos (a tiempo, con autoridad vigente, sin tareas pendientes, sin supuestos no verificados).
- **Complementariedad con VIGÍA y herramientas externas:** KRAKADYL prepara el caso; VIGÍA u otro motor decide lo que la evidencia sostiene (incluido un `ABSTAIN` legítimo); Velociraptor/SIFT adquieren y examinan; i2 Analyst's Notebook analiza vínculos. Ninguna integración del Nivel 7 existe todavía.

### 14.2 Objeciones comerciales previsibles

| Objeción | Respuesta respaldada |
|---|---|
| «Ya tenemos TheHive/IRIS» | Bien: KRAKADYL no los reemplaza. Lo que ellos no documentan es la verificación por otra persona y su efecto sobre el permiso de actuar (§9.11). Un adaptador puede reflejar sus tareas |
| «Agrega fricción» | Es cierto que verificar cuesta. La evidencia de I-PASS sugiere que estructurar los traspasos no empeoró el flujo de trabajo de los residentes [H2]; para DFIR no está medido |
| «¿Quién verifica al verificador?» | La independencia es de identidad autenticada, no resistencia a la colusión. Dos personas de acuerdo pueden marcar `VERIFIED_DONE`. Esto debe decirse |
| «¿Es admisible en un tribunal?» | No evaluado. Puede mapearse a requisitos de cadena de custodia (§17, R-10), pero no hay jurisprudencia sobre KRAKADYL |
| «No escala» | Correcto hoy (SQLite, un nodo) |

### 14.3 Posicionamiento y taglines

**¿Comunica bien «memoria externa y guardián de mandato»?** Es preciso para quien ya entiende el problema, pero tiene dos debilidades ante un jurado no especializado: «mandato» es jerga jurídica y «memoria externa» suena a un gestor de notas. Además, el núcleo diferencial — que lo reportado no pase por verificado — no aparece en la frase.

| # | Tagline | Respaldo | Riesgo |
|---|---|---|---|
| A | **«Lo reportado no es lo verificado. KRAKADYL no deja que el caso los confunda, ni que una autoridad revocada siga actuando.»** | Código (validador, `authority_under_chain`, demos 001 y 003); casos Liam Allan [I3], Continental 2574 [I1]; evidencia de agentes [A6] | Largo; conviene una versión corta: «Lo reportado no es lo verificado.» |
| B | «Memoria externa y guardián de mandato para investigaciones bajo presión.» | Código y literatura de descarga cognitiva [H7][H9] | Abstracto; no dice qué falla evita |
| C | «Antes de que la evidencia desaparezca: qué falta, quién lo tiene, y si todavía podés actuar.» | `next_move`, `RecoveryWindow`, `resume_after_gap`; RFC 3227 [S1]; Storm-0558 [I4] | Puede sugerir que KRAKADYL adquiere la evidencia, cosa que no hace salvo en el flujo de Nivel 3 |

**Recomendación:** A como titular, con B como subtítulo descriptivo en la documentación. A es la que tiene respaldo más directo en código, en casos reales y en evidencia externa sobre agentes.

---

## 15. Mercado y posibles usuarios

- **Respuesta a incidentes y SOC:** 79 % de los SOC encuestados opera 24/7 y el 69 % reporta métricas de forma manual [H11]; los traspasos de turno son estructurales. Sin datos sobre cuántos usan herramientas de casos con verificación independiente.
- **Ministerios públicos y policía técnica:** los marcos de Argentina, Brasil, India y Corea ya exigen registros de quién entrega y quién recibe (§4.2). Estos usuarios necesitan cumplimiento demostrable más que agentes.
- **Consultoras DFIR pequeñas:** sensibles a licencias; KRAKADYL es Apache-2.0.
- **Periodismo de investigación:** problemas de verificación y traspaso análogos; sin requisitos legales de custodia en la mayoría de los casos.
- **Investigación de incidentes de seguridad de IA:** el patrón «delegación reportada que no ocurrió» ya aparece en producción [A6].

No se estima tamaño de mercado. No se encontró fuente fiable para hacerlo sin fabricar cifras.

---

## 16. Material respaldado para la demo y las slides — «Por qué KRAKADYL importa»

### 16.1 Cinco hallazgos sobre la magnitud del problema

1. **Los traspasos fallan de forma asimétrica:** los receptores juzgaron fallidos el 37 % de los traspasos; los emisores, el 21 % [H1].
2. **Estructurar los traspasos reduce daños medibles:** −23 % de errores médicos y −30 % de eventos adversos prevenibles con I-PASS [H2].
3. **La ventana de evidencia la decide un tercero:** 90 días de historial de CloudTrail por defecto [S11]; en Storm-0558 no se pudo saber cómo se robó la clave porque no había logs [I4].
4. **Los atacantes se quedan más que la memoria de los sistemas:** 393 días de permanencia promedio en BRICKSTORM frente a una retención estándar de 90 días que impidió encontrar el vector inicial [I8].
5. **Los agentes exceden su autorización y pierden límites al delegar:** 19,2 % de trayectorias con acciones fuera de autorización en AuthorizationBench [A4]; en un framework, una delegación produjo 55 llamadas con un límite declarado de 5 [A7].

### 16.2 Cinco datos o casos para diapositivas

| # | Diapositiva | Fuente |
|---|---|---|
| 1 | «Creía haber revisado los 57.000 mensajes.» Liam Allan, 2017 | [I3] |
| 2 | «47 tornillos y un cambio de turno.» Continental Express 2574, 1991 | [I1] |
| 3 | «Sin logs, sin respuesta.» Storm-0558, 2023 | [I4] |
| 4 | «Una delegación reportada como exitosa que nunca ocurrió.» Plataforma de IA en producción, 2026 | [A6] |
| 5 | «37 % vs. 21 %: quien entrega cree que transmitió más.» Joint Commission | [H1] |

### 16.2b Ocho fallas, ocho datos (una diapositiva por falla o una tabla)

| Falla | Dato para la diapositiva | Fuente |
|---|---|---|
| Llegar tarde a la ventana | Sepsis: +7,6 % de mortalidad por hora de demora | [H14] |
| Reportado ≠ verificado | Knight Capital: 1 de 8 servidores sin actualizar, sin revisión; más de USD 460 M en ~45 min | [I10] |
| Traspaso | Texas City: sin requisito de comunicación en el cambio de turno; 15 muertos | [I11] |
| Información no vinculada | Errores de historial de medicación al ingreso en 10–67 % de los pacientes | [H15] |
| Estado o autoridad que cambió | Pausas de verificación quirúrgica que se volvieron ritual; 31 cirugías en sitio equivocado en Minnesota en 2010 | [H17] |
| Interrupciones | Reducirlas con chalecos: −15 cada 100, solo 48 % de apoyo del personal | [H16] |
| Supuestos no verificados | Mars Climate Orbiter: «la nave es igual a la anterior» | [I12] |
| Ventana sin autoridad | Volcado de RAM: equipo encendido + especialista + orden judicial | [S4] |

### 16.3 Tres comparaciones justas

1. **TheHive 5:** impide cerrar un caso con tareas obligatorias incompletas; no documenta verificación por otra persona ni vínculo con el permiso de actuar [D4]. *KRAKADYL no reemplaza la gestión de casos; agrega la regla que falta.*
2. **Root-scoped quiescence [A5]:** revocación más rigurosa y multi-endpoint que la de KRAKADYL. *KRAKADYL la aplica a evidencia y la combina con verificación y reorientación.*
3. **LangGraph [A13]:** un flujo pausado espera indefinidamente y la documentación no trata el vencimiento de aprobaciones. *KRAKADYL revalida la cadena de autoridad al ejecutar y muestra qué caducó durante la pausa.*

### 16.4 Argumento central de 30 segundos

> Las investigaciones no siempre fallan por falta de talento. Fallan cuando alguien dijo que preservó la evidencia, otro lo dio por hecho y nadie lo comprobó — y cuando se descubre, la evidencia ya no existe. Pasó con 57.000 mensajes en un juicio en Londres. Pasó con un traspaso de turno en un avión. KRAKADYL hace que lo reportado nunca pase por verificado, que una autoridad revocada no siga actuando, y que al volver después de días sepas qué se perdió. El modelo de IA propone; nunca autoriza.

### 16.5 Narrativa de 90 segundos

> En 2017, un juicio en Londres colapsó porque un oficial creía haber revisado los más de 57.000 mensajes de un teléfono, y la fiscalía le creyó sin preguntar. Nadie mintió. Lo reportado se trató como verificado. En 1991, un avión perdió el borde de un estabilizador porque un turno retiró 47 tornillos y el siguiente no lo supo. En 2023, Microsoft no pudo saber cómo le robaron una clave porque los logs ya no existían.
>
> Son tres disciplinas y un mismo patrón: la información se pierde en los traspasos, en las interrupciones y en el tiempo.
>
> KRAKADYL es la capa que va antes del análisis. Separa cuatro cosas que en la práctica se mezclan: asignado, aceptado, reportado y verificado. No deja usar como evidencia algo que solo fue reportado, y exige que lo verifique otra persona. Cuando alguien delega autoridad y la raíz se revoca, se revoca todo lo de abajo, incluso lo que estaba preparado. Cuando volvés después de cuatro días, te dice qué se cerró mientras no estabas.
>
> Usa Muse Spark para proponer acciones, pero la propuesta pasa por los mismos controles determinísticos que cualquier otra. Cada decisión, aprobada o rechazada, deja un recibo encadenado que un verificador independiente puede comprobar.
>
> No reemplaza a TheHive, a Velociraptor ni al investigador. Hace que lleguen a la decisión con el caso realmente listo.

### 16.6 Narrativa de tres minutos (estructura con evidencia)

1. **(0:00–0:30) El patrón.** Liam Allan [I3] y Continental 2574 [I1]. Una frase: «nadie mintió; lo reportado pasó por verificado».
2. **(0:30–0:50) Por qué no es falta de talento.** Interrupciones de 2,8 segundos duplican errores [H4]; fatiga de 17–19 horas equivale a 0,05 % de alcoholemia [H5]; el sesgo de automatización afecta también a expertos [H6]. KRAKADYL se diseñó para quien trabaja así, que es casi todo el mundo en este campo.
3. **(0:50–1:10) Por qué ahora.** Ventanas cortas y ajenas [S11][I8]; agentes que exceden autorización [A4]; delegaciones que no componen [A7].
4. **(1:10–2:20) Demo en vivo** (§16.7): evidencia reportada pero no verificada → `forbidden`; revocación de la raíz → el junior queda sin autoridad; reanudación tras 4 días.
5. **(2:20–2:40) Qué no es.** No decide qué prueba la evidencia (eso es VIGÍA o el investigador); no reemplaza las herramientas DFIR; no es el primero en revocación transitiva — citar [A5] por nombre muestra rigor.
6. **(2:40–3:00) Qué sigue.** Benchmark de traspasos, estudio con investigadores, adaptadores abiertos. Cierre con el tagline A.

### 16.7 Tres escenarios de demostración

Los tres usan **solo funcionalidad existente** en `main` y se reproducen con los comandos indicados. Son **sintéticos**.

**Escenario 1 — Evidencia volátil a punto de perderse.**
- *Para el jurado:* «Hay cuatro fuentes. Una ya se perdió. Otra se pierde si alguien apaga un equipo, y no sabemos cuándo.»
- *Consecuencia visible:* la fuente perdida aparece como cerrada, no escondida; la fuente que depende de un evento aparece en vigilancia condicional, no al fondo de la lista.
- *Prueba técnica:* `uv run python demo/run_case_004_gap.py` (líneas «recovery windows closed while away» y «on conditional/unknown watch»); `tests/test_continuity.py`.
- *No inventar:* KRAKADYL no detecta por sí mismo que un equipo se va a apagar. La condición la registra una persona.

**Escenario 2 — Tarea reportada como hecha y no verificada.**
- *Para el jurado:* «El archivo está intacto. Alguien dijo que lo preservó. Nadie más lo comprobó.»
- *Consecuencia visible:* el empaquetado de evidencia se rechaza con el motivo explícito, y se emite un recibo del rechazo.
- *Prueba técnica:* `uv run python demo/run_case_001.py`, sección «4. Reported done, never verified». Para mostrar el verificador independiente hace falta construir antes el `chain.json` (las demos no lo generan; ver §3.2); hasta que exista un exportador (R-3), conviene mostrar el verificador aceptando una cadena íntegra y rechazando la misma cadena con un veredicto alterado, y decirlo así.
- *No inventar:* KRAKADYL no juzga si la verificación fue buena; solo exige que exista y que la haga otra identidad.

**Escenario 3 — Autoridad delegada que deja de ser válida y reanudación tras una interrupción.**
- *Para el jurado:* «La jefa delega en un líder, que delega en un junior. La investigación se reasigna y se revoca a la jefa. ¿Puede el junior seguir?»
- *Consecuencia visible:* el junior queda denegado aunque su sub-mandato nunca se tocó; al volver días después, el informe muestra que su delegación caducó.
- *Prueba técnica:* `uv run python demo/run_case_003_level6.py` (pasos 4 y 6); `uv run python demo/run_case_004_gap.py`; revocación entre prepare y execute: RT-L6-2 en `docs/red-team-level6-delegation-2026-11-01.md` y `tools/redteam_level6_probes.py`.
- *No inventar:* la revocación es dentro de un solo almacén; no hay federación entre organizaciones.

### 16.8 Afirmaciones que hay que evitar

| No decir | Por qué | Decir en su lugar |
|---|---|---|
| «El primero / el único / nadie lo hace» | Cada garantía tiene antecedentes (§9) | «No encontramos esta combinación documentada en los sistemas que revisamos» |
| «Evita la pérdida de evidencia» | No adquiere por sí mismo | «Hace visible qué se puede perder y cuándo» |
| «Recibos que prueban que la acción estaba autorizada» | KL-002 | «Recibos cuya integridad y orden se comprueban con un verificador independiente» |
| «El 80 % de los errores graves se debe a fallas de traspaso» | No aparece en la alerta de la Joint Commission consultada [H1] | Usar 37 % vs. 21 % [H1] o I-PASS [H2] |
| «KRAKADYL habría evitado el caso X» | Contrafáctico no demostrable | «El mecanismo X apunta a ese patrón» |
| «Probado con investigadores» | No hubo estudios con usuarios | «Probado con tests y red team propio» |
| «Integrado con Velociraptor / i2 / VIGÍA» | Nivel 7 no implementado | «Diseñado para integrarse; adaptadores en el plan» |
| «IBM i2» | i2 pertenece a Harris (i2 Group) [D10] | «i2 Analyst's Notebook» |
| «Resistente a prompt injection» | KL-003; cobertura acotada | «La salida del modelo no tiene camino hacia la autoridad» |
| «Reduce los ABSTAIN evitables» | No medido | «Está diseñado para reducir…; lo vamos a medir así: …» |
| «Sentinel es una autoridad determinística» | No confirmado en fuentes primarias | «Sentinel aprueba el acceso saliente de Muse» [A8] |
| Cualquier porcentaje sobre cuántas investigaciones fallan por coordinación | No existe la cifra | «No hay un dato global; esto es lo que muestran los casos» |
| Presentar el caso Muse/domicilio como hecho establecido | Disputado [A9] | Omitirlo o decir «disputado» |

### 16.9 Preguntas difíciles del jurado

1. **«¿No es TheHive con más estados?»** — TheHive exige un log para completar tareas obligatorias; no documenta verificación por otra persona ni que ese estado condicione actuar sobre la evidencia [D4]. KRAKADYL puede vivir junto a TheHive.
2. **«¿Qué impide que dos personas se pongan de acuerdo y marquen verificado?»** — Nada técnico. La independencia es de identidad autenticada, no resistencia a la colusión. Lo que sí queda es un registro inmutable de quién verificó qué y cómo.
3. **«¿Y si la evidencia nunca entra a KRAKADYL?»** — Entonces KRAKADYL no la ve. Es un sistema de registro, no de descubrimiento; por eso los adaptadores del Nivel 7 importan.
4. **«¿Midieron algo con personas?»** — No. Está en el plan (§17, R-8 y R-9), con métricas definidas antes de medir.
5. **«¿Por qué usar un LLM?»** — Para proponer el siguiente paso a partir del estado real del caso. La propuesta no tiene camino a la autoridad: pasa por los mismos controles que una acción escrita a mano.
6. **«Zhu y Wang ya resolvieron la revocación con efectos en vuelo.»** — Sí, en un modelo más general. KRAKADYL lo aplica a acciones sobre evidencia y lo combina con verificación y reorientación. Lo citamos.
7. **«¿Sirve en un tribunal?»** — No está evaluado. Registra los campos que exigen varios marcos (quién entrega, quién recibe, cuándo, hash), pero la admisibilidad depende de cada jurisdicción.
8. **«¿Escala?»** — Hoy es un nodo con SQLite. Es suficiente para un equipo; no para varias organizaciones.
9. **«¿El verificador de recibos prueba la autoridad?»** — No: prueba sello y encadenamiento. La autoridad requiere el estado del caso vinculado (KL-002).
10. **«¿Esto no agrega trabajo a gente ya sobrecargada?»** — Verificar agrega un paso. A cambio, nadie tiene que reconstruir el caso de memoria al volver. Si el balance es positivo es una pregunta empírica que todavía no respondimos.
11. **«¿Es viable algo hecho en días?»** — El historial de git es público: 205 commits entre el 27/10 y el 2/11, tests desde el primer día y auditorías que corrigieron sobreafirmaciones. Lo construido está completo y probado; lo que falta está declarado (§3.2, §17).

### 16.10 Matriz de trazabilidad del pitch

| Afirmación del pitch | Evidencia | Tipo | Estado |
|---|---|---|---|
| Lo reportado nunca pasa por verificado | `continuity.evidence_state_from_requirement`; demo 001 corrida 4 | Código | CONFIRMED |
| Verificación por otra identidad | Validador `TaskResponsibility`; `tests/test_model_invariants.py` | Código | CONFIRMED |
| Revocar la raíz revoca la cadena, incluso entre prepare y execute | demo 003; RT-L6-2 | Código / red team propio | CONFIRMED / DOCUMENTED_ONLY (en vivo) |
| Al volver, informa qué se perdió por el tiempo | demo 004 | Código | CONFIRMED |
| El modelo propone, nunca autoriza | Flujo `ProposedActionCandidate` → `decide()`; `test_policy.py` | Código | CONFIRMED (cobertura estrecha) |
| Recibos comprobables con un verificador independiente | `tools/verify_receipt.py`; comprobación cruzada con `krakadyl.core.receipt.seal` en esta investigación | Código | CONFIRMED (sello y cadena, dado el payload; falta exportador, §3.2) |
| 57.000 mensajes | [I3] | Prensa sobre revisión oficial | Secundaria |
| 47 tornillos, 14 muertos | [I1] | Institucional (FAA) | Primaria |
| Sin logs, sin respuesta (Storm-0558) | [I4] | Prensa sobre informe CSRB | Secundaria |
| 37 % vs. 21 % | [H1] | Institucional | Primaria |
| −23 % / −30 % I-PASS | [H2] | Peer-reviewed (vía nota de prensa) | Primaria indirecta |
| 19,2 % AuthorizationBench | [A4] | Prensa sobre preprint | Secundaria |
| 55 llamadas con límite 5 | [A7] | Workshop | Primaria |
| Delegación reportada que no ocurrió | [A6] | Preprint | Primaria |
| 90 días CloudTrail | [S11] | Documentación del proveedor | Primaria |
| 393 días BRICKSTORM / retención 90 días | [I8] | Informe de proveedor de seguridad | Primaria (proveedor) |

---

## 17. Recomendaciones post-hackathon

Priorizadas por lo que se puede construir y validar sin licencias comerciales. Ninguna corresponde a funcionalidades pendientes del Nivel 6: las de integración son Nivel 7.

| ID | Recomendación | Beneficio esperado | Dificultad | Dependencias | Riesgos | Criterio de aceptación |
|---|---|---|---|---|---|---|
| R-1 | Actualizar `docs/levels.md` (interfaz del Nivel 6 ya construida), matizar el README sobre recibos (KL-002), corregir «composition closure», agregar [A5], [A6] y [A7] al arte previo | Coherencia ante el jurado y ante especialistas | Baja | Ninguna | Ninguno | Ninguna contradicción entre docs y código; arte previo incluye [A5] |
| R-2 | Sobre de autoridad y evidencia versionado (cierre de KL-002), inspirado en el diseño de recibos de [A1] | El verificador offline puede reconstruir y reproducir la decisión | Media | Esquema canónico estable | Crecimiento del tamaño del recibo; exposición de datos sensibles en el sobre | Un verificador sin dependencias de `krakadyl.core` reproduce `decide()` para 100 % de los recibos de las demos y rechaza sobres alterados |
| R-3 | Agregar un exportador `chain.json` (por caso, vía API o `tools/`) y ampliar la batería del verificador de recibos (hoy 2 tests, ambos de falla): un test de aceptación de cadenas reales selladas por el núcleo y un corpus de cadenas modificadas y re-selladas, al estilo de [A5] | Que «cualquiera puede verificar» sea literalmente cierto para un caso real | Baja | — | Que el exportador filtre datos sensibles del manifiesto | El verificador acepta el 100 % de las cadenas exportadas de los casos de demo y rechaza el 100 % de un corpus de ≥ 40 mutaciones semánticas consistentemente re-hasheadas |
| R-4 | Control de composición de acciones en `check_mandate` (pares/k-tuplas prohibidas sobre el historial del caso), siguiendo [A2] y [A3] | Cerrar la clase de ataques por encadenamiento | Media | Taxonomía de acciones | Falsos positivos | Escenarios de exfiltración por composición del corpus de [A3] aplicables al dominio son bloqueados; sin regresiones en 451 tests |
| R-5 | Adaptador de lectura para DFIR-IRIS (LGPL-3) y luego TheHive (licencia Community) que refleje tareas como `REPORTED_DONE` hasta que una segunda identidad verifique | Adopción sin reemplazar herramientas | Media | API de cada producto | Cambios de API; licencias de TheHive | Una tarea completada en IRIS aparece como `REPORTED_DONE` en KRAKADYL y bloquea una acción hasta su verificación |
| R-6 | Adaptador de Velociraptor (AGPLv3): resultados de colección con hashes → `Observation` + `EvidenceCustody` | Fuente de observaciones real | Media | API de Velociraptor; cuidado con AGPL si se distribuye código derivado | Licencia; volumen | Una colección real se registra con hash y procedencia; el ejecutor la incluye solo tras verificación |
| R-7 | Exportar actividad y recibos a Timesketch (Apache-2.0) | Visión cronológica para analistas | Baja | — | — | Un caso de demo se visualiza en Timesketch con cada recibo como evento |
| R-8 | Benchmark de coordinación y continuidad: escenarios sintéticos de traspaso, interrupción, revocación y ventanas que se cierran, con métricas preregistradas (proporción de resultados no concluyentes de tipo B según §4.0, omisiones evitables, errores de traspaso, tiempo para retomar, acciones fuera de autoridad) | Primer dato propio sobre la hipótesis central | Media-alta | Diseño de escenarios; inspiración en [A4] y [A7] | Que el benchmark se ajuste a KRAKADYL | Preregistro público antes de correrlo; comparación contra una línea base (gestor de tareas sin verificación) |
| R-9 | Estudio de usabilidad con investigadores reales (dentro de sujetos, con interrupciones controladas como en [H4]), evaluación contra criterios de [S13]; incluir participantes neurodivergentes sin usar el diagnóstico como predictor | Evidencia de impacto humano | Alta | Ética, reclutamiento | Muestra pequeña; efecto Hawthorne | Métricas definidas antes: aciertos al identificar ítems no verificados, tiempo para retomar, carga subjetiva (por ejemplo NASA-TLX) |
| R-10 | Mapas de cumplimiento: eventos de KRAKADYL ↔ etapas del art. 158-B (Brasil), hoja de ruta de la Res. 234/2016 (Argentina), certificado de la s. 63 BSA (India), guía IDF (Japón) | Utilidad para ministerios públicos | Media | Asesoramiento jurídico | Interpretaciones erróneas | Revisión por un profesional del derecho de cada jurisdicción |
| R-11 | Exportar sub-mandatos como capacidades UCAN o Biscuit para uso entre organizaciones; adoptar el modelo de cercos de [A5] para revocación distribuida | Federación | Alta | Elegir formato; gestión de claves | Complejidad; semántica de revocación de Biscuit requiere estado externo [A16] | Una revocación en la organización A invalida una acción preparada en la organización B antes de su punto de compromiso |
| R-12 | Anclar cabezas de la cadena de recibos en un log de transparencia (Rekor o equivalente) | Evidencia externa de que la cadena no se reescribió | Media | Decidir qué datos se publican | Filtración de metadatos | Prueba de inclusión verificable para cada cabeza anclada |
| R-13 | Integración con VIGÍA: contrato explícito para entregar un caso «listo para evaluar» y recibir `ABSTAIN` con motivo | Cerrar el ciclo que motiva el proyecto | Media | Ambos proyectos son de la autora | Acoplamiento | Un `ABSTAIN` por evidencia faltante se traduce en un requisito abierto con ventana |
| R-14 | i2 Analyst's Notebook: exportación de entidades y vínculos (formato de importación del producto) | Interoperabilidad con analistas de inteligencia | Media | Licencia comercial de i2 para probar | Licencia | Un caso exportado se importa sin pérdida de procedencia |
| R-15 | Auditoría independiente del núcleo de autoridad por terceros | Credibilidad | Variable | Financiamiento o comunidad | — | Informe público con hallazgos y su cierre |

Costos: no se estiman en dinero salvo donde dependen de licencias comerciales (R-5 TheHive en niveles pagos, R-14 i2), cuyo precio no se consultó.

---

## 18. Limitaciones de la investigación

- **No se examinó el árbol de trabajo local.** La internacionalización ES/EN y cualquier cambio sin commit quedan sin verificar.
- **No se probó la interfaz en un navegador**, ni se ejecutaron Muse, Laya o SAM en vivo, ni las sondas de red team en vivo.
- **Varias fuentes son secundarias:** AuthorizationBench, AgentScope, DeerFlow, GigaCowork, IBM 2026, DFIR-IRIS, el reglamento coreano, las reglas chinas de 2019. Se marcó cada caso.
- **Fuentes primarias inaccesibles:** páginas `arxiv.org/abs` (se usaron los PDF), PubMed y PMC (bloqueos de verificación), traducción de las reglas chinas, la nota de WRAL sobre i2.
- **No se buscó en hindi ni en hebreo**, y la cobertura de Japón, Corea e India se limitó a marcos normativos.
- **No se hizo búsqueda de patentes.**
- **No se investigaron plataformas SOAR y de playbooks** (por ejemplo Cortex XSOAR, Tines o Shuffle), que son las más cercanas en la función de disciplina de uso. Es la próxima búsqueda que habría que hacer.
- **No se consultaron textos completos de papers con muro de pago** (NEJM, Human Factors); se usaron resúmenes oficiales y notas de prensa de las instituciones.
- **Fuentes no abiertas en esta sesión y citadas solo bibliográficamente:** Macaroons [A17], Rekor [A18], Temporal [A14], Hutchins [H9], NIST SP 800-61r3 [S10].
- **Sesgo de búsqueda:** los resultados en inglés son más abundantes; la ausencia de resultados en otros idiomas no prueba ausencia de soluciones.
- **Una sola sesión, un solo investigador (un modelo de IA).** Las afirmaciones deberían revisarse por una persona antes de usarlas en público.

---

## 19. Afirmaciones corregidas o descartadas

| # | Lo que parecía cierto | Lo que se encontró | Decisión |
|---|---|---|---|
| 1 | La interfaz del Nivel 6 no está construida (según `docs/levels.md`) | Está en `main` (`93be916`, `635c80b`) y compila | Documento desactualizado; corregir (R-1) |
| 2 | «El 80 % de los errores médicos graves involucra fallas de comunicación en traspasos» (cifra muy citada y atribuida a la Joint Commission) | No figura en la Alerta 58 consultada [H1] | **Descartada** para el pitch |
| 3 | I-PASS redujo 23 % los eventos adversos prevenibles (reseña de PSNet) | La nota institucional y la Joint Commission indican −23 % errores y −30 % eventos adversos prevenibles [H2][H1] | Se usa la versión institucional |
| 4 | «IBM i2 Analyst's Notebook» | IBM vendió i2 a Harris; hoy es i2 Group [D10] | Corregir el nombre |
| 5 | Biscuit soporta revocación | Su documentación indica que la revocación requiere estado externo [A16] | Matizado |
| 6 | Sentinel es una autoridad determinística | No confirmado en el anuncio primario [A8] | UNVERIFIED |
| 7 | «Composition closure» de KRAKADYL = la de Bounded Agents | Son conceptos distintos (§3.3) | Cambiar terminología |
| 8 | El certificado de Equifax llevaba «19 meses» vencido (cifra que circula) | GAO dice unos 10 meses antes de la brecha [I5] | Se usa GAO; la otra cifra no se verificó |
| 9 | En Mayfield la verificación no fue ciega | El resumen del OIG consultado no lo afirma [I6] | No se afirma |
| 10 | Ningún trabajo académico trata la revocación transitiva con efectos en vuelo para agentes | Existe [A5], y es más general | **Hallazgo desfavorable**; citar |
| 11 | AgentBound encadena sus recibos por hash | El paper no describe encadenamiento [A1] | Matizado |
| 12 | Habría una estadística global de investigaciones fallidas por coordinación | No se encontró | Declarado explícitamente (§6) |
| 13 | Westbrook: «12,7 %» como único número | 12,1 % para fallas de procedimiento y 12,7 % para errores clínicos [H3] | Se reportan ambos |
| 14 | Los recibos de un caso pueden pasarse directamente al verificador independiente | El payload sellado no se persiste y no hay exportador de `chain.json`; el verificador sí coincide con el sellado del núcleo cuando se le da el payload (comprobado en esta investigación) | Matizado en §3.2 y §16.7; R-3 |
| 15 | (Encuadre de la primera versión) KRAKADYL comparado con Velociraptor, TheHive o Cellebrite como competidor en escala | KRAKADYL es la disciplina previa que hace que esas herramientas se usen correctamente; su métrica es evitar `ABSTAIN` evitables aguas abajo (corrección de la autora, 2026-11-02) | Reescritos §1, §8, §9.11, §11 y §12 |

---

## 20. Bibliografía completa

Fecha de consulta de todas las fuentes: **2026-11-02**. «Prov.» = documentación del proveedor; «Sec.» = fuente secundaria.

### Repositorio

- **[R1]** annatchijova, *KRAKADYL*, commit `1d56d66`, 2026-11-02. https://github.com/annatchijova/krakadyl/tree/1d56d66fdbad18396626f49f0b51770133695678
- **[R2]** *docs/levels.md*, mismo commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/levels.md
- **[R3]** *docs/known-limitations.md*, mismo commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/known-limitations.md
- **[R4]** *docs/red-team-level6-delegation-2026-11-01.md*, mismo commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/red-team-level6-delegation-2026-11-01.md

- **[V1]** annatchijova, *VIGÍA* (vigia-intent-analysis), README_ES.md, sección «Arquitectura — Aislamiento del LLM». https://github.com/annatchijova/vigia-intent-analysis

### Autorización, agentes y continuidad

- **[A1]** Kaul, A.; Lan, Q. (eBay Inc.); Gupta, P. *Behavioral Governance for Autonomous AI Agents: The AgentBound Framework*. arXiv 2606.30970, 2026. https://arxiv.org/pdf/2606.30970
- **[A2]** Muruaga, X. *Bounded Agents: Delegation Security for Multi-Agent AI Systems*. arXiv 2608.15888, 2026. https://arxiv.org/pdf/2608.15888
- **[A3]** Celebi, Y. (Plaw, Inc.; Arizona State University). *Can Is Not May: Authority Models for Governable AI Agents*. Marzo de 2026. https://yazzone.pages.dev/can-is-not-may.pdf
- **[A4]** LDS Team. *AuthorizationBench study finds LLM agents exceeded user authorization in 19.2% of tested trajectories*. 2026-10-21 (sobre arXiv 2610.27548). Sec. https://letsdatascience.com/news/authorizationbench-benchmark-finds-llm-agents-exceed-user-au-cb3b903c
- **[A5]** Zhu, G.; Wang, C. (Accentrust). *Authorization Revocation for Long-Running AI Agents: Root-Scoped Quiescence under Delegation and Asynchronous Execution*. arXiv 2609.21284v1, 2026-09-18. https://arxiv.org/pdf/2609.21284
- **[A6]** Tallam, K. (Kamiwaza AI). *Authorization Propagation in Multi-Agent AI Systems: Identity Governance as Infrastructure*. arXiv 2605.05440v1, 2026-05-06. https://arxiv.org/pdf/2605.05440
- **[A7]** Das, S.; Bhattacharya, S. *Bounds That Do Not Compose: Measuring OS-Level Containment in Eight Agent Frameworks*. Workshop AgenticOS, NeurIPS 2026. https://neurips.cc/virtual/2026/166794
- **[A8]** Meta. *Introducing Muse*. 2026-09-08 (modificado 2026-09-30). Prov. https://about.fb.com/news/2026/09/introducing-muse
- **[A9]** Xenospectrum. *Meta Muse address approval scope*. 2026-09-29. Sec. https://xenospectrum.com/en/meta-muse-address-approval-scope/
- **[A10]** KuCoin/MarsBit. *Alibaba Launches AgentScope 2.0…*. 2026-05-26. Sec. https://www.kucoin.com/news/flash/alibaba-launches-agentscope-2-0-to-enhance-agent-deployment-security-and-stability
- **[A11]** VentureBeat. *What is DeerFlow and what should enterprises know…*. 2026. Sec. https://venturebeat.com/orchestration/what-is-deerflow-and-what-should-enterprises-know-about-this-new-local-ai
- **[A12]** EastRussia. *Сбер открыл тестовый доступ к платформе GigaCowork…*. 2026-05-21. Sec. https://www.eastrussia.ru/news/sber-otkryl-testovyy-dostup-k-platforme-gigacowork-sisteme-upravleniya-ii-agentami-dlya-vsey-kompani/
- **[A13]** LangChain. *Human-in-the-loop* (LangGraph). Prov. https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- **[A14]** Temporal. *Workflow Execution overview*. Prov. No abierta en esta sesión. https://docs.temporal.io/workflow-execution.md
- **[A15]** UCAN Working Group. *UCAN Specification* v1.0.0. https://github.com/ucan-wg/spec
- **[A16]** *biscuit-auth* 6.0.0, documentación. https://docs.rs/biscuit-auth/latest/biscuit_auth/
- **[A17]** Birgisson, A. et al. *Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud*. NDSS 2014. No abierta en esta sesión. https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/
- **[A18]** Sigstore. *Logging overview (Rekor)*. Prov. No abierta en esta sesión. https://docs.sigstore.dev/logging/overview/

### DFIR y gestión de evidencia

- **[D1]** noze. *Velociraptor: DFIR and endpoint monitoring with VQL*. Sec. https://www.noze.it/en/insights/velociraptor-dfir
- **[D2]** Google. *Timesketch* (GitHub). https://github.com/google/timesketch/
- **[D3]** BrightCoding. *IRIS: The Collaborative Incident Response Platform…*. 2026-04-02. Sec. (promocional). https://www.blog.brightcoding.dev/2026/04/02/iris-the-collaborative-incident-response-platform-every-security-team-needs
- **[D4]** StrangeBee. *TheHive 5 — About tasks*. Prov. https://docs.strangebee.com/thehive/user-guides/analyst-corner/tasks/about-tasks/
- **[D5]** StrangeBee. *TheHive — License*. Prov. https://docs.strangebee.com/thehive/installation/licenses/license/
- **[D6]** Cellebrite. *Guardian*. Prov. https://cellebrite.com/en/guardian
- **[D7]** Belkasoft. *Preserving chain of custody*. Prov. https://belkasoft.com/preserving_chain_of_custody
- **[D8]** 平安证券 (Ping An Securities). Informe sobre 美亚柏科 (300188). 2019-06-03. https://img3.gelonghui.com/pdf/f6b38-95fcfed4-3a21-431b-90f8-04f8198f500c.pdf
- **[D9]** Help Net Security. *Detego DFIR Platform…*. 2025-11-27. Sec. https://www.helpnetsecurity.com/2025/11/27/detego-case-manager-dfir/
- **[D10]** TyN Magazine. *Harris acquires i2 product portfolio from IBM*. Sec. https://tynmagazine.com/harris-acquires-i2-product-portfolio-from-ibm/

### Estándares y normativa

- **[S1]** Brezinski, D.; Killalea, T. *RFC 3227 — Guidelines for Evidence Collection and Archiving*. IETF, 2002. https://www.rfc-editor.org/rfc/rfc3227
- **[S2]** デジタル・フォレンジック研究会. *証拠保全ガイドライン 第10版*. 2025-03-15. https://digitalforensic.jp/wp-content/uploads/2025/03/shokohozenGL10.pdf
- **[S3]** Ministerio de Seguridad (Argentina). *Resolución 234/2016*. BO 2016-06-14. https://www.argentina.gob.ar/normativa/nacional/norma-262787/texto
- **[S4]** Procuración General de la Nación (Argentina). Resolución PGN que aprueba el *Protocolo para la identificación, recolección, preservación, procesamiento y presentación de evidencia digital*. 2023-04-18. https://www.mpf.gob.ar/resoluciones/PGN/2023/PGN-0019-2023-001.pdf
- **[S5]** Brasil, CPP arts. 158-A a 158-F (Lei 13.964/2019), reproducción en Migalhas. https://www.migalhas.com.br/arquivos/2020/3/CA87D1CAE19D01_LeiAnticrime%E2%80%93CadeiadeCustodiae.pdf
- **[S6]** LiveLaw. *Supreme Court Rejects Challenge To S.63(4) BSA…* (*Pune Bar Association v Union of India*, 2026-05-22). 2026-05-28. Sec. https://www.livelaw.in/top-stories/supreme-court-rejects-challenge-to-s634-bsa-mandating-hash-value-disclosure-for-electronic-evidence-535950
- **[S7]** LawWin. Resumen del 대검찰청예규 제1449호. 2025-08-05. Sec. https://www.lawwin.co.kr/suwon/knowledgedetail?index=7303
- **[S8]** Герасимов, Н. *О проблеме изъятия электронных носителей информации в рамках следственных действий*. Адвокатская газета, 2019-04-24. https://www.advgazeta.ru/mneniya/o-probleme-izyatiya-elektronnykh-nositeley-informatsii-v-ramkakh-sledstvennykh-deystviy/
- **[S10]** NIST. *SP 800-61 Rev. 3*. Abril de 2025. No abierta en esta sesión. https://csrc.nist.gov/pubs/sp/800/61/r3/final
- **[S11]** AWS. *How CloudTrail works*. Prov. https://docs.aws.amazon.com/awscloudtrail/latest/userguide/how-cloudtrail-works.html
- **[S12]** Federal News Network. *OMB revamps cyber event logging requirements*. Mayo de 2026. Sec. https://federalnewsnetwork.com/cybersecurity/2026/05/omb-revamps-cyber-event-logging-requirements/
- **[S13]** W3C. *Making Content Usable for People with Cognitive and Learning Disabilities*. Nota, 2021-04-29. https://www.w3.org/TR/coga-usable

- **[S14]** EE. UU., 14 CFR § 121.371 (Required inspection personnel). https://www.law.cornell.edu/cfr/text/14/121.371
- **[S15]** Health and Safety Executive (Reino Unido). *Why are permit to work systems important?* https://hse.gov.uk/humanfactors/topics/ptw.htm
- **[S16]** SC OSHA. *Lockout/Tagout Fact Sheet*. https://osha.llr.sc.gov/outreach/factsheets/Lockout-Tagout-Fact-Sheet.pdf

(El identificador [S9] se reservó para el texto primario de las reglas chinas de 2019, que no pudo abrirse; se cita a través de [D8].)

### Factores humanos

- **[H1]** The Joint Commission. *Sentinel Event Alert 58: Inadequate hand-off communication*. 2017-09-12. https://jointcommission.org/-/media/tjc/documents/resources/patient-safety-topics/sentinel-event/sea_58_hand_off_comms_9_6_17_final_(1).pd
- **[H2]** Starmer, A. J. et al. *Changes in Medical Errors after Implementation of a Handoff Program*. NEJM 371(19):1803–1812, 2014. doi:10.1056/NEJMsa1405556. Nota institucional: https://www.eurekalert.org/news-releases/628556 · Reseña: https://psnet.ahrq.gov/issue/changes-medical-errors-after-implementation-handoff-program
- **[H3]** Westbrook, J. et al. *Archives of Internal Medicine*, 2010-04-26. Nota institucional: https://www.eurekalert.org/news-releases/687593
- **[H4]** Altmann, E. M.; Trafton, J. G.; Hambrick, D. Z. *Journal of Experimental Psychology: General* (en línea 2013). Nota institucional: https://www.eurekalert.org/news-releases/680690
- **[H5]** Williamson, A.; Feyer, A.-M.; Friswell, R.; Finlay-Brown, S. *Development of measures of fatigue: using an alcohol comparison…* (CR 189), 2000. https://www.infrastructure.gov.au/department/media/publications/cr-189-development-measures-fatigue-using-alcohol-comparison-validate-effects-fatigue-performance
- **[H6]** Parasuraman, R.; Manzey, D. *Complacency and Bias in Human Use of Automation: An Attentional Integration*. Human Factors 52(3):381–410, 2010. doi:10.1177/0018720810376055. https://depositonce.tu-berlin.de/items/0c787d91-6021-480b-a333-009e0d1d0092/full
- **[H7]** Risko, E. F.; Gilbert, S. J. *Cognitive Offloading*. Trends in Cognitive Sciences 20(9):676–688, 2016. doi:10.1016/j.tics.2016.07.002. https://discovery.ucl.ac.uk/id/eprint/1508770/
- **[H8]** Kassin, S. M.; Dror, I. E.; Kukucka, J. *The forensic confirmation bias: Problems, perspectives, and proposed solutions*. JARMAC 2:42–52, 2013. doi:10.1016/j.jarmac.2013.01.001. https://web.williams.edu/Psychology/Faculty/Kassin/files/1%20Kassin%20Dror%20Kukucka%20(2013)%20-%20FCB.pdf
- **[H9]** Hutchins, E. *How a cockpit remembers its speeds*. Cognitive Science, 1995. No abierta en esta sesión. https://courses.ischool.berkeley.edu/i290-3/s05/papers/How_a_cockpit_remembers_its_speeds.pdf
- **[H10]** Karidi, D. *Remembering the Future: How ADHD Affects Prospective Memory…*. Attention Magazine (CHADD), diciembre de 2025. Divulgativa. https://chadd.org/attention-article/remembering-the-future-how-adhd-affects-prospective-memory-and-how-to-work-with-it/
- **[H11]** Crowley, C. *SANS 2025 SOC Survey*. SANS, julio de 2025. https://www.elastic.co/pdf/sans-soc-survey-2025.pdf

- **[H12]** Haynes, A. B. et al. *A Surgical Safety Checklist to Reduce Morbidity and Mortality in a Global Population*. NEJM, 2009. Resumen: https://www.reliasmedia.com/articles/112170-study-safety-checklist-reduces-mortality (Sec.; PubMed inaccesible: https://pubmed.ncbi.nlm.nih.gov/19144931/)
- **[H13]** Fonarow, G. C. et al. Target: Stroke, JAMA, abril de 2014. Resumen: https://www.tctmd.com/news/society-led-quality-improvement-effort-speeds-treatment-acute-ischemic-stroke (Sec.)
- **[H14]** Kumar, A. et al. Crit Care Med 34(6):1589–96, 2006. PMID 16625125. Resumen: https://clincalc.com/blog/2013/10/kumar-2006-antibiotic-delay-septic-mortality/ (Sec.)
- **[H15]** Tam, V. C. et al. *Frequency, type and clinical importance of medication history errors at admission to hospital: a systematic review*. CMAJ 173(5):510, 2005. https://www.cmaj.ca/content/173/5/510
- **[H16]** Rafferty, A. M.; Dean Franklin, B. Editorial sobre el ensayo «Do not interrupt» de Westbrook et al. BMJ Quality & Safety 26(9). https://qualitysafety.bmj.com/content/26/9/701.abstract
- **[H17]** Rydrych, D.; Apold, J.; Harder, K. *Preventing Wrong-Site Surgery in Minnesota: A 5-Year Journey*. PSQH, 2012-12-04. https://psqh.com/analysis/preventing-wrong-site-surgery-in-minnesota-a-5-year-journey

### Incidentes y consecuencias

- **[I1]** FAA. *Lessons Learned: Continental Express 2574 (N33701)*. https://www.faa.gov/lessons_learned/transport_airplane/accidents/N33701
- **[I2]** Scott, D.; Bunn, A. *Piper Alpha – process safety then and now*. Loss Prevention Bulletin 261, IChemE, junio de 2018. https://www.icheme.org/media/1988/lpb261_pg25.pdf
- **[I3]** HuffPost UK. *Police apologise to student Liam Allan after review of collapsed rape trial*. Enero de 2018. Sec. https://huffingtonpost.co.uk/amp/entry/police-apologise-to-student-liam-allan-after-review-of-collapsed-rape-trial_n_19115170
- **[I4]** Help Net Security. *A "cascade" of errors let Chinese hackers into US government inboxes* (sobre el informe del CSRB). 2024-04-03. Sec. https://www.helpnetsecurity.com/2024/04/03/microsoft-storm-0558-key/
- **[I5]** GAO. *GAO-18-559: Data Protection: Actions Taken by Equifax and Federal Agencies in Response to the 2017 Breach*. 2018. https://www.gao.gov/assets/700/694347.pdf
- **[I6]** DOJ OIG. *Semiannual Report to Congress* (Mayfield). 2006. https://oig.justice.gov/archives/semiannual/0605/fbi.htm
- **[I7]** The Register. *Vibe coding service Replit deleted user's production database…*. 2025-07-21. Sec. https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/
- **[I8]** Mandiant / Google Cloud. *M-Trends 2026, edición ejecutiva (español latinoamericano)*. 2026. Prov. https://services.google.com/fh/files/misc/m_trends_2026_executive_edition_esla.pdf
- **[I10]** Varma, J. R. *SEC order explains Knight Capital systems failure* (resumen de la orden de la SEC, 2013). Sec. https://www.jrvarma.in/blog/Y2013/Knight-Capital.html
- **[I11]** U.S. Chemical Safety Board. *Investigation Report: Refinery Explosion and Fire, BP Texas City* (2007). https://www.csb.gov/assets/1/20/CSBFinalReportBP.pdf?13841
- **[I12]** NASA. *Mars Climate Orbiter Mishap Investigation Board Phase I Report*. 1999-11-10. https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf
- **[I9]** eSecurity Planet. *IBM 2026 Cost of a Data Breach Report: Key Findings*. 2026-07-30. Sec. https://www.esecurityplanet.com/cybersecurity/ibm-2026-cost-of-a-data-breach-report-key-findings/


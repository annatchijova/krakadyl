[English](getting-started.md) · [Español](getting-started.es.md)

# Ejecutar KRAKADYL en tu máquina

Una guía de reproducción para jurados y revisores: clonar el repositorio,
levantar el backend y el workspace, y recorrer los mismos cuatro casos que se
ven en el video del demo. Cada botón llama a un endpoint real y a las mismas
funciones de `krakadyl.core` que ejercitan los tests — nada en la pantalla es
simulado. Con tu propia clave de Meta, Muse Spark y SAM 3.1 corren en vivo.

## Requisitos

- Python 3.11 o superior
- Node.js 20 o superior (para el frontend Vite)
- git
- Una clave de API de Meta con créditos del hackathon — es un hackathon de Meta,
  así que poné tu propia clave y mirá a Muse Spark y SAM 3.1 en acción. Sin ella,
  el núcleo determinista funciona igual; solo "Ask Muse" y las capturas de SAM se
  rechazan, de forma honesta y antes de cualquier llamada.

## 1. Obtener el código

```
git clone https://github.com/annatchijova/krakadyl.git
cd krakadyl
```

## 2. Instalar el backend

Se recomienda un entorno virtual para aislar la instalación:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e '.[api]'
```

Opcional: `pip install -e '.[api,laya]'` habilita además el panel "Handoff note
(Laya)". Sin el extra `laya`, ese único panel devuelve un 503 claro y nada más se
ve afectado.

## 3. Generar los tokens de operador

```
python tools/operator_token.py investigator-A investigator-C
```

Esto imprime cada token una sola vez (con estos iniciás sesión — nunca se
almacenan) y una línea `export KRAKADYL_OPERATOR_TOKENS='...'` que contiene solo
hashes SHA-256. Guardá los dos tokens para la pantalla de login.

- `investigator-A` actúa: prepare, execute, proponer y despachar capturas.
- `investigator-C` evalúa de forma independiente — el segundo par de ojos que
  resuelve un requisito de adquisición. Una autoevaluación se registra como una
  afirmación, nunca como una resolución.

## 4. Levantar el backend

En la terminal que va a correr el backend, definí las credenciales y tu clave de
Meta, y arrancá el servidor:

```
export KRAKADYL_OPERATOR_TOKENS='investigator-A=...;investigator-C=...'   # del paso 3
export META_API_KEY='tu-clave-de-meta'                                    # tu propia clave de Meta

KRAKADYL_ENABLE_SAM=1 KRAKADYL_ENABLE_DEV_ROUTES=1 \
  uvicorn krakadyl.api.app:app --port 8000
```

- Los cuatro casos del demo se siembran automáticamente en el primer arranque.
- `KRAKADYL_ENABLE_SAM=1` activa las capturas en vivo con SAM 3.1.
- `KRAKADYL_ENABLE_DEV_ROUTES=1` activa el panel Simulate para provocar
  obsolescencia (alterar un archivo, revocar un mandato). Un despliegue real lo
  restringe.

El backend está listo cuando `http://localhost:8000/openapi.json` responde.

## 5. Levantar el workspace

En una segunda terminal:

```
cd frontend
npm install
npm run dev
```

Abrí `http://localhost:5173` e iniciá sesión con el token de `investigator-A`. El
frontend apunta a `http://localhost:8000` por defecto; si levantaste el backend en
otro puerto, arrancalo con `VITE_API_BASE=http://localhost:PUERTO npm run dev`.

## 6. Qué vas a ver — los cuatro casos

El selector de casos de arriba cambia entre los cuatro casos sembrados:

| Caso | Qué demuestra | Veredicto |
|---|---|---|
| `case-001` | Verificado y dentro de alcance — la exportación se habilita y se sella | `ALLOWED` |
| `case-gather` | Un requisito sigue abierto pero una fuente autorizada puede resolverlo | `GATHER_EVIDENCE` |
| `case-lost` | Reportado como hecho, nunca verificado de forma independiente, ya no recuperable | `FORBIDDEN` |
| `case-scope` | La acción queda fuera del alcance del mandato | `FORBIDDEN` |

Cosas para probar:

- **Prepare y después Execute.** Prepare decide (gratis, determinista); Execute
  revalida todo y sella un recibo encadenado. Están separados a propósito: pasa
  tiempo entre decidir y actuar.
- **Ask Muse.** Una llamada real y facturada a Meta propone la próxima acción — y
  el motor determinista la revisa igual que a una acción hecha a mano. La
  propuesta es solo para mostrar hasta que el motor se pronuncia.
- **Adquisición.** Proponé y despachá una captura como `investigator-A`, después
  evaluala como `investigator-C`. Solo el evaluador independiente resuelve el
  requisito.
- **Simulate (panel dev).** Alterá un archivo o revocá el mandato, y volvé a
  Execute: la misma acción preparada ahora se rechaza, y el rechazo queda sellado
  en un recibo. "Rechazado, y acá está exactamente por qué" es un resultado de
  primera clase.

## Facturación y comportamiento offline

"Ask Muse" y las capturas de SAM son llamadas reales y facturadas a Meta. Sin
`META_API_KEY` se rechazan antes de cualquier llamada, con una razón clara —
mientras que las lecturas, Prepare, Execute, obsolescencia, recuperación y
delegación no necesitan red en absoluto. Esa es la propiedad de degradación
honesta, demostrada en vez de descrita.

## Para profundizar

- Reproducir casos sin interfaz: `demo/run_case_001.py` y los demás scripts
  `demo/run_case_*.py`; `tools/api_smoke.py` recorre la narrativa del núcleo.
- Detalle de desarrollo del frontend (generación de tipos, puertos):
  `frontend/README.md`.
- Arquitectura y garantías: `TECHNICAL_README.md`.
- Lo que honestamente no se afirma: `docs/known-limitations.md`.
- El demo hosteado para el jurado (Docker + HTTPS público): `docs/judge-demo-guide.md`.

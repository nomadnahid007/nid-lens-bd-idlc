# NID Lens BD

NID Lens BD is a small API and demo UI that reads both sides of a Bangladesh National ID (NID) card
and returns structured, English-translated JSON — name, parents' names, date of birth, NID number,
and both addresses — with per-field confidence scores. It exists to replace manual NID data entry in
KYC/onboarding flows with a single image upload.

## Table of Contents

- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Technology Stack](#technology-stack)
  - [AI / OCR Libraries Used](#ai--ocr-libraries-used)
- [Quick Start](#quick-start)
  - [Build Instructions](#build-instructions)
  - [Run Instructions](#run-instructions)
- [Demo UI](#demo-ui)
- [Configuration](#configuration)
- [Live Mode Setup](#live-mode-setup)
- [API Endpoints](#api-endpoints)
- [Request/Response Examples](#requestresponse-examples)
- [Error Codes](#error-codes)
- [Project Structure](#project-structure)
- [Design Decisions](#design-decisions)
- [Testing](#testing)
- [Privacy](#privacy)
- [AI Usage](#ai-usage)
- [Limitations](#limitations)
- [License](#license)

## Overview

**What it does.** A caller uploads two images — the front and back of a Bangladesh NID card — to
`POST /api/v1/nid/extract`. The service validates both images, sends them to Gemini's flash-tier
model with a fixed extraction prompt, runs the model's output through a deterministic normalizer, and returns a
single JSON object with the seven fields the case study asks for, plus confidence scores, raw OCR
text, warnings, and request metadata.

**Who it's for.** Back-office KYC/onboarding teams who currently retype NID fields by hand from
scanned or photographed cards, and engineers who need a drop-in extraction API to sit in front of an
onboarding form.

**Why Gemini multimodal instead of classical OCR.** A classical pipeline (Tesseract or similar)
gives you raw character recognition and stops there — it does not know that `জেলা` means "District",
that `মোঃ রহিম` should become "Md. Rahim" rather than a literal dictionary translation, or that a
NID's Bengali digits (`১২৩৪৫৬৭৮৯০`) are the same NID number as `1234567890`. Getting from "pixels"
to "the seven fields IDLC asked for, in English, with correct meaning preserved" with classical OCR
would require bolting on a separate Bengali NLP translation model, a script-aware digit/date
normalizer, and hand-tuned layout heuristics for where each field sits on the card — essentially
re-deriving a chunk of what a multimodal LLM already does natively. Gemini reads the image and
reasons about layout, script, and meaning in one pass, which collapses OCR + translation +
layout-understanding into a single model call. The tradeoff — external API dependency, per-call
cost, non-determinism — is deliberately fenced in behind the [normalizer as a trust
boundary](#design-decisions) rather than trusted blindly.

**A note on the specific model name.** This project originally targeted `gemini-2.5-flash` per the
case study's spec. That exact model version has since been deprecated for new API keys ("no longer
available to new users" as of mid-2026) — a real-world illustration of exactly the kind of drift
[prompt/model versioning](#design-decisions) is meant to make visible rather than silently break on.
The default is now `gemini-flash-latest`, a stable alias Google maintains for their current
recommended flash-tier model, so this project keeps working without needing another manual bump the
next time a specific version is retired.

## Architecture Diagram

```
                 ┌──────────────┐        ┌──────────────┐
   Browser /     │  POST         │        │  FastAPI     │
   curl client   │  multipart    │───────▶│  route layer │
                 │  (front,back) │        └──────┬───────┘
                 └──────────────┘                │
                                                  ▼
                                   ┌─────────────────────────────┐
                                   │  1. VALIDATE                │
                                   │  app/imaging/processor.py    │
                                   │  size · decode · format ·    │
                                   │  min-dimension checks         │
                                   └──────────────┬───────────────┘
                                                  ▼
                                   ┌─────────────────────────────┐
                                   │  2. PREPROCESS               │
                                   │  EXIF-rotate · RGB convert ·  │
                                   │  downscale ≤2000px · re-encode│
                                   │  JPEG q90 · contrast signal   │
                                   └──────────────┬───────────────┘
                                                  ▼
                        demo mode         ┌───────────────┐        live mode
                     ┌───────────────────▶│ 3. PROVIDER   │◀───────────────────┐
                     │                    │ ExtractionProvider (interface)     │
                     │                    └───────┬───────┘                    │
              ┌──────┴───────┐                    │                    ┌───────┴────────┐
              │ FixtureProvider│                    │                    │ GeminiProvider │
              │ fixtures/      │                    │                    │ google-genai   │
              │ demo_response  │                    │                    │ gemini-flash-  │
              │ .json          │                    │                    │ latest         │
              └────────────────┘                    ▼                    └────────────────┘
                                   ┌─────────────────────────────┐
                                   │  4. NORMALIZE (trust boundary)│
                                   │  app/extraction/normalizer.py│
                                   │  Bengali digits → ASCII ·     │
                                   │  NID digit/length checks ·    │
                                   │  DOB parsing + future-date    │
                                   │  guard · whitespace/empty     │
                                   │  cleanup · warning collection │
                                   └──────────────┬───────────────┘
                                                  ▼
                                   ┌─────────────────────────────┐
                                   │  5. RESPOND                  │
                                   │  ExtractionService assembles  │
                                   │  ExtractionResponse: data +   │
                                   │  confidence + rawText +       │
                                   │  warnings + status +          │
                                   │  requestId/model/promptVersion│
                                   └──────────────┬───────────────┘
                                                  ▼
                                          200 OK JSON (or a
                                          typed 4xx/5xx error)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the component diagram, per-request data flow,
and threat model.

## Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Language / runtime | Python 3.12 | Wide library support for imaging + async web frameworks; team familiarity. |
| Web framework | FastAPI + Uvicorn | Async-native, generates OpenAPI/Swagger for free, first-class Pydantic integration. |
| Validation / schemas | Pydantic v2 + pydantic-settings | Single source of truth for request/response shapes and typed environment config; camelCase aliasing keeps the JSON contract clean without polluting Python style. |
| Image handling | Pillow | Battle-tested, pure-Python-adjacent, no native OCR needed since Gemini reads pixels directly. |
| Extraction model | google-genai (Gemini, flash-tier — `gemini-flash-latest`) | Multimodal reasoning collapses OCR + translation + layout-understanding into one call (see [Overview](#overview)). |
| Containerization | Docker + Docker Compose | Evaluator runs one command, no local Python/dependency setup. |
| Demo UI | Vanilla HTML/CSS/JS + Google Fonts "Inter" | No build step, no framework version drift, trivially served as static files by FastAPI. Inter (via CDN link, no bundler) is the one intentional external dependency — a widely-used professional UI typeface (Linear, Stripe, GitHub) swapped in for the system font stack to read as a polished product rather than a generic form. |
| Testing | pytest + FastAPI TestClient | In-process HTTP testing without a running server; runs identically on host or in-container. |

### AI / OCR Libraries Used

- **[`google-genai`](https://pypi.org/project/google-genai/)** — Google's Gemini SDK. This is the
  project's OCR *and* translation layer: Gemini (flash-tier, `gemini-flash-latest`) reads the NID
  images directly and returns structured, English-translated fields in one call. See
  [Overview](#overview) for why this replaces a classical OCR engine (e.g. Tesseract) rather than
  sitting alongside one.
- **[`Pillow`](https://pypi.org/project/pillow/)** — image validation and preprocessing only
  (format/size checks, EXIF rotation, resizing). Does no OCR itself; all text recognition and
  translation is Gemini's.

No traditional OCR library (Tesseract, EasyOCR, etc.) is used — that is a deliberate architectural
choice, not an omission; see [Overview](#overview) for the reasoning.

## Quick Start

```bash
git clone https://github.com/nomadnahid007/nid-lens-bd-idlc.git
cd nid-lens-bd-idlc
cp .env.example .env
```

### Build Instructions

```bash
docker compose build
```

Builds the API image (slim Python 3.12 base, pinned dependencies from `requirements.txt`, non-root
user) — no local Python installation or dependency setup required.

### Run Instructions

```bash
docker compose up
```

Or build and run in a single step (the recommended golden path, used throughout this README):

```bash
docker compose up --build
```

Then open `http://localhost:8000` in a browser, or check the health endpoint:

```bash
curl http://localhost:8000/health
# {"status":"ready","mode":"demo","model":"gemini-flash-latest"}
```

The default `.env` ships with `APP_MODE=demo` — **evaluators can exercise the entire system,
including a full extraction round-trip, without any Gemini API key.** Demo mode returns pre-recorded
fixture data (see [fixtures/demo_response.json](fixtures/demo_response.json)) instead of calling the
live model, so the UI, validation, normalization warnings, and error paths are all real — only the
model call itself is swapped out.

## Demo UI

`http://localhost:8000/` serves a single-page vanilla HTML/CSS/JS interface — no framework, no build
step, served directly by FastAPI's `StaticFiles` mount.

- **Header** — title, subtitle, and a live mode badge populated from `GET /health` on load (green
"Demo mode · fixture data", green "Live mode · gemini-flash-latest", or amber "Live mode: API key
missing").
- **Demo mode is a fixed fixture, not a live analysis of your images — and every response says so.**
`APP_MODE=demo` exists so the entire system (upload validation, error handling, response shape, this
UI) can be exercised with zero API key and zero cost. It does **not** simulate per-image OCR — it
returns the same pre-recorded `fixtures/demo_response.json` regardless of what's uploaded. Every
demo-mode response carries an explicit `simulated_response` warning saying exactly that, so it can
never be mistaken for a real read of the images you selected. Switch to `APP_MODE=live` (see [Live
Mode Setup](#live-mode-setup)) to have your actual images analyzed.
- **Upload zone** — two drag-and-drop targets ("NID Front" / "NID Back"), each also click-to-browse.
Selecting a file shows a thumbnail preview, filename, and size. `.jpg`/`.jpeg`/`.png` only, checked
client-side before upload and re-validated server-side regardless.
- **Use sample NID images** — one click fetches `/api/v1/samples/front` and `/api/v1/samples/back`
(the synthetic PNGs described in [Project Structure](#project-structure)) and populates both drop
zones, so a full round trip needs zero local files.
- **Extract** — disabled until both images are selected; shows a spinner while the request is in
flight.
- **Results panel** — a status pill (`COMPLETE`/`PARTIAL`), the seven extracted fields each with a
confidence bar, collapsible raw-OCR-text sections for front/back, a warnings list (or "No
warnings."), and a metadata footer (`requestId`, `processingTimeMs`, `model`, `promptVersion`).
**Copy JSON** and **Download JSON** buttons work off the exact response body — nothing is
reformatted or re-derived client-side.
- **Errors** — a non-2xx response renders a red banner with the `code`, `message`, and `suggestion`
(or FastAPI's validation summary for 422s), instead of failing silently.
- **Reset** clears both uploads and hides the results panel. Uploaded bytes are never written to
`localStorage` or sent anywhere except `/api/v1/nid/extract` — the UI states this explicitly under
the upload zone.

## Configuration

All configuration is environment variables, read via `pydantic-settings` in `app/config.py`. Only
`APP_MODE`, `GEMINI_API_KEY`, and `GEMINI_MODEL` are exposed in `.env.example`; the imaging limits
below have sane defaults and are typically left alone.

| Variable | Default | Meaning |
|---|---|---|
| `APP_MODE` | `demo` | `demo` uses `FixtureProvider` (no API key needed); `live` calls Gemini via `GeminiProvider`. |
| `GEMINI_API_KEY` | *(unset)* | Required when `APP_MODE=live`. Ignored in demo mode. |
| `GEMINI_MODEL` | `gemini-flash-latest` | Model ID passed to the Gemini SDK, and echoed back in every response's `model` field in live mode. A stable alias for Google's current recommended flash-tier model — see [Design Decisions](#design-decisions) for why a pinned version name (e.g. the once-current `gemini-2.5-flash`) isn't used instead. |
| `MAX_IMAGE_SIZE_MB` | `8` | Uploads larger than this are rejected with `413 IMAGE_TOO_LARGE` before decoding. |
| `MIN_IMAGE_DIMENSION` | `64` | Hard floor, in pixels/side, after EXIF rotation — only images too small to plausibly contain a legible card are rejected with `400 INVALID_IMAGE`. Deliberately low; see [Design Decisions](#design-decisions) for why this isn't the ~300px it once was, and why there's no *soft* pixel threshold either. Images below 900px on the long side are upscaled before the model call so smaller uploads still get a fair shot. |

## Live Mode Setup

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in, click **Create
API key**. Takes about 60 seconds; no billing setup required for the free tier.
2. Open `.env` (created from `.env.example` in Quick Start) and set:
   ```
   APP_MODE=live
   GEMINI_API_KEY=your-key-here
   ```
3. Restart the stack: `docker compose up --build`.
4. `GET /health` now reports `{"status":"ready","mode":"live","model":"gemini-flash-latest"}`. If the
key is missing or blank while `APP_MODE=live`, health reports `{"status":"no_api_key", ...}` and the
UI shows an amber "Live mode: API key missing" badge instead of failing silently.

Live-mode calls incur Gemini API usage under your key; demo mode incurs none.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service status, active mode, and configured model. |
| POST | `/api/v1/nid/extract` | Extract structured fields from an NID front/back image pair. `multipart/form-data`, fields `front` and `back`. |
| GET | `/api/v1/samples/front` | Serves the bundled synthetic NID front image (used by the UI's "Use sample NID images" link). |
| GET | `/api/v1/samples/back` | Serves the bundled synthetic NID back image. |
| GET | `/docs` | Interactive Swagger UI — full request/response schemas, try-it-out console. |
| GET | `/` | Static demo UI. |

Full request/response schemas, including all field types and the `GeminiExtractionSchema` used
internally, are in Swagger at `/docs` once the container is running.

## Request/Response Examples

**Happy path** — both images valid, demo mode:

```bash
curl -X POST http://localhost:8000/api/v1/nid/extract \
  -F "front=@fixtures/samples/nid_front_synthetic.png;type=image/png" \
  -F "back=@fixtures/samples/nid_back_synthetic.png;type=image/png"
```

```json
{
  "requestId": "c69e9218-17d1-406a-a91c-7f941dd480a7",
  "status": "complete",
  "data": {
    "name": "Md. Rahim Uddin",
    "fatherName": "Md. Abdul Karim",
    "motherName": "Amena Begum",
    "dateOfBirth": "1998-01-15",
    "nidNumber": "1234567890",
    "presentAddress": "House 12, Road 4, Dhanmondi, Dhaka",
    "permanentAddress": "Dakshinpara Village, Sadar Post Office, Cumilla"
  },
  "confidence": {
    "name": 0.98,
    "fatherName": 0.91,
    "motherName": 0.93,
    "dateOfBirth": 0.99,
    "nidNumber": 0.99,
    "presentAddress": 0.88,
    "permanentAddress": 0.86
  },
  "rawText": {
    "front": "গণপ্রজাতন্ত্রী বাংলাদেশ সরকার\nজাতীয় পরিচয় পত্র\n...",
    "back": "ঠিকানা:\nবাসা ১২, রোড ৪, ধানমন্ডি, ঢাকা\n..."
  },
  "warnings": [],
  "processingTimeMs": 808,
  "model": "fixture",
  "promptVersion": "v1.0.0"
}
```

**Error case** — missing `back` field:

```bash
curl -X POST http://localhost:8000/api/v1/nid/extract \
  -F "front=@fixtures/samples/nid_front_synthetic.png;type=image/png"
```

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "back"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

`422` here is FastAPI's native request-validation response (multipart field missing entirely), not
one of this service's own error codes — see below for the distinction.

**Error case** — wrong image format (e.g. a BMP instead of JPEG/PNG):

```bash
curl -X POST http://localhost:8000/api/v1/nid/extract \
  -F "front=@front.bmp;type=image/bmp" \
  -F "back=@fixtures/samples/nid_back_synthetic.png;type=image/png"
```

```json
{
  "code": "UNSUPPORTED_MEDIA_TYPE",
  "message": "front image must be JPG, JPEG, or PNG, got BMP",
  "suggestion": "Upload JPG, JPEG, or PNG only"
}
```

## Error Codes

| HTTP Status | `code` | Meaning | Suggested Action |
|---|---|---|---|
| 400 | `INVALID_IMAGE` | Image is empty, undecodable, or below the hard minimum dimension (64px/side — genuinely too small to be a legible card, not a general "small image" rejection). | Re-upload a readable image. |
| 413 | `IMAGE_TOO_LARGE` | Image exceeds `max_image_size_mb` (default 8 MB). | Compress the image or use a smaller resolution. |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | File decodes as an image but isn't JPEG or PNG. | Upload JPG, JPEG, or PNG only. |
| 422 | *(FastAPI native)* | Request is missing a required field or has the wrong shape — not a JSON body with a `code` field, but FastAPI's standard `{"detail": [...]}` validation array. | Check the field names (`front`, `back`) and that both are present. |
| 503 | `NO_API_KEY` | `APP_MODE=live` but `GEMINI_API_KEY` is unset. Returned as `{"detail": {"code": ..., ...}}` since it's raised via `HTTPException`, not a custom exception handler. | Set `GEMINI_API_KEY` in `.env`, or switch `APP_MODE=demo`. |
| 503 | `PROVIDER_UNAVAILABLE` | The Gemini SDK call raised (network error, invalid/unparseable response, or the call exceeded a 30-second timeout). The underlying exception is logged server-side for debugging but never included in the response — the client-facing message is always one of a small set of generic, safe strings. | Retry shortly, or switch `APP_MODE=demo`. |

Two response shapes exist by design: the custom exception handlers in `app/main.py`
(400/413/415/`PROVIDER_UNAVAILABLE`) return a flat body — `{"code", "message", "suggestion"}` —
while `NO_API_KEY` is raised as a plain FastAPI `HTTPException`, whose default handler wraps that
same shape under `{"detail": {...}}`. The UI's `app.js` normalizes both shapes before displaying an
error banner. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for why this wasn't unified further.

### Warnings (non-blocking, but not all equally serious)

Not every quality issue is a hard error. A request can still succeed (`200`) while carrying
`warnings` that flag something worth a human's attention. But "non-blocking" doesn't mean "doesn't
affect `status`" — a **critical** warning below means the data present is likely *wrong*, not just
imprecise, so it forces `status: "partial"` even if all seven fields technically have a value.
Non-critical warnings are informational only and never change `status` on their own.

| `code` | Critical? | Raised by | Meaning |
|---|---|---|---|
| `not_an_nid` | **Yes — forces partial** | Gemini (prompt rule 3) | The uploaded image doesn't look like a Bangladesh NID at all. |
| `duplicate_address` | **Yes — forces partial** | `extraction/normalizer.py` | Present and permanent address came back byte-identical — almost always means the model copied one field into both rather than reading two genuinely matching addresses. |
| `cross_field_collision` | **Yes — forces partial** | `extraction/normalizer.py` | Two of name/father's name/mother's name came back identical — a near-certain read error. |
| `low_confidence` | No | `extraction/service.py` | Gemini itself returned a confidence below 60% for a specific field that still has a value. Tied to the model's own judgment, not a pixel-count guess — see [Design Decisions](#design-decisions) for why an earlier resolution/contrast-based warning was removed in favor of this. |
| `missing_nid` | No *(field is already null, so this can't cause a false "complete")* | `extraction/normalizer.py` | The model couldn't read any NID digits at all. |
| `unusual_nid_length` | No | `extraction/normalizer.py` | NID digits were read, but the count isn't 10, 13, or 17 — kept, not discarded, since some legitimate formats vary. |
| `unparseable_dob` | No *(field is already null, so this can't cause a false "complete")* | `extraction/normalizer.py` | Date of birth couldn't be parsed from any known format, or came back in the future. |
| `simulated_response` | No | `extraction/service.py` | **Always present in demo mode, on every response.** States explicitly that the data is pre-recorded fixture output, not a live read of the uploaded images — see [Demo UI](#demo-ui) and [Design Decisions](#design-decisions). |

## Project Structure

```
.
├── app/
│   ├── main.py                # FastAPI app, CORS, static mount, exception handlers
│   ├── config.py               # pydantic-settings Settings + get_settings()
│   ├── api/routes.py           # /health, /api/v1/nid/extract, /api/v1/samples/*
│   ├── models/schemas.py       # Pydantic response/request models (camelCase JSON)
│   ├── imaging/processor.py    # Image validation + preprocessing (validate_and_prepare)
│   ├── extraction/
│   │   ├── provider.py         # ExtractionProvider abstract interface
│   │   ├── gemini_provider.py  # Live Gemini provider + prompt + PROMPT_VERSION
│   │   ├── fixture_provider.py # Demo-mode provider (fixtures/demo_response.json)
│   │   ├── normalizer.py       # Deterministic post-processing / trust boundary
│   │   └── service.py          # Orchestrates validate → extract → normalize → respond
│   └── static/                 # index.html, styles.css, app.js — the demo UI
├── fixtures/
│   ├── demo_response.json      # Fixture data returned in demo mode
│   └── samples/                # Synthetic NID front/back PNGs for the UI's sample link
├── scripts/
│   ├── generate_samples.py     # Regenerates the synthetic NID PNGs
│   ├── smoke_test.sh           # curl-based end-to-end smoke test (bash)
│   └── smoke_test.ps1          # Same, for PowerShell
├── tests/                      # pytest suite (health, extraction, normalizer)
├── docs/                       # ARCHITECTURE.md (deeper technical detail than this README)
├── Dockerfile, docker-compose.yml
└── requirements.txt, .env.example, LICENSE
```

## Design Decisions

- **Gemini over Tesseract.** Explained in [Overview](#overview) — a single multimodal call replaces
OCR + translation + layout-heuristics, at the cost of an external dependency the
[normalizer](#privacy) doesn't blindly trust.
- **Dual-mode provider pattern.** `ExtractionProvider` is an abstract interface with two
implementations — `FixtureProvider` (demo) and `GeminiProvider` (live) — selected at request time in
`routes.py` based on `APP_MODE`. This lets evaluators run and test the entire system, UI included,
with zero API key, and lets the route/service/normalizer code stay identical regardless of which
provider answers.
- **The normalizer is a trust boundary, not a formatter.** Gemini's output is treated as untrusted
input, not ground truth: `normalizer.py` re-validates NID digit count, re-parses dates with an
explicit future-date guard, and strips ambiguous values rather than passing them through. Any field
the model got wrong in a *structurally detectable* way (bad NID length, unparseable or future date)
is caught deterministically instead of silently trusted.
- **Image-quality warnings are confidence-based, not pixel-based.** An earlier version rejected
images below 300px outright, then relaxed that to a soft "below 400px" warning — both were arbitrary
thresholds nobody had validated against actual extraction accuracy, and the second one visibly
misfired: a real 477×304px NID photo extracted perfectly and still got flagged as "low resolution."
Both were removed. The only hard floor left is 64px (genuinely too small to contain a legible card,
essentially never triggered by a real photo), and the "should this be re-uploaded?" signal now comes
from Gemini's own per-field confidence score — the model was already instructed to lower confidence
for text it found blurred, cropped, or ambiguous, which is a far better predictor than a fixed pixel
count decided before anyone looked at the image. A field with a value but confidence below 60% gets
a `low_confidence` warning naming that specific field, instead of a blanket "this whole image might
be bad" guess.
- **Critical warnings override field-completeness for `status`.** `status` was originally just "are
all seven fields non-null" — but a field can be non-null and still be wrong (Gemini duplicating one
address into both `presentAddress` and `permanentAddress`, or copying a name across `name`/
`fatherName`/`motherName`). `duplicate_address`, `cross_field_collision`, and `not_an_nid` are marked
critical (`CRITICAL_WARNING_CODES` in `service.py`) specifically because each one means the *data*
is very likely wrong, not just imprecise — their presence forces `status: "partial"` regardless of
field completeness. `low_confidence` and the normalizer's per-field warnings are deliberately **not**
critical: they're informational flags for a human reviewer, not evidence the extraction failed.
- **Bounded, defensive image handling.** Beyond the compressed-upload-size cap (`MAX_IMAGE_SIZE_MB`,
checked before decode), decoded images are also capped at 50 megapixels — a small, highly-compressible
file can still decode into an enormous pixel grid ("decompression bomb"), which a compressed-byte-size
limit alone can't catch. The Gemini call itself has a 30-second timeout (`PROVIDER_TIMEOUT_SECONDS`),
so a hung provider can't hang the request indefinitely; any provider failure (timeout, network error,
unparseable response) is logged with full detail server-side but surfaced to the client as one of a
few fixed, generic messages — the raw SDK exception is never echoed back, since it can carry internal
details that shouldn't cross the API boundary.
- **Prompt versioning (`PROMPT_VERSION = "v1.0.0"`).** Every response echoes the exact version of
the *Gemini extraction prompt text* (`EXTRACTION_PROMPT` in `gemini_provider.py`) that produced it —
it is not a version for the whole pipeline. Normalizer/validation logic (the critical-warning rules,
cross-field checks, image bounds, etc.) can and does change independently without bumping this
number, because those changes don't affect what was asked of the model, only how its output is
checked afterward. Since LLM output for the same input can drift across *prompt* edits specifically,
this makes extraction results reproducible/auditable against prompt changes and lets a future
consumer detect "this record was extracted under an older prompt" without guessing.
- **No persistence of uploaded data.** Images and extracted field values exist only in request memory
for the duration of one call; neither is ever written to disk, a database, or a log line. This is a
deliberate scope boundary for a KYC-adjacent PII use case — see [Privacy](#privacy). This is
distinct from *operational* logging: provider failures do write a sanitized, PII-free error record
(exception type and traceback, never field values or image bytes) so failures are debuggable.
- **In-memory, single-request processing.** No queue, no background jobs, no batch endpoint. Simpler
failure model (the HTTP response *is* the result — no polling), appropriate for the case study's
synchronous, single-card use case; batch/async would be the natural next step for production volume
(see [Limitations](#limitations)).

## Testing

```bash
docker compose up -d
docker compose exec api pytest -v
```

The image bundles `tests/` specifically so this works without a separate host Python environment.
Coverage:

| File | Covers |
|---|---|
| `tests/test_health.py` | `GET /health` returns 200 and `status: "ready"` in demo mode. |
| `tests/test_extraction_demo.py` | Full demo-mode extraction (200, all fields, `status: "complete"`); missing field → 422; wrong-format image → 415; undersized image → 400. |
| `tests/test_normalizer.py` | Bengali digit conversion, ISO/Bengali-month date parsing, future-date rejection, NID length validation, missing-NID handling. |

**End-to-end smoke test** (outside pytest, against a running container, using the real HTTP
surface):

```bash
docker compose up -d
./scripts/smoke_test.sh                       # bash
# or
powershell -File scripts/smoke_test.ps1        # Windows PowerShell 5.1+ or PowerShell 7+
```

Both scripts hit `/health`, run a full extraction with the bundled sample images, confirm a
missing-field request returns 422, and confirm the sample-image routes respond — printing
`PASS`/`FAIL` per case and a final count.

## Privacy

- **No persistence.** Front/back images are read into memory, validated, preprocessed, sent to the
provider, and discarded when the request completes. No file, database, or object-store write ever
happens.
- **No PII in logs.** The startup log line prints only `mode` and `model`; per-request logs are
Uvicorn's access log (method/path/status), not field values. Provider failures (timeout, network
error, unparseable response) are logged server-side with the exception type/traceback for debugging,
but never with the uploaded image bytes or any extracted field value — and the corresponding
`PROVIDER_UNAVAILABLE` response sent to the client is always one of a few fixed, generic strings,
never the raw exception (see [Error Codes](#error-codes)).
- **Synthetic images only in this repo.** `fixtures/samples/*.png` are programmatically generated
(see [scripts/generate_samples.py](scripts/generate_samples.py)) and contain no real person's data.
- **This is not production-ready for real PII as-is.** Real deployment against real NID cards would
require: a paid Gemini tier with a data-processing agreement (DPA) and a commitment that inputs
aren't used for model training, explicit customer consent language before upload, encryption in
transit (already true — HTTPS at the ingress in front of this service) and a documented retention
policy (currently: none, by design, but a production system would need audit trails), and a security
review of the multipart upload path.

## AI Usage

**Tools.** Claude (via the Claude Code CLI/VS Code extension) was used for scaffolding and
implementation throughout this project. Gemini (flash-tier, via `gemini-flash-latest`) is a runtime
dependency of the shipped application itself — it performs live extraction in `APP_MODE=live` — not
a development tool.

**Verification approach.** Every change was checked the same way: the automated test suite
(`docker compose exec api pytest`), curl/smoke-test checks against a running container for new
endpoints and error paths, and a full read-through of generated code before treating it as done —
not accepted on the basis that it "looked right."

**What AI-generated code was changed, and why.** A non-exhaustive but representative sample: an
early dependency version's response-schema handling didn't work against the live API and was
upgraded; a model alias that stopped being available for new API keys was swapped for a stable one;
a CSS rule was found to silently defeat an element-visibility toggle and was fixed at its root cause;
an initial image-quality heuristic (a fixed resolution/contrast threshold) was found to misfire on a
real photo and was replaced with a confidence-driven check instead. In each case the fix was verified
against a real run of the system, not assumed from reading the diff.

## Limitations

- **Single NID layout tested.** The extraction prompt and synthetic samples reflect one common NID
card layout; older/alternate layouts, smart-card-style NIDs, or heavily worn cards are untested.
- **Live mode depends on an external API.** Gemini availability, quota, and latency are outside this
service's control; `PROVIDER_UNAVAILABLE` (503) is the explicit failure mode rather than a silent
hang.
- **No batch processing.** One request handles exactly one card (front + back). High-volume
onboarding would need a queue-backed batch endpoint.
- **No authentication.** There is no API key, JWT, or rate limiting on this service's own endpoints
— it's designed to sit behind a gateway/BFF in a real deployment, not to be exposed directly.
- **English output quality is bounded by the model.** Transliteration and address translation
quality reflect the underlying Gemini model's judgment; the normalizer catches *structural* errors (bad dates,
bad NID lengths) but cannot verify that a transliterated name is objectively "correct" — that
requires human review for high-stakes use.

## License

MIT — see [LICENSE](LICENSE).

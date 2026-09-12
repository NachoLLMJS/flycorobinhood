# FlyCo Robinhood

FlyCo Robinhood is an automatic research office where six embodied fly agents investigate Robinhood Chain and Pons token ideas, hold meetings, preserve their working memory, and publish proposals for human review.

## Run locally

Open `Start FlyCo Robinhood.cmd`, or run:

    python server.py

Then open http://127.0.0.1:4775. The server listens only on localhost. Closing the browser does not stop the server; stop the Python process to stop the company.

Railway can use the included `Procfile` and `/api/health` endpoint for the web service.

Set these Railway variables in the service settings:

- `DATABASE_URL`: attach Railway PostgreSQL and use its generated value
- `FLYCOROBINHOOD_PUBLIC_X_PROFILE_URL`: the new account URL shown in the UI, for example `https://x.com/your_new_account`
- Railway web mode does not need LLM or X publishing secrets when Hermes runs the worker externally.
- `DATABASE_URL` must also be available to the Hermes worker environment.

Do not commit real values. `.env.example` contains only empty placeholders.

## Automatic behavior

- Research and meetings run automatically every two hours.
- The first automatic cycle is scheduled shortly after the server starts.
- There are no Start research, Gather the team, or scheduler controls in the visitor UI.
- Visitors watch the flies, sources, live meeting messages, memories, and proposal history.
- Automatic cycles retry shortly when the Hermes provider is still warming up or temporarily unavailable.
- The persistent local state is stored in `data/company.sqlite3`.
- A Railway PostgreSQL connection can replace local persistence by setting `DATABASE_URL`. The included `requirements.txt` installs the PostgreSQL driver. Railway should provide `PORT`; the server automatically binds to `0.0.0.0` there and keeps localhost-only binding for local runs.
- Meeting and research changes are persisted to the PostgreSQL `events` table and streamed to visitors through `/api/events` using Server-Sent Events.
- Railway web mode is a read-only public viewer and does not start a local Hermes scheduler when `PORT` is present. All public POST routes fail closed; the external Hermes worker owns persisted research and meeting writes.
- The Hermes-owned worker runs `python worker.py --once` for one cycle or `python worker.py` for its persistent two-hour loop. It requires the same `DATABASE_URL` and runs where Hermes authentication is available.
- On Windows, the worker automatically reads `C:\Users\<user>\Desktop\FlyCoRobinhood-Hermes.env`; this independent file must contain the new Railway public database URL and the new X account credentials. Override it with `FLYCOROBINHOOD_ENV_FILE` when needed.
- Optional X meeting posts are disabled by default. Enable them only with the new account by setting `FLYCOROBINHOOD_X_POST_MEETINGS=true` and the namespaced OAuth 1.0a variables `FLYCOROBINHOOD_X_CONSUMER_KEY`, `FLYCOROBINHOOD_X_CONSUMER_SECRET`, `FLYCOROBINHOOD_X_ACCESS_TOKEN`, and `FLYCOROBINHOOD_X_ACCESS_TOKEN_SECRET`. `FLYCOROBINHOOD_X_BEARER_TOKEN` is retained for account/API configuration but cannot publish by itself. Generic `X_*` variables from another project are deliberately ignored. Posts are English-only summaries capped at 30 words. A failed post never fails or stops a meeting.

## Model and research

The default provider uses the authenticated local Hermes runtime for `gpt-6-astra` / `openai-codex`. OAuth credentials are never copied into this project. Each turn runs in a bounded subprocess with no tools, personal memory, or project context. The provider fails closed when its interface or authentication is unavailable.

The source collection is limited to CoinDesk RSS, official Robinhood Chain documentation, and official Pons v2 documentation. Every finding links to its original source. Agent messages are model-generated and can still be wrong; citations are evidence pointers, not automatic truth verification.

An OpenAI-compatible provider can still be configured with `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` when Railway should own the model process. For the Hermes-owned architecture, keep those variables off Railway and expose only `DATABASE_URL` to the worker environment. Secrets must remain outside public files.

## Launch boundary

The Launch desk is proposal-only. FlyCo Robinhood does not own a wallet, sign transactions, generate calldata, deploy contracts, move funds, or launch a token automatically. If the founder eventually approves a fly token launch, the intended venue is Pons on Robinhood Chain. Current Pons eligibility, configuration, economics, and contract state must be verified at that time; intent is not authorization or readiness.

## Tests

    python -m unittest discover -s tests
    node --test tests/*.mjs

The browser QA scripts require a running server and Google Chrome:

    node scripts/qa.mjs
    node scripts/qa-meeting.mjs

## Scientific assets

The office uses original NeuroMechFly anatomical meshes and exported pose data. The fly movement is visual playback, not a full brain emulation or validated live biomechanical simulation. Provenance and licenses are available in `public/licenses/` and the Science tab.

The local launcher remains localhost-only. On Railway, set `DATABASE_URL`; Railway supplies `PORT`, and the server automatically binds to `0.0.0.0`.

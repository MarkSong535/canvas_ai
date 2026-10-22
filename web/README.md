# Canvas AI web client (React)

React + TypeScript port of `frontend/index.html`, built with Vite. Same WebSocket protocol, same look;
`frontend/index.html` is untouched and still what markso.ng serves.

```
npm install
npm run dev        # http://localhost:5173
npm run build      # type-checks, then writes static files to dist/ (host them anywhere)
```

## Publishing to markso.ng (cv2)

markso.ng is the cv2 Astro site on Cloudflare Pages; the demo lives at `/demo/canvas`. With cv2 checked out next to
this repo (`../cv2`):

```
npm run build:cv2  # writes the build to ../cv2/public/demo/canvas (replacing what's there); then commit it in cv2
```

The build uses absolute `/demo/canvas/` asset paths: cv2's Pages Function serves `/demo/canvas` without redirecting
to the trailing slash, so relative paths would resolve against `/demo/`. cv2's `public/_headers` caches the hashed
`assets/` for a year and `public/_routes.json` keeps the Function off them. Preview deployments (`*.pages.dev`) can't
connect: the server only accepts `https://markso.ng`.

Settings are read at build time from `.env.local` (see `.env.example`); the defaults are production's.
Note that `ws_server.py` only accepts connections from `https://markso.ng` and with a valid Turnstile token,
so a locally served copy can't talk to the production server.

## Layout

- `src/useCanvasSocket.ts` – the WebSocket: Turnstile verification, sending, batching streamed deltas per frame
- `src/chatState.ts` – the reducer that turns server frames (`tool`, `delta`, `retract`, `route`, answer, error, course list) into chat state
- `src/protocol.ts` – message types for both directions
- `src/render/richText.ts` – Markdown + LaTeX + chemfig rendering; its math/chemfig extraction must stay in step with `src/utils/latex_svg.py`, whose SVG `renders` it swaps in
- `src/components/` – Header, MessageList/Message, Composer, CourseModal, Turnstile

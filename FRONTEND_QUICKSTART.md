# Frontend Development Quickstart

You're on `feature/viewer-frontend` — isolated from main. Here's the fast path:

## 1. Start the dev server

```bash
npm run dev:viewer
```

Opens at `http://localhost:5173` with hot reload.

## 2. Build the Timeline component

**Key file:** `viewer/src/components/Timeline.tsx`

The timeline is the product (from spec section 4.2):
- Vertical stream, newest at top
- Risk colors: gray (info), blue (write), amber (exec), purple (network), red (sensitive)
- Each row shows: risk dot · time · tool badge · summary · inline first-line-of-reasoning
- Click → detail drawer opens

Spec anatomy:
```
🔴 14:07:31  Bash  useradd staging-svc
  ↳ why: "I need a service account for…"
```

## 3. Build the Detail Drawer

**Key file:** `viewer/src/components/DetailDrawer.tsx`

Four tabs:
- **WHAT** — tool, full arguments (syntax-highlighted), files touched
- **WHY** — captured reasoning verbatim + timestamp + "captured live before compaction" badge
- **CONTEXT** — cwd, git branch, HEAD, dirty flag, session link
- **RESULT** — output, exit status, truncation marker

Should slide up from bottom when a row is clicked. Click outside or Esc to close.

## 4. Fake data while backend is building

**File:** `viewer/src/lib/mockData.ts`

Generate fake events so you can build UI without live Claude sessions. Partner is building the real API.

```typescript
export const mockEvents = [
  {
    id: 1,
    ts: Date.now() - 60000,
    phase: "post",
    tool: "Bash",
    arguments: "npm run migrate",
    reasoning: "The database needs to be updated for the new schema...",
    risk: "exec",
    files: [],
  },
  // ... more events
]
```

## 5. Connect to real API (later)

When partner finishes:
- Replace mock calls with `fetch('/api/events')`
- Set up SSE stream listener in `useEffect`
- Real events slide in to the timeline live

**Current contract (from spec 3.2):**
- `GET /api/sessions` → list sessions
- `GET /api/sessions/{id}/events?filter=...` → events for a session
- `GET /api/events/{id}` → full detail incl. reasoning
- `GET /api/search?q=...` → search results
- `GET /api/stream` → SSE tail of new events

## 6. Polish checklist

By end of day:
- [ ] Timeline renders mock data
- [ ] Risk colors correct (gray/blue/amber/purple/red)
- [ ] Click row → drawer opens with tabs
- [ ] Drawer shows reasoning in the WHY tab
- [ ] Close drawer on Esc or click outside
- [ ] Top bar shows `● REC` and search box
- [ ] Session sidebar left (can be minimal for now)

## 7. Keyboard nav (bonus if time)

- `j` / `k` to navigate rows
- `Enter` to open detail drawer
- `/` to focus search box
- `Esc` to close drawer or exit search

---

**Remember:** timeline + drawer are the PRODUCT. Search UI, polish, sessions sidebar are secondary. Focus on the two hero components first.

**Test:** `npm run dev:viewer` should start in 3 seconds, hot reload should work instantly.

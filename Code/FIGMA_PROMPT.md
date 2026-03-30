# Figma AI Create — DFS Frontend Prompt

Paste the following prompt directly into Figma's AI Create (or Figma Make):

---

## Prompt

Design and build a complete single-page web application for a **Distributed File Conversion Service (DFS)**. This is a university computer networking project that converts files (images, documents, text) over a secure TCP+TLS socket backend.

### Visual Style
Dark theme. Industrial-technical aesthetic. Think: developer tool meets clean SaaS dashboard. Use a dark background (#0a0a0f), subtle grid overlay, and a blue-purple accent gradient (#4f6ef7 → #7c3aed). Typography: Space Mono (monospace, for labels and IDs) + DM Sans (clean body text). Avoid generic purple-gradient-on-white AI aesthetics. The UI should feel like a professional CLI tool translated into a beautiful web interface.

### Pages / Sections (all on one page, no routing)

**1. Header Bar**
- Logo: small gradient square icon + "DFS" in Space Mono bold + subtitle "Distributed File Conversion" in small caps
- Right side: server status pill — shows a pulsing green dot + "online · 2ms" when connected, red dot + "server offline" when not. Clicking it re-pings the server.

**2. File Upload Zone**
- Large drag-and-drop area spanning full width
- Dashed border that glows blue on hover/drag
- Upload icon, heading "Drop your file here", subtext showing supported file types
- "Browse Files" button in accent blue
- Once a file is selected: show filename + file size in a pill below the button

**3. Format Selector + Convert Button (two-column below the drop zone)**
Left card:
- Title "TARGET FORMAT" in small caps monospace
- Dynamic chip grid — chips are auto-populated based on what input file was selected (fetched from /api/formats)
- Each chip shows the format extension (JPG, PNG, PDF, etc.) — selected chip is highlighted blue
- "CONVERT FILE" button below — disabled until both file and format are chosen — gradient blue-purple

Right card:
- Title "SUPPORTED FORMATS" in small caps
- Static reference table showing: input format → available output formats
- Populated from /api/formats endpoint

**4. Job Progress Section (appears after clicking convert)**
- Card with: "CONVERSION JOB" label, animated state badge (QUEUED / PROCESSING / DONE / FAILED with appropriate colors), animated progress bar, job UUID shown in small monospace text
- Green "DOWNLOAD RESULT" button appears only when state = DONE

**5. Job History Table (always visible at bottom)**
- Title "JOB HISTORY" + "REFRESH" button
- Table columns: Job ID (truncated), File, Conversion (e.g. PNG→JPG), Status badge, Download link
- Empty state: "No jobs yet. Upload a file to get started."
- Rows auto-refresh every time a conversion completes

**6. Footer**
- Minimal: "DFS · Socket Programming Project · TCP + TLS · Python"

### Backend API Endpoints to wire up

All calls go to the same origin (the Python web_server.py serves both HTML and API):

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ping` | GET | Returns `{"status":"ok","rtt_ms":2.5}` — use for server status dot |
| `/api/formats` | GET | Returns JSON map of `{src_format: [target_formats]}` — use to populate format chips |
| `/api/convert` | POST | multipart/form-data with `file` (binary) and `format` (string) — returns `{"job_id":"uuid"}` |
| `/api/status/<job_id>` | GET | Returns `{"state":"DONE","job_id":"...","file_size":1234,...}` |
| `/api/download/<job_id>` | GET | Streams the converted file as a download |
| `/api/jobs` | GET | Returns array of all jobs for this browser session |

### State Management Logic

1. On page load: call `/api/ping` → update status dot. Call `/api/formats` → populate format reference. Call `/api/jobs` → populate history table.
2. When file is dropped/selected: extract file extension, call `/api/formats`, filter to that extension's targets, render format chips.
3. When "CONVERT FILE" is clicked: POST to `/api/convert` with FormData (file + format). On success, show progress section with job_id.
4. Poll `/api/status/<job_id>` every 800ms until state = DONE or FAILED. Update progress bar and badge accordingly.
5. When DONE: show download button. Clicking it navigates to `/api/download/<job_id>`.
6. After conversion: refresh `/api/jobs` to update history table.

### Color tokens
```
--bg:        #0a0a0f
--surface:   #13131a
--surface2:  #1c1c28
--border:    #2a2a3d
--accent:    #4f6ef7
--accent2:   #7c3aed
--success:   #10b981
--warning:   #f59e0b
--error:     #ef4444
--text:      #e2e8f0
--muted:     #64748b
```

### Technical requirements
- Pure HTML/CSS/JS — no React, no build step required
- Must work when served from Python's `http.server` or the included `web_server.py`
- Use `fetch()` for all API calls
- Use `FormData` for file upload (multipart/form-data)
- Session cookie `dfs_session` is automatically set by the server on first conversion — no need to manage it manually
- All API responses are JSON except `/api/download` which is a binary file stream

### Animations
- Drop zone border glow on drag
- Format chip selection with smooth color transition
- Progress bar pulse animation during PROCESSING state
- Toast notification (bottom-right) for success/error events
- Smooth appear/disappear for progress section


# DESIGN.md — Tracing Vellum Design System

**TraceLedger: Daylight Editorial Forensic Audit Suite**

## 1. Principles
- **Daylight Editorial**: Paper and ink. No dark mode, no neon accents, no crypto cliches.
- **Evidence-First**: Every conclusion is a path. The core motif is a fine vertical thread linking circular nodes; dashed segments represent missing evidence.
- **Zero Script Interception**: Forms contain zero client-side scripts to protect synthesized clipboard dictation (Wispr Flow).
- **Accessible & Multimodal**: Never rely on color alone. Every state pairs a color with an explicit icon and text label. AA contrast ratio maintained across all tokens.

---

## 2. Color Tokens

```css
:root {
  /* Paper & Surfaces */
  --color-paper: #f3efe6;
  --color-surface: #fdf9f0;
  --color-surface-low: #f7f3ea;
  --color-surface-high: #ece8df;
  --color-vellum: rgba(255, 255, 255, 0.75);
  --color-vellum-translucent: rgba(255, 255, 255, 0.55);

  /* Ink & Typography */
  --color-ink: #16213e;
  --color-ink-primary: #010a27;
  --color-ink-secondary: #545f72;
  --color-ink-muted: #76767e;

  /* Line & Borders */
  --color-line: rgba(22, 33, 62, 0.12);
  --color-line-subtle: rgba(22, 33, 62, 0.06);

  /* Status Tokens */
  --color-verified: #1f7a5c;
  --color-verified-bg: #eaf5f0;
  --color-contradicted: #d9482b;
  --color-contradicted-bg: #fdf0ed;
  --color-candidate: #c99a2e;
  --color-candidate-bg: #fcf6e8;
  --color-missing: #9a948a;
  --color-missing-bg: #f5f4f2;
}
```

---

## 3. Typography

- **Display / Editorial**: `'Fraunces', 'Newsreader', Georgia, serif`
  - Used for Page titles, major headlines, brand wordmark.
- **Body / Interface**: `'Instrument Sans', -apple-system, sans-serif`
  - Used for body text, form labels, buttons, navigation, table data.
- **Data & Hashes**: `'JetBrains Mono', monospace`
  - Strictly reserved for transaction hashes, block numbers, wallet addresses, and base-unit currency values.

---

## 4. Components

### A. Vellum Card
Soft white translucent surface with subtle layered elevation:
```css
background: var(--color-vellum);
backdrop-filter: blur(8px);
border: 1px solid var(--color-line);
border-radius: 6px;
box-shadow: 0 1px 3px rgba(22, 33, 62, 0.05), 0 4px 12px rgba(22, 33, 62, 0.03);
```

### B. Status Badges
Always paired with an icon glyph and text label:
- `VERIFIED`: `✓ Verified` (solid emerald border & background)
- `CONFLICT`: `⚠ Conflict` (solid rust border & background)
- `MISSING`: `◌ Missing Evidence` (dashed gray border)
- `UNRESOLVED`: `◬ Unresolved` (neutral amber/slate pill)

### C. Citation Chips
Rendered with an anchor link: `<a href="#ev-0x3e1b..." class="citation-chip">#0x3e1b...</a>`.
When clicked, the target finding or evidence card is highlighted via pure CSS `:target`:
```css
.finding-card:target {
  outline: 2px solid var(--color-ink);
  background-color: #fff9e6;
}
```

### D. Evidence Thread (SVG)
Vertical thread motif connecting:
`Invoice` &rarr; `Payment Request` &rarr; `Approved Address` &rarr; `Transaction` &rarr; `Ledger`.
- Solid emerald link: verified connection.
- Dashed link: missing or unresolved relationship.


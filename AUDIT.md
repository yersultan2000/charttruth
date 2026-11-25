# ChartTruth UX and quality audit (25 Nov 2026)

Method: automated Playwright sweep at 320, 414, 768, 1280 and 1920 px (horizontal overflow, tap targets < 32 px, unnamed controls, text < 12.5 px, heading order, console errors, broken anchors, every button clicked), plus visual review of screenshots.

## Findings, by priority
| # | Priority | Problem | Fix |
|---|---|---|---|
| 1 | P0 | The auditor, the core tool, started ~1,500 px down on phones; page was 18,900 px long | Compact hero; auditor is the first section; tricks as a compact list (desktop 10,500 → 8,400 px) |
| 2 | P0 | Upload was only a tile at the end of a horizontally scrolling strip (off-screen on phones) | "Upload a chart" in the hero and the auditor toolbar, drop-anywhere overlay, paste with Ctrl+V |
| 3 | P0 | AI panel toggle was 22 px tall | 44 px targets on all summaries and buttons |
| 4 | P1 | Decoration with no job: rotated stickers, infinite marquee, auto-cycling hero, giant footer wordmark, announcement bar | Removed |
| 5 | P1 | Headings up to 92 px; 8 different corner radii; 3 button heights | One type scale (hero 58, sections 40), radii 8/12/14 px, buttons 38/44/46 px |
| 6 | P1 | Trick gallery redrew six full charts the auditor already shows; lab charts stacked and oversized | Thumbnails plus a link to the auditor; lab charts side by side |
| 7 | P1 | Nav icons squeezed to 31 px at 320 px; 11 px hint text | Fixed-size icons; minimum 12 px |
| 8 | P2 | No way to share an audit or export the data | Share link (numbers packed into the URL), CSV download |
| 9 | P3 | Each edit redrew all charts twice | One render per edit; history recorded separately |
| 10 | P3 | `aria-label` on divs without a role | `role="group"` |
| 11 | P3 | Hero animation ran off-screen | Removed with the hero demo |

## Verified after the changes
- 0 horizontal overflow, 0 undersized targets, 0 console errors at all five widths
- Every button and anchor works. End to end: upload, paste, drop, manual entry with validation, undo, share link round trip (and a damaged link), CSV and PNG downloads, provider switching, keyboard shortcuts, guided tour
- The web rule engine and `eval_misviz.py` give identical verdicts on 15 test cases; the game's answer key matched on 1,800 generated charts

## Round 2 (user feedback: "uncomfortable, not understandable"; wanted futuristic)
- Restructured into three tabs (Check a chart, Spot the lie, Learn). The main page went from 8,400 px to about 2,100 px on desktop.
- Check a chart is now a numbered 1-2-3 flow with a live step tracker: pick a chart, see what's wrong, share.
- After an upload, one clear choice: "Let AI read it" or "Type the numbers myself". The disabled button explains why it's disabled.
- Plain language throughout ("Exaggeration 2.88×" instead of a bare lie factor). The number editor is folded away and opens automatically only when ChartTruth needs you.
- Futuristic dark visual: glowing glass panels, HUD-framed comparison viewer, scan animation while the AI reads. Reduced motion is respected.
- Re-tested: 0 overflow and 0 console errors at 5 widths; every interaction passes end to end.

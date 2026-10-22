# HCI Principles Applied in CinePhile

Author: Ayush Sabale · Subject: Human-Computer Interaction (lab / continuous evaluation)

## 1. Nielsen's 10 usability heuristics

| # | Heuristic | Where it appears in CinePhile |
|---|-----------|-------------------------------|
| 1 | Visibility of system status | Toast messages after adding/removing a film; live count badge on "My List"; search announces "N suggestions available"; result counts on the search page; pressed state (✓) on list buttons. |
| 2 | Match between system and real world | Familiar film vocabulary (Top rated, My List, More like this); posters, star ratings, runtime as "2h 32m". |
| 3 | User control and freedom | The same button adds and removes a film (undo); Escape closes suggestions; breadcrumbs and "Back to browse" on every detail page. |
| 4 | Consistency and standards | One card component, one button style, one colour for actions (red) and one for success (green) across all pages; follows streaming-service conventions users already know. |
| 5 | Error prevention | Search needs 2+ characters before querying; buttons are disabled while a request is in flight (no double submits); duplicate list entries are blocked by a database constraint. |
| 6 | Recognition rather than recall | Genre chips, suggestions dropdown, visible navigation, poster cards with title/genre/rating always visible (not hidden behind hover). |
| 7 | Flexibility and efficiency of use | Press `/` anywhere to focus search; arrow keys + Enter in suggestions; horizontal rows scroll with mouse, touch, trackpad or arrow buttons. |
| 8 | Aesthetic and minimalist design | Dark theme that keeps focus on content; only essential information on cards; generous spacing; two typefaces only (Outfit for headings, Inter for text). |
| 9 | Help users recognise, diagnose and recover from errors | Friendly "Nothing matched" page with suggestions and a "Browse all films" button; custom 404 page; failed list updates roll back the button and show a clear message. |
| 10 | Help and documentation | "About" page explains how recommendations work; similarity scores have a tooltip; hint text under "More like this". |

## 2. Gestalt principles

- **Proximity:** a film's poster and its text are grouped; rows are separated by generous whitespace.
- **Similarity:** every poster card has the same shape and size, so users scan quickly.
- **Continuity:** horizontal rows imply "there is more to the right" (a partially visible next card).
- **Figure/ground:** the dark background makes colourful posters and the red call-to-action stand out.
- **Common region:** facts (director, cast, themes) are grouped in one ruled list.

## 3. Laws of UX

- **Fitts's law:** primary buttons are large (min 48 px tall); navigation targets are at least 44 px; carousel arrows span the full row height.
- **Hick's law:** the home page limits each row to 16 films and groups them by genre to reduce decision time; search offers at most 8 suggestions.
- **Jakob's law:** layout follows the conventions of popular streaming apps (top navigation, hero, rows).
- **Miller's law:** short, chunked lists (2 genres on cards, up to 3 shared reasons).
- **Doherty threshold:** the UI responds immediately (optimistic updates, 220 ms search debounce) and the ML model is trained once at start-up so recommendations return in milliseconds.
- **Aesthetic-usability effect:** polished visuals increase perceived usability and trust.

## 4. Accessibility (WCAG 2.2 oriented)

- Semantic landmarks (`header`, `nav`, `main`, `footer`), one `h1` per page, logical heading order.
- "Skip to main content" link.
- Visible 3 px focus ring on all interactive elements; full keyboard operation.
- ARIA: `aria-label` on cards and carousel buttons, `aria-pressed` on toggle buttons, combobox/listbox pattern for search, `aria-live` regions for toasts and search status, `aria-current` on navigation.
- Colour contrast: body text and muted text have high contrast against the dark background; information is never conveyed by colour alone (✓ icon plus label text on saved films).
- `prefers-reduced-motion` disables animation and hover movement.
- Responsive from 320 px to wide desktop; touch targets at least 44 px.

## 5. Explainable and user-controlled recommendations

- Each suggestion shows its **similarity %** and a bar, plus **"Shared: …"** reasons (genre, theme, cast, director). This makes the ML model transparent and builds trust.
- Personalisation is entirely user-controlled: it only uses films the user chose to add to My List, and removing a film immediately changes the suggestions.
- No account, email or tracking is required; an anonymous cookie stores the list.

## 6. Suggested evaluation methods for your report

1. **Heuristic evaluation** using the table in section 1 (score each heuristic 0-4 for severity).
2. **Task-based usability test** with about 5 users: find a film, save two films, find "Picked for you", search by actor. Record time on task, errors and satisfaction.
3. **System Usability Scale (SUS)** questionnaire after the test.
4. **Accessibility checks:** keyboard-only navigation, a screen reader, and Lighthouse / axe DevTools.

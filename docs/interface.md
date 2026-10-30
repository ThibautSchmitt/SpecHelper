# Interface conventions

The AI Connections screen is the visual reference for all SpecHelper screens.
Use the existing shared components and theme variables to preserve this direction.

- Use quiet card surfaces, a single thin border and regular spacing. Keep nested
  information in smaller inset panels or expandable details.
- Use rectangular buttons with a small corner radius. Use fully rounded tags for
  status, model and role labels; color conveys a consistent meaning.
- Keep names and status visible. Put detailed quota observations, logs and
  technical provenance behind explicit disclosures.
- Avoid decorative shadows, glows and illustrated backgrounds in content panels.
  Retain the existing hover/focus treatment on analysis, ticket and activity rows.
- Respect the configurable accent, light/dark modes, visible keyboard focus and
  mobile wrapping. Never rely on color alone to communicate status.

Shared surfaces live in `frontend/src/app/dashboard.css`; controls and semantic
states use `frontend/src/app/globals.css` and `frontend/src/components/ui/`.
These conventions change presentation only, not analysis or publication behavior.

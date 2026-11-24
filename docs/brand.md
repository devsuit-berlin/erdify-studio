# Brand

erdify-studio belongs to the [erdify](https://github.com/devsuit-berlin/erdify) family. It
uses erdify's devsuit palette and icon frame, plus one element of its own: the **dragged
card**.

## Logo

| Asset | File | Use |
| --- | --- | --- |
| Icon | `docs/assets/erdify-studio-icon.svg` (`-512.png`, `-1024.png`) | Avatars, app icons, the docs header, square spaces |
| Wordmark, light | `docs/assets/erdify-studio-wordmark-light.svg` (`.png`) | On white or light backgrounds |
| Wordmark, dark | `docs/assets/erdify-studio-wordmark-dark.svg` (`.png`) | On dark backgrounds |
| Favicon | `docs/assets/favicon.png` (64 px), `frontend/public/favicon.svg` | Browser tabs: docs site and the studio UI |

<p align="center">
  <img alt="erdify-studio icon" src="assets/erdify-studio-icon.svg" width="160">
  &nbsp;&nbsp;
  <img alt="erdify-studio wordmark" src="assets/erdify-studio-wordmark-light.svg" width="440">
</p>

### Anatomy

- **Frame:** a rounded square in indigo (corner radius 224/1024). It's the same as erdify's.
- **Entity cards:** two white cards with navy headers, a yellow key dot and lavender field
  bars, joined by a white relation line with a crow's foot. Same drawing as erdify's icon.
- **Studio element:** the lower card is lifted out of its slot. The **dashed cyan outline**
  is where it was, and the **pointer** on its header is dragging it.
- **Wordmark:** "erdify" uses erdify's own glyphs ("erd" indigo, "ify" navy). "studio" is
  a monoline word in cyan, with the same round caps and line weight as the relation line.

### Usage

- **Clear space:** keep at least a quarter of the icon's height free on every side.
- **Minimum size:** icon 16 px (favicon), wordmark 120 px wide.
- **Light/dark:** use the light wordmark on light backgrounds and the dark one on dark
  backgrounds. In READMEs, switch with `<picture>` and `prefers-color-scheme`. The icon
  works on both.
- **README and PyPI:** reference the assets by absolute
  `raw.githubusercontent.com/.../main/docs/assets/...` URLs. PyPI renders the README as
  the long description, and relative paths break there.

### Don'ts

- Don't recolour, stretch, rotate or add effects (shadows, gradients, outlines).
- Don't remove the dashed slot or the pointer from the icon. Without them it's erdify's icon.
- Don't use the cyan "studio" word without "erdify", or type the wordmark in another font.
- Don't put the light wordmark on a dark background, or the other way round.
- Don't use erdify's icon for studio, or studio's icon for erdify.

## Colours

The devsuit palette, shared with erdify (`docs/stylesheets/extra.css`). Contrast ratios
are WCAG 2.x.

| Name | Hex | Role | Contrast |
| --- | --- | --- | --- |
| Indigo | `#4150AA` | Primary, icon frame, "erd", links (light) | 7.11:1 on white |
| Indigo light | `#6573C3` | Primary, light variant | — |
| Navy | `#192346` | Card headers, "ify", dark primary | 15.33:1 on white |
| Cyan | `#18B4E0` | Accent on dark, "studio" (dark), dashed slot | 2.43:1 on white: **don't use for text on light** |
| Cyan dark | `#087F9E` | Accent on light, "studio" (light), link hover | 4.63:1 on white (AA) |
| Periwinkle | `#8C9EFF` | "erd" and links on dark backgrounds | 6.48:1 on `#1E2129` |
| Yellow | `#F5DC19` | Key dot only (decorative) | 1.39:1 on white: never text |
| Lavender | `#C5CAE9` | Field bars only (decorative) | — |
| White | `#FFFFFF` | Cards, relation line, "ify" on dark | 7.11:1 on indigo |

## Typography

- **Docs site:** MkDocs Material's theme fonts (Roboto, Roboto Mono), same as erdify.
- **Studio UI:** system fonts only. The UI loads no external assets.
- **Wordmark:** outlined paths, never live text. Edit the SVGs instead of retyping them.

## Changing the assets

- The SVGs are the sources. Regenerate the PNGs from them, e.g.
  `rsvg-convert -w 1024 erdify-studio-icon.svg -o erdify-studio-icon-1024.png`
  (wordmark PNGs at 1120 px height, favicon at 64 px).
- If erdify's icon or palette changes, update studio to match. The family look comes first.

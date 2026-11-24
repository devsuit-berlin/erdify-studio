# Brand

erdify-studio belongs to the [erdify](https://github.com/devsuit-berlin/erdify) family. It
uses erdify's devsuit palette and icon frame, plus one element of its own: the **dragged
card**.

## Logo

| Asset | File | Use |
| --- | --- | --- |
| Icon | `docs/assets/erdify-studio-icon.svg` (`-512.png`, `-1024.png`) | Avatars, app icons, square spaces from 48 px |
| Wordmark, light | `docs/assets/erdify-studio-wordmark-light.svg` (`.png`) | On white or light backgrounds |
| Wordmark, dark | `docs/assets/erdify-studio-wordmark-dark.svg` (`.png`) | On dark backgrounds |
| Favicon | `docs/assets/erdify-studio-favicon.svg` (source), `docs/assets/favicon.png` (64 px), `frontend/public/favicon.svg` | Browser tabs, the docs header, the studio toolbar, anything below 48 px |

<p align="center">
  <img alt="erdify-studio icon" src="assets/erdify-studio-icon.svg" width="160">
  &nbsp;&nbsp;
  <img alt="erdify-studio wordmark" src="assets/erdify-studio-wordmark-light.svg#gh-light-mode-only" width="320">
  <img alt="erdify-studio wordmark" src="assets/erdify-studio-wordmark-dark.svg#gh-dark-mode-only" width="320">
</p>

### Anatomy

- **Frame:** a rounded square in indigo (corner radius 224/1024). It's the same as erdify's.
- **Entity cards:** two white cards with navy headers, a yellow key dot and lavender field
  bars, joined by a white relation line with a crow's foot. Same drawing as erdify's icon.
- **Studio element:** the lower card is lifted out of its slot. The **dashed cyan outline**
  is where it was, and the **pointer** on its header is dragging it.
- **Wordmark:** "erdify" uses erdify's own glyphs (Roboto Bold, "erd" indigo, "ify" navy).
  "studio" is a descriptor: Roboto Medium at about 64 % of the size, on the same baseline,
  in cyan. One type family, and "erdify" stays the dominant word.
- **Favicon:** a reduced icon for small sizes. Same frame, cards and dashed slot, but no
  pointer, crow's foot, key dots or field bars, and heavier strokes, so it stays legible
  at 16 px.

### Usage

- **Clear space:** keep at least a quarter of the icon's height free on every side.
- **Minimum size:** full icon 48 px; below that use the favicon (down to 16 px). Wordmark
  160 px wide.
- **Light/dark:** use the light wordmark on light backgrounds and the dark one on dark
  backgrounds. In READMEs, switch with `<picture>` and `prefers-color-scheme`. The icon
  works on both.
- **README and PyPI:** reference the assets by absolute `raw.githubusercontent.com` URLs
  on `main`. PyPI renders the README as the long description, and relative paths break
  there. The README heading:

  ```html
  <p align="center">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/devsuit-berlin/erdify-studio/main/docs/assets/erdify-studio-wordmark-dark.svg">
      <img alt="erdify studio" src="https://raw.githubusercontent.com/devsuit-berlin/erdify-studio/main/docs/assets/erdify-studio-wordmark-light.svg" width="441">
    </picture>
  </p>
  ```

### Don'ts

- Don't recolour, stretch, rotate or add effects (shadows, gradients, outlines).
- Don't remove the dashed slot or the pointer from the icon. Without them it's erdify's icon.
- Don't use the cyan "studio" word without "erdify", or type the wordmark in another font.
- Don't use the full icon below 48 px, or the favicon above it.
- Don't put the light wordmark on a dark background, or the other way round.
- Don't use erdify's icon for studio, or studio's icon for erdify.

## Colours

The devsuit palette, shared with erdify (`docs/stylesheets/extra.css`). Contrast ratios
are WCAG 2.x.

| Name | Hex | Role | Contrast |
| --- | --- | --- | --- |
| Indigo | `#4150AA` | Primary, icon frame, "erd", links (light) | 7.11:1 on white |
| Indigo light | `#6573C3` | Primary, light variant | 4.38:1 on white: large text and UI only |
| Navy | `#192346` | Card headers, "ify", dark primary | 15.33:1 on white |
| Cyan | `#18B4E0` | Accent on dark, "studio" (dark), dashed slot | 2.43:1 on white: **don't use for text on light** |
| Cyan dark | `#087F9E` | Accent on light, "studio" (light), link hover | 4.63:1 on white (AA) |
| Periwinkle | `#8C9EFF` | "erd" and links on dark backgrounds | 6.48:1 on `#1E2129` (a dark background like Material's slate scheme) |
| Yellow | `#F5DC19` | Key dot only (decorative) | 1.39:1 on white: never text |
| Lavender | `#C5CAE9` | Field bars only (decorative) | — |
| White | `#FFFFFF` | Cards, relation line, "ify" on dark | 7.11:1 on indigo |

## Typography

- **Docs site:** MkDocs Material's theme fonts (Roboto, Roboto Mono), same as erdify.
- **Studio UI:** system fonts only. The UI loads no external assets.
- **Wordmark:** outlined paths, never live text. Edit the SVGs instead of retyping them.

## Changing the assets

- The SVGs are the sources. Regenerate the PNGs with `rsvg-convert` (from librsvg, e.g.
  `brew install librsvg` or `apt install librsvg2-bin`), from `docs/assets/`:

  ```bash
  rsvg-convert -w 1024 erdify-studio-icon.svg -o erdify-studio-icon-1024.png
  rsvg-convert -w 512 erdify-studio-icon.svg -o erdify-studio-icon-512.png
  rsvg-convert -w 64 erdify-studio-favicon.svg -o favicon.png
  rsvg-convert -h 1120 erdify-studio-wordmark-light.svg -o erdify-studio-wordmark-light.png
  rsvg-convert -h 1120 erdify-studio-wordmark-dark.svg -o erdify-studio-wordmark-dark.png
  cp erdify-studio-favicon.svg ../../frontend/public/favicon.svg
  ```
- If erdify's icon or palette changes, update studio to match. The family look comes first.

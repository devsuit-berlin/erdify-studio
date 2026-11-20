// How the canvas draws a box. Sizes come from Python (_place.py); this file only
// holds what turns them into pixels, so a later SVG export can draw the same.

/** Advance width of JetBrains Mono per em: font size = charWidth / FONT_ADVANCE. */
export const FONT_ADVANCE = 0.6;
/** The font the box sizes are measured for (bundled, see style.css). */
export const FONT_FAMILY = '"JetBrains Mono", ui-monospace, monospace';
/** Characters reserved in front of a field name for its PK / FK / UK badges. */
export const MARKER_CHARS = 6;
/** Distance between parallel edges of the same two boxes. */
export const FAN_STEP = 16;
/** Margin around the boxes when the view is fitted. */
export const FIT_MARGIN = 40;
export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 4;

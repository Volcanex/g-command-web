/* g-design@1.7.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// htm bound to Preact's h, and the hooks the kit uses. Bare imports: the consumer's bundler
// (or import map) resolves "preact" and "htm", so the kit shares the app's one Preact.
import { h, Fragment } from "preact";
import htm from "htm";
export const html = htm.bind(h);
export { h, Fragment };
export { useState, useEffect, useRef, useCallback, useLayoutEffect } from "preact/hooks";

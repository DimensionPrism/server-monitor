# UI/UX Debug Review - March 13, 2026

## Overview

A comprehensive audit of the current Server Monitor Dashboard (v1.3.x) against the "Premium Refinement" and "Visual Optimization" design specifications. While the visual language successfully achieves a high-end "operator surface" aesthetic, several critical interaction and animation regressions have been identified that impact real-time monitoring and feel.

## 🟢 Successes (Spec-Compliant)

### 1. Visual Language & Typography
- **Dual-Font System**: Successfully implemented with Aptos for UI controls and JetBrains Mono for metrics, providing excellent scanability and a technical, "instrument" feel.
- **Semantic Coloring**: Utilization coloring (clean, warn, alert) and GPU heat levels (cool, warm, hot) are correctly mapped to CSS variables and data attributes.
- **Surface Layering**: The `surface-0` through `surface-4` palette creates clear elevation and depth, especially on the Settings "Overview Rail" and "Editor Canvas".

### 2. Layout & Responsiveness
- **Add Server Visibility**: Correctly follows the "Collapse Adjustment" spec (collapsed by default when servers exist), avoiding clutter while remaining accessible.
- **Mobile Adaptive**: Grid transitions and summary stacking (down to 560px) preserve core monitoring data without horizontal scrolling.
- **Settings Selection-First Model**: The left-rail/right-canvas pattern effectively separates server selection from focused editing.

## 🔴 Critical Issues (UX & Polish)

### 1. Broken Metric Transitions
- **Issue**: The `transition: width 220ms ease` on `.meter-fill` is non-functional during live updates.
- **Root Cause**: `app.js` uses `innerHTML` replacement in `patchCardBody`. This destroys the existing DOM nodes and recreates them on every WebSocket message, preventing CSS transitions from calculating between states.
- **Impact**: Metrics appear to "jump" or flicker rather than gliding smoothly, failing the "Premium" feel requirement.

### 2. Real-time Feedback "Dead Zone" (Interaction Lock)
- **Issue**: Hovering a server card freezes its state updates.
- **Root Cause**: `isCardInteractionLocked` returns `true` if a card is hovered. While intended to prevent "blinking" during hover/press, it defers all updates (storing them in `__pendingBodyHtml`) until the mouse leaves the card.
- **Impact**: If a user clicks "Pull" or "Reboot" and keeps their mouse on the card to watch for success, they see **nothing** change until they move their mouse away. This is a severe UX regression for real-time monitoring.

### 3. Stale Hover Transitions
- **Issue**: When a card finally updates (after mouseleave), it may re-trigger its entry transition or lose its "active" highlight.
- **Impact**: Frequent WebSocket updates can lead to a "shimmering" effect where elements lose their hover state momentarily as the DOM is swapped.

## 🛠 Recommended Fixes

1.  **Transition to Surgical DOM Updates**: Refactor `patchCardBody` to target specific elements (`.meter-fill`, `.badge`, `.status-text`) using `querySelector` and update `style.width` or `textContent` directly. This preserves the DOM nodes and enables CSS animations.
2.  **Refine Interaction Locking**: Replace the blanket hover-lock with a more granular system. Only lock specific input fields that have focus, allowing background status text and progress bars to continue updating in real-time.
3.  **Mouseleave Update Trigger**: If `__pendingBodyHtml` exists, apply it immediately on the `mouseleave` event rather than waiting for the next random WebSocket update.

---
**Status**: Critical Fixes Required for v1.4 Milestone.

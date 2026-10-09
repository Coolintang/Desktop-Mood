# V4 — Immersive Wallpaper Desktop

## Interaction architecture
- Pond visual layer is always `WindowStaysOnBottomHint` and permanently mouse-through.
- Tool clicks are handled by a separate transparent `InteractionWindow`.
- `InteractionWindow` is a **lowered normal Tool window**, not `WindowStaysOnBottomHint`; its native mask is restricted to the pond ellipse. This fixes Linux desktop-layer windows becoming visible but unclickable.
- Ordinary application windows remain above the interaction layer.
- Right click on pond cancels the selected tool.

## Floating orb
- Replaces the fixed toolbar.
- Hover the orb to expand tools.
- Click the active tool again to cancel, or use `取消`.
- Includes pause/start and exit controls.
- The orb is lowered periodically so it behaves as wallpaper UI rather than an always-on-top panel.

## Anime environment
- translucent anime-film atmospheric wash over the real wallpaper
- drifting sakura petals and light dust
- painterly stone/moss pond rim and grass tufts
- moving sky/cloud reflections in glass water
- existing dynamic caustics, flow highlights, depth patches and micro-ripples retained

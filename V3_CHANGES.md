# Desktop Pond V3 changes

## Wallpaper layer
- Pond window never uses `WindowStaysOnTopHint`.
- Pond always uses `WindowStaysOnBottomHint`.
- Toolbar also uses `WindowStaysOnBottomHint` and `Qt.Tool`.
- Normal application windows cover both pond and toolbar.
- No tool selected: pond is mouse-through and does not accept focus.
- Tool selected: pond receives tool clicks but remains in the bottom layer.

> Linux/X11: Qt maps `WindowStaysOnBottomHint` to the window manager's below state.
> Wayland compositors may impose their own stacking policy; the program never
> requests top-most behavior.

## Tool state fixes
- Clicking another tool switches immediately.
- Clicking the currently selected tool again cancels it.
- `取消` always returns to `Tool.NONE`.
- Right click on the pond cancels the current tool.
- `Esc` cancels when the pond/toolbar has keyboard focus.
- Button checked state is synchronized with the active tool.

## Dynamic water
- Continuous drifting caustic arcs.
- Same-direction curved flow highlights; no crossing grid families.
- Slowly moving underwater depth patches.
- Sparse ambient surface-tension ripples.
- Tool ripples use a two-ring decay animation.

## Glass visual language
- Pond water is translucent rather than a nearly opaque cyan fill.
- Layered radial water depth + broad frosted reflections.
- Soft specular blooms and a double glass rim.
- Toolbar is a translucent glass capsule with restrained highlight and shadow.

# VoiceClaw Bot Development Rules

## 1. UI Standards: 100% Discord Components V2
- **NO SIDE COLORS / STRIPES:** Never add `accent_color` to Discord UI Containers (`accent_color=None`).
- **NO LEGACY EMBEDS WITH SIDE COLORS:** Never use legacy `discord.Embed(..., color=...)` for bot responses, embeds, or modals. Side color stripes (yellow, blue, green, pink, etc.) are strictly forbidden.
- **BORDERLESS V2 CONTAINERS:** All command overviews, guides, statuses, whitelists, and info responses must use Discord Components V2:
  ```python
  view = discord.ui.LayoutView()
  container = discord.ui.Container(
      discord.ui.TextDisplay("..."),
      accent_color=None
  )
  view.add_item(container)
  await ctx.send(view=view, ephemeral=True)
  ```
- **NO DUPLICATE COMMAND INVOCATIONS:** Always define `@commands.hybrid_group(..., invoke_without_command=True)` so that running a subcommand does not trigger the parent group callback.

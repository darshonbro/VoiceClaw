import os
import sys
import asyncio
import traceback
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

# Load environment variables from .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOT_PREFIX = os.getenv("BOT_PREFIX", ".")

OWNER_ID = int(os.getenv("OWNER_ID", "1281114279948582923"))

if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
    print("\n[WARNING] DISCORD_TOKEN is not configured in .env file!")
    print("Please open .env and set your DISCORD_TOKEN to start VoiceClaw.\n")

# Discord Intents configuration for Verified Bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

def get_prefix(bot, message):
    guild_id = message.guild.id if message and message.guild else None
    prefix = getattr(bot, "guild_prefixes", {}).get(guild_id, BOT_PREFIX)
    return commands.when_mentioned_or(prefix, f"{prefix} ")(bot, message)

class VoiceClawBot(commands.Bot):
    def __init__(self):
        self.guild_prefixes = {}
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
            owner_ids={OWNER_ID}
        )

    async def setup_hook(self):
        """Standard discord.py v2 lifecycle hook for loading extensions and persistent views"""
        try:
            from redis_manager import redis_manager
            await redis_manager.connect()
            self.redis = redis_manager
        except Exception as e:
            print(f"[VoiceClaw] Redis init warning: {e}", file=sys.stderr)

        print("[VoiceClaw] Initializing extensions...")
        try:
            await self.load_extension('cogs.voice')
            print("[VoiceClaw] Loaded extension: cogs.voice")
            
            self.tree.on_error = self.on_app_command_error
            # Do NOT sync globally on every restart - Discord rate limits and blocks the REST session queue
            if os.getenv("SYNC_ON_STARTUP", "false").lower() == "true":
                asyncio.create_task(self.sync_tree_background())
            else:
                print("[VoiceClaw] Fast startup active (slash commands cached). Use '.sync' if commands are changed.")
        except Exception as e:
            print(f"[VoiceClaw] Failed during setup_hook: {e}", file=sys.stderr)
            traceback.print_exc()

    async def close(self):
        if hasattr(self, 'redis') and self.redis:
            await self.redis.close()
        await super().close()

    async def sync_tree_background(self):
        try:
            synced = await self.tree.sync()
            print(f"[VoiceClaw] Successfully synced {len(synced)} slash commands globally!")
        except Exception as e:
            print(f"[VoiceClaw] Background slash sync warning: {e}", file=sys.stderr)

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            msg = f"⏳ This command is on cooldown. Try again in `{round(error.retry_after, 1)}` seconds."
        elif isinstance(error, discord.app_commands.MissingPermissions):
            msg = f"✕ You lack the required permissions: `{', '.join(error.missing_permissions)}`"
        elif isinstance(error, discord.app_commands.CheckFailure):
            msg = "✕ You do not have permission to execute this command."
        elif isinstance(error, discord.app_commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException) and error.original.status == 429:
            retry_after = getattr(error.original, 'retry_after', None)
            wait_text = f" in `{round(retry_after, 1)}` seconds" if retry_after else " shortly"
            msg = f"⚠️ Discord rate limit reached. Please retry{wait_text}."
        else:
            msg = f"✕ Error executing slash command: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    async def update_bot_presence(self):
        """Update Discord status to Streaming with active server count."""
        try:
            guild_count = len(self.guilds)
            stream_url = os.getenv("STREAM_URL", "https://twitch.tv/discord")
            activity = discord.Streaming(
                name=f"| In {guild_count} Servers",
                url=stream_url
            )
            await self.change_presence(activity=activity)
            print(f"[VoiceClaw] Updated presence to Streaming: '| In {guild_count} Servers'")
        except Exception as e:
            print(f"[VoiceClaw] Presence update error: {e}", file=sys.stderr)

    @tasks.loop(minutes=10)
    async def presence_updater_task(self):
        await self.update_bot_presence()

    @presence_updater_task.before_loop
    async def before_presence_updater(self):
        await self.wait_until_ready()

    async def on_ready(self):
        guild_count = len(self.guilds)
        print("========================================")
        print(f" VoiceClaw Bot Online")
        print(f" Logged in as: {self.user.name} (ID: {self.user.id})")
        print(f" Active in: {guild_count} servers")
        print(f" discord.py v{discord.__version__} | Components v2 Active")
        print("========================================")
        
        # Set dynamic bot presence: Streaming | In X Servers
        await self.update_bot_presence()
        if not self.presence_updater_task.is_running():
            self.presence_updater_task.start()

bot = VoiceClawBot()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"⏳ This command is on cooldown. Try again in `{round(error.retry_after, 1)}` seconds.")
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send(f"✕ You lack the required permissions: `{', '.join(error.missing_permissions)}`")
    if isinstance(error, commands.NotOwner):
        return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.")
    if isinstance(error, commands.MissingRequiredArgument):
        cmd_name = ctx.command.qualified_name if ctx.command else "command"
        pref = getattr(ctx.bot, 'guild_prefixes', {}).get(ctx.guild.id if ctx.guild else None, BOT_PREFIX)
        return await ctx.send(f"✕ Missing required argument: `{error.param.name}`. Correct usage: `{pref}{cmd_name} <{error.param.name}>`")
    if isinstance(error, commands.BadArgument):
        return await ctx.send(f"✕ Invalid argument: {error}")
    if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException) and error.original.status == 429:
        retry_after = getattr(error.original, 'retry_after', None)
        wait_text = f" in `{round(retry_after, 1)}` seconds" if retry_after else " shortly"
        return await ctx.send(f"⚠️ Discord rate limit reached. Please retry{wait_text}.")
    print(f"[VoiceClaw] Command error in {getattr(ctx, 'command', 'unknown')}: {error}", file=sys.stderr)

@bot.command(name="sync")
async def manual_sync(ctx):
    """Manually re-sync slash commands (Bot owner only)"""
    if ctx.author.id != OWNER_ID and (not bot.owner_ids or ctx.author.id not in bot.owner_ids):
        return await ctx.send("✕ Only the bot owner can use this command.")
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✓ Successfully synced {len(synced)} slash commands globally!")
    except Exception as e:
        await ctx.send(f"✕ Sync failed: {e}")

@bot.command(name="setstatus", aliases=["refreshstatus"])
async def manual_set_status(ctx):
    """Manually refresh bot Streaming presence with server count (Bot Owner only)"""
    if ctx.author.id != OWNER_ID and (not bot.owner_ids or ctx.author.id not in bot.owner_ids):
        return await ctx.send("✕ Only the bot owner can use this command.")
    await bot.update_bot_presence()
    await ctx.send(f"✓ Presence updated to: **Streaming | In {len(bot.guilds)} Servers**")

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Check if the joined guild is blacklisted by Bot Owner; leave immediately if so."""
    try:
        from mongo_db import is_guild_blacklisted_async
        if await is_guild_blacklisted_async(guild.id):
            print(f"[Blacklist Guard] Server {guild.name} ({guild.id}) is blacklisted. Leaving immediately.")
            try:
                target_ch = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
                if target_ch:
                    view = discord.ui.LayoutView()
                    container = discord.ui.Container(
                        discord.ui.TextDisplay("🚫 **This server has been banned from using VoiceClaw by the bot developer.**"),
                        accent_color=None
                    )
                    view.add_item(container)
                    await target_ch.send(view=view)
            except Exception:
                pass
            await guild.leave()
            return
        
        # Dynamically refresh status with updated server count
        await bot.update_bot_presence()
    except Exception as e:
        print(f"[on_guild_join error]: {e}", file=sys.stderr)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Dynamically refresh status when removed from a server."""
    try:
        await bot.update_bot_presence()
    except Exception as e:
        print(f"[on_guild_remove error]: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Extra Ownership Management (Discord Components V2)
# ---------------------------------------------------------------------------

@bot.group(name="extraowner", invoke_without_command=True)
async def extraowner_group(ctx):
    """Manage Extra Owners who can configure VoiceClaw hubs and dashboard."""
    if not ctx.guild:
        return await ctx.send("✕ This command can only be used inside a server.")

    pref = getattr(ctx.bot, 'guild_prefixes', {}).get(ctx.guild.id, BOT_PREFIX)
    text = (
        "## 👑 Server Extra Ownership\n"
        "Extra Owners have complete permission to set up VoiceClaw voice hubs, "
        "modify categories, adjust bitrates, and access the Web Dashboard.\n\n"
        f"**Available Commands:**\n"
        f"• `{pref}extraowner add <@user|ID>` — Grant Extra Owner permission\n"
        f"• `{pref}extraowner remove <@user|ID>` — Revoke Extra Owner permission\n"
        f"• `{pref}extraowner list` — View all active Extra Owners"
    )
    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

@extraowner_group.command(name="add")
async def extraowner_add(ctx, user: discord.User):
    """Grant Extra Owner permissions to a user (Server Owner only)."""
    if not ctx.guild:
        return
    if ctx.author.id != ctx.guild.owner_id and ctx.author.id != OWNER_ID:
        return await ctx.send("✕ Only the Discord Server Owner or Bot Developer can grant Extra Ownership.")

    from mongo_db import add_extra_owner_async
    success = await add_extra_owner_async(ctx.guild.id, user.id, added_by=ctx.author.id)
    if success:
        text = f"✅ **Granted Extra Ownership** to <@{user.id}> (`{user.name}`).\nThey can now configure VoiceClaw via chat commands and the Web Dashboard."
    else:
        text = f"✕ Failed to add <@{user.id}> as Extra Owner. Database error."

    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

@extraowner_group.command(name="remove")
async def extraowner_remove(ctx, user: discord.User):
    """Revoke Extra Owner permissions from a user (Server Owner only)."""
    if not ctx.guild:
        return
    if ctx.author.id != ctx.guild.owner_id and ctx.author.id != OWNER_ID:
        return await ctx.send("✕ Only the Discord Server Owner or Bot Developer can revoke Extra Ownership.")

    from mongo_db import remove_extra_owner_async
    success = await remove_extra_owner_async(ctx.guild.id, user.id)
    if success:
        text = f"🗑️ **Revoked Extra Ownership** from <@{user.id}> (`{user.name}`)."
    else:
        text = f"✕ Failed to remove <@{user.id}> from Extra Owners."

    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

@extraowner_group.command(name="list")
async def extraowner_list(ctx):
    """List all Extra Owners for this server."""
    if not ctx.guild:
        return
    from mongo_db import get_extra_owners_async
    owners = await get_extra_owners_async(ctx.guild.id)
    if not owners:
        lines = "No Extra Owners assigned yet for this server.\nOnly the Server Owner has management access."
    else:
        lines = "\n".join([f"• <@{uid}> (`{uid}`)" for uid in owners])

    text = f"## 👑 Extra Owners for {ctx.guild.name}\n\n{lines}"
    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

# ---------------------------------------------------------------------------
# Bot Super Owner Server Administration (botban, botunban)
# ---------------------------------------------------------------------------

@bot.command(name="botban")
async def botban_server(ctx, guild_id: int, *, reason: str = "Banned by Bot Owner"):
    """Ban a server from using the bot (Bot Owner only)."""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("✕ Only the Bot Owner can use this command.")

    from mongo_db import blacklist_guild_async
    await blacklist_guild_async(guild_id, reason=reason, banned_by=ctx.author.id)

    target_g = bot.get_guild(guild_id)
    g_name = target_g.name if target_g else f"Guild {guild_id}"
    if target_g:
        try:
            await target_g.leave()
        except Exception:
            pass

    text = f"🚫 **Server Blacklisted**: `{g_name}` (`{guild_id}`)\n**Reason**: {reason}\nBot has departed the server."
    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

@bot.command(name="botunban")
async def botunban_server(ctx, guild_id: int):
    """Unban a server from using the bot (Bot Owner only)."""
    if ctx.author.id != OWNER_ID:
        return await ctx.send("✕ Only the Bot Owner can use this command.")

    from mongo_db import unblacklist_guild_async
    await unblacklist_guild_async(guild_id)

    text = f"✅ **Server Unbanned**: `{guild_id}`. This server can now invite and use VoiceClaw."
    view = discord.ui.LayoutView()
    container = discord.ui.Container(discord.ui.TextDisplay(text), accent_color=None)
    view.add_item(container)
    await ctx.send(view=view)

if __name__ == "__main__":
    if DISCORD_TOKEN and DISCORD_TOKEN != "your_discord_bot_token_here":
        bot.run(DISCORD_TOKEN)
    else:
        print("[VoiceClaw] Bot ready to run once DISCORD_TOKEN is added to .env.")

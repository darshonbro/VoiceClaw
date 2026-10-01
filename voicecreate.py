import os
import sys
import asyncio
import traceback
import discord
from discord.ext import commands
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

    async def on_ready(self):
        print("========================================")
        print(f" VoiceClaw Bot Online")
        print(f" Logged in as: {self.user.name} (ID: {self.user.id})")
        print(f" discord.py v{discord.__version__} | Components v2 Active")
        print("========================================")
        
        # Set dynamic bot presence
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{BOT_PREFIX}help | /voice"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

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

if __name__ == "__main__":
    if DISCORD_TOKEN and DISCORD_TOKEN != "your_discord_bot_token_here":
        bot.run(DISCORD_TOKEN)
    else:
        print("[VoiceClaw] Bot ready to run once DISCORD_TOKEN is added to .env.")

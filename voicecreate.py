import os
import sys
import asyncio
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOT_PREFIX = os.getenv("BOT_PREFIX", ".")

if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
    print("\n[WARNING] DISCORD_TOKEN is not configured in .env file!")
    print("Please open .env and set your DISCORD_TOKEN to start VoiceClaw.\n")

# Discord Intents configuration for Verified Bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

class VoiceClawBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        """Standard discord.py v2 lifecycle hook for loading extensions and persistent views"""
        print("[VoiceClaw] Initializing extensions...")
        try:
            await self.load_extension('cogs.voice')
            print("[VoiceClaw] Loaded extension: cogs.voice")
        except Exception as e:
            print(f"[VoiceClaw] Failed to load cogs.voice: {e}", file=sys.stderr)
            traceback.print_exc()

    async def on_ready(self):
        print("========================================")
        print(f" VoiceClaw Bot Online")
        print(f" Logged in as: {self.user.name} (ID: {self.user.id})")
        print(f" discord.py v{discord.__version__} | Components v2 Active")
        print("========================================")
        
        # Set dynamic bot presence
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{BOT_PREFIX}help | Dynamic Voice"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

bot = VoiceClawBot()

if __name__ == "__main__":
    if DISCORD_TOKEN and DISCORD_TOKEN != "your_discord_bot_token_here":
        bot.run(DISCORD_TOKEN)
    else:
        print("[VoiceClaw] Bot ready to run once DISCORD_TOKEN is added to .env.")

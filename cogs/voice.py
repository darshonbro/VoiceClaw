import asyncio
import os
import time
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = 'voice.db'

# ==========================================
# Discord UI Components v2 - Modals
# ==========================================

class ChannelRenameModal(discord.ui.Modal, title="Rename Voice Channel"):
    name_input = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="e.g. 🎧 Chill Lounge",
        min_length=1,
        max_length=100,
        required=True
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()
        try:
            await self.channel.edit(name=new_name)
            await self.cog.save_user_setting(interaction.user.id, channel_name=new_name)
            await interaction.response.send_message(
                f"✅ Channel name successfully changed to **{new_name}**!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to rename channel: {e}",
                ephemeral=True
            )


class ChannelLimitModal(discord.ui.Modal, title="Set User Limit"):
    limit_input = discord.ui.TextInput(
        label="User Limit (0 = Unlimited)",
        placeholder="Enter a number between 0 and 99",
        min_length=1,
        max_length=2,
        required=True
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        val = self.limit_input.value.strip()
        if not val.isdigit():
            return await interaction.response.send_message("❌ Please enter a valid number (0 - 99).", ephemeral=True)
        limit = int(val)
        if limit < 0 or limit > 99:
            return await interaction.response.send_message("❌ Limit must be between 0 and 99.", ephemeral=True)
        try:
            await self.channel.edit(user_limit=limit)
            await self.cog.save_user_setting(interaction.user.id, channel_limit=limit)
            txt = "Unlimited" if limit == 0 else str(limit)
            await interaction.response.send_message(
                f"✅ User limit set to **{txt}**!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to update limit: {e}", ephemeral=True)


# ==========================================
# Discord UI Components v2 - Knock & Request Views
# ==========================================

class KnockResponseView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel, requester: discord.Member, owner_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel = channel
        self.requester = requester
        self.owner_id = owner_id

    @discord.ui.button(emoji="✅", label="Allow Entry", style=discord.ButtonStyle.success)
    async def allow_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Only the channel host can respond to knock requests.", ephemeral=True)

        # Grant full access
        await self.channel.set_permissions(self.requester, connect=True, view_channel=True, read_messages=True)
        
        # Pull requester in if currently connected to a voice channel
        moved_msg = ""
        if self.requester.voice and self.requester.voice.channel:
            try:
                await self.requester.move_to(self.channel)
                moved_msg = " and pulled into the room"
            except Exception:
                pass

        # Disable buttons
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="🚪 Knock Request Accepted",
            description=f"✅ {interaction.user.mention} granted entry to {self.requester.mention}{moved_msg}!",
            color=0x10B981
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="❌", label="Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Only the channel host can respond to knock requests.", ephemeral=True)

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="🚪 Knock Request Declined",
            description=f"❌ {interaction.user.mention} politely declined {self.requester.mention}'s request.",
            color=0xF43F5E
        )
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
# Discord UI Components v2 - User Select Views
# ==========================================

class PermitUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to permit / grant access...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("❌ Member not found.", ephemeral=True)

        await self.channel.set_permissions(member, connect=True, view_channel=True, read_messages=True)
        await interaction.response.send_message(
            f"✅ Granted {member.mention} access to the channel.",
            ephemeral=True
        )


class PermitSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(PermitUserSelect(channel))


class RejectUserSelect(discord.ui.UserSelect):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to disconnect & reject...", min_values=1, max_values=1)
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("❌ Member not found.", ephemeral=True)

        if member in self.channel.members:
            guild_cfg = await self.cog.get_guild_config(interaction.guild.id)
            root_chan = interaction.guild.get_channel(guild_cfg[2]) if guild_cfg else None
            try:
                if root_chan and isinstance(root_chan, discord.VoiceChannel):
                    await member.move_to(root_chan)
                else:
                    await member.move_to(None)
            except Exception:
                pass

        await self.channel.set_permissions(member, connect=False, view_channel=False)
        await interaction.response.send_message(
            f"🚫 Rejected {member.mention} and revoked their access.",
            ephemeral=True
        )


class RejectSelectView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(RejectUserSelect(cog, channel))


class TransferOwnerSelect(discord.ui.UserSelect):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a room member to pass ownership...", min_values=1, max_values=1)
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member or member not in self.channel.members:
            return await interaction.response.send_message("❌ Selected member must currently be inside the room!", ephemeral=True)

        await self.cog.set_channel_owner(self.channel.id, member.id)
        await self.channel.set_permissions(member, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await interaction.response.send_message(f"👑 Ownership successfully transferred to {member.mention}!", ephemeral=False)


class TransferOwnerView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(TransferOwnerSelect(cog, channel))


# ==========================================
# Discord UI Components v2 - Persistent Dashboard
# ==========================================

class VoiceControlView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def _get_voice_context(self, interaction: discord.Interaction):
        user = interaction.user
        voice_state = user.voice
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message("❌ You are not in a voice channel!", ephemeral=True)
            return None, None

        channel = voice_state.channel
        owner_id = await self.cog.get_channel_owner(channel.id)
        if not owner_id:
            await interaction.response.send_message("❌ This is not an active VoiceClaw temporary channel!", ephemeral=True)
            return None, None

        return channel, owner_id

    # Row 0: Privacy, Invisibility & Knocking Controls
    @discord.ui.button(emoji="🔒", label="Lock", style=discord.ButtonStyle.danger, custom_id="vc_btn_lock", row=0)
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can lock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 **Channel locked!** Unauthorized members cannot connect (they can still knock).", ephemeral=True)

    @discord.ui.button(emoji="🔓", label="Unlock", style=discord.ButtonStyle.success, custom_id="vc_btn_unlock", row=0)
    async def unlock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can unlock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 **Channel unlocked!** Public connection allowed.", ephemeral=True)

    @discord.ui.button(emoji="👻", label="Ghost", style=discord.ButtonStyle.secondary, custom_id="vc_btn_ghost", row=0)
    async def ghost_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can ghost this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=False, connect=False)
        await interaction.response.send_message("👻 **Ghost Mode Activated!** The room is completely invisible to @everyone.", ephemeral=True)

    @discord.ui.button(emoji="👁️", label="Reveal", style=discord.ButtonStyle.secondary, custom_id="vc_btn_reveal", row=0)
    async def reveal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can reveal this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message("👁️ **Channel revealed!** Visible on the channel list again.", ephemeral=True)

    @discord.ui.button(emoji="🔔", label="Knock Mode", style=discord.ButtonStyle.primary, custom_id="vc_btn_knock_toggle", row=0)
    async def knock_toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can change knock settings.", ephemeral=True)

        current_status = self.cog.knock_settings.get(channel.id, True)
        new_status = not current_status
        self.cog.knock_settings[channel.id] = new_status

        if new_status:
            await interaction.response.send_message("🔔 **Knock Mode: ENABLED**\nFriends outside can knock (`.knock`) to request entry when locked/ghosted.", ephemeral=True)
        else:
            await interaction.response.send_message("🔕 **Knock Mode: MUTED (Do Not Disturb)**\nKnock requests are disabled. No one can ring the bell.", ephemeral=True)

    # Row 1: Customization & Ownership
    @discord.ui.button(emoji="✏️", label="Rename", style=discord.ButtonStyle.primary, custom_id="vc_btn_rename", row=1)
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can rename this channel.", ephemeral=True)

        await interaction.response.send_modal(ChannelRenameModal(self.cog, channel))

    @discord.ui.button(emoji="🔢", label="Limit", style=discord.ButtonStyle.primary, custom_id="vc_btn_limit", row=1)
    async def limit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can change the limit.", ephemeral=True)

        await interaction.response.send_modal(ChannelLimitModal(self.cog, channel))

    @discord.ui.button(emoji="👑", label="Claim", style=discord.ButtonStyle.secondary, custom_id="vc_btn_claim", row=1)
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        voice_state = user.voice
        if not voice_state or not voice_state.channel:
            return await interaction.response.send_message("❌ You must be in the voice channel to claim it!", ephemeral=True)

        channel = voice_state.channel
        owner_id = await self.cog.get_channel_owner(channel.id)
        if not owner_id:
            return await interaction.response.send_message("❌ This is not a VoiceClaw channel.", ephemeral=True)

        if user.id == owner_id:
            return await interaction.response.send_message("ℹ️ You are already the owner of this channel!", ephemeral=True)

        owner_member = channel.guild.get_member(owner_id)
        if owner_member and owner_member in channel.members:
            return await interaction.response.send_message(f"❌ Cannot claim: the owner {owner_member.mention} is still in the room!", ephemeral=True)

        await self.cog.set_channel_owner(channel.id, user.id)
        await channel.set_permissions(user, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await interaction.response.send_message(f"👑 **Congratulations!** You are now the new owner of {channel.name}.", ephemeral=False)

    @discord.ui.button(emoji="🤝", label="Transfer", style=discord.ButtonStyle.secondary, custom_id="vc_btn_transfer", row=1)
    async def transfer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can transfer ownership.", ephemeral=True)

        await interaction.response.send_message("Select a room member to pass channel ownership to:", view=TransferOwnerView(self.cog, channel), ephemeral=True)

    # Row 2: User Access & Info
    @discord.ui.button(emoji="👤", label="Permit", style=discord.ButtonStyle.success, custom_id="vc_btn_permit", row=2)
    async def permit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can permit members.", ephemeral=True)

        await interaction.response.send_message("Select a member to grant access to your channel:", view=PermitSelectView(channel), ephemeral=True)

    @discord.ui.button(emoji="🚫", label="Reject", style=discord.ButtonStyle.danger, custom_id="vc_btn_reject", row=2)
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"❌ Only the channel host (<@{owner_id}>) can reject members.", ephemeral=True)

        await interaction.response.send_message("Select a member to disconnect and deny access:", view=RejectSelectView(self.cog, channel), ephemeral=True)

    @discord.ui.button(emoji="ℹ️", label="Info", style=discord.ButtonStyle.secondary, custom_id="vc_btn_info", row=2)
    async def info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return

        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.mention if owner else f"User ID: {owner_id}"
        limit_text = "Unlimited" if channel.user_limit == 0 else f"{len(channel.members)}/{channel.user_limit}"
        knock_mode = "🔔 Enabled" if self.cog.knock_settings.get(channel.id, True) else "🔕 Muted"

        embed = discord.Embed(title="📊 Room Information", color=0x5865F2)
        embed.add_field(name="Channel Name", value=channel.name, inline=True)
        embed.add_field(name="Host", value=owner_name, inline=True)
        embed.add_field(name="Capacity", value=limit_text, inline=True)
        embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000} kbps", inline=True)
        embed.add_field(name="Knock Mode", value=knock_mode, inline=True)
        embed.set_footer(text="VoiceClaw Interactive Privacy Suite")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# Main Cog Implementation
# ==========================================

class voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.knock_cooldowns = {}
        self.knock_settings = {}  # channel_id -> bool (Knock allowed)

    async def cog_load(self):
        """Initialize database tables and register persistent views"""
        await self.init_db()
        self.bot.add_view(VoiceControlView(self))

    # --- Asynchronous Database Utilities ---
    async def init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voiceChannel (
                    userID INTEGER,
                    voiceID INTEGER PRIMARY KEY
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guild (
                    guildID INTEGER PRIMARY KEY,
                    ownerID INTEGER,
                    voiceChannelID INTEGER,
                    voiceCategoryID INTEGER
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS userSettings (
                    userID INTEGER PRIMARY KEY,
                    channelName TEXT,
                    channelLimit INTEGER
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guildSettings (
                    guildID INTEGER PRIMARY KEY,
                    channelName TEXT,
                    channelLimit INTEGER
                )
            ''')
            await db.commit()

    async def get_guild_config(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT guildID, ownerID, voiceChannelID, voiceCategoryID FROM guild WHERE guildID = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def get_channel_owner(self, voice_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT userID FROM voiceChannel WHERE voiceID = ?", (voice_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_owner_channel(self, owner_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (owner_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_channel_owner(self, voice_id: int, new_owner_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE voiceChannel SET userID = ? WHERE voiceID = ?", (new_owner_id, voice_id))
            await db.commit()

    async def register_temp_channel(self, user_id: int, voice_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO voiceChannel (userID, voiceID) VALUES (?, ?)", (user_id, voice_id))
            await db.commit()

    async def delete_temp_channel_record(self, voice_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (voice_id,))
            await db.commit()

    async def get_user_setting(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channelName, channelLimit FROM userSettings WHERE userID = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def save_user_setting(self, user_id: int, channel_name: str = None, channel_limit: int = None):
        async with aiosqlite.connect(DB_PATH) as db:
            current = await self.get_user_setting(user_id)
            name = channel_name if channel_name is not None else (current[0] if current else None)
            limit = channel_limit if channel_limit is not None else (current[1] if current else 0)
            await db.execute(
                "INSERT INTO userSettings (userID, channelName, channelLimit) VALUES (?, ?, ?) ON CONFLICT(userID) DO UPDATE SET channelName=excluded.channelName, channelLimit=excluded.channelLimit",
                (user_id, name, limit)
            )
            await db.commit()

    async def get_guild_setting(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channelName, channelLimit FROM guildSettings WHERE guildID = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    # --- Listener: Voice State Updates ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        guild = member.guild
        guild_cfg = await self.get_guild_config(guild.id)
        if not guild_cfg:
            return

        _, _, master_channel_id, category_id = guild_cfg

        # 1. User Joined the "Join to Create" Master Channel
        if after.channel and after.channel.id == master_channel_id:
            now = asyncio.get_event_loop().time()
            if member.id in self.cooldowns and (now - self.cooldowns[member.id]) < 15:
                try:
                    await member.send("⚠️ You're creating voice channels too fast! Please wait 15 seconds.")
                except Exception:
                    pass
                return

            self.cooldowns[member.id] = now

            user_pref = await self.get_user_setting(member.id)
            guild_pref = await self.get_guild_setting(guild.id)

            chan_name = f"{member.display_name}'s Channel"
            chan_limit = 0

            if guild_pref:
                chan_limit = guild_pref[1]

            if user_pref:
                if user_pref[0]: chan_name = user_pref[0]
                if user_pref[1] is not None: chan_limit = user_pref[1]

            category = guild.get_channel(category_id)
            if not isinstance(category, discord.CategoryChannel):
                category = None

            try:
                temp_channel = await guild.create_voice_channel(
                    name=chan_name,
                    category=category,
                    user_limit=chan_limit
                )

                await temp_channel.set_permissions(self.bot.user, connect=True, view_channel=True, manage_channels=True)
                await temp_channel.set_permissions(member, connect=True, view_channel=True, read_messages=True, manage_channels=True)

                await member.move_to(temp_channel)
                await self.register_temp_channel(member.id, temp_channel.id)
                self.knock_settings[temp_channel.id] = True  # Knock enabled by default

                embed = discord.Embed(
                    title="🎙️ VoiceClaw Privacy & Control Dashboard",
                    description=(
                        f"Welcome to your private room, {member.mention}!\n"
                        "Control your privacy and channel settings with the buttons below:\n\n"
                        "🛡️ **Privacy Suite:**\n"
                        "🔒 `Lock` / 🔓 `Unlock` — Toggle public connection\n"
                        "👻 `Ghost` / 👁️ `Reveal` — Invisibility toggle for @everyone\n"
                        "🔔 `Knock Mode` — Toggle whether guests can request entry\n\n"
                        "⚙️ **Channel Controls:**\n"
                        "✏️ `Rename` & 🔢 `Limit` — Direct popup modal inputs\n"
                        "👤 `Permit` & 🚫 `Reject` — Member select menus\n"
                        "👑 `Claim` & 🤝 `Transfer` — Ownership management"
                    ),
                    color=0x5865F2
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="VoiceClaw Verified System • Zero Command Clutter")
                
                await temp_channel.send(embed=embed, view=VoiceControlView(self))

            except Exception as e:
                print(f"[VoiceClaw Error] Failed to create channel: {e}")

        # 2. Member Left a Temporary Channel
        if before.channel and before.channel.id != master_channel_id:
            chan_id = before.channel.id
            owner_id = await self.get_channel_owner(chan_id)
            if owner_id:
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="VoiceClaw: Temporary channel empty")
                    except Exception:
                        pass
                    await self.delete_temp_channel_record(chan_id)
                    self.knock_settings.pop(chan_id, None)

    # --- Knock / Request to Join Command ---
    @commands.command(name="knock")
    async def knock_cmd(self, ctx, target: discord.Member = None):
        """Request permission to join a locked or ghosted voice room"""
        user = ctx.author

        # Anti-spam cooldown (30 seconds per knocker)
        now = time.time()
        if user.id in self.knock_cooldowns and (now - self.knock_cooldowns[user.id]) < 30:
            rem = int(30 - (now - self.knock_cooldowns[user.id]))
            return await ctx.send(f"⏳ Please wait {rem} seconds before knocking again.", delete_after=5)

        target_channel = None
        owner_id = None

        if target:
            voice_id = await self.get_owner_channel(target.id)
            if voice_id:
                target_channel = ctx.guild.get_channel(voice_id)
                owner_id = target.id
            elif target.voice and target.voice.channel:
                chan = target.voice.channel
                oid = await self.get_channel_owner(chan.id)
                if oid:
                    target_channel = chan
                    owner_id = oid

        if not target_channel:
            # If user mentions no one, check if user is targeting a channel or in an active guild
            return await ctx.send("❓ Please mention the room host or a member inside the room! (e.g. `.knock @Host`)", delete_after=8)

        if user in target_channel.members:
            return await ctx.send("ℹ️ You are already inside that voice channel!", delete_after=5)

        # Check if Knock is enabled for this channel
        if not self.knock_settings.get(target_channel.id, True):
            return await ctx.send("🔕 This room has Knock Mode disabled (Do Not Disturb).", delete_after=6)

        self.knock_cooldowns[user.id] = now

        # Send alert into the target voice channel chat
        embed = discord.Embed(
            title="🚪 Knock, Knock!",
            description=(
                f"🔔 {user.mention} is requesting to enter this room!\n"
                f"**Host:** <@{owner_id}>\n\n"
                "Click **Allow Entry** to grant permission and pull them in, or **Decline** to deny."
            ),
            color=0xF59E0B
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="VoiceClaw Doorbell Notification")

        view = KnockResponseView(self, target_channel, user, owner_id)
        await target_channel.send(f"<@{owner_id}>", embed=embed, view=view)
        await ctx.send(f"🔔 You knocked on **{target_channel.name}**! Waiting for the host to answer...", delete_after=8)

    # --- Setup & Management Commands ---
    @commands.group(name="voice", invoke_without_command=True)
    async def voice_cmd(self, ctx):
        await ctx.invoke(self.help_cmd)

    @voice_cmd.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_cmd(self, ctx):
        """Interactive setup for VoiceClaw Join-to-Create category and voice channel"""
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        await ctx.send("⚙️ **Starting VoiceClaw Setup...**\n1/2: Please enter the name for the **Category** (e.g. `Voice Channels`):")
        try:
            cat_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Setup timed out.")

        await ctx.send("2/2: Please enter the name for the **Join-to-Create** root channel (e.g. `➕ Join to Create`):")
        try:
            chan_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Setup timed out.")

        try:
            new_cat = await ctx.guild.create_category(cat_msg.content.strip())
            new_chan = await ctx.guild.create_voice_channel(chan_msg.content.strip(), category=new_cat)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guildID) DO UPDATE SET
                        ownerID=excluded.ownerID,
                        voiceChannelID=excluded.voiceChannelID,
                        voiceCategoryID=excluded.voiceCategoryID
                ''', (ctx.guild.id, ctx.author.id, new_chan.id, new_cat.id))
                await db.commit()

            await ctx.send(
                f"✅ **VoiceClaw setup successfully!**\n"
                f"• Category: **{new_cat.name}**\n"
                f"• Root Channel: {new_chan.mention}\n\n"
                f"Join {new_chan.mention} to test your automated dynamic channels!"
            )
        except Exception as e:
            await ctx.send(f"❌ Failed to setup channels: {e}")

    @voice_cmd.command(name="panel")
    async def panel_cmd(self, ctx):
        """Send the VoiceClaw Control Dashboard directly into current channel"""
        embed = discord.Embed(
            title="🎙️ VoiceClaw Control Dashboard",
            description="Manage your temporary voice channel using the interactive buttons below.",
            color=0x5865F2
        )
        embed.set_footer(text="VoiceClaw UI Components v2")
        await ctx.send(embed=embed, view=VoiceControlView(self))

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Help embed showing VoiceClaw features and dashboard guide"""
        embed = discord.Embed(
            title="🎙️ VoiceClaw - Verified Voice Management",
            description=(
                "VoiceClaw is a next-generation dynamic voice bot equipped with **Discord UI Components v2**.\n"
                "Everything is managed via real-time interactive buttons, modals, and privacy doorbell notifications!"
            ),
            color=0x5865F2
        )
        embed.add_field(
            name="🛡️ Privacy Suite (Buttons)",
            value=(
                "🔒 **Lock / 🔓 Unlock** — Toggle public connection\n"
                "👻 **Ghost / 👁️ Reveal** — Make channel invisible to @everyone\n"
                "🔔 **Knock Mode** — Enable/mute knock requests for your room"
            ),
            inline=False
        )
        embed.add_field(
            name="🚪 Knocking on Locked Rooms",
            value="`.knock @Host` — Ring the doorbell of a locked/ghosted room. The host gets an **Allow/Decline** prompt!",
            inline=False
        )
        embed.add_field(
            name="🛠️ Admin Commands",
            value="`.voice setup` — Automatically configure category and Join-to-Create channel\n`.voice panel` — Post dashboard view",
            inline=False
        )
        embed.set_footer(text="VoiceClaw • Modern, Clean & High Performance")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(voice(bot))

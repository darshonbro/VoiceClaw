import asyncio
import os
import time
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = 'voice.db'
BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.jpg")

# ==========================================
# Discord UI Components v2 - Modals
# ==========================================

class ChannelRenameModal(discord.ui.Modal, title="Rename Voice Channel"):
    name_input = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="e.g. Chill Lounge",
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
                f"✦ Channel renamed to **{new_name}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"✕ Failed to rename channel: {e}",
                ephemeral=True
            )


class ChannelLimitModal(discord.ui.Modal, title="Set User Limit"):
    limit_input = discord.ui.TextInput(
        label="User Limit (0 = Unlimited)",
        placeholder="0 - 99",
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
            return await interaction.response.send_message("✕ Please enter a valid number (0 - 99).", ephemeral=True)
        limit = int(val)
        if limit < 0 or limit > 99:
            return await interaction.response.send_message("✕ Limit must be between 0 and 99.", ephemeral=True)
        try:
            await self.channel.edit(user_limit=limit)
            await self.cog.save_user_setting(interaction.user.id, channel_limit=limit)
            txt = "Unlimited" if limit == 0 else str(limit)
            await interaction.response.send_message(
                f"✦ User limit set to **{txt}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to update limit: {e}", ephemeral=True)


class SetupCustomModal(discord.ui.Modal, title="Custom Voice Setup"):
    category_name = discord.ui.TextInput(
        label="Category Name",
        default="Voice Channels",
        placeholder="e.g. Voice Lounge",
        max_length=50,
        required=True
    )
    channel_name = discord.ui.TextInput(
        label="Join-to-Create Channel Name",
        default="＋ Join to Create",
        placeholder="e.g. ＋ Create Room",
        max_length=50,
        required=True
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_name = self.category_name.value.strip()
        chan_name = self.channel_name.value.strip()
        guild = interaction.guild

        try:
            new_cat = await guild.create_category(cat_name)
            new_chan = await guild.create_voice_channel(chan_name, category=new_cat)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM guild WHERE guildID = ?", (guild.id,))
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID)
                    VALUES (?, ?, ?, ?)
                ''', (guild.id, interaction.user.id, new_chan.id, new_cat.id))
                await db.commit()

            complete_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ✦ Setup Complete\n"
                    f"• **Category:** `{new_cat.name}`\n"
                    f"• **Join Channel:** {new_chan.mention}\n\n"
                    f"Join {new_chan.mention} to launch your private room."
                ),
                accent_color=None
            )
            complete_view.add_item(container)
            await interaction.followup.send(view=complete_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Setup failed: {e}", ephemeral=True)


# ==========================================
# Discord UI Components v2 - Setup LayoutView
# ==========================================

class SetupLayoutView(discord.ui.LayoutView):
    def __init__(self, cog, author_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id

        # Minimalist Hero Banner without ANY blue sidebar stripe
        gallery_item = discord.MediaGalleryItem("attachment://banner.jpg")
        gallery = discord.ui.MediaGallery(gallery_item)

        container = discord.ui.Container(
            gallery,
            discord.ui.TextDisplay("### VoiceClaw • Dynamic Voice Engine\nConfigure your server's automated temporary voice channels."),
            accent_color=None
        )
        self.add_item(container)

        # Clean Custom Aesthetic Icon Buttons (No default emojis)
        btn_quick = discord.ui.Button(label="Quick Setup", style=discord.ButtonStyle.success, emoji="✦", custom_id="vc_setup_quick")
        btn_custom = discord.ui.Button(label="Custom Setup", style=discord.ButtonStyle.primary, emoji="◈", custom_id="vc_setup_custom")
        btn_cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✕", custom_id="vc_setup_cancel")

        btn_quick.callback = self.quick_setup_callback
        btn_custom.callback = self.custom_setup_callback
        btn_cancel.callback = self.cancel_callback

        action_row = discord.ui.ActionRow(btn_quick, btn_custom, btn_cancel)
        self.add_item(action_row)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("✕ Only the administrator who invoked setup can use these controls.", ephemeral=True)
            return False
        return True

    async def quick_setup_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        try:
            new_cat = await guild.create_category("Voice Channels")
            new_chan = await guild.create_voice_channel("＋ Join to Create", category=new_cat)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM guild WHERE guildID = ?", (guild.id,))
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID)
                    VALUES (?, ?, ?, ?)
                ''', (guild.id, interaction.user.id, new_chan.id, new_cat.id))
                await db.commit()

            success_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ✦ Setup Complete\n"
                    f"• **Category:** `{new_cat.name}`\n"
                    f"• **Root Channel:** {new_chan.mention}\n\n"
                    f"Join {new_chan.mention} to start your automated private room."
                ),
                accent_color=None
            )
            success_view.add_item(container)
            await interaction.edit_original_response(view=success_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Error creating channels: {e}", ephemeral=True)

    async def custom_setup_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SetupCustomModal(self.cog))

    async def cancel_callback(self, interaction: discord.Interaction):
        cancel_view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay("### ✕ Setup Cancelled\nVoiceClaw setup has been cancelled."),
            accent_color=None
        )
        cancel_view.add_item(container)
        await interaction.response.edit_message(view=cancel_view)


# ==========================================
# Discord UI Components v2 - Knock Doorbell Views
# ==========================================

class KnockResponseView(discord.ui.LayoutView):
    def __init__(self, cog, channel: discord.VoiceChannel, requester: discord.Member, owner_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel = channel
        self.requester = requester
        self.owner_id = owner_id

        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"### 🚪 Doorbell Alert\n"
                    f"**{requester.display_name}** ({requester.mention}) is requesting to enter this room.\n"
                    f"**Host:** <@{owner_id}>"
                ),
                accessory=discord.ui.Thumbnail(requester.display_avatar.url)
            ),
            accent_color=None
        )
        self.add_item(container)

        btn_allow = discord.ui.Button(label="Allow Entry", style=discord.ButtonStyle.success, emoji="✦", custom_id="vc_knock_allow")
        btn_decline = discord.ui.Button(label="Decline", style=discord.ButtonStyle.danger, emoji="✕", custom_id="vc_knock_decline")

        btn_allow.callback = self.allow_callback
        btn_decline.callback = self.decline_callback

        row = discord.ui.ActionRow(btn_allow, btn_decline)
        self.add_item(row)

    async def allow_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("✕ Only the channel host can respond to knock requests.", ephemeral=True)

        await self.channel.set_permissions(self.requester, connect=True, view_channel=True, read_messages=True)
        
        moved_msg = ""
        if self.requester.voice and self.requester.voice.channel:
            try:
                await self.requester.move_to(self.channel)
                moved_msg = " and pulled into the room"
            except Exception:
                pass

        resp_view = discord.ui.LayoutView()
        c = discord.ui.Container(
            discord.ui.TextDisplay(f"### ✦ Request Accepted\n{interaction.user.mention} granted entry to {self.requester.mention}{moved_msg}."),
            accent_color=None
        )
        resp_view.add_item(c)
        await interaction.response.edit_message(view=resp_view)

    async def decline_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("✕ Only the channel host can respond to knock requests.", ephemeral=True)

        resp_view = discord.ui.LayoutView()
        c = discord.ui.Container(
            discord.ui.TextDisplay(f"### ✕ Request Declined\n{interaction.user.mention} declined {self.requester.mention}'s knock request."),
            accent_color=None
        )
        resp_view.add_item(c)
        await interaction.response.edit_message(view=resp_view)


# ==========================================
# Discord UI Components v2 - User Select Views
# ==========================================

class PermitUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to permit...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        await self.channel.set_permissions(member, connect=True, view_channel=True, read_messages=True)
        await interaction.response.send_message(
            f"✦ Granted {member.mention} access to the channel.",
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
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

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
            f"✕ Disconnected {member.mention} and revoked their access.",
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
            return await interaction.response.send_message("✕ Selected member must currently be inside the room!", ephemeral=True)

        await self.cog.set_channel_owner(self.channel.id, member.id)
        await self.channel.set_permissions(member, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await interaction.response.send_message(f"♔ Ownership transferred to {member.mention}!", ephemeral=False)


class TransferOwnerView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(TransferOwnerSelect(cog, channel))


# ==========================================
# Discord UI Components v2 - Voice Room LayoutView
# ==========================================

class VoiceControlLayoutView(discord.ui.LayoutView):
    def __init__(self, cog, member_avatar_url: str = "https://cdn.discordapp.com/embed/avatars/0.png", member_name: str = "Member"):
        super().__init__(timeout=None)
        self.cog = cog

        # Pure Components v2 Minimalist Card (No blue border!)
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(f"### VoiceClaw • {member_name}'s Room\nConfigure your channel privacy, limits and access below."),
                accessory=discord.ui.Thumbnail(member_avatar_url)
            ),
            accent_color=None
        )
        self.add_item(container)

        # Row 0: Privacy & Knocking Controls (Aesthetic Custom Glyphs)
        btn_lock = discord.ui.Button(emoji="⚿", label="Lock", style=discord.ButtonStyle.danger, custom_id="vc_btn_lock")
        btn_unlock = discord.ui.Button(emoji="✧", label="Unlock", style=discord.ButtonStyle.success, custom_id="vc_btn_unlock")
        btn_ghost = discord.ui.Button(emoji="◈", label="Ghost", style=discord.ButtonStyle.secondary, custom_id="vc_btn_ghost")
        btn_reveal = discord.ui.Button(emoji="◇", label="Reveal", style=discord.ButtonStyle.secondary, custom_id="vc_btn_reveal")
        btn_knock = discord.ui.Button(emoji="⌬", label="Knock", style=discord.ButtonStyle.primary, custom_id="vc_btn_knock_toggle")

        btn_lock.callback = self.lock_callback
        btn_unlock.callback = self.unlock_callback
        btn_ghost.callback = self.ghost_callback
        btn_reveal.callback = self.reveal_callback
        btn_knock.callback = self.knock_toggle_callback

        row0 = discord.ui.ActionRow(btn_lock, btn_unlock, btn_ghost, btn_reveal, btn_knock)
        self.add_item(row0)

        # Row 1: Customization & Ownership
        btn_rename = discord.ui.Button(emoji="✎", label="Rename", style=discord.ButtonStyle.primary, custom_id="vc_btn_rename")
        btn_limit = discord.ui.Button(emoji="⌗", label="Limit", style=discord.ButtonStyle.primary, custom_id="vc_btn_limit")
        btn_claim = discord.ui.Button(emoji="♔", label="Claim", style=discord.ButtonStyle.secondary, custom_id="vc_btn_claim")
        btn_transfer = discord.ui.Button(emoji="⇄", label="Transfer", style=discord.ButtonStyle.secondary, custom_id="vc_btn_transfer")

        btn_rename.callback = self.rename_callback
        btn_limit.callback = self.limit_callback
        btn_claim.callback = self.claim_callback
        btn_transfer.callback = self.transfer_callback

        row1 = discord.ui.ActionRow(btn_rename, btn_limit, btn_claim, btn_transfer)
        self.add_item(row1)

        # Row 2: Access & Info
        btn_permit = discord.ui.Button(emoji="＋", label="Permit", style=discord.ButtonStyle.success, custom_id="vc_btn_permit")
        btn_reject = discord.ui.Button(emoji="✕", label="Reject", style=discord.ButtonStyle.danger, custom_id="vc_btn_reject")
        btn_info = discord.ui.Button(emoji="ℹ", label="Info", style=discord.ButtonStyle.secondary, custom_id="vc_btn_info")

        btn_permit.callback = self.permit_callback
        btn_reject.callback = self.reject_callback
        btn_info.callback = self.info_callback

        row2 = discord.ui.ActionRow(btn_permit, btn_reject, btn_info)
        self.add_item(row2)

    async def _get_voice_context(self, interaction: discord.Interaction):
        user = interaction.user
        voice_state = user.voice
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message("✕ You are not in a voice channel!", ephemeral=True)
            return None, None

        channel = voice_state.channel
        owner_id = await self.cog.get_channel_owner(channel.id)
        if not owner_id:
            await interaction.response.send_message("✕ This is not an active VoiceClaw temporary channel!", ephemeral=True)
            return None, None

        return channel, owner_id

    async def lock_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can lock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("⚿ **Channel locked!** Unauthorized members cannot connect (they can still knock).", ephemeral=True)

    async def unlock_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can unlock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("✧ **Channel unlocked!** Public connection allowed.", ephemeral=True)

    async def ghost_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can ghost this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=False, connect=False)
        await interaction.response.send_message("◈ **Ghost Mode Activated!** The room is completely invisible to @everyone.", ephemeral=True)

    async def reveal_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can reveal this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message("◇ **Channel revealed!** Visible on the channel list again.", ephemeral=True)

    async def knock_toggle_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change knock settings.", ephemeral=True)

        current_status = self.cog.knock_settings.get(channel.id, True)
        new_status = not current_status
        self.cog.knock_settings[channel.id] = new_status

        if new_status:
            await interaction.response.send_message("⌬ **Knock Mode: ENABLED**\nFriends outside can knock (`.knock`) to request entry.", ephemeral=True)
        else:
            await interaction.response.send_message("✕ **Knock Mode: MUTED (Do Not Disturb)**\nKnock requests are disabled.", ephemeral=True)

    async def rename_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can rename this channel.", ephemeral=True)

        await interaction.response.send_modal(ChannelRenameModal(self.cog, channel))

    async def limit_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change the limit.", ephemeral=True)

        await interaction.response.send_modal(ChannelLimitModal(self.cog, channel))

    async def claim_callback(self, interaction: discord.Interaction):
        user = interaction.user
        voice_state = user.voice
        if not voice_state or not voice_state.channel:
            return await interaction.response.send_message("✕ You must be in the voice channel to claim it!", ephemeral=True)

        channel = voice_state.channel
        owner_id = await self.cog.get_channel_owner(channel.id)
        if not owner_id:
            return await interaction.response.send_message("✕ This is not a VoiceClaw channel.", ephemeral=True)

        if user.id == owner_id:
            return await interaction.response.send_message("ℹ You are already the owner of this channel!", ephemeral=True)

        owner_member = channel.guild.get_member(owner_id)
        if owner_member and owner_member in channel.members:
            return await interaction.response.send_message(f"✕ Cannot claim: the owner {owner_member.mention} is still in the room!", ephemeral=True)

        await self.cog.set_channel_owner(channel.id, user.id)
        await channel.set_permissions(user, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await interaction.response.send_message(f"♔ **Congratulations!** You are now the new owner of {channel.name}.", ephemeral=False)

    async def transfer_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can transfer ownership.", ephemeral=True)

        await interaction.response.send_message("Select a room member to pass channel ownership to:", view=TransferOwnerView(self.cog, channel), ephemeral=True)

    async def permit_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can permit members.", ephemeral=True)

        await interaction.response.send_message("Select a member to grant access to your channel:", view=PermitSelectView(channel), ephemeral=True)

    async def reject_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can reject members.", ephemeral=True)

        await interaction.response.send_message("Select a member to disconnect and deny access:", view=RejectSelectView(self.cog, channel), ephemeral=True)

    async def info_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return

        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.mention if owner else f"User ID: {owner_id}"
        limit_text = "Unlimited" if channel.user_limit == 0 else f"{len(channel.members)}/{channel.user_limit}"
        knock_mode = "Enabled" if self.cog.knock_settings.get(channel.id, True) else "Muted"

        info_view = discord.ui.LayoutView()
        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"### ℹ Room Overview\n"
                f"• **Room:** `{channel.name}`\n"
                f"• **Host:** {owner_name}\n"
                f"• **Occupancy:** `{limit_text}`\n"
                f"• **Bitrate:** `{channel.bitrate // 1000} kbps`\n"
                f"• **Doorbell:** `{knock_mode}`"
            ),
            accent_color=None
        )
        info_view.add_item(c)
        await interaction.response.send_message(view=info_view, ephemeral=True)


# ==========================================
# Main Cog Implementation
# ==========================================

class voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.knock_cooldowns = {}
        self.knock_settings = {}

    async def cog_load(self):
        """Initialize database tables and register persistent views"""
        await self.init_db()
        self.bot.add_view(VoiceControlLayoutView(self))

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
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_guildID ON guild(guildID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_voiceChannel_voiceID ON voiceChannel(voiceID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_userSettings_userID ON userSettings(userID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_guildSettings_guildID ON guildSettings(guildID)')
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
            await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (voice_id,))
            await db.execute("INSERT INTO voiceChannel (userID, voiceID) VALUES (?, ?)", (user_id, voice_id))
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
            await db.execute("DELETE FROM userSettings WHERE userID = ?", (user_id,))
            await db.execute(
                "INSERT INTO userSettings (userID, channelName, channelLimit) VALUES (?, ?, ?)",
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
                    await member.send("✕ You're creating voice channels too fast! Please wait 15 seconds.")
                except Exception:
                    pass
                return

            self.cooldowns[member.id] = now

            user_pref = await self.get_user_setting(member.id)
            guild_pref = await self.get_guild_setting(guild.id)

            chan_name = f"{member.display_name}'s Room"
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
                self.knock_settings[temp_channel.id] = True

                # Send Minimalist Discord Components v2 LayoutView (No blue line, clean icons)
                ctrl_view = VoiceControlLayoutView(self, member.display_avatar.url, member.display_name)
                await temp_channel.send(view=ctrl_view)

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
        """Request permission to join a locked or ghosted voice room (Components v2)"""
        user = ctx.author

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
            return await ctx.send("❓ Please mention the room host or a member inside the room! (e.g. `.knock @Host`)", delete_after=8)

        if user in target_channel.members:
            return await ctx.send("ℹ You are already inside that voice channel!", delete_after=5)

        if not self.knock_settings.get(target_channel.id, True):
            return await ctx.send("✕ This room has Knock Mode disabled (Do Not Disturb).", delete_after=6)

        self.knock_cooldowns[user.id] = now

        # Send Minimalist Components v2 Doorbell Alert into target voice channel
        doorbell_view = KnockResponseView(self, target_channel, user, owner_id)
        await target_channel.send(content=f"<@{owner_id}>", view=doorbell_view)
        await ctx.send(f"⌬ Knock sent to **{target_channel.name}**! Waiting for response...", delete_after=8)

    # --- Setup & Management Commands ---
    @commands.group(name="voice", invoke_without_command=True)
    async def voice_cmd(self, ctx):
        await ctx.invoke(self.help_cmd)

    @voice_cmd.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_cmd(self, ctx):
        """Minimalist Discord Components v2 Interactive Setup (Image Banner, No Blue Stripe, Custom Icons)"""
        view = SetupLayoutView(self, ctx.author.id)
        if os.path.exists(BANNER_PATH):
            file = discord.File(BANNER_PATH, filename="banner.jpg")
            await ctx.send(file=file, view=view)
        else:
            await ctx.send(view=view)

    @voice_cmd.command(name="panel")
    async def panel_cmd(self, ctx):
        """Send the VoiceClaw Control Center directly using Components v2"""
        view = VoiceControlLayoutView(self, ctx.author.display_avatar.url, ctx.author.display_name)
        await ctx.send(view=view)

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Help view powered by Minimalist Discord Components v2"""
        help_view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "### VoiceClaw • Dynamic Voice Engine\n"
                "• ⚿ **Lock / Unlock** — Restrict or allow connection\n"
                "• ◈ **Ghost / Reveal** — Invisibility for `@everyone`\n"
                "• ⌬ **Knock Mode** — Doorbell request toggle\n"
                "• ✎ **Rename** & ⌗ **Limit** — Instant modal inputs\n"
                "• ＋ **Permit** & ✕ **Reject** — Access control\n\n"
                "**Commands:**\n"
                "• `.voice setup` — One-Click Interactive Setup\n"
                "• `.knock @Host` — Ring the doorbell of a private room"
            ),
            accent_color=None
        )
        help_view.add_item(container)
        await ctx.send(view=help_view)


async def setup(bot):
    await bot.add_cog(voice(bot))

import asyncio
import datetime
import os
import time
import traceback
import typing
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "voice.db"))
BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.jpg")
GUIDE_BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "guide.jpg")
PREMIUM_BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "premium.jpg")
HUBS_BANNER_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "hubs.jpg")

def make_v2_card(title: str, text: str, banner_filename: typing.Optional[str] = None) -> discord.ui.LayoutView:
    """Create a minimalist Discord Components v2 LayoutView container with optional banner and NO side accent stripe"""
    view = discord.ui.LayoutView()
    items = []
    if banner_filename:
        items.append(discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{banner_filename}")))
    content = f"### {title}\n{text}" if title else text
    items.append(discord.ui.TextDisplay(content))
    container = discord.ui.Container(
        *items,
        accent_color=None
    )
    view.add_item(container)
    return view

# ==========================================
# Discord UI Components v2 - Modals
# ==========================================

class ChannelRenameModal(discord.ui.Modal, title="Rename Voice Channel"):
    name_input = discord.ui.TextInput(
        label="New Channel Name (Blank = Reset)",
        placeholder="Leave blank to reset to default name...",
        min_length=0,
        max_length=100,
        required=False
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        if await self.cog.is_channel_locked_name(self.channel.id):
            return await interaction.response.send_message(
                f"✕ This voice room has a locked name (`{self.channel.name}`) configured by server administration and cannot be renamed.",
                ephemeral=True
            )
        raw_val = self.name_input.value.strip()
        is_reset = not bool(raw_val)

        if is_reset:
            clean_name = " ".join(interaction.user.display_name.split())
            new_name = f"{clean_name}'s Room"
            await self.cog.save_user_setting(interaction.user.id, clear_name=True)
        else:
            new_name = raw_val
            await self.cog.save_user_setting(interaction.user.id, channel_name=new_name)

        # Discord 2 renames per 10 minutes rate limit check
        wait_sec = self.cog.check_channel_rename_ratelimit(self.channel.id)
        if wait_sec:
            mins = wait_sec // 60
            secs = wait_sec % 60
            time_msg = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            return await interaction.response.send_message(
                f"⏳ **Rate Limited by Discord:** Discord strictly limits channel renames to **2 times per 10 minutes**.\n"
                f"Please wait `{time_msg}` before renaming this channel again.",
                ephemeral=True
            )

        try:
            await self.channel.edit(name=new_name)
            self.cog.record_channel_rename(self.channel.id)
            msg = f"↺ Channel name reset to default: **{new_name}**" if is_reset else f"✦ Channel renamed to **{new_name}**"
            await interaction.response.send_message(
                msg,
                ephemeral=True
            )
            await self.cog.log_voice_event(
                interaction.guild,
                title="↺ Room Name Reset" if is_reset else "✎ Room Renamed",
                description=f"Host {interaction.user.mention} {'reset room name to default' if is_reset else f'renamed room to **{new_name}**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await interaction.response.send_message(
                    f"⏳ **Discord Rate Limit:** Too many requests sent to Discord. Please try again{wait_text}.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✕ Failed to rename channel: {e}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"✕ Failed to rename channel: {e}",
                ephemeral=True
            )


class ChannelLimitModal(discord.ui.Modal, title="Set User Limit"):
    limit_input = discord.ui.TextInput(
        label="User Limit (0 = Unlimited, Blank = Reset)",
        placeholder="0 - 99 (Leave blank to reset to unlimited)",
        min_length=0,
        max_length=2,
        required=False
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.limit_input.value.strip()
        is_reset = not bool(raw_val)

        if is_reset:
            guild_pref = await self.cog.get_guild_setting(interaction.guild.id)
            limit = guild_pref[1] if guild_pref and guild_pref[1] is not None else 0
            await self.cog.save_user_setting(interaction.user.id, clear_limit=True)
        else:
            if not raw_val.isdigit():
                return await interaction.response.send_message("✕ Please enter a valid number (0 - 99).", ephemeral=True)
            limit = int(raw_val)
            if limit < 0 or limit > 99:
                return await interaction.response.send_message("✕ Limit must be between 0 and 99.", ephemeral=True)
            await self.cog.save_user_setting(interaction.user.id, channel_limit=limit)

        try:
            await self.channel.edit(user_limit=limit)
            txt = "Unlimited" if limit == 0 else str(limit)
            msg = f"↺ User limit reset to default (**{txt}**)" if is_reset else f"✦ User limit set to **{txt}**"
            await interaction.response.send_message(
                msg,
                ephemeral=True
            )
            await self.cog.log_voice_event(
                interaction.guild,
                title="↺ User Limit Reset" if is_reset else "⌗ User Limit Changed",
                description=f"Host {interaction.user.mention} {'reset room limit to default' if is_reset else f'set capacity of `{self.channel.name}` to **{txt}**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await interaction.response.send_message(f"⏳ **Rate Limited:** Discord API limit reached. Try again{wait_text}.", ephemeral=True)
            else:
                await interaction.response.send_message(f"✕ Failed to update limit: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to update limit: {e}", ephemeral=True)


class ChannelBitrateModal(discord.ui.Modal, title="Adjust Audio Bitrate"):
    bitrate_input = discord.ui.TextInput(
        label="Bitrate in kbps (Blank = Reset)",
        placeholder="8 - Server Max (Leave blank to reset to 64 kbps)",
        min_length=0,
        max_length=3,
        required=False
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.bitrate_input.value.strip()
        is_reset = not bool(raw_val)
        max_kbps = interaction.guild.bitrate_limit // 1000

        if is_reset:
            default_kbps = min(64, max_kbps)
            kbps = default_kbps
            await self.cog.save_user_setting(interaction.user.id, clear_bitrate=True)
        else:
            if not raw_val.isdigit():
                return await interaction.response.send_message("✕ Please enter a valid numeric value.", ephemeral=True)
            kbps = int(raw_val)
            if kbps < 8 or kbps > max_kbps:
                return await interaction.response.send_message(f"✕ Bitrate must be between 8 kbps and {max_kbps} kbps for this server.", ephemeral=True)
            await self.cog.save_user_setting(interaction.user.id, bitrate=kbps)
        
        try:
            await self.channel.edit(bitrate=kbps * 1000)
            msg = f"↺ Audio bitrate reset to default (**{kbps} kbps**)!" if is_reset else f"🔊 Audio bitrate set to **{kbps} kbps**!"
            await interaction.response.send_message(msg, ephemeral=True)
            await self.cog.log_voice_event(
                interaction.guild,
                title="↺ Bitrate Reset" if is_reset else "🔊 Room Bitrate Changed",
                description=f"Host {interaction.user.mention} {'reset bitrate to default' if is_reset else f'adjusted bitrate of `{self.channel.name}` to **{kbps} kbps**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await interaction.response.send_message(f"⏳ **Rate Limited:** Discord API limit reached. Try again{wait_text}.", ephemeral=True)
            else:
                await interaction.response.send_message(f"✕ Failed to update bitrate: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to update bitrate: {e}", ephemeral=True)


class PresetSaveModal(discord.ui.Modal, title="Save Room Preset"):
    name_input = discord.ui.TextInput(
        label="Preset Name (e.g. Gaming, Chill, Duo)",
        placeholder="Enter preset identifier",
        min_length=1,
        max_length=30,
        required=True
    )

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        p_name = self.name_input.value.strip()
        bitrate_kbps = self.channel.bitrate // 1000
        await self.cog.save_user_preset(
            user_id=interaction.user.id,
            preset_name=p_name,
            channel_name=self.channel.name,
            channel_limit=self.channel.user_limit,
            bitrate=bitrate_kbps
        )
        await interaction.response.send_message(
            f"💾 **Preset '{p_name}' Saved!**\n"
            f"• **Name:** `{self.channel.name}`\n"
            f"• **Limit:** `{self.channel.user_limit if self.channel.user_limit > 0 else 'Unlimited'}`\n"
            f"• **Bitrate:** `{bitrate_kbps} kbps`\n\n"
            f"Load it anytime with `/voice preset load {p_name}` or `.preset load {p_name}`.",
            ephemeral=True
        )


class JtcSetupModal(discord.ui.Modal, title="Configure Join to Create VC"):
    category_name = discord.ui.TextInput(
        label="Category Name (Required)",
        default="Voice Channels",
        placeholder="Enter category name (e.g. Voice Channels)",
        max_length=50,
        required=True
    )
    join_channel_name = discord.ui.TextInput(
        label="Join to Create VC Name (Optional)",
        default="＋ Join to Create",
        placeholder="Default: ＋ Join to Create",
        max_length=50,
        required=False
    )
    interface_name = discord.ui.TextInput(
        label="Interface Channel Name (Optional)",
        default="interface",
        placeholder="Default: interface",
        max_length=50,
        required=False
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_name = self.category_name.value.strip() or "Voice Channels"
        join_name = self.join_channel_name.value.strip() or "＋ Join to Create"
        iface_name = self.interface_name.value.strip().lstrip("#") or "interface"

        try:
            temp_cat, temp_chan, interface_chan = await self.cog.perform_temp_setup(
                interaction.guild,
                interaction.user.id,
                category_name=cat_name,
                join_name=join_name,
                interface_name=iface_name
            )

            children = []
            if os.path.exists(BANNER_PATH):
                children.append(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://banner.jpg")))
            children.append(discord.ui.TextDisplay(
                f"### ✦ Temporary Dynamic Voice Setup Complete\n\n"
                f"• **Category:** `{temp_cat.name}`\n"
                f"• **Join Channel:** {temp_chan.mention}\n"
                f"• **Interface Panel:** {interface_chan.mention}\n\n"
                f"Join {temp_chan.mention} to start your dynamic voice room, and control it from {interface_chan.mention}!"
            ))

            success_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                *children,
                accent_color=None
            )
            success_view.add_item(container)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interaction.followup.send(file=file, view=success_view)
            else:
                await interaction.followup.send(view=success_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Error creating voice setup: {e}", ephemeral=True)


class PermSetupModal(discord.ui.Modal, title="Configure Permanent Voice Rooms"):
    category_name = discord.ui.TextInput(
        label="Permanent Category Name (Required)",
        default="Permanent Rooms",
        placeholder="Enter category name (e.g. Permanent Rooms)",
        max_length=50,
        required=True
    )
    create_channel_name = discord.ui.TextInput(
        label="Create VC Name (Optional)",
        default="＋ Create Permanent VC",
        placeholder="Default: ＋ Create Permanent VC",
        max_length=50,
        required=False
    )
    interface_name = discord.ui.TextInput(
        label="Interface Channel Name (Optional)",
        default="interface",
        placeholder="Default: interface",
        max_length=50,
        required=False
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_name = self.category_name.value.strip() or "Permanent Rooms"
        create_name = self.create_channel_name.value.strip() or "＋ Create Permanent VC"
        iface_name = self.interface_name.value.strip().lstrip("#") or "interface"

        try:
            perm_cat, perm_chan, perm_interface = await self.cog.perform_perm_setup(
                interaction.guild,
                interaction.user.id,
                category_name=cat_name,
                create_name=create_name,
                interface_name=iface_name
            )

            children = []
            if os.path.exists(BANNER_PATH):
                children.append(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://banner.jpg")))
            children.append(discord.ui.TextDisplay(
                f"### ✦ Permanent Voice Setup Complete\n\n"
                f"• **Category:** `{perm_cat.name}`\n"
                f"• **Create Channel:** {perm_chan.mention}\n"
                f"• **Interface Panel:** {perm_interface.mention}\n\n"
                f"Join {perm_chan.mention} to claim your 24/7 permanent room that never auto-deletes!"
            ))

            success_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                *children,
                accent_color=None
            )
            success_view.add_item(container)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interaction.followup.send(file=file, view=success_view)
            else:
                await interaction.followup.send(view=success_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Error creating permanent setup: {e}", ephemeral=True)


class DualSetupModal(discord.ui.Modal, title="Configure Dual Voice System"):
    temp_category = discord.ui.TextInput(
        label="Temporary Category Name (Required)",
        default="Voice Channels",
        placeholder="e.g. Voice Channels",
        max_length=50,
        required=True
    )
    perm_category = discord.ui.TextInput(
        label="Permanent Category Name (Required)",
        default="Permanent Rooms",
        placeholder="e.g. Permanent Rooms",
        max_length=50,
        required=True
    )
    temp_join_name = discord.ui.TextInput(
        label="Temporary Join VC Name (Optional)",
        default="＋ Join to Create",
        placeholder="Default: ＋ Join to Create",
        max_length=50,
        required=False
    )
    perm_create_name = discord.ui.TextInput(
        label="Permanent Create VC Name (Optional)",
        default="＋ Create Permanent VC",
        placeholder="Default: ＋ Create Permanent VC",
        max_length=50,
        required=False
    )
    interface_name = discord.ui.TextInput(
        label="Interface Channel Name (Optional)",
        default="interface",
        placeholder="Default: interface",
        max_length=50,
        required=False
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        t_cat = self.temp_category.value.strip() or "Voice Channels"
        p_cat = self.perm_category.value.strip() or "Permanent Rooms"
        t_join = self.temp_join_name.value.strip() or "＋ Join to Create"
        p_create = self.perm_create_name.value.strip() or "＋ Create Permanent VC"
        iface = self.interface_name.value.strip().lstrip("#") or "interface"

        try:
            temp_cat, temp_chan, interface_chan, perm_cat, perm_chan, perm_interface = await self.cog.perform_dual_setup(
                interaction.guild,
                interaction.user.id,
                temp_category_name=t_cat,
                perm_category_name=p_cat,
                temp_join_name=t_join,
                perm_create_name=p_create,
                interface_name=iface
            )

            children = []
            if os.path.exists(BANNER_PATH):
                children.append(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://banner.jpg")))
            children.append(discord.ui.TextDisplay(
                f"### ✦ Dual Voice Setup Complete\n\n"
                f"**🌀 Temporary Voice System:**\n"
                f"• Category: `{temp_cat.name}`\n"
                f"• Join Channel: {temp_chan.mention}\n"
                f"• Interface Panel: {interface_chan.mention}\n\n"
                f"**✦ Permanent Voice System:**\n"
                f"• Category: `{perm_cat.name}`\n"
                f"• Create Channel: {perm_chan.mention}\n"
                f"• Interface Panel: {perm_interface.mention}\n\n"
                f"All channels and control interfaces are initialized and ready to use!"
            ))

            success_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                *children,
                accent_color=None
            )
            success_view.add_item(container)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interaction.followup.send(file=file, view=success_view)
            else:
                await interaction.followup.send(view=success_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Error creating dual setup: {e}", ephemeral=True)


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
            interface_chan = await guild.create_text_channel(
                "interface",
                category=new_cat,
                topic="VoiceClaw Temporary Voice Channel Control Interface"
            )
            await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

            new_chan = await guild.create_voice_channel(chan_name, category=new_cat)

            ctrl_view = VoiceControlLayoutView(self.cog, has_banner=os.path.exists(BANNER_PATH))
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interface_chan.send(file=file, view=ctrl_view)
            else:
                await interface_chan.send(view=ctrl_view)

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM guild WHERE guildID = ?", (guild.id,))
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID)
                    VALUES (?, ?, ?, ?, ?)
                ''', (guild.id, interaction.user.id, new_chan.id, new_cat.id, interface_chan.id))
                await db.commit()

            complete_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ✦ Setup Complete\n"
                    f"• **Category:** `{new_cat.name}`\n"
                    f"• **Interface:** {interface_chan.mention}\n"
                    f"• **Join Channel:** {new_chan.mention}\n\n"
                    f"Join {new_chan.mention} to start your room, and control it from {interface_chan.mention}!"
                ),
                accent_color=None
            )
            complete_view.add_item(container)
            await interaction.followup.send(view=complete_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Setup failed: {e}", ephemeral=True)


class HubSetupModal(discord.ui.Modal, title="Fixed-Name Themed Hub Setup"):
    category_name = discord.ui.TextInput(
        label="Category Name",
        default="🎮 Gaming Lounge",
        placeholder="e.g. Gaming Lounge or Minecraft World",
        max_length=50,
        required=True
    )
    channel_name = discord.ui.TextInput(
        label="Join-to-Create Channel Name",
        default="＋ Create VC",
        placeholder="e.g. ＋ Create VC or ＋ Join Room",
        max_length=50,
        required=True
    )
    fixed_name = discord.ui.TextInput(
        label="Fixed Room Name (Cannot be changed)",
        default="Gaming",
        placeholder="e.g. Gaming or Minecraft",
        max_length=50,
        required=True
    )
    user_limit = discord.ui.TextInput(
        label="User Limit (0 = Unlimited)",
        default="0",
        placeholder="0 - 99",
        min_length=1,
        max_length=2,
        required=False
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat_name = self.category_name.value.strip()
        chan_name = self.channel_name.value.strip()
        fixed_room_name = self.fixed_name.value.strip()
        limit_val = self.user_limit.value.strip() if self.user_limit.value else "0"
        limit = int(limit_val) if limit_val.isdigit() else 0
        guild = interaction.guild

        try:
            new_cat = await guild.create_category(cat_name)
            interface_chan = await guild.create_text_channel(
                "interface",
                category=new_cat,
                topic=f"VoiceClaw Control Interface for {fixed_room_name} Rooms"
            )
            await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

            join_chan = await guild.create_voice_channel(chan_name, category=new_cat)

            ctrl_view = VoiceControlLayoutView(self.cog, has_banner=os.path.exists(BANNER_PATH))
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interface_chan.send(file=file, view=ctrl_view)
            else:
                await interface_chan.send(view=ctrl_view)

            await self.cog.create_voice_hub(
                guild_id=guild.id,
                category_id=new_cat.id,
                join_channel_id=join_chan.id,
                interface_channel_id=interface_chan.id,
                fixed_name=fixed_room_name,
                user_limit=limit,
                lock_name=1
            )

            complete_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ✦ Fixed-Name Themed Hub Created\n"
                    f"• **Category:** `{new_cat.name}`\n"
                    f"• **Join Channel:** {join_chan.mention}\n"
                    f"• **Interface:** {interface_chan.mention}\n"
                    f"• **Fixed Room Name:** `{fixed_room_name}` *(Locked from renaming)*\n"
                    f"• **Default Capacity:** `{limit if limit > 0 else 'Unlimited'}`\n\n"
                    f"Anyone who joins {join_chan.mention} will get a temporary room named **`{fixed_room_name}`** that auto-deletes once empty!"
                ),
                accent_color=None
            )
            complete_view.add_item(container)
            await interaction.followup.send(view=complete_view)
        except Exception as e:
            await interaction.followup.send(f"✕ Hub creation failed: {e}", ephemeral=True)


# ==========================================
# Discord UI Components v2 - Setup Select & LayoutView
# ==========================================

class SetupSelect(discord.ui.Select):
    def __init__(self, cog, author_id: int):
        options = [
            discord.SelectOption(
                label="🌀  Temporary Dynamic Voice (JTC)",
                value="quick",
                description="Auto-deleting temporary voice rooms with #interface control panel"
            ),
            discord.SelectOption(
                label="👑  Permanent 24/7 Voice Rooms",
                value="permanent_only",
                description="Persistent 24/7 voice channels with saved presets"
            ),
            discord.SelectOption(
                label="🌟  Dual Setup (Temp + Permanent)",
                value="dual",
                description="Deploy both Temporary and Permanent voice categories"
            ),
            discord.SelectOption(
                label="🏷️  Fixed-Name Themed Hub",
                value="fixed_hub",
                description="Creates category with fixed-name Temp VCs (e.g. Gaming, Duo)"
            ),
            discord.SelectOption(
                label="◈  Custom Setup Wizard",
                value="custom",
                description="Configure custom category and channel names"
            ),
            discord.SelectOption(
                label="✕  Cancel Setup",
                value="cancel",
                description="Abort and close this setup configuration"
            )
        ]
        super().__init__(
            placeholder="Select a voice system to set up...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_setup_dropdown"
        )
        self.cog = cog
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("✕ Only the administrator who invoked setup can use these controls.", ephemeral=True)

        selected = self.values[0]
        if selected == "dual":
            await interaction.response.send_modal(DualSetupModal(self.cog))

        elif selected == "quick":
            await interaction.response.send_modal(JtcSetupModal(self.cog))

        elif selected == "permanent_only":
            await interaction.response.send_modal(PermSetupModal(self.cog))

        elif selected == "fixed_hub":
            await interaction.response.send_modal(HubSetupModal(self.cog))

        elif selected == "custom":
            await interaction.response.send_modal(SetupCustomModal(self.cog))

        elif selected == "cancel":
            cancel_view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay("### ✕ Setup Cancelled\nVoiceClaw setup has been cancelled."),
                accent_color=None
            )
            cancel_view.add_item(container)
            await interaction.response.edit_message(view=cancel_view)


class SetupLayoutView(discord.ui.LayoutView):
    def __init__(self, cog, author_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id

        container_children = []
        if os.path.exists(BANNER_PATH):
            gallery_item = discord.MediaGalleryItem("attachment://banner.jpg")
            container_children.append(discord.ui.MediaGallery(gallery_item))

        header_text = discord.ui.TextDisplay(
            "### ✦ VoiceClaw • Interactive Setup Wizard\n"
            "Select which voice channel system you want to configure for this server from the menu below."
        )
        container_children.append(header_text)

        setup_select = SetupSelect(cog, author_id)
        action_row = discord.ui.ActionRow(setup_select)
        container_children.append(action_row)

        btn_refresh = discord.ui.Button(label="Refresh Wizard", emoji=APP_EMOJIS["transfer"], style=discord.ButtonStyle.secondary, custom_id="setup_refresh_btn")
        btn_refresh.callback = self.refresh_callback
        action_row_btn = discord.ui.ActionRow(btn_refresh)
        container_children.append(action_row_btn)

        container = discord.ui.Container(
            *container_children,
            accent_color=None
        )
        self.add_item(container)

    async def refresh_callback(self, interaction: discord.Interaction):
        new_view = SetupLayoutView(self.cog, self.author_id)
        await interaction.response.edit_message(view=new_view)
        await interaction.followup.send("✓ Setup wizard refreshed!", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("✕ Only the administrator who invoked setup can use these controls.", ephemeral=True)
            return False
        return True


# ==========================================
# Discord UI Components v2 - Knock Doorbell Views
# ==========================================

class KnockChannelSelect(discord.ui.Select):
    def __init__(self, cog, channels_data):
        options = []
        for chan, owner_id in channels_data[:25]:
            options.append(discord.SelectOption(
                label=f"⌬  {chan.name[:50]}",
                value=str(chan.id),
                description=f"Host ID: {owner_id}"
            ))
        super().__init__(
            placeholder="Select a room to knock on...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        chan_id = int(self.values[0])
        target_channel = interaction.guild.get_channel(chan_id)
        if not target_channel:
            return await interaction.response.send_message("✕ That channel no longer exists.", ephemeral=True)

        owner_id = await self.cog.get_channel_owner(chan_id)
        if not owner_id:
            return await interaction.response.send_message("✕ Host not found for this channel.", ephemeral=True)

        if not self.cog.knock_settings.get(chan_id, True):
            return await interaction.response.send_message("✕ This room has Knock Mode set to **Do Not Disturb**.", ephemeral=True)

        doorbell_view = KnockResponseView(self.cog, target_channel, interaction.user, owner_id)
        await target_channel.send(content=f"<@{owner_id}>", view=doorbell_view)
        await interaction.response.send_message(
            f"⌬ **Doorbell Ring Sent!**\nKnocked on **{target_channel.name}** for host <@{owner_id}>. Waiting for them to allow entry...",
            ephemeral=True
        )


class KnockChannelSelectView(discord.ui.View):
    def __init__(self, cog, channels_data):
        super().__init__(timeout=60)
        self.add_item(KnockChannelSelect(cog, channels_data))


class HostKnockSettingsView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel = channel

        btn_enable = discord.ui.Button(label="✦  Enable Knock", style=discord.ButtonStyle.secondary, custom_id="vc_hknock_enable")
        btn_disable = discord.ui.Button(label="✕  Mute (Do Not Disturb)", style=discord.ButtonStyle.secondary, custom_id="vc_hknock_disable")

        btn_enable.callback = self.enable_callback
        btn_disable.callback = self.disable_callback

        self.add_item(btn_enable)
        self.add_item(btn_disable)

    async def enable_callback(self, interaction: discord.Interaction):
        self.cog.knock_settings[self.channel.id] = True
        await interaction.response.send_message(
            "⌬ **Knock Mode: ENABLED**\nMembers who cannot join can now knock to request entry.",
            ephemeral=True
        )

    async def disable_callback(self, interaction: discord.Interaction):
        self.cog.knock_settings[self.channel.id] = False
        await interaction.response.send_message(
            "✕ **Knock Mode: MUTED (Do Not Disturb)**\nKnock requests are silenced for this room.",
            ephemeral=True
        )


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

        btn_allow = discord.ui.Button(label="✦  Allow Entry", style=discord.ButtonStyle.success, custom_id="vc_knock_allow")
        btn_decline = discord.ui.Button(label="✕  Decline", style=discord.ButtonStyle.danger, custom_id="vc_knock_decline")

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
# Discord UI Components v2 - Advanced Controls (Bitrate, Region, Activities, Permissions, Presets)
# ==========================================

RTC_REGIONS_MAP = {
    "Automatic": None,
    "Singapore": "singapore",
    "India": "india",
    "Hong Kong": "hongkong",
    "Rotterdam": "rotterdam",
    "US-Central": "us-central",
    "US-East": "us-east",
    "US-West": "us-west",
    "Sydney": "sydney",
    "Japan": "japan",
    "Brazil": "brazil"
}

class RegionSelect(discord.ui.Select):
    def __init__(self, cog, channel: discord.VoiceChannel):
        options = [
            discord.SelectOption(label="Automatic (Default)", value="auto", description="Discord automatically selects optimal region"),
            discord.SelectOption(label="Singapore", value="singapore", description="Lowest ping for South & Southeast Asia"),
            discord.SelectOption(label="India", value="india", description="Optimized for Indian subcontinent"),
            discord.SelectOption(label="Hong Kong", value="hongkong", description="East Asia low-latency"),
            discord.SelectOption(label="Rotterdam", value="rotterdam", description="Europe primary datacenter"),
            discord.SelectOption(label="US-Central", value="us-central", description="North America central"),
            discord.SelectOption(label="US-East", value="us-east", description="North America east coast"),
            discord.SelectOption(label="US-West", value="us-west", description="North America west coast"),
            discord.SelectOption(label="Sydney", value="sydney", description="Oceania & Australia"),
            discord.SelectOption(label="Japan", value="japan", description="Tokyo datacenter")
        ]
        super().__init__(placeholder="Select Voice RTC Server Region...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the room host can change the voice region.", ephemeral=True)

        selected = self.values[0]
        region_val = None if selected == "auto" else selected
        region_label = "Automatic" if region_val is None else selected.capitalize()

        try:
            await self.channel.edit(rtc_region=region_val)
            await interaction.response.send_message(f"🌐 Voice server region set to **{region_label}**!", ephemeral=True)
            await self.cog.log_voice_event(
                interaction.guild,
                title="🌐 Room Region Changed",
                description=f"Host {interaction.user.mention} switched RTC region of `{self.channel.name}` to **{region_label}**.",
                color=0x5865F2
            )
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to update region: {e}", ephemeral=True)


class RegionSelectView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(RegionSelect(cog, channel))


DISCORD_ACTIVITIES = {
    "YouTube Watch Together": 880218394199220334,
    "Chess in the Park": 832012774040141894,
    "Checkers in the Park": 832013003968348200,
    "Poker Night": 755827207812677713,
    "Betrayal.io": 773336526917861400,
    "Gartic Phone": 1007373802972749934,
    "SpellCast": 852509694341283871,
    "Letter League": 879863686565621790,
    "Sketch Heads": 902271654783242291,
    "Putt Party": 945737671223947305,
    "Bobble League": 947957217959759964,
    "Rythm": 235088799074484224,
}

class ActivitySelect(discord.ui.Select):
    def __init__(self, channel: discord.VoiceChannel):
        options = [
            discord.SelectOption(label=name, value=name, description=f"Launch {name} in this room")
            for name in DISCORD_ACTIVITIES.keys()
        ]
        super().__init__(placeholder="Select a Discord Activity / Game to launch...", min_values=1, max_values=1, options=options)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        game_name = self.values[0]
        app_id = DISCORD_ACTIVITIES.get(game_name)
        if not app_id:
            return await interaction.response.send_message("✕ Unknown activity.", ephemeral=True)

        try:
            invite = await self.channel.create_invite(
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=app_id,
                max_age=86400,
                max_uses=0,
                unique=False,
                reason=f"Activity launched by {interaction.user.name}"
            )
            btn = discord.ui.Button(label=f"🎮 Join {game_name}", url=invite.url, style=discord.ButtonStyle.link)
            v = discord.ui.View()
            v.add_item(btn)
            await interaction.response.send_message(
                f"### 🎮 {game_name}\nClick below to start playing **{game_name}** in {self.channel.mention}:",
                view=v,
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"✕ Could not launch activity: {e}", ephemeral=True)


class ActivitySelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(ActivitySelect(channel))


class PermissionsControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel = channel

        btn_sb_allow = discord.ui.Button(label="🔊 Allow Soundboard", style=discord.ButtonStyle.secondary, custom_id="vc_perm_sb_allow")
        btn_sb_mute = discord.ui.Button(label="🔇 Mute Soundboard", style=discord.ButtonStyle.secondary, custom_id="vc_perm_sb_mute")
        btn_st_allow = discord.ui.Button(label="📺 Allow Screen Share", style=discord.ButtonStyle.secondary, custom_id="vc_perm_st_allow")
        btn_st_mute = discord.ui.Button(label="🚫 Block Screen Share", style=discord.ButtonStyle.secondary, custom_id="vc_perm_st_mute")

        btn_sb_allow.callback = self.sb_allow
        btn_sb_mute.callback = self.sb_mute
        btn_st_allow.callback = self.st_allow
        btn_st_mute.callback = self.st_mute

        self.add_item(btn_sb_allow)
        self.add_item(btn_sb_mute)
        self.add_item(btn_st_allow)
        self.add_item(btn_st_mute)

    async def sb_allow(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the host can configure room permissions.", ephemeral=True)
        await self.channel.set_permissions(interaction.guild.default_role, use_soundboard=True, use_external_sounds=True)
        await interaction.response.send_message("🔊 Soundboard is now **ENABLED** for members in this room.", ephemeral=True)

    async def sb_mute(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the host can configure room permissions.", ephemeral=True)
        await self.channel.set_permissions(interaction.guild.default_role, use_soundboard=False, use_external_sounds=False)
        await interaction.response.send_message("🔇 Soundboard is now **MUTED** for members in this room.", ephemeral=True)

    async def st_allow(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the host can configure room permissions.", ephemeral=True)
        await self.channel.set_permissions(interaction.guild.default_role, stream=True)
        await interaction.response.send_message("📺 Screen sharing & video is now **ENABLED** in this room.", ephemeral=True)

    async def st_mute(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the host can configure room permissions.", ephemeral=True)
        await self.channel.set_permissions(interaction.guild.default_role, stream=False)
        await interaction.response.send_message("🚫 Screen sharing & video is now **MUTED** in this room.", ephemeral=True)


class PresetManageView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel, user_presets: list):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel = channel
        self.user_presets = user_presets

        btn_save = discord.ui.Button(label="💾 Save Current Settings", style=discord.ButtonStyle.primary, custom_id="vc_preset_save_btn")
        btn_save.callback = self.save_callback
        self.add_item(btn_save)

        if user_presets:
            options = [
                discord.SelectOption(
                    label=p[0],
                    value=p[0],
                    description=f"Name: {p[1][:25]} | Limit: {p[2]} | {p[3] or 64}k"
                )
                for p in user_presets[:25]
            ]
            sel = discord.ui.Select(placeholder="Select a preset to load immediately...", options=options, custom_id="vc_preset_load_sel")
            sel.callback = self.load_callback
            self.add_item(sel)

    async def save_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PresetSaveModal(self.cog, self.channel))

    async def load_callback(self, interaction: discord.Interaction):
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("✕ Only the host can apply presets to this room.", ephemeral=True)

        preset_name = interaction.data["values"][0]
        preset = await self.cog.get_user_preset(interaction.user.id, preset_name)
        if not preset:
            return await interaction.response.send_message("✕ Preset not found.", ephemeral=True)

        name = preset[1]
        limit = preset[2]
        bitrate = preset[3]

        edit_kwargs = {}
        if name: edit_kwargs["name"] = name
        if limit is not None: edit_kwargs["user_limit"] = limit
        if bitrate: edit_kwargs["bitrate"] = min(bitrate * 1000, interaction.guild.bitrate_limit)

        try:
            await self.channel.edit(**edit_kwargs)
            await self.cog.save_user_setting(interaction.user.id, channel_name=name, channel_limit=limit, bitrate=bitrate)
            await interaction.response.send_message(f"📂 Applied preset **{preset_name}** to your room!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to apply preset: {e}", ephemeral=True)


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
        await self.cog.log_voice_event(
            interaction.guild,
            title="♔ Ownership Transferred",
            description=f"Host {interaction.user.mention} transferred room `{self.channel.name}` to {member.mention}.",
            color=0xFEE75C
        )


class TransferOwnerView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(TransferOwnerSelect(cog, channel))


class TrustUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to grant VIP Trust...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        await self.channel.set_permissions(member, connect=True, view_channel=True, speak=True, stream=True)
        await interaction.response.send_message(
            f"👤+ **{member.mention}** is now a **Trusted Member**! They can bypass channel lock and join freely.",
            ephemeral=True
        )


class TrustSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(TrustUserSelect(channel))


class UntrustUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to remove Trust...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        await self.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(
            f"👤- Removed trusted status from **{member.mention}**.",
            ephemeral=True
        )


class UntrustSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(UntrustUserSelect(channel))


class BlockUserSelect(discord.ui.UserSelect):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to block & ban...", min_values=1, max_values=1)
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        if member in self.channel.members:
            try:
                await member.move_to(None)
            except Exception:
                pass

        await self.channel.set_permissions(member, connect=False, view_channel=False)
        await interaction.response.send_message(
            f"🚫 **{member.mention}** has been **blocked** and banished from this room.",
            ephemeral=True
        )
        await self.cog.log_voice_event(
            interaction.guild,
            title="🚫 Member Blocked",
            description=f"Host {interaction.user.mention} blocked and disconnected {member.mention} from `{self.channel.name}`.",
            color=0xED4245
        )


class BlockSelectView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(BlockUserSelect(cog, channel))


class UnblockUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to unblock...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        await self.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(
            f"✓ **{member.mention}** has been **unblocked**.",
            ephemeral=True
        )


class UnblockSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(UnblockUserSelect(channel))


class KickUserSelect(discord.ui.UserSelect):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to disconnect (kick)...", min_values=1, max_values=1)
        self.cog = cog
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        if member not in self.channel.members:
            return await interaction.response.send_message("✕ That member is not currently inside this room!", ephemeral=True)

        try:
            await member.move_to(None)
            await interaction.response.send_message(f"⎋ Kicked **{member.mention}** from the voice channel.", ephemeral=True)
            await self.cog.log_voice_event(
                interaction.guild,
                title="⎋ Member Kicked",
                description=f"Host {interaction.user.mention} kicked {member.mention} from `{self.channel.name}`.",
                color=0xED4245
            )
        except Exception as e:
            await interaction.response.send_message(f"✕ Could not kick member: {e}", ephemeral=True)


class KickSelectView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(KickUserSelect(cog, channel))


class InviteUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a friend to invite...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        try:
            invite = await self.channel.create_invite(max_age=3600, max_uses=1, unique=True, reason=f"Invited by {interaction.user.name}")
            await self.channel.set_permissions(member, connect=True, view_channel=True)

            dm_sent = True
            try:
                await member.send(
                    f"✉ **{interaction.user.display_name}** invited you to join their voice room **{self.channel.name}** in **{interaction.guild.name}**!\n🔗 {invite.url}"
                )
            except Exception:
                dm_sent = False

            if dm_sent:
                await interaction.response.send_message(f"✉ Direct invitation sent to **{member.mention}**!", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"✉ Invited **{member.mention}** (their DMs are closed). Share this direct link with them: {invite.url}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"✕ Failed to create invite: {e}", ephemeral=True)


class InviteSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(InviteUserSelect(channel))


# ==========================================
# Discord UI Components v2 - Voice Room LayoutView
# ==========================================

APP_EMOJIS = {
    "activity": discord.PartialEmoji(name="vc_activity", id=1555103014132383794),
    "bitrate": discord.PartialEmoji(name="vc_bitrate", id=1555101565138894872),
    "block": discord.PartialEmoji(name="vc_block", id=1554955933187317763),
    "claim": discord.PartialEmoji(name="vc_claim", id=1554955937083564042),
    "delete": discord.PartialEmoji(name="vc_delete", id=1554955940325892096),
    "ghost": discord.PartialEmoji(name="vc_ghost", id=1554955943618420839),
    "host": discord.PartialEmoji(name="vc_host", id=1554955947150024814),
    "hubs": discord.PartialEmoji(name="vc_hubs", id=1554955950379761704),
    "info": discord.PartialEmoji(name="vc_info", id=1554955954100117587),
    "interface": discord.PartialEmoji(name="vc_interface", id=1554955957447032874),
    "invite": discord.PartialEmoji(name="vc_invite", id=1554955961410519090),
    "kick": discord.PartialEmoji(name="vc_kick", id=1554955964409712795),
    "knock": discord.PartialEmoji(name="vc_knock", id=1554955967840526349),
    "leaderboard": discord.PartialEmoji(name="vc_leaderboard", id=1554955971405815888),
    "limit": discord.PartialEmoji(name="vc_limit", id=1554955974899667015),
    "lock": discord.PartialEmoji(name="vc_lock", id=1554955978284466297),
    "maintenance": discord.PartialEmoji(name="vc_maintenance", id=1554955991714365461),
    "members": discord.PartialEmoji(name="vc_members", id=1554955995011354655),
    "mute": discord.PartialEmoji(name="vc_mute", id=1554955999083888741),
    "overview": discord.PartialEmoji(name="vc_overview", id=1554956002544062474),
    "permanent": discord.PartialEmoji(name="vc_permanent", id=1554956006226792628),
    "privacy": discord.PartialEmoji(name="vc_privacy", id=1554956009301086312),
    "region": discord.PartialEmoji(name="vc_region", id=1554956013554114583),
    "rename": discord.PartialEmoji(name="vc_rename", id=1554956017433968670),
    "reveal": discord.PartialEmoji(name="vc_reveal", id=1554956020864778284),
    "settings": discord.PartialEmoji(name="vc_settings", id=1554956024342126602),
    "setup": discord.PartialEmoji(name="vc_setup", id=1554956027366215812),
    "soundboard": discord.PartialEmoji(name="vc_soundboard", id=1554956031073722428),
    "transfer": discord.PartialEmoji(name="vc_transfer", id=1554956034437816413),
    "trust": discord.PartialEmoji(name="vc_trust", id=1554956038174674946),
    "unblock": discord.PartialEmoji(name="vc_unblock", id=1554956041974845540),
    "unlock": discord.PartialEmoji(name="vc_unlock", id=1554956052775305416),
    "unmute": discord.PartialEmoji(name="vc_unmute", id=1554956056667627640),
    "untrust": discord.PartialEmoji(name="vc_untrust", id=1554956060387704843),
    "video": discord.PartialEmoji(name="vc_video", id=1554956063994945618),
}


# ==========================================
# Streamlined Minimal Voice Controls Views & Dropdowns
# ==========================================

class PrivacySelect(discord.ui.Select):
    def __init__(self, cog, channel: discord.VoiceChannel):
        self.cog = cog
        self.channel = channel
        options = [
            discord.SelectOption(label="Ghost Channel (Invisible)", emoji=APP_EMOJIS["ghost"], value="ghost", description="Hide room from server sidebar"),
            discord.SelectOption(label="Reveal Channel (Visible)", emoji=APP_EMOJIS["reveal"], value="reveal", description="Make room visible on sidebar"),
            discord.SelectOption(label="Open Voice Chat", emoji="💬", value="open_chat", description="Allow everyone to send text messages"),
            discord.SelectOption(label="Close Voice Chat", emoji="🔇", value="close_chat", description="Only host can send text messages"),
        ]
        super().__init__(
            placeholder="Select an advanced privacy action...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_privacy_select"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        guild = interaction.guild
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can change privacy settings.", ephemeral=True)

        if val == "lock":
            await self.channel.set_permissions(guild.default_role, connect=False)
            await interaction.response.send_message("🔒 **Channel locked!** Unauthorized members cannot connect (they can still knock).", ephemeral=True)
            await self.cog.log_voice_event(guild, "🔒 Room Locked", f"Host {interaction.user.mention} locked `{self.channel.name}`.", 0xED4245)

        elif val == "unlock":
            await self.channel.set_permissions(guild.default_role, connect=True)
            await interaction.response.send_message("🔓 **Channel unlocked!** Public connection allowed.", ephemeral=True)
            await self.cog.log_voice_event(guild, "🔓 Room Unlocked", f"Host {interaction.user.mention} unlocked `{self.channel.name}`.", 0x57F287)

        elif val == "ghost":
            await self.channel.set_permissions(guild.default_role, view_channel=False, connect=False)
            await interaction.response.send_message("👻 **Ghost Mode Activated!** Room is now hidden from @everyone on the sidebar.", ephemeral=True)
            await self.cog.log_voice_event(guild, "👻 Room Ghosted", f"Host {interaction.user.mention} hid `{self.channel.name}` from sidebar.", 0x747F8D)

        elif val == "reveal":
            await self.channel.set_permissions(guild.default_role, view_channel=True)
            await interaction.response.send_message("👁️ **Channel revealed!** Visible on the sidebar again.", ephemeral=True)
            await self.cog.log_voice_event(guild, "👁️ Room Revealed", f"Host {interaction.user.mention} revealed `{self.channel.name}`.", 0x5865F2)

        elif val == "open_chat":
            await self.channel.set_permissions(guild.default_role, send_messages=True, read_messages=True)
            await interaction.response.send_message("💬 **Voice Text Chat Opened!** Everyone in the room can now send text messages.", ephemeral=True)
            await self.cog.log_voice_event(guild, "💬 Voice Chat Opened", f"Host {interaction.user.mention} opened text chat in `{self.channel.name}`.", 0x5865F2)

        elif val == "close_chat":
            await self.channel.set_permissions(guild.default_role, send_messages=False)
            await interaction.response.send_message("🔇 **Voice Text Chat Closed!** Text messages in this channel are restricted to the host.", ephemeral=True)
            await self.cog.log_voice_event(guild, "🔇 Voice Chat Closed", f"Host {interaction.user.mention} closed text chat in `{self.channel.name}`.", 0xED4245)

        elif val == "knock":
            status = "ENABLED (Doorbell Active)" if self.cog.knock_settings.get(self.channel.id, True) else "MUTED (Do Not Disturb)"
            view = HostKnockSettingsView(self.cog, self.channel)
            await interaction.response.send_message(
                f"### 🚪 Doorbell / Knock Settings\n"
                f"• **Room:** `{self.channel.name}`\n"
                f"• **Current Status:** `{status}`\n\n"
                f"When enabled, friends outside can knock to request entry into your room.",
                view=view,
                ephemeral=True
            )


class PrivacyControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.add_item(PrivacySelect(cog, channel))


class SettingsSelect(discord.ui.Select):
    def __init__(self, cog, channel: discord.VoiceChannel):
        self.cog = cog
        self.channel = channel
        options = [
            discord.SelectOption(label="Rename Channel", emoji=APP_EMOJIS["rename"], value="rename", description="Change room name via popup modal"),
            discord.SelectOption(label="Member Limit", emoji=APP_EMOJIS["limit"], value="limit", description="Set user capacity (0 = Unlimited)"),
            discord.SelectOption(label="Audio Bitrate", emoji=APP_EMOJIS["bitrate"], value="bitrate", description="Adjust audio quality in kbps"),
            discord.SelectOption(label="Soundboard & Video", emoji=APP_EMOJIS["privacy"], value="permissions", description="Toggle screen share & soundboard permissions"),
            discord.SelectOption(label="Room Presets", emoji=APP_EMOJIS["settings"], value="preset", description="Save or load customized room profiles"),
            discord.SelectOption(label="Discord Activities", emoji=APP_EMOJIS["activity"], value="activity", description="Launch Watch Together & Party Games"),
        ]
        super().__init__(
            placeholder="Select a setting to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_settings_select"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if val in ["rename", "limit", "bitrate", "permissions", "preset"]:
            if owner_id and interaction.user.id != owner_id:
                return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can modify room settings.", ephemeral=True)

        if val == "rename":
            if await self.cog.is_channel_locked_name(self.channel.id):
                return await interaction.response.send_message(
                    f"✕ This voice room has a locked name (`{self.channel.name}`) configured by server administration and cannot be renamed.",
                    ephemeral=True
                )
            await interaction.response.send_modal(ChannelRenameModal(self.cog, self.channel))
        elif val == "limit":
            await interaction.response.send_modal(ChannelLimitModal(self.cog, self.channel))
        elif val == "bitrate":
            await interaction.response.send_modal(ChannelBitrateModal(self.cog, self.channel))
        elif val == "permissions":
            view = PermissionsControlView(self.cog, self.channel)
            await interaction.response.send_message("🛡️ Configure Soundboard and Video / Screen sharing permissions:", view=view, ephemeral=True)
        elif val == "preset":
            user_presets = await self.cog.get_user_presets(interaction.user.id)
            view = PresetManageView(self.cog, self.channel, user_presets)
            await interaction.response.send_message(
                f"### 💾 Voice Room Presets • `{self.channel.name}`\nSave your current channel settings or load a previously saved configuration:",
                view=view,
                ephemeral=True
            )
        elif val == "activity":
            view = ActivitySelectView(self.channel)
            await interaction.response.send_message("🎮 Select a Discord Game or Watch Together activity to launch:", view=view, ephemeral=True)


class SettingsControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.add_item(SettingsSelect(cog, channel))


class MembersActionSelect(discord.ui.Select):
    def __init__(self, cog, channel: discord.VoiceChannel):
        self.cog = cog
        self.channel = channel
        options = [
            discord.SelectOption(label="Trust Member", emoji=APP_EMOJIS["trust"], value="trust", description="Grant VIP bypass access to a member"),
            discord.SelectOption(label="Untrust Member", emoji=APP_EMOJIS["untrust"], value="untrust", description="Remove trusted bypass status from a member"),
            discord.SelectOption(label="Invite Member", emoji=APP_EMOJIS["invite"], value="invite", description="Send direct invite link to a member"),
            discord.SelectOption(label="Kick Member", emoji=APP_EMOJIS["kick"], value="kick", description="Disconnect member from this room"),
            discord.SelectOption(label="Block Member", emoji=APP_EMOJIS["block"], value="block", description="Ban and disconnect member from this room"),
            discord.SelectOption(label="Unblock Member", emoji=APP_EMOJIS["unblock"], value="unblock", description="Remove ban from a member"),
        ]
        super().__init__(
            placeholder="Select a member action...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_members_select"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        owner_id = await self.cog.get_channel_owner(self.channel.id)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can manage members.", ephemeral=True)

        if val == "trust":
            await interaction.response.send_message("Select a member to grant VIP Trust (bypass lock & ghost):", view=TrustSelectView(self.channel), ephemeral=True)
        elif val == "untrust":
            await interaction.response.send_message("Select a member to remove Trust status from:", view=UntrustSelectView(self.channel), ephemeral=True)
        elif val == "invite":
            await interaction.response.send_message("Select a member to invite to this room:", view=InviteSelectView(self.channel), ephemeral=True)
        elif val == "kick":
            await interaction.response.send_message("Select a member inside this room to kick:", view=KickSelectView(self.cog, self.channel), ephemeral=True)
        elif val == "block":
            await interaction.response.send_message("Select a member to block & ban from this room:", view=BlockSelectView(self.cog, self.channel), ephemeral=True)
        elif val == "unblock":
            await interaction.response.send_message("Select a member to unblock:", view=UnblockSelectView(self.channel), ephemeral=True)


class MembersControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.add_item(MembersActionSelect(cog, channel))


class HostActionSelect(discord.ui.Select):
    def __init__(self, cog, channel: discord.VoiceChannel):
        self.cog = cog
        self.channel = channel
        options = [
            discord.SelectOption(label="Claim Ownership", emoji=APP_EMOJIS["claim"], value="claim", description="Claim host status if current host left room"),
            discord.SelectOption(label="Transfer Ownership", emoji=APP_EMOJIS["transfer"], value="transfer", description="Transfer room host to another member"),
            discord.SelectOption(label="Room Info & Stats", emoji=APP_EMOJIS["info"], value="info", description="View host info, bitrate & stats"),
        ]
        super().__init__(
            placeholder="Select host action...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_host_select"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        user = interaction.user
        owner_id = await self.cog.get_channel_owner(self.channel.id)

        if val == "claim":
            voice_state = user.voice
            if not voice_state or not voice_state.channel or voice_state.channel.id != self.channel.id:
                return await interaction.response.send_message("✕ You must be connected inside this voice room to claim it!", ephemeral=True)

            if user.id == owner_id:
                return await interaction.response.send_message("ℹ You are already the owner of this room!", ephemeral=True)

            owner_member = self.channel.guild.get_member(owner_id) if owner_id else None
            if owner_member and owner_member in self.channel.members:
                return await interaction.response.send_message(f"✕ Cannot claim: the owner {owner_member.mention} is still in the room!", ephemeral=True)

            await self.cog.set_channel_owner(self.channel.id, user.id)
            await self.channel.set_permissions(user, connect=True, view_channel=True, read_messages=True, manage_channels=True)
            await interaction.response.send_message(f"👑 **Congratulations!** You are now the host of `{self.channel.name}`.", ephemeral=False)
            await self.cog.log_voice_event(
                interaction.guild,
                title="👑 Channel Claimed",
                description=f"{user.mention} claimed ownership of `{self.channel.name}` (former host: <@{owner_id}>).",
                color=0xFEE75C
            )

        elif val == "transfer":
            if owner_id and user.id != owner_id:
                return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can transfer ownership.", ephemeral=True)
            await interaction.response.send_message("Select a room member to pass channel ownership to:", view=TransferOwnerView(self.cog, self.channel), ephemeral=True)

        elif val == "info":
            owner = interaction.guild.get_member(owner_id) if owner_id else None
            owner_name = owner.mention if owner else (f"<@{owner_id}>" if owner_id else "None")
            limit_text = "Unlimited" if self.channel.user_limit == 0 else f"{len(self.channel.members)}/{self.channel.user_limit}"
            knock_mode = "Enabled" if self.cog.knock_settings.get(self.channel.id, True) else "Muted"
            region_str = self.channel.rtc_region.capitalize() if self.channel.rtc_region else "Automatic"
            is_perm = await self.cog.is_channel_permanent(self.channel.id)
            room_type = "Permanent (Never auto-deletes)" if is_perm else "Temporary (Auto-deletes when empty)"

            info_view = discord.ui.LayoutView()
            c = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ℹ Room Overview\n"
                    f"• **Room:** `{self.channel.name}`\n"
                    f"• **Type:** `{room_type}`\n"
                    f"• **Host:** {owner_name}\n"
                    f"• **Occupancy:** `{limit_text}`\n"
                    f"• **Bitrate:** `{self.channel.bitrate // 1000} kbps`\n"
                    f"• **Region:** `{region_str}`\n"
                    f"• **Doorbell (Knock):** `{knock_mode}`"
                ),
                accent_color=None
            )
            info_view.add_item(c)
            await interaction.response.send_message(view=info_view, ephemeral=True)


class HostControlView(discord.ui.View):
    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.add_item(HostActionSelect(cog, channel))


class DeleteChannelSelect(discord.ui.Select):
    def __init__(self, cog, channels: typing.List[discord.VoiceChannel]):
        self.cog = cog
        self.channel_map = {str(c.id): c for c in channels}
        options = []
        for c in channels:
            desc = f"Members: {len(c.members)} | Capacity: {'Unlimited' if c.user_limit == 0 else c.user_limit}"
            options.append(
                discord.SelectOption(
                    label=c.name[:100],
                    value=str(c.id),
                    description=desc[:100],
                    emoji="🗑️"
                )
            )
        super().__init__(
            placeholder="Select which voice room you wish to delete...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_delete_select"
        )

    async def callback(self, interaction: discord.Interaction):
        chan_id = int(self.values[0])
        chan = self.channel_map.get(str(chan_id)) or interaction.guild.get_channel(chan_id)
        if not chan:
            return await interaction.response.send_message("✕ Channel not found or already deleted.", ephemeral=True)

        chan_name = chan.name
        await self.cog.delete_temp_channel_record(chan.id)
        self.cog.knock_settings.pop(chan.id, None)
        self.cog.afk_tracker.pop(chan.id, None)
        try:
            await chan.delete(reason=f"Deleted by room owner {interaction.user.name}")
        except Exception:
            pass
        await interaction.response.send_message(f"🗑 **Voice room `{chan_name}` has been deleted successfully!**", ephemeral=True)
        await self.cog.log_voice_event(
            interaction.guild,
            title="🗑 Room Deleted",
            description=f"Host {interaction.user.mention} deleted room `{chan_name}`.",
            color=0xED4245
        )


class DeleteChannelSelectView(discord.ui.View):
    def __init__(self, cog, channels: typing.List[discord.VoiceChannel]):
        super().__init__(timeout=60)
        self.add_item(DeleteChannelSelect(cog, channels))


class RoomSelect(discord.ui.Select):
    def __init__(self, cog, channels: typing.List[discord.VoiceChannel], action_type: str):
        self.cog = cog
        self.action_type = action_type
        self.channel_map = {str(c.id): c for c in channels}
        options = []
        for c in channels:
            desc = f"Members: {len(c.members)} | Capacity: {'Unlimited' if c.user_limit == 0 else c.user_limit}"
            options.append(
                discord.SelectOption(
                    label=c.name[:100],
                    value=str(c.id),
                    description=desc[:100],
                    emoji="🎙️"
                )
            )
        super().__init__(
            placeholder="Select room to manage...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"vc_room_select_{action_type}"
        )

    async def callback(self, interaction: discord.Interaction):
        chan_id = int(self.values[0])
        channel = self.channel_map.get(str(chan_id)) or interaction.guild.get_channel(chan_id)
        if not channel:
            return await interaction.response.send_message("✕ Channel not found.", ephemeral=True)

        if self.action_type == "privacy":
            view = PrivacyControlView(self.cog, channel)
            await interaction.response.send_message(
                f"### 🔒 Privacy Controls • `{channel.name}`\nSelect a privacy action from the dropdown below:",
                view=view,
                ephemeral=True
            )
        elif self.action_type == "settings":
            view = SettingsControlView(self.cog, channel)
            await interaction.response.send_message(
                f"### ⚙️ Channel Settings • `{channel.name}`\nSelect a setting to modify from the dropdown below:",
                view=view,
                ephemeral=True
            )
        elif self.action_type == "region":
            view = RegionSelectView(self.cog, channel)
            await interaction.response.send_message(
                f"### 🌐 Voice Region Selector • `{channel.name}`\nSelect an optimal RTC voice datacenter:",
                view=view,
                ephemeral=True
            )
        elif self.action_type == "members":
            view = MembersControlView(self.cog, channel)
            await interaction.response.send_message(
                f"### 👥 Member Management • `{channel.name}`\nSelect an action from the dropdown below:",
                view=view,
                ephemeral=True
            )
        elif self.action_type == "host":
            view = HostControlView(self.cog, channel)
            await interaction.response.send_message(
                f"### 👑 Host & Ownership • `{channel.name}`\nSelect an action from the dropdown below:",
                view=view,
                ephemeral=True
            )


class RoomSelectForActionView(discord.ui.View):
    def __init__(self, cog, channels: typing.List[discord.VoiceChannel], action_type: str):
        super().__init__(timeout=60)
        self.add_item(RoomSelect(cog, channels, action_type))


class VoiceControlSelect(discord.ui.Select):
    def __init__(self, cog):
        options = [
            discord.SelectOption(label="Lock Channel", emoji=APP_EMOJIS["lock"], value="lock", description="Restrict connections to your room"),
            discord.SelectOption(label="Unlock Channel", emoji=APP_EMOJIS["unlock"], value="unlock", description="Open connection to everyone"),
            discord.SelectOption(label="Ghost Channel", emoji=APP_EMOJIS["ghost"], value="ghost", description="Hide room from server sidebar"),
            discord.SelectOption(label="Reveal Channel", emoji=APP_EMOJIS["reveal"], value="reveal", description="Make room visible on sidebar"),
            discord.SelectOption(label="Rename Channel", emoji=APP_EMOJIS["rename"], value="rename", description="Change channel name via popup modal"),
            discord.SelectOption(label="Set Member Limit", emoji=APP_EMOJIS["limit"], value="limit", description="Set user capacity limit via modal"),
            discord.SelectOption(label="Audio Bitrate", emoji=APP_EMOJIS["bitrate"], value="bitrate", description="Adjust audio quality in kbps"),
            discord.SelectOption(label="Voice Region", emoji=APP_EMOJIS["region"], value="region", description="Switch RTC datacenter for lower ping"),
            discord.SelectOption(label="Discord Activities", emoji=APP_EMOJIS["activity"], value="activity", description="Launch Watch Together & Games"),
            discord.SelectOption(label="Soundboard & Video", emoji=APP_EMOJIS["privacy"], value="permissions", description="Toggle soundboard and screen share"),
            discord.SelectOption(label="Room Presets", emoji=APP_EMOJIS["settings"], value="preset", description="Save or load customized room profiles"),
            discord.SelectOption(label="Trust Member", emoji=APP_EMOJIS["trust"], value="trust", description="Grant bypass access to a member"),
            discord.SelectOption(label="Untrust Member", emoji=APP_EMOJIS["untrust"], value="untrust", description="Remove trusted status from a member"),
            discord.SelectOption(label="Invite Member", emoji=APP_EMOJIS["invite"], value="invite", description="Send direct invite link to a member"),
            discord.SelectOption(label="Kick Member", emoji=APP_EMOJIS["kick"], value="kick", description="Disconnect member from your room"),
            discord.SelectOption(label="Block Member", emoji=APP_EMOJIS["block"], value="block", description="Ban and disconnect member from room"),
            discord.SelectOption(label="Unblock Member", emoji=APP_EMOJIS["unblock"], value="unblock", description="Unban member from room"),
            discord.SelectOption(label="Waiting Room (Knock)", emoji=APP_EMOJIS["knock"], value="knock", description="Allow or disable doorbell requests"),
            discord.SelectOption(label="Claim Ownership", emoji=APP_EMOJIS["claim"], value="claim", description="Claim channel if host left the room"),
            discord.SelectOption(label="Transfer Ownership", emoji=APP_EMOJIS["transfer"], value="transfer", description="Transfer host to another member"),
            discord.SelectOption(label="Delete Channel", emoji=APP_EMOJIS["delete"], value="delete", description="Instantly delete this voice room"),
            discord.SelectOption(label="Channel Info", emoji=APP_EMOJIS["info"], value="info", description="View current room host, settings & stats"),
        ]
        super().__init__(
            placeholder="Choose an action to control your room...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vc_control_dropdown"
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if hasattr(self.view, "dispatch_action"):
            await self.view.dispatch_action(interaction, val)


class VoiceControlLayoutView(discord.ui.LayoutView):
    def __init__(self, cog, member_avatar_url: str = None, member_name: str = None, has_banner: bool = None, banner_url: str = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.member_avatar_url = member_avatar_url
        self.member_name = member_name
        self.banner_url = banner_url
        if has_banner is None:
            has_banner = os.path.exists(BANNER_PATH) if not banner_url else False
        self.has_banner = has_banner

        clean_name = " ".join(member_name.split()) if member_name else None
        title = f"### ✦ VoiceClaw • {clean_name}'s Room" if clean_name else "### ✦ VoiceClaw • Voice Control Panel"
        subtitle = "Click any button below to manage your dynamic voice channel."

        container_children = []

        # 1. MediaGallery Banner FIRST at the very top
        if self.banner_url:
            container_children.append(
                discord.ui.MediaGallery(discord.MediaGalleryItem(self.banner_url))
            )
        elif self.has_banner:
            container_children.append(
                discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://banner.jpg"))
            )

        # 2. Minimal, clean text header
        if member_avatar_url:
            section = discord.ui.Section(
                discord.ui.TextDisplay(f"{title}\n{subtitle}"),
                accessory=discord.ui.Thumbnail(member_avatar_url)
            )
            container_children.append(section)
        else:
            container_children.append(discord.ui.TextDisplay(f"{title}\n{subtitle}"))

        # Row 0: Privacy, Settings, Region, Members, Host (Uniform Square Icons)
        btn_privacy = discord.ui.Button(emoji=APP_EMOJIS["privacy"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_privacy")
        btn_settings = discord.ui.Button(emoji=APP_EMOJIS["settings"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_settings")
        btn_region = discord.ui.Button(emoji=APP_EMOJIS["region"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_region")
        btn_members = discord.ui.Button(emoji=APP_EMOJIS["members"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_members")
        btn_host = discord.ui.Button(emoji=APP_EMOJIS["host"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_host")

        btn_privacy.callback = self.privacy_callback
        btn_settings.callback = self.settings_callback
        btn_region.callback = self.region_callback
        btn_members.callback = self.members_callback
        btn_host.callback = self.host_callback

        row0 = discord.ui.ActionRow(btn_privacy, btn_settings, btn_region, btn_members, btn_host)
        container_children.append(row0)

        # Row 1: Delete, Lock, Unlock, Ghost, Reveal (Uniform Square Icons)
        btn_delete = discord.ui.Button(emoji=APP_EMOJIS["delete"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_delete")
        btn_lock = discord.ui.Button(emoji=APP_EMOJIS["lock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_lock")
        btn_unlock = discord.ui.Button(emoji=APP_EMOJIS["unlock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_unlock")
        btn_ghost = discord.ui.Button(emoji=APP_EMOJIS["ghost"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_ghost")
        btn_reveal = discord.ui.Button(emoji=APP_EMOJIS["reveal"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_reveal")

        btn_delete.callback = self.delete_callback
        btn_lock.callback = self.lock_callback
        btn_unlock.callback = self.unlock_callback
        btn_ghost.callback = self.ghost_callback
        btn_reveal.callback = self.reveal_callback

        row1 = discord.ui.ActionRow(btn_delete, btn_lock, btn_unlock, btn_ghost, btn_reveal)
        container_children.append(row1)

        # Row 2: Knock, Rename, Limit, Trust, Untrust (Uniform Square Icons)
        btn_knock = discord.ui.Button(emoji=APP_EMOJIS["knock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_knock")
        btn_rename = discord.ui.Button(emoji=APP_EMOJIS["rename"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_rename")
        btn_limit = discord.ui.Button(emoji=APP_EMOJIS["limit"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_limit")
        btn_trust = discord.ui.Button(emoji=APP_EMOJIS["trust"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_trust")
        btn_untrust = discord.ui.Button(emoji=APP_EMOJIS["untrust"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_untrust")

        btn_knock.callback = self.knock_toggle_callback
        btn_rename.callback = self.rename_callback
        btn_limit.callback = self.limit_callback
        btn_trust.callback = self.trust_callback
        btn_untrust.callback = self.untrust_callback

        row2 = discord.ui.ActionRow(btn_knock, btn_rename, btn_limit, btn_trust, btn_untrust)
        container_children.append(row2)

        # 3. Unified borderless V2 Container
        container = discord.ui.Container(*container_children, accent_color=None)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        loop_now = asyncio.get_event_loop().time()
        last_time = self.cog.panel_cooldowns.get(interaction.user.id, 0)
        if (loop_now - last_time) < 1.5:
            rem = round(1.5 - (loop_now - last_time), 1)
            await interaction.response.send_message(
                f"⏳ Please slow down! Control panel is cooling down (`{rem}`s).",
                ephemeral=True
            )
            return False
        self.cog.panel_cooldowns[interaction.user.id] = loop_now
        return True

    async def refresh_callback(self, interaction: discord.Interaction):
        try:
            if not await self.cog.is_premium_user_or_guild(interaction.user, interaction.guild):
                return await interaction.response.send_message(
                    "✕ **VoiceClaw Panel Refresh is an exclusive VoiceClaw Premium feature!**\n"
                    "Use `/premium status` to view or unlock premium perks for this server.",
                    ephemeral=True
                )
            banner_url = await self.cog.get_guild_banner_url(interaction.guild.id)
            has_banner = os.path.exists(BANNER_PATH) if not banner_url else False
            new_view = VoiceControlLayoutView(self.cog, has_banner=has_banner, banner_url=banner_url)
            await interaction.response.edit_message(view=new_view)
            await interaction.followup.send("✓ VoiceClaw interface refreshed with latest layout and updates!", ephemeral=True)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"✕ Could not refresh: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"✕ Could not refresh: {e}", ephemeral=True)
            except Exception:
                pass


    async def dispatch_action(self, interaction: discord.Interaction, action: str):
        mapping = {
            "lock": self.lock_callback,
            "unlock": self.unlock_callback,
            "ghost": self.ghost_callback,
            "reveal": self.reveal_callback,
            "knock": self.knock_toggle_callback,
            "rename": self.rename_callback,
            "limit": self.limit_callback,
            "bitrate": self.bitrate_callback,
            "region": self.region_callback,
            "activity": self.activity_callback,
            "permissions": self.permissions_callback,
            "preset": self.preset_callback,
            "trust": self.trust_callback,
            "untrust": self.untrust_callback,
            "invite": self.invite_callback,
            "kick": self.kick_callback,
            "block": self.block_callback,
            "unblock": self.unblock_callback,
            "claim": self.claim_callback,
            "transfer": self.transfer_callback,
            "delete": self.delete_callback,
            "info": self.info_callback,
        }
        handler = mapping.get(action)
        if handler:
            await handler(interaction)

    async def _get_voice_context(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        channel = None
        owner_id = None

        # 1. Resolve voice state from guild member cache
        member = guild.get_member(user.id) if guild else None
        if not member and isinstance(user, discord.Member):
            member = user

        voice_state = member.voice if member else getattr(user, "voice", None)
        if voice_state and voice_state.channel and voice_state.channel.guild.id == guild.id:
            channel = voice_state.channel

        # 2. Resilient voice detection fallback: check voice channel member lists
        if not channel and guild:
            for vc in guild.voice_channels:
                if any(m.id == user.id for m in vc.members):
                    channel = vc
                    break

        if channel:
            owner_id = await self.cog.get_channel_owner(channel.id)
            if not owner_id:
                # User is inside an active voice room; self-heal ownership:
                owner_id = user.id
                await self.cog.register_temp_channel(user.id, channel.id)

        # 3. If user is not currently inside a voice channel, check owned channels in this server
        if not channel or not owner_id:
            owned = await self.cog.get_user_owned_channels(guild, user.id)
            if len(owned) == 1:
                channel = owned[0]
                owner_id = user.id
            elif not channel:
                perm_id = await self.cog.get_user_permanent_channel(guild.id, user.id)
                if perm_id:
                    perm_chan = guild.get_channel(perm_id)
                    if perm_chan and isinstance(perm_chan, discord.VoiceChannel):
                        channel = perm_chan
                        owner_id = user.id

        if not channel:
            await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)
            return None, None

        if not owner_id:
            owner_id = user.id

        return channel, owner_id

    async def _resolve_user_channel_context(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        channel = None
        owner_id = None

        # 1. Resolve voice state from guild member cache
        member = guild.get_member(user.id) if guild else None
        if not member and isinstance(user, discord.Member):
            member = user

        voice_state = member.voice if member else getattr(user, "voice", None)
        if voice_state and voice_state.channel and voice_state.channel.guild.id == guild.id:
            channel = voice_state.channel

        # 2. Resilient voice detection fallback
        if not channel and guild:
            for vc in guild.voice_channels:
                if any(m.id == user.id for m in vc.members):
                    channel = vc
                    break

        if channel:
            o_id = await self.cog.get_channel_owner(channel.id)
            channel = channel
            owner_id = o_id or user.id
            if not o_id:
                await self.cog.register_temp_channel(user.id, channel.id)

        owned = await self.cog.get_user_owned_channels(guild, user.id)

        # If user is in a channel, use it directly (whether host or guest)
        if channel:
            return channel, owner_id, owned

        # If user is outside voice:
        if len(owned) == 1:
            return owned[0], user.id, owned
        elif len(owned) > 1:
            return None, user.id, owned

        return None, None, []

    async def privacy_callback(self, interaction: discord.Interaction):
        channel, owner_id, owned = await self._resolve_user_channel_context(interaction)
        if not channel and len(owned) > 1:
            view = RoomSelectForActionView(self.cog, owned, action_type="privacy")
            return await interaction.response.send_message(
                "### 🔒 Privacy Controls\nYou own multiple voice rooms. Select which room you want to configure:",
                view=view,
                ephemeral=True
            )
        if not channel:
            return await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can manage privacy settings.", ephemeral=True)

        view = PrivacyControlView(self.cog, channel)
        await interaction.response.send_message(
            f"### 🔒 Privacy Controls • `{channel.name}`\nSelect a privacy action from the dropdown below:",
            view=view,
            ephemeral=True
        )

    async def settings_callback(self, interaction: discord.Interaction):
        channel, owner_id, owned = await self._resolve_user_channel_context(interaction)
        if not channel and len(owned) > 1:
            view = RoomSelectForActionView(self.cog, owned, action_type="settings")
            return await interaction.response.send_message(
                "### ⚙️ Channel Settings\nYou own multiple voice rooms. Select which room you want to configure:",
                view=view,
                ephemeral=True
            )
        if not channel:
            return await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can adjust channel settings.", ephemeral=True)

        view = SettingsControlView(self.cog, channel)
        await interaction.response.send_message(
            f"### ⚙️ Channel Settings • `{channel.name}`\nSelect a setting to modify from the dropdown below:",
            view=view,
            ephemeral=True
        )

    async def members_callback(self, interaction: discord.Interaction):
        channel, owner_id, owned = await self._resolve_user_channel_context(interaction)
        if not channel and len(owned) > 1:
            view = RoomSelectForActionView(self.cog, owned, action_type="members")
            return await interaction.response.send_message(
                "### 👥 Member Management\nYou own multiple voice rooms. Select which room you want to manage members for:",
                view=view,
                ephemeral=True
            )
        if not channel:
            return await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the room host (<@{owner_id}>) can manage members.", ephemeral=True)

        view = MembersControlView(self.cog, channel)
        await interaction.response.send_message(
            f"### 👥 Member Management • `{channel.name}`\nSelect an action from the dropdown below:",
            view=view,
            ephemeral=True
        )

    async def host_callback(self, interaction: discord.Interaction):
        channel, owner_id, owned = await self._resolve_user_channel_context(interaction)
        if not channel and len(owned) > 1:
            view = RoomSelectForActionView(self.cog, owned, action_type="host")
            return await interaction.response.send_message(
                "### 👑 Host & Ownership\nYou own multiple voice rooms. Select which room you want to manage:",
                view=view,
                ephemeral=True
            )
        if not channel:
            return await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)

        view = HostControlView(self.cog, channel)
        await interaction.response.send_message(
            f"### 👑 Host & Ownership • `{channel.name}`\nSelect an action from the dropdown below:",
            view=view,
            ephemeral=True
        )

    async def lock_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can lock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("🔒 **Channel locked!** Unauthorized members cannot connect (they can still knock).", ephemeral=True)

    async def unlock_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can unlock this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("🔓 **Channel unlocked!** Public connection allowed.", ephemeral=True)

    async def ghost_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can ghost this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=False, connect=False)
        await interaction.response.send_message("◈ **Ghost Mode Activated!** The room is hidden from @everyone.", ephemeral=True)

    async def reveal_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can reveal this channel.", ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message("◇ **Channel revealed!** Visible on the sidebar again.", ephemeral=True)

    async def knock_toggle_callback(self, interaction: discord.Interaction):
        user = interaction.user
        voice_state = user.voice

        if voice_state and voice_state.channel:
            owner_id = await self.cog.get_channel_owner(voice_state.channel.id)
            if owner_id == user.id:
                status = "ENABLED (Doorbell Active)" if self.cog.knock_settings.get(voice_state.channel.id, True) else "MUTED (Do Not Disturb)"
                view = HostKnockSettingsView(self.cog, voice_state.channel)
                return await interaction.response.send_message(
                    f"### ⌬ Knock Doorbell Settings\n"
                    f"• **Room:** `{voice_state.channel.name}`\n"
                    f"• **Current Status:** `{status}`\n\n"
                    f"When enabled, friends outside can knock to request entry into your room.",
                    view=view,
                    ephemeral=True
                )

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT voiceID, userID FROM voiceChannel") as cursor:
                rows = await cursor.fetchall()

        valid_channels = []
        for voice_id, owner_id in rows:
            chan = interaction.guild.get_channel(voice_id)
            if chan and isinstance(chan, discord.VoiceChannel):
                if not voice_state or voice_state.channel.id != chan.id:
                    valid_channels.append((chan, owner_id))

        if not valid_channels:
            return await interaction.response.send_message("✕ There are no active private rooms to knock on right now.", ephemeral=True)

        view = KnockChannelSelectView(self.cog, valid_channels)
        await interaction.response.send_message(
            "### ⌬ Request to Join (Knock)\nSelect which private voice room you would like to knock on:",
            view=view,
            ephemeral=True
        )

    async def rename_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can rename this channel.", ephemeral=True)
        if await self.cog.is_channel_locked_name(channel.id):
            return await interaction.response.send_message(
                f"✕ This voice room has a locked name (`{channel.name}`) configured by server administration and cannot be renamed.",
                ephemeral=True
            )

        await interaction.response.send_modal(ChannelRenameModal(self.cog, channel))

    async def limit_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change the limit.", ephemeral=True)

        await interaction.response.send_modal(ChannelLimitModal(self.cog, channel))

    async def bitrate_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change audio bitrate.", ephemeral=True)

        await interaction.response.send_modal(ChannelBitrateModal(self.cog, channel))

    async def region_callback(self, interaction: discord.Interaction):
        channel, owner_id, owned = await self._resolve_user_channel_context(interaction)
        if not channel and len(owned) > 1:
            view = RoomSelectForActionView(self.cog, owned, action_type="region")
            return await interaction.response.send_message(
                "### 🌐 Voice Region\nYou own multiple voice rooms. Select which room you want to change region for:",
                view=view,
                ephemeral=True
            )
        if not channel:
            return await interaction.response.send_message("✕ You are not connected to a voice channel and do not own an active voice room in this server!", ephemeral=True)
        if owner_id and interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change the voice region.", ephemeral=True)

        await interaction.response.send_message(
            f"🌐 Select optimal RTC voice server region for lower ping (`{channel.name}`):",
            view=RegionSelectView(self.cog, channel),
            ephemeral=True
        )

    async def activity_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return

        await interaction.response.send_message("🎮 Select a Discord Game or Watch Together activity to launch:", view=ActivitySelectView(channel), ephemeral=True)

    async def permissions_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can modify room permissions.", ephemeral=True)

        await interaction.response.send_message("🛡️ Configure Soundboard and Video / Stream permissions:", view=PermissionsControlView(self.cog, channel), ephemeral=True)

    async def preset_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can manage room presets.", ephemeral=True)

        user_presets = await self.cog.get_user_presets(interaction.user.id)
        await interaction.response.send_message(
            f"### 💾 Voice Room Presets\nSave your current channel settings or load a previously saved configuration:",
            view=PresetManageView(self.cog, channel, user_presets),
            ephemeral=True
        )

    async def trust_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can manage trusted members.", ephemeral=True)

        await interaction.response.send_message("Select a member to grant VIP Trust (bypass lock & ghost):", view=TrustSelectView(channel), ephemeral=True)

    async def untrust_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can manage trusted members.", ephemeral=True)

        await interaction.response.send_message("Select a member to remove Trust status from:", view=UntrustSelectView(channel), ephemeral=True)

    async def invite_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can send invites.", ephemeral=True)

        await interaction.response.send_message("Select a member to invite to this room:", view=InviteSelectView(channel), ephemeral=True)

    async def kick_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can kick members.", ephemeral=True)

        await interaction.response.send_message("Select a member inside this room to kick:", view=KickSelectView(self.cog, channel), ephemeral=True)

    async def block_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can block members.", ephemeral=True)

        await interaction.response.send_message("Select a member to block & ban from this room:", view=BlockSelectView(self.cog, channel), ephemeral=True)

    async def unblock_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can unblock members.", ephemeral=True)

        await interaction.response.send_message("Select a member to unblock:", view=UnblockSelectView(channel), ephemeral=True)

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
        await interaction.response.send_message(f"👑 **Congratulations!** You are now the new owner of {channel.name}.", ephemeral=False)
        await self.cog.log_voice_event(
            interaction.guild,
            title="👑 Channel Claimed",
            description=f"{user.mention} claimed ownership of `{channel.name}` (former host: <@{owner_id}>).",
            color=0xFEE75C
        )

    async def transfer_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can transfer ownership.", ephemeral=True)

        await interaction.response.send_message("Select a room member to pass channel ownership to:", view=TransferOwnerView(self.cog, channel), ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        if not await self.cog.can_delete_voice_channel(guild, user):
            return await interaction.response.send_message(
                "✕ **Voice channel manual deletion is restricted on this server.**\n"
                "Only the **Server Owner** and **Whitelisted Members/Roles** can manually delete voice rooms.\n"
                "*(Your channel will automatically delete when everyone leaves).* ",
                ephemeral=True
            )

        owned = await self.cog.get_user_owned_channels(guild, user.id)
        if user.voice and user.voice.channel:
            curr_chan = user.voice.channel
            curr_owner = await self.cog.get_channel_owner(curr_chan.id)
            if curr_owner == user.id and curr_chan not in owned:
                owned.append(curr_chan)

        if not owned:
            return await interaction.response.send_message("✕ You do not own any active voice rooms in this server.", ephemeral=True)

        if len(owned) == 1:
            target = owned[0]
            chan_name = target.name
            await interaction.response.send_message(f"🗑 **Deleting voice room `{chan_name}`...**", ephemeral=True)
            await self.cog.delete_temp_channel_record(target.id)
            self.cog.knock_settings.pop(target.id, None)
            self.cog.afk_tracker.pop(target.id, None)
            try:
                await target.delete(reason=f"Deleted by room owner {user.name}")
            except Exception:
                pass
            await self.cog.log_voice_event(
                guild,
                title="🗑 Room Deleted",
                description=f"Host {user.mention} deleted room `{chan_name}`.",
                color=0xED4245
            )
        else:
            view = DeleteChannelSelectView(self.cog, owned)
            await interaction.response.send_message(
                f"### 🗑️ Delete Voice Room\nYou own **{len(owned)}** voice rooms. Select which room you want to delete from the dropdown:",
                view=view,
                ephemeral=True
            )

    async def info_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return

        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.mention if owner else f"User ID: {owner_id}"
        limit_text = "Unlimited" if channel.user_limit == 0 else f"{len(channel.members)}/{channel.user_limit}"
        knock_mode = "Enabled" if self.cog.knock_settings.get(channel.id, True) else "Muted"
        region_str = channel.rtc_region.capitalize() if channel.rtc_region else "Automatic"
        is_perm = await self.cog.is_channel_permanent(channel.id)
        room_type = "Permanent (Never auto-deletes)" if is_perm else "Temporary (Auto-deletes when empty)"

        info_view = discord.ui.LayoutView()
        c = discord.ui.Container(
            discord.ui.TextDisplay(
                f"### ℹ Room Overview\n"
                f"• **Room:** `{channel.name}`\n"
                f"• **Type:** `{room_type}`\n"
                f"• **Host:** {owner_name}\n"
                f"• **Occupancy:** `{limit_text}`\n"
                f"• **Bitrate:** `{channel.bitrate // 1000} kbps`\n"
                f"• **Region:** `{region_str}`\n"
                f"• **Doorbell (Knock):** `{knock_mode}`"
            ),
            accent_color=None
        )
        info_view.add_item(c)
def get_help_content(category: str) -> tuple[str, str]:
    cat = (category or "overview").lower()
    synonyms = {
        "wizard": "setup",
        "bot_setup": "setup",
        "hub": "hubs",
        "theme": "hubs",
        "themed": "hubs",
        "perm": "permanent",
        "presets": "permanent",
        "preset": "permanent",
        "logs": "maintenance",
        "admin": "maintenance",
        "panel": "interface",
        "jtc": "interface",
        "bot": "profile",
        "serverprofile": "profile",
        "botprofile": "profile",
        "avatar": "profile",
        "banner": "profile",
        "reset": "profile",
        "purge": "premium",
    }
    cat = synonyms.get(cat, cat)

    if cat == "setup":
        title = "✦ Bot Setup Guide (/voice setup)"
        desc = (
            "Run `/voice setup` or `/setup` to configure the voice system in your server.\n\n"
            "**Setup Modes:**\n"
            "• **Dual Hub:** Temporary VC + Permanent VC + automated `#interface` panel.\n"
            "• **Temporary Hub Only:** Standard Join-to-Create voice channels with control panel.\n"
            "• **Permanent Hub Only:** 24/7 persistent voice category for VIPs.\n"
            "• **Fixed-Name Themed Hub:** Setup fixed-name voice categories.\n\n"
            "✦ *Running the setup automatically creates categories, channels, and control buttons.*"
        )
    elif cat == "hubs":
        title = "✦ Fixed-Name Themed Hubs (/hub)"
        desc = (
            "Commands for dedicated themed voice hubs (Gaming, Duo, etc.):\n\n"
            "• `/hub create <category> <join_vc> <hub_vc_name>`\n"
            "  *Creates a new themed category & generator VC (room names stay fixed).*\n"
            "  *Example:* `/hub create Gaming Lounge ＋ Create VC Gaming Room`\n\n"
            "• `/hub list` — View all active themed hubs and category IDs in the server.\n"
            "• `/hub delete <category_id>` — Delete a themed hub configuration.\n\n"
            "✦ *Room names are rename-protected and automatically delete when empty.*"
        )
    elif cat == "permanent":
        title = "✦ Permanent Rooms & Presets"
        desc = (
            "Commands for persistent 24/7 rooms and custom configuration presets:\n\n"
            "• `/permanent create <name>` — Create a persistent voice room (never deletes when empty).\n"
            "• `/permanent delete` — Delete your persistent voice room.\n"
            "• `/preset save <name>` — Save current channel settings (user limit, bitrate, etc.).\n"
            "• `/preset load <name>` — Apply saved preset settings to your room.\n"
            "• `/preset list` — View all your saved presets.\n"
            "• `/preset delete <name>` — Delete a specific preset."
        )
    elif cat == "maintenance":
        title = "✦ Maintenance, Logs & Stats"
        desc = (
            "Management, audit logging, and utility commands:\n\n"
            "• `/voice logchannel <#channel>` — Set audit log channel for room events (create, rename, kick, ban).\n"
            "• `/interface` (or `/panel`) — Resend the voice control panel if `#interface` is missing.\n"
            "• `/prefix set <prefix>` — Set custom bot prefix for this server (Server Owner / Admin).\n"
            "• `/prefix` (or `.prefix`) — View or reset server-specific prefix.\n"
            "• `/leaderboard` (or `.top`) — View voice activity rankings and total voice hours.\n"
            "• `.sync` — Re-sync application slash commands (Bot Owner only)."
        )
    elif cat == "interface":
        title = "✦ Voice Interface & JTC System"
        desc = (
            "Member guide for using Join-to-Create voice channels:\n\n"
            "1. **Join to Create (JTC):** Join `＋ Create VC` to instantly generate your private room.\n"
            "2. **#interface Panel:** Click buttons in the text channel to manage your room:\n"
            "   • **Privacy:** Lock, Unlock, Ghost, Reveal, Chat, Knock\n"
            "   • **Settings:** Rename, Limit, Bitrate, Region, Activities, Soundboard\n"
            "   • **Members:** Trust VIP, Untrust, Invite, Kick, Block\n"
            "   • **Host:** Claim ownership, Transfer host, Info & Delete\n"
            "3. **Auto Cleanup:** The room deletes automatically when all members leave."
        )
    elif cat == "profile":
        title = "✦ Custom Server Bot Profile & Reset (/bot)"
        desc = (
            "Customize the bot's identity and control panel in this server:\n\n"
            "• `/bot serveravatar <image>` — Set a custom server avatar for the bot.\n"
            "• `/bot serverbanner <image>` — Set custom banner for bot & `#interface` control panel.\n"
            "• `/bot nickname <name>` — Set a custom server nickname for the bot.\n"
            "• `/bot serverbio <text>` — Set a custom about/bio for the bot in this server.\n"
            "• `/bot profile` — View your server's customized bot profile card.\n\n"
            "**Reset Commands:**\n"
            "• `/bot reset <target>` — Reset `avatar`, `banner`, `bio`, `nickname`, or `all` to default.\n"
            "• `/bot resetavatar` — Quick reset server avatar back to bot default.\n"
            "• `/bot resetbanner` — Quick reset banner & `#interface` panel back to default."
        )
    elif cat == "premium":
        title = "✦ VoiceClaw Premium & Moderation"
        desc = (
            "VoiceClaw Premium status, bulk purge & whitelists:\n\n"
            "• `/premium status` — Check VoiceClaw Premium subscription status for this server.\n"
            "• `/purge <amount> [member] [contains]` — Bulk delete messages with advanced filters.\n"
            "• `/purge_whitelist add <role/user>` — Whitelist roles/users permitted to purge.\n"
            "• `/purge_whitelist list` — View all whitelisted purge roles & members.\n"
            "• `/purge_whitelist remove <role/user>` — Remove a role/user from purge whitelist."
        )
    else:  # overview
        title = "✦ VoiceClaw • System & Setup Guide"
        desc = (
            "Next-generation dynamic voice and Join-to-Create engine.\n\n"
            "**Command Categories:**\n"
            "• **Bot Setup Guide:** `/voice setup` wizard for Dual, Temp & Permanent hubs\n"
            "• **Themed Hubs:** `/hub create`, `/hub list`, `/hub delete`\n"
            "• **Permanent Rooms & Presets:** `/permanent`, `/preset`\n"
            "• **Maintenance & Logs:** `/voice logchannel`, `/interface`, `/leaderboard`\n"
            "• **Voice Interface:** Full button control guide for `#interface`\n"
            "• **Server Profile & Reset:** `/bot serveravatar`, `/bot serverbanner`, `/bot reset`\n"
            "• **Premium & Moderation:** `/premium status`, `/purge`\n\n"
            "✦ *Select any category from the menu below for detailed guides.*"
        )

    return title, desc


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, current_category: str = "overview"):
        options = [
            discord.SelectOption(
                label="System Overview",
                value="overview",
                description="Core overview and system guide directory",
                emoji=APP_EMOJIS["overview"]
            ),
            discord.SelectOption(
                label="Bot Setup Guide",
                value="setup",
                description="Automated /voice setup wizard & modes",
                emoji=APP_EMOJIS["setup"]
            ),
            discord.SelectOption(
                label="Themed Hubs (/hub)",
                value="hubs",
                description="Fixed-name voice categories via /hub",
                emoji=APP_EMOJIS["hubs"]
            ),
            discord.SelectOption(
                label="Permanent Rooms & Presets",
                value="permanent",
                description="24/7 persistent rooms & saved presets",
                emoji=APP_EMOJIS["permanent"]
            ),
            discord.SelectOption(
                label="Maintenance & Logs",
                value="maintenance",
                description="Audit logging, panel recovery & leaderboards",
                emoji=APP_EMOJIS["maintenance"]
            ),
            discord.SelectOption(
                label="Voice Interface (JTC)",
                value="interface",
                description="Member guide for joining & panel buttons",
                emoji=APP_EMOJIS["interface"]
            ),
            discord.SelectOption(
                label="Server Profile & Reset",
                value="profile",
                description="Custom avatar, banner, bio & reset commands",
                emoji=APP_EMOJIS["setup"]
            ),
            discord.SelectOption(
                label="Premium & Moderation",
                value="premium",
                description="VoiceClaw Premium & /purge system",
                emoji=APP_EMOJIS["overview"]
            ),
        ]
        super().__init__(
            placeholder="Select an option...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="voice_help_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        new_view = HelpLayoutView(category=category)
        await interaction.response.edit_message(view=new_view)


class HelpLayoutView(discord.ui.LayoutView):
    def __init__(self, category: str = "overview"):
        super().__init__(timeout=None)
        self.category = category

        container_children = []
        if os.path.exists(GUIDE_BANNER_PATH):
            gallery_item = discord.MediaGalleryItem("attachment://guide.jpg")
            container_children.append(discord.ui.MediaGallery(gallery_item))

        title, desc = get_help_content(category)
        if category != "overview" and desc:
            header_text = f"### {title}\n{desc}" if title else desc
            container_children.append(discord.ui.TextDisplay(header_text))
        elif category == "overview":
            container_children.append(
                discord.ui.TextDisplay("✦ Select a category from the dropdown below to view full setup wizards, commands & controls.")
            )

        select = HelpCategorySelect(current_category=category)
        action_row = discord.ui.ActionRow(select)
        container_children.append(action_row)

        btn_refresh = discord.ui.Button(label="Refresh Guide", emoji=APP_EMOJIS["transfer"], style=discord.ButtonStyle.secondary, custom_id="guide_refresh_btn")
        btn_refresh.callback = self.refresh_callback
        action_row_btn = discord.ui.ActionRow(btn_refresh)
        container_children.append(action_row_btn)

        # Place image banner, subtitle text, and dropdown INSIDE the borderless V2 Container
        container = discord.ui.Container(
            *container_children,
            accent_color=None
        )
        self.add_item(container)

    async def refresh_callback(self, interaction: discord.Interaction):
        new_view = HelpLayoutView(category=self.category)
        await interaction.response.edit_message(view=new_view)
        await interaction.followup.send("✓ VoiceClaw guide refreshed with latest updates!", ephemeral=True)


# ==========================================
# Main Cog Implementation
# ==========================================

class voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._app_owner_id = None
        self._premium_cache = {}
        self.cooldowns = {}
        self.knock_cooldowns = {}
        self.knock_settings = {}
        self.voice_sessions = {}
        self.afk_tracker = {}
        self.panel_cooldowns = {}
        self.rename_history = {}

    def check_channel_rename_ratelimit(self, channel_id: int) -> typing.Optional[int]:
        """Checks Discord's 2-renames per 10-minutes rule. Returns remaining wait seconds if rate limited, else None."""
        now = time.time()
        history = self.rename_history.get(channel_id, [])
        history = [t for t in history if now - t < 600]
        self.rename_history[channel_id] = history
        if len(history) >= 2:
            oldest = history[0]
            return max(1, int(600 - (now - oldest)))
        return None

    def record_channel_rename(self, channel_id: int):
        """Records a successful rename timestamp for rate-limiting calculation."""
        now = time.time()
        history = self.rename_history.get(channel_id, [])
        history = [t for t in history if now - t < 600]
        history.append(now)
        self.rename_history[channel_id] = history

    async def cog_load(self):
        """Initialize database tables, register views, sweep channels, and start background tasks"""
        if self.bot.help_command:
            self.bot.help_command = None
        await self.init_db()
        if not hasattr(self.bot, 'guild_prefixes'):
            self.bot.guild_prefixes = {}
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT guildID, prefix FROM guildSettings WHERE prefix IS NOT NULL") as cur:
                    rows = await cur.fetchall()
                    for gid, pref in rows:
                        if pref:
                            self.bot.guild_prefixes[gid] = pref
            print(f"[VoiceClaw] Loaded {len(self.bot.guild_prefixes)} custom guild prefix(es).")
        except Exception as e:
            print(f"[VoiceClaw] Error loading guild prefixes: {e}")
        self.bot.add_view(VoiceControlLayoutView(self))
        asyncio.create_task(self.cleanup_stale_channels())
        asyncio.create_task(self.cleanup_interface_messages())
        
        # Start AFK timeout background checker
        if not self.afk_inactivity_check.is_running():
            self.afk_inactivity_check.start()

        # Track existing members currently in voice
        now = time.time()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for m in vc.members:
                    if not m.bot:
                        self.voice_sessions[(guild.id, m.id)] = now

    def cog_unload(self):
        """Cancel tasks and flush remaining voice sessions to database"""
        self.afk_inactivity_check.cancel()
        asyncio.create_task(self._flush_voice_sessions())

    async def _flush_voice_sessions(self):
        now = time.time()
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                for (guild_id, user_id), start_time in list(self.voice_sessions.items()):
                    dur = int(now - start_time)
                    if dur > 5:
                        await db.execute('''
                            INSERT INTO voiceTime (guildID, userID, totalSeconds)
                            VALUES (?, ?, ?)
                            ON CONFLICT(guildID, userID) DO UPDATE SET totalSeconds = totalSeconds + ?
                        ''', (guild_id, user_id, dur, dur))
                await db.commit()
        except Exception:
            pass
        self.voice_sessions.clear()

    # --- Background Loop: Anti-AFK Inactivity Timeout ---
    @tasks.loop(minutes=2)
    async def afk_inactivity_check(self):
        try:
            await self.bot.wait_until_ready()
        except Exception:
            return
        try:
            now = time.time()
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT voiceID, userID FROM voiceChannel") as cursor:
                    active_rooms = await cursor.fetchall()

            for voice_id, owner_id in active_rooms:
                chan = self.bot.get_channel(voice_id)
                if not chan or not isinstance(chan, discord.VoiceChannel):
                    continue

                if len(chan.members) == 1:
                    member = chan.members[0]
                    if member.bot:
                        continue
                    if member.voice and (member.voice.self_deaf or member.voice.deaf):
                        if voice_id not in self.afk_tracker:
                            self.afk_tracker[voice_id] = now
                        elif (now - self.afk_tracker[voice_id]) >= 900:  # 15 minutes
                            try:
                                await member.move_to(None)
                                await member.send(f"💤 You were disconnected from **{chan.name}** due to being alone and deafened for 15+ minutes.")
                            except Exception:
                                pass
                            try:
                                await chan.delete(reason="VoiceClaw: AFK Inactivity Timeout")
                            except Exception:
                                pass
                            await self.delete_temp_channel_record(voice_id)
                            self.knock_settings.pop(voice_id, None)
                            self.afk_tracker.pop(voice_id, None)
                            await self.log_voice_event(
                                chan.guild,
                                title="💤 Room Auto-Closed (AFK Inactivity)",
                                description=f"Room `{chan.name}` was closed after {member.mention} was alone and deafened for 15+ minutes.",
                                color=0xED4245
                            )
                    else:
                        self.afk_tracker.pop(voice_id, None)
                else:
                    self.afk_tracker.pop(voice_id, None)
        except Exception as e:
            print(f"[VoiceClaw] AFK sweep error: {e}")

    async def cleanup_stale_channels(self):
        """Sweep and delete any leftover empty temp channels on startup"""
        try:
            await self.bot.wait_until_ready()
        except Exception:
            return
        print("[VoiceClaw] Performing startup sweep of empty temporary channels...")
        for guild in self.bot.guilds:
            try:
                guild_cfg = await self.get_guild_config(guild.id)
                if not guild_cfg: continue
                category_id = guild_cfg[3]
                master_id = guild_cfg[2]
                cat = guild.get_channel(category_id)
                if cat and isinstance(cat, discord.CategoryChannel):
                    for chan in cat.voice_channels:
                        if chan.id != master_id and len(chan.members) == 0:
                            owner = await self.get_channel_owner(chan.id)
                            if owner:
                                if await self.is_channel_permanent(chan.id):
                                    continue
                                try:
                                    await chan.delete(reason="VoiceClaw: Startup empty room cleanup")
                                    print(f"[VoiceClaw] Cleaned empty room {chan.name} ({chan.id}) on startup")
                                except Exception:
                                    pass
                                await self.delete_temp_channel_record(chan.id)
            except Exception as e:
                print(f"[VoiceClaw] Startup sweep error: {e}")

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
                    voiceCategoryID INTEGER,
                    interfaceChannelID INTEGER,
                    logChannelID INTEGER
                )
            ''')
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN interfaceChannelID INTEGER")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN logChannelID INTEGER")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE voiceChannel ADD COLUMN isPermanent INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE voiceChannel ADD COLUMN isLockedName INTEGER DEFAULT 0")
            except Exception:
                pass
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voiceHubs (
                    hubID INTEGER PRIMARY KEY AUTOINCREMENT,
                    guildID INTEGER NOT NULL,
                    categoryID INTEGER NOT NULL,
                    joinChannelID INTEGER NOT NULL UNIQUE,
                    interfaceChannelID INTEGER,
                    fixedName TEXT NOT NULL,
                    userLimit INTEGER DEFAULT 0,
                    lockName INTEGER DEFAULT 1
                )
            ''')
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN permCategoryID INTEGER")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN permChannelID INTEGER")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN permInterfaceID INTEGER")
            except Exception:
                pass
            await db.execute('''
                CREATE TABLE IF NOT EXISTS userSettings (
                    userID INTEGER PRIMARY KEY,
                    channelName TEXT,
                    channelLimit INTEGER,
                    bitrate INTEGER
                )
            ''')
            try:
                await db.execute("ALTER TABLE userSettings ADD COLUMN bitrate INTEGER")
            except Exception:
                pass
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guildSettings (
                    guildID INTEGER PRIMARY KEY,
                    channelName TEXT,
                    channelLimit INTEGER,
                    prefix TEXT
                )
            ''')
            try:
                await db.execute("ALTER TABLE guildSettings ADD COLUMN prefix TEXT")
            except Exception:
                pass
            await db.execute('''
                CREATE TABLE IF NOT EXISTS userPresets (
                    userID INTEGER,
                    presetName TEXT,
                    channelName TEXT,
                    channelLimit INTEGER,
                    bitrate INTEGER,
                    PRIMARY KEY (userID, presetName)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voiceTime (
                    guildID INTEGER,
                    userID INTEGER,
                    totalSeconds INTEGER DEFAULT 0,
                    PRIMARY KEY (guildID, userID)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS premiumGuilds (
                    guildID INTEGER PRIMARY KEY,
                    plan TEXT DEFAULT 'Lifetime',
                    grantedBy INTEGER,
                    addedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS premiumUsers (
                    userID INTEGER PRIMARY KEY,
                    plan TEXT DEFAULT 'Lifetime',
                    grantedBy INTEGER,
                    addedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS serverBotProfile (
                    guildID INTEGER PRIMARY KEY,
                    serverAvatar TEXT,
                    serverBanner TEXT,
                    serverBio TEXT,
                    serverNickname TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS purgeWhitelist (
                    guildID INTEGER,
                    targetType TEXT,
                    targetID INTEGER,
                    addedBy INTEGER,
                    PRIMARY KEY (guildID, targetType, targetID)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS deleteWhitelist (
                    guildID INTEGER,
                    targetType TEXT,
                    targetID INTEGER,
                    addedBy INTEGER,
                    PRIMARY KEY (guildID, targetType, targetID)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guildPolicy (
                    guildID INTEGER PRIMARY KEY,
                    allowPublicDelete INTEGER DEFAULT 0
                )
            ''')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_guildID ON guild(guildID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_voiceChannel_voiceID ON voiceChannel(voiceID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_userSettings_userID ON userSettings(userID)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_guildSettings_guildID ON guildSettings(guildID)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_voiceTime_guild ON voiceTime(guildID, totalSeconds DESC)')
            await db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_voiceHubs_joinChannel ON voiceHubs(joinChannelID)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_voiceHubs_guildID ON voiceHubs(guildID)')
            await db.commit()

    async def get_app_owner_id(self) -> typing.Optional[int]:
        if getattr(self, '_app_owner_id', None) is not None:
            return self._app_owner_id
        try:
            app = await self.bot.application_info()
            self._app_owner_id = app.owner.id
            return self._app_owner_id
        except Exception:
            return None

    async def is_bot_owner(self, user: typing.Union[discord.User, discord.Member]) -> bool:
        if not user: return False
        if user.id == 1281114279948582923:
            return True
        if self.bot.owner_ids and user.id in self.bot.owner_ids:
            return True
        owner_id = await self.get_app_owner_id()
        return user.id == owner_id if owner_id else False

    async def is_guild_premium(self, guild: discord.Guild) -> bool:
        if not guild: return False
        now = time.time()
        cached = self._premium_cache.get(guild.id)
        if cached and (now - cached[1]) < 60:
            return cached[0]

        if guild.owner_id == 1281114279948582923 or (self.bot.owner_ids and guild.owner_id in self.bot.owner_ids):
            self._premium_cache[guild.id] = (True, now)
            return True
        owner_id = await self.get_app_owner_id()
        if owner_id and guild.owner_id == owner_id:
            self._premium_cache[guild.id] = (True, now)
            return True

        is_prem = False
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM premiumGuilds WHERE guildID = ?", (guild.id,)) as cur:
                if await cur.fetchone():
                    is_prem = True
            if not is_prem:
                async with db.execute("SELECT 1 FROM premiumUsers WHERE userID = ?", (guild.owner_id,)) as cur:
                    if await cur.fetchone():
                        is_prem = True

        self._premium_cache[guild.id] = (is_prem, now)
        return is_prem

    async def is_premium_user_or_guild(self, user: typing.Union[discord.User, discord.Member], guild: typing.Optional[discord.Guild] = None) -> bool:
        if await self.is_bot_owner(user):
            return True
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM premiumUsers WHERE userID = ?", (user.id,)) as cur:
                if await cur.fetchone():
                    return True
        if guild:
            if await self.is_guild_premium(guild):
                return True
        return False

    async def can_delete_voice_channel(self, guild: discord.Guild, member: typing.Union[discord.Member, discord.User]) -> bool:
        if not guild or not member: return False
        if await self.is_bot_owner(member):
            return True
        if member.id == guild.owner_id:
            return True
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM deleteWhitelist WHERE guildID = ? AND targetType = 'user' AND targetID = ?", (guild.id, member.id)) as cur:
                if await cur.fetchone():
                    return True
            if isinstance(member, discord.Member):
                user_role_ids = [r.id for r in member.roles]
                if user_role_ids:
                    placeholders = ','.join('?' for _ in user_role_ids)
                    async with db.execute(f"SELECT 1 FROM deleteWhitelist WHERE guildID = ? AND targetType = 'role' AND targetID IN ({placeholders})", (guild.id, *user_role_ids)) as cur:
                        if await cur.fetchone():
                            return True
            async with db.execute("SELECT allowPublicDelete FROM guildPolicy WHERE guildID = ?", (guild.id,)) as cur:
                row = await cur.fetchone()
                if row and row[0] == 1:
                    return True
        return False

    async def can_purge_messages(self, guild: discord.Guild, member: typing.Union[discord.Member, discord.User]) -> bool:
        if not guild or not member: return False
        if await self.is_bot_owner(member):
            return True
        if member.id == guild.owner_id:
            return True
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM purgeWhitelist WHERE guildID = ? AND targetType = 'user' AND targetID = ?", (guild.id, member.id)) as cur:
                if await cur.fetchone():
                    return True
            if isinstance(member, discord.Member):
                user_role_ids = [r.id for r in member.roles]
                if user_role_ids:
                    placeholders = ','.join('?' for _ in user_role_ids)
                    async with db.execute(f"SELECT 1 FROM purgeWhitelist WHERE guildID = ? AND targetType = 'role' AND targetID IN ({placeholders})", (guild.id, *user_role_ids)) as cur:
                        if await cur.fetchone():
                            return True
        return False

    async def get_guild_config(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                async with db.execute("SELECT guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID, logChannelID, permCategoryID, permChannelID, permInterfaceID FROM guild WHERE guildID = ?", (guild_id,)) as cursor:
                    return await cursor.fetchone()
            except Exception:
                async with db.execute("SELECT guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID, logChannelID, permCategoryID, permChannelID FROM guild WHERE guildID = ?", (guild_id,)) as cursor:
                    row = await cursor.fetchone()
                    return (*row, None) if row else None

    async def is_channel_permanent(self, voice_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT isPermanent FROM voiceChannel WHERE voiceID = ?", (voice_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row and len(row) > 0 and row[0] == 1)

    async def get_user_permanent_channels(self, guild_id: int, user_id: int) -> typing.List[discord.VoiceChannel]:
        guild = self.bot.get_guild(guild_id)
        if not guild: return []
        valid_channels = []
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ? AND isPermanent = 1", (user_id,)) as cursor:
                rows = await cursor.fetchall()
        for (v_id,) in rows:
            chan = guild.get_channel(v_id)
            if chan and isinstance(chan, discord.VoiceChannel):
                valid_channels.append(chan)
            elif not self.bot.get_channel(v_id):
                await self.delete_temp_channel_record(v_id)
        return valid_channels

    async def get_user_owned_channels(self, guild: discord.Guild, user_id: int) -> typing.List[discord.VoiceChannel]:
        if not guild: return []
        valid_channels = []
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (user_id,)) as cursor:
                rows = await cursor.fetchall()
        for (v_id,) in rows:
            chan = guild.get_channel(v_id)
            if chan and isinstance(chan, discord.VoiceChannel):
                if chan not in valid_channels:
                    valid_channels.append(chan)
            elif not self.bot.get_channel(v_id):
                await self.delete_temp_channel_record(v_id)
        return valid_channels

    async def get_user_permanent_channel(self, guild_id: int, user_id: int) -> typing.Optional[int]:
        channels = await self.get_user_permanent_channels(guild_id, user_id)
        return channels[0].id if channels else None

    async def set_guild_log_channel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE guild SET logChannelID = ? WHERE guildID = ?", (channel_id, guild_id))
            await db.commit()

    async def log_voice_event(self, guild: discord.Guild, title: str, description: str, color: typing.Optional[int] = None):
        try:
            guild_cfg = await self.get_guild_config(guild.id)
            if not guild_cfg or len(guild_cfg) < 6 or not guild_cfg[5]:
                return
            log_chan = guild.get_channel(guild_cfg[5])
            if not log_chan or not isinstance(log_chan, discord.TextChannel):
                return

            embed = discord.Embed(
                title=title,
                description=description,
                color=None,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="VoiceClaw Audit Engine", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)
            await log_chan.send(embed=embed)
        except Exception as e:
            print(f"[VoiceClaw Log Error] {e}")

    async def get_channel_owner(self, voice_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT userID FROM voiceChannel WHERE voiceID = ?", (voice_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]

        # Automatic Self-Healing Fallback for voice rooms:
        channel = self.bot.get_channel(voice_id)
        if channel and isinstance(channel, discord.VoiceChannel):
            # 1. Check member overwrites for manage_channels=True
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and not target.bot:
                    if overwrite.manage_channels is True:
                        await self.register_temp_channel(target.id, voice_id)
                        print(f"[VoiceClaw Self-Heal] Recovered owner {target.display_name} ({target.id}) for room {channel.name} from permission overwrites.")
                        return target.id

            # 2. Check channel name matching a member (e.g. "{name}'s Room")
            for m in channel.members:
                if not m.bot:
                    clean = " ".join(m.display_name.split()).lower()
                    cname = channel.name.lower()
                    if f"{clean}'s room" in cname or cname.startswith(clean):
                        await self.register_temp_channel(m.id, voice_id)
                        print(f"[VoiceClaw Self-Heal] Recovered owner {m.display_name} ({m.id}) for room {channel.name} from member name.")
                        return m.id

            # 3. First non-bot member in channel
            first_human = next((m for m in channel.members if not m.bot), None)
            if first_human:
                await self.register_temp_channel(first_human.id, voice_id)
                print(f"[VoiceClaw Self-Heal] Recovered owner {first_human.display_name} ({first_human.id}) for room {channel.name} as primary member.")
                return first_human.id

        return None

    async def get_owner_channel(self, owner_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (owner_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_channel_owner(self, voice_id: int, new_owner_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE voiceChannel SET userID = ? WHERE voiceID = ?", (new_owner_id, voice_id))
            await db.commit()

    async def register_temp_channel(self, user_id: int, voice_id: int, is_permanent: int = 0, is_locked_name: int = 0):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (voice_id,))
            await db.execute("INSERT INTO voiceChannel (userID, voiceID, isPermanent, isLockedName) VALUES (?, ?, ?, ?)", (user_id, voice_id, is_permanent, is_locked_name))
            await db.commit()

    async def is_channel_locked_name(self, voice_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT isLockedName FROM voiceChannel WHERE voiceID = ?", (voice_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row and row[0])

    async def create_voice_hub(self, guild_id: int, category_id: int, join_channel_id: int, interface_channel_id: typing.Optional[int], fixed_name: str, user_limit: int = 0, lock_name: int = 1):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO voiceHubs (guildID, categoryID, joinChannelID, interfaceChannelID, fixedName, userLimit, lockName)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(joinChannelID) DO UPDATE SET
                    categoryID = excluded.categoryID,
                    interfaceChannelID = excluded.interfaceChannelID,
                    fixedName = excluded.fixedName,
                    userLimit = excluded.userLimit,
                    lockName = excluded.lockName
            ''', (guild_id, category_id, join_channel_id, interface_channel_id, fixed_name, user_limit, lock_name))
            await db.commit()

    async def get_voice_hub(self, join_channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT hubID, guildID, categoryID, joinChannelID, interfaceChannelID, fixedName, userLimit, lockName FROM voiceHubs WHERE joinChannelID = ?", (join_channel_id,)) as cursor:
                return await cursor.fetchone()

    async def get_guild_hubs(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT hubID, guildID, categoryID, joinChannelID, interfaceChannelID, fixedName, userLimit, lockName FROM voiceHubs WHERE guildID = ?", (guild_id,)) as cursor:
                return await cursor.fetchall()

    async def delete_voice_hub(self, hub_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM voiceHubs WHERE hubID = ?", (hub_id,))
            await db.commit()

    async def delete_voice_hub_by_join(self, join_channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM voiceHubs WHERE joinChannelID = ?", (join_channel_id,))
            await db.commit()

    async def is_hub_join_channel(self, channel_id: int) -> bool:
        hub = await self.get_voice_hub(channel_id)
        return hub is not None

    async def perform_dual_setup(
        self,
        guild: discord.Guild,
        author_id: int,
        temp_category_name: typing.Optional[str] = None,
        perm_category_name: typing.Optional[str] = None,
        temp_join_name: typing.Optional[str] = None,
        perm_create_name: typing.Optional[str] = None,
        interface_name: typing.Optional[str] = None
    ):
        """Creates both Temporary and Permanent voice categories, interfaces, and join channels with custom names"""
        t_cat_name = (temp_category_name or "Voice Channels").strip()
        p_cat_name = (perm_category_name or "Permanent Rooms").strip()
        t_join = (temp_join_name or "＋ Join to Create").strip()
        p_create = (perm_create_name or "＋ Create Permanent VC").strip()
        raw_iface = (interface_name or "interface").strip().lstrip("#")
        i_name = raw_iface if raw_iface else "interface"

        # 1. Temporary Category & Channels
        temp_cat = None
        for c in guild.categories:
            if c.name.lower() == t_cat_name.lower():
                temp_cat = c
                break
        if not temp_cat:
            temp_cat = await guild.create_category(t_cat_name)

        interface_chan = discord.utils.get(temp_cat.text_channels, name=i_name)
        if not interface_chan:
            interface_chan = await guild.create_text_channel(
                i_name,
                category=temp_cat,
                topic="VoiceClaw Temporary Voice Channel Control Interface"
            )
            await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        temp_chan = discord.utils.get(temp_cat.voice_channels, name=t_join)
        if not temp_chan:
            temp_chan = await guild.create_voice_channel(t_join, category=temp_cat)

        # 2. Permanent Category & Channels
        perm_cat = None
        for c in guild.categories:
            if c.name.lower() == p_cat_name.lower():
                perm_cat = c
                break
        if not perm_cat:
            perm_cat = await guild.create_category(p_cat_name)

        perm_interface = discord.utils.get(perm_cat.text_channels, name=i_name)
        if not perm_interface:
            perm_interface = await guild.create_text_channel(
                i_name,
                category=perm_cat,
                topic="VoiceClaw Permanent Voice Channel Control Interface"
            )
            await perm_interface.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await perm_interface.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        perm_chan = discord.utils.get(perm_cat.voice_channels, name=p_create)
        if not perm_chan:
            perm_chan = await guild.create_voice_channel(p_create, category=perm_cat)

        # Deploy interface control panels with banner
        has_banner = os.path.exists(BANNER_PATH)
        ctrl_view1 = VoiceControlLayoutView(self, has_banner=has_banner)
        ctrl_view2 = VoiceControlLayoutView(self, has_banner=has_banner)
        try:
            await interface_chan.purge(limit=25, check=lambda m: m.author == self.bot.user)
            await perm_interface.purge(limit=25, check=lambda m: m.author == self.bot.user)
        except Exception:
            pass
        if has_banner:
            file1 = discord.File(BANNER_PATH, filename="banner.jpg")
            await interface_chan.send(file=file1, view=ctrl_view1)
            file2 = discord.File(BANNER_PATH, filename="banner.jpg")
            await perm_interface.send(file=file2, view=ctrl_view2)
        else:
            await interface_chan.send(view=ctrl_view1)
            await perm_interface.send(view=ctrl_view2)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM guild WHERE guildID = ?", (guild.id,))
            await db.execute('''
                INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID, permCategoryID, permChannelID, permInterfaceID)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (guild.id, author_id, temp_chan.id, temp_cat.id, interface_chan.id, perm_cat.id, perm_chan.id, perm_interface.id))
            await db.commit()

        return temp_cat, temp_chan, interface_chan, perm_cat, perm_chan, perm_interface

    async def perform_temp_setup(self, guild: discord.Guild, author_id: int, category_name: typing.Optional[str] = None, join_name: typing.Optional[str] = None, interface_name: typing.Optional[str] = None):
        """Creates only Temporary voice category, interface, and join channel with customizable names"""
        cat_name = (category_name or "Voice Channels").strip()
        j_name = (join_name or "＋ Join to Create").strip()
        raw_iface = (interface_name or "interface").strip().lstrip("#")
        i_name = raw_iface if raw_iface else "interface"

        temp_cat = None
        for c in guild.categories:
            if c.name.lower() == cat_name.lower():
                temp_cat = c
                break
        if not temp_cat:
            temp_cat = await guild.create_category(cat_name)

        interface_chan = discord.utils.get(temp_cat.text_channels, name=i_name)
        if not interface_chan:
            interface_chan = await guild.create_text_channel(
                i_name,
                category=temp_cat,
                topic="VoiceClaw Temporary Voice Channel Control Interface"
            )
            await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        temp_chan = discord.utils.get(temp_cat.voice_channels, name=j_name)
        if not temp_chan:
            temp_chan = await guild.create_voice_channel(j_name, category=temp_cat)

        has_banner = os.path.exists(BANNER_PATH)
        ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner)
        try:
            await interface_chan.purge(limit=25, check=lambda m: m.author == self.bot.user)
        except Exception:
            pass
        if has_banner:
            file = discord.File(BANNER_PATH, filename="banner.jpg")
            await interface_chan.send(file=file, view=ctrl_view)
        else:
            await interface_chan.send(view=ctrl_view)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guildID) DO UPDATE SET 
                    voiceCategoryID = excluded.voiceCategoryID,
                    voiceChannelID = excluded.voiceChannelID,
                    interfaceChannelID = excluded.interfaceChannelID
            ''', (guild.id, author_id, temp_chan.id, temp_cat.id, interface_chan.id))
            await db.commit()

        return temp_cat, temp_chan, interface_chan

    async def perform_perm_setup(
        self,
        guild: discord.Guild,
        author_id: int,
        category_name: typing.Optional[str] = None,
        create_name: typing.Optional[str] = None,
        interface_name: typing.Optional[str] = None
    ):
        """Creates only Permanent voice category, interface, and join channel with customizable names"""
        cat_name = (category_name or "Permanent Rooms").strip()
        c_name = (create_name or "＋ Create Permanent VC").strip()
        raw_iface = (interface_name or "interface").strip().lstrip("#")
        i_name = raw_iface if raw_iface else "interface"

        perm_cat = None
        for c in guild.categories:
            if c.name.lower() == cat_name.lower():
                perm_cat = c
                break
        if not perm_cat:
            perm_cat = await guild.create_category(cat_name)

        perm_interface = discord.utils.get(perm_cat.text_channels, name=i_name)
        if not perm_interface:
            perm_interface = await guild.create_text_channel(
                i_name,
                category=perm_cat,
                topic="VoiceClaw Permanent Voice Channel Control Interface"
            )
            await perm_interface.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await perm_interface.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        perm_chan = discord.utils.get(perm_cat.voice_channels, name=c_name)
        if not perm_chan:
            perm_chan = await guild.create_voice_channel(c_name, category=perm_cat)

        has_banner = os.path.exists(BANNER_PATH)
        ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner)
        try:
            await perm_interface.purge(limit=25, check=lambda m: m.author == self.bot.user)
        except Exception:
            pass
        if has_banner:
            file = discord.File(BANNER_PATH, filename="banner.jpg")
            await perm_interface.send(file=file, view=ctrl_view)
        else:
            await perm_interface.send(view=ctrl_view)

        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, permCategoryID, permChannelID, permInterfaceID)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guildID) DO UPDATE SET 
                        permCategoryID = excluded.permCategoryID,
                        permChannelID = excluded.permChannelID,
                        permInterfaceID = excluded.permInterfaceID
                ''', (guild.id, author_id, perm_cat.id, perm_chan.id, perm_interface.id))
                await db.commit()
            except Exception:
                pass

        return perm_cat, perm_chan, perm_interface

    async def delete_temp_channel_record(self, voice_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (voice_id,))
            await db.commit()

    async def get_user_setting(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channelName, channelLimit, bitrate FROM userSettings WHERE userID = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def save_user_setting(self, user_id: int, channel_name: str = None, channel_limit: int = None, bitrate: int = None,
                                clear_name: bool = False, clear_limit: bool = False, clear_bitrate: bool = False):
        async with aiosqlite.connect(DB_PATH) as db:
            current = await self.get_user_setting(user_id)
            if clear_name:
                name = None
            else:
                name = channel_name if channel_name is not None else (current[0] if current else None)

            if clear_limit:
                limit = 0
            else:
                limit = channel_limit if channel_limit is not None else (current[1] if current else 0)

            if clear_bitrate:
                bit = None
            else:
                bit = bitrate if bitrate is not None else (current[2] if current and len(current) > 2 else None)

            await db.execute("DELETE FROM userSettings WHERE userID = ?", (user_id,))
            await db.execute(
                "INSERT INTO userSettings (userID, channelName, channelLimit, bitrate) VALUES (?, ?, ?, ?)",
                (user_id, name, limit, bit)
            )
            await db.commit()

    async def reset_user_settings(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM userSettings WHERE userID = ?", (user_id,))
            await db.commit()

    async def get_guild_setting(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channelName, channelLimit FROM guildSettings WHERE guildID = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def save_user_preset(self, user_id: int, preset_name: str, channel_name: str, channel_limit: int, bitrate: int = None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO userPresets (userID, presetName, channelName, channelLimit, bitrate)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(userID, presetName) DO UPDATE SET
                    channelName = excluded.channelName,
                    channelLimit = excluded.channelLimit,
                    bitrate = excluded.bitrate
            ''', (user_id, preset_name, channel_name, channel_limit, bitrate))
            await db.commit()

    async def get_user_presets(self, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT presetName, channelName, channelLimit, bitrate FROM userPresets WHERE userID = ?", (user_id,)) as cursor:
                return await cursor.fetchall()

    async def get_user_preset(self, user_id: int, preset_name: str):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT presetName, channelName, channelLimit, bitrate FROM userPresets WHERE userID = ? AND presetName = ?", (user_id, preset_name)) as cursor:
                return await cursor.fetchone()

    async def delete_user_preset(self, user_id: int, preset_name: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM userPresets WHERE userID = ? AND presetName = ?", (user_id, preset_name))
            await db.commit()

    async def cleanup_empty_category_channels(self, category: discord.CategoryChannel, master_channel_id: int):
        try:
            for c in list(category.voice_channels):
                if c.id != master_channel_id and len(c.members) == 0:
                    is_temp = await self.get_channel_owner(c.id)
                    if is_temp:
                        if await self.is_channel_permanent(c.id):
                            continue
                        try:
                            await c.delete(reason="VoiceClaw: Auto-cleanup empty temp room")
                            print(f"[VoiceClaw] Cleaned empty channel {c.name} ({c.id})")
                        except Exception:
                            pass
                        await self.delete_temp_channel_record(c.id)
                        self.knock_settings.pop(c.id, None)
        except Exception:
            pass

    def is_control_panel_message(self, m: discord.Message) -> bool:
        if m.author != self.bot.user:
            return False
        if m.components:
            return True
        if m.attachments:
            return True
        if m.embeds:
            return True
        return True

    async def is_interface_channel(self, channel: discord.TextChannel) -> bool:
        if not channel or not isinstance(channel, discord.TextChannel):
            return False
        if channel.name.lower() in ["interface", "control-panel", "voice-interface"]:
            return True
        config = await self.get_guild_config(channel.guild.id)
        if config:
            if config[4] == channel.id:
                return True
            if len(config) > 8 and config[8] == channel.id:
                return True
        try:
            hubs = await self.get_guild_hubs(channel.guild.id)
            for h in hubs:
                if len(h) > 4 and h[4] == channel.id:
                    return True
        except Exception:
            pass
        return False

    async def get_guild_banner_url(self, guild_id: int) -> typing.Optional[str]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT serverBanner FROM serverBotProfile WHERE guildID = ?", (guild_id,)) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return row[0]
        return None

    async def refresh_all_guild_interfaces(self, guild: discord.Guild):
        banner_url = await self.get_guild_banner_url(guild.id)
        chan_ids = set()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT interfaceChannelID, permInterfaceID FROM guild WHERE guildID = ?", (guild.id,)) as cur:
                row = await cur.fetchone()
                if row:
                    if row[0]: chan_ids.add(row[0])
                    if len(row) > 1 and row[1]: chan_ids.add(row[1])
            async with db.execute("SELECT interfaceChannelID FROM voiceHubs WHERE guildID = ?", (guild.id,)) as cur:
                rows = await cur.fetchall()
                for r in rows:
                    if r[0]: chan_ids.add(r[0])
        for c in guild.text_channels:
            if c.name.lower() in ["interface", "control-panel", "voice-interface"]:
                chan_ids.add(c.id)

        for cid in chan_ids:
            chan = guild.get_channel(cid)
            if not chan or not isinstance(chan, discord.TextChannel):
                continue
            try:
                found_panel = False
                async for msg in chan.history(limit=10):
                    if msg.author == self.bot.user and self.is_control_panel_message(msg):
                        has_b = os.path.exists(BANNER_PATH) if not banner_url else False
                        view = VoiceControlLayoutView(self, has_banner=has_b, banner_url=banner_url)
                        if banner_url:
                            await msg.edit(view=view, attachments=[])
                        elif has_b:
                            file = discord.File(BANNER_PATH, filename="banner.jpg")
                            await msg.edit(attachments=[file], view=view)
                        else:
                            await msg.edit(attachments=[], view=view)
                        found_panel = True
                        break
                if not found_panel:
                    has_b = os.path.exists(BANNER_PATH) if not banner_url else False
                    view = VoiceControlLayoutView(self, has_banner=has_b, banner_url=banner_url)
                    if banner_url:
                        await chan.send(view=view)
                    elif has_b:
                        file = discord.File(BANNER_PATH, filename="banner.jpg")
                        await chan.send(file=file, view=view)
                    else:
                        await chan.send(view=view)
            except Exception as e:
                print(f"[VoiceClaw] Could not refresh interface in #{chan.name}: {e}")

    async def cleanup_interface_messages(self):
        """Purge any stray messages from interface channels and ensure the voice control panel is always present"""
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(2)
            for guild in self.bot.guilds:
                config = await self.get_guild_config(guild.id)
                target_ids = []
                if config:
                    if config[4]: target_ids.append(config[4])
                    if len(config) > 8 and config[8]: target_ids.append(config[8])
                try:
                    hubs = await self.get_guild_hubs(guild.id)
                    for h in hubs:
                        if len(h) > 4 and h[4]: target_ids.append(h[4])
                except Exception:
                    pass
                for c in guild.text_channels:
                    if c.name.lower() in ["interface", "control-panel", "voice-interface"]:
                        if c.id not in target_ids: target_ids.append(c.id)

                for chan_id in set(target_ids):
                    chan = guild.get_channel(chan_id)
                    if chan and isinstance(chan, discord.TextChannel):
                        try:
                            # Fetch messages in reverse chronological order (newest first)
                            messages = []
                            async for m in chan.history(limit=50):
                                messages.append(m)

                            keep_panel = None
                            for m in messages:
                                if m.author == self.bot.user:
                                    if keep_panel is None and self.is_control_panel_message(m):
                                        # Keep the newest/bottom control panel
                                        keep_panel = m
                                    else:
                                        # Delete all older panels and bot messages
                                        try:
                                            await m.delete()
                                        except Exception:
                                            pass
                                elif not m.pinned:
                                    # Delete stray user messages in interface channel
                                    try:
                                        await m.delete()
                                    except Exception:
                                        pass

                            if not keep_panel:
                                banner_url = await self.get_guild_banner_url(guild.id)
                                has_banner = os.path.exists(BANNER_PATH) if not banner_url else False
                                ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner, banner_url=banner_url)
                                if banner_url:
                                    await chan.send(view=ctrl_view)
                                elif has_banner:
                                    file = discord.File(BANNER_PATH, filename="banner.jpg")
                                    await chan.send(file=file, view=ctrl_view)
                                else:
                                    await chan.send(view=ctrl_view)
                                print(f"[VoiceClaw] Restored single control panel in #{chan.name} ({chan.id})")
                            else:
                                banner_url = await self.get_guild_banner_url(guild.id)
                                has_banner = os.path.exists(BANNER_PATH) if not banner_url else False
                                ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner, banner_url=banner_url)
                                try:
                                    if banner_url:
                                        await keep_panel.edit(attachments=[], view=ctrl_view)
                                    elif has_banner:
                                        file = discord.File(BANNER_PATH, filename="banner.jpg")
                                        await keep_panel.edit(attachments=[file], view=ctrl_view)
                                    else:
                                        await keep_panel.edit(attachments=[], view=ctrl_view)
                                except Exception:
                                    pass
                                print(f"[VoiceClaw] Retained and updated active panel in #{chan.name} ({chan.id}) with latest banner.")
                        except Exception as e:
                            print(f"[VoiceClaw] Failed cleanup in #{chan.name}: {e}")
        except Exception:
            pass

    # --- Listener: Auto-delete all messages in interface channels ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        if await self.is_interface_channel(message.channel):
            if not self.is_control_panel_message(message):
                try:
                    await asyncio.sleep(3)
                    await message.delete()
                except Exception:
                    pass

    # --- Listener: Voice State Updates & Time Tracking ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        try:
            guild = member.guild
            now = time.time()

            # Voice Activity Tracking
            if before.channel is None and after.channel is not None:
                self.voice_sessions[(guild.id, member.id)] = now
            elif before.channel is not None and after.channel is None:
                start_time = self.voice_sessions.pop((guild.id, member.id), None)
                if start_time:
                    dur = int(now - start_time)
                    if dur > 5:
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute('''
                                INSERT INTO voiceTime (guildID, userID, totalSeconds)
                                VALUES (?, ?, ?)
                                ON CONFLICT(guildID, userID) DO UPDATE SET totalSeconds = totalSeconds + ?
                            ''', (guild.id, member.id, dur, dur))
                            await db.commit()

            guild_cfg = await self.get_guild_config(guild.id)
            master_channel_id = guild_cfg[2] if guild_cfg else None
            category_id = guild_cfg[3] if guild_cfg else None
            perm_channel_id = guild_cfg[7] if guild_cfg and len(guild_cfg) > 7 else None
            perm_category_id = guild_cfg[6] if guild_cfg and len(guild_cfg) > 6 else None

            # 1. User Joined the "Join to Create" Master Channel
            if after.channel and master_channel_id and after.channel.id == master_channel_id:
                loop_now = asyncio.get_event_loop().time()
                if member.id in self.cooldowns and (loop_now - self.cooldowns[member.id]) < 4:
                    return

                self.cooldowns[member.id] = loop_now

                # If this member ALREADY has an active voice room, move them back to it
                existing_chan_id = await self.get_owner_channel(member.id)
                if existing_chan_id:
                    existing_chan = guild.get_channel(existing_chan_id)
                    if existing_chan and isinstance(existing_chan, discord.VoiceChannel):
                        try:
                            await member.move_to(existing_chan)
                            print(f"[VoiceClaw] Moved {member.display_name} back to existing room {existing_chan.name}")
                            return
                        except Exception:
                            pass
                    else:
                        await self.delete_temp_channel_record(existing_chan_id)

                category = guild.get_channel(category_id)
                if isinstance(category, discord.CategoryChannel):
                    asyncio.create_task(self.cleanup_empty_category_channels(category, master_channel_id))
                else:
                    category = None

                user_pref = await self.get_user_setting(member.id)
                guild_pref = await self.get_guild_setting(guild.id)

                clean_name = " ".join(member.display_name.split())
                chan_name = f"{clean_name}'s Room"
                chan_limit = 0
                target_bitrate = None

                if guild_pref:
                    chan_limit = guild_pref[1]

                if user_pref:
                    if user_pref[0]: chan_name = user_pref[0]
                    if user_pref[1] is not None: chan_limit = user_pref[1]
                    if len(user_pref) > 2 and user_pref[2]:
                        target_bitrate = min(user_pref[2] * 1000, guild.bitrate_limit)

                print(f"[VoiceClaw] Creating temporary room '{chan_name}' for {member.display_name}...")

                bot_user = self.bot.user
                bot_member = guild.me or (guild.get_member(bot_user.id) if bot_user else None)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=True, read_message_history=True),
                    member: discord.PermissionOverwrite(
                        connect=True, view_channel=True, read_messages=True,
                        send_messages=True, read_message_history=True, manage_channels=True
                    )
                }
                if bot_member:
                    overwrites[bot_member] = discord.PermissionOverwrite(
                        connect=True, view_channel=True, read_messages=True,
                        send_messages=True, read_message_history=True, manage_channels=True
                    )

                temp_channel = await guild.create_voice_channel(
                    name=chan_name,
                    category=category,
                    user_limit=chan_limit,
                    bitrate=target_bitrate,
                    overwrites=overwrites
                )

                # Move member IMMEDIATELY upon creation
                try:
                    if member.voice and member.voice.channel:
                        await member.move_to(temp_channel)
                        print(f"[VoiceClaw] Instantly moved {member.display_name} to {temp_channel.name} ({temp_channel.id})")
                    else:
                        if len(temp_channel.members) == 0:
                            await temp_channel.delete(reason="VoiceClaw: Member left before being moved")
                            return
                except discord.HTTPException as move_err:
                    print(f"[VoiceClaw] Could not move member {member.display_name}: {move_err}")
                    if len(temp_channel.members) == 0:
                        try:
                            await temp_channel.delete(reason="VoiceClaw: Member not in voice")
                        except Exception:
                            pass
                        return

                await self.register_temp_channel(member.id, temp_channel.id)
                self.knock_settings[temp_channel.id] = True

                # Send Minimalist Discord Components v2 LayoutView
                try:
                    has_banner = os.path.exists(BANNER_PATH)
                    ctrl_view = VoiceControlLayoutView(self, member.display_avatar.url, member.display_name, has_banner=has_banner)
                    if has_banner:
                        file = discord.File(BANNER_PATH, filename="banner.jpg")
                        msg = await temp_channel.send(file=file, view=ctrl_view)
                    else:
                        msg = await temp_channel.send(view=ctrl_view)
                    print(f"[VoiceClaw] Sent interface message ({msg.id}) into {temp_channel.name}")
                except Exception as send_err:
                    print(f"[VoiceClaw Error] Failed to send interface message into {temp_channel.name}: {send_err}")

                # Log creation
                await self.log_voice_event(
                    guild,
                    title="✦ Temporary Room Created",
                    description=f"**Room:** `{chan_name}` ({temp_channel.mention})\n**Host:** {member.mention}\n**Bitrate:** `{temp_channel.bitrate // 1000} kbps`",
                    color=0x57F287
                )

            # 2. User Joined the "Create Permanent VC" Master Channel
            perm_channel_id = guild_cfg[7] if guild_cfg and len(guild_cfg) > 7 else None
            perm_category_id = guild_cfg[6] if guild_cfg and len(guild_cfg) > 6 else None
            if after.channel and perm_channel_id and after.channel.id == perm_channel_id:
                loop_now = asyncio.get_event_loop().time()
                if member.id in self.cooldowns and (loop_now - self.cooldowns[member.id]) < 4:
                    return
                self.cooldowns[member.id] = loop_now

                # Check member's existing permanent rooms (up to 3 rooms supported)
                existing_perms = await self.get_user_permanent_channels(guild.id, member.id)
                if len(existing_perms) >= 3:
                    try:
                        await member.move_to(existing_perms[0])
                        print(f"[VoiceClaw] Moved {member.display_name} to their existing permanent room {existing_perms[0].name} (limit 3 reached)")
                        return
                    except Exception:
                        pass
                    return

                # Create permanent channel under perm_category_id
                category = guild.get_channel(perm_category_id) if perm_category_id else None
                clean_name = " ".join(member.display_name.split())
                chan_name = f"{clean_name}'s Room" if len(existing_perms) == 0 else f"{clean_name}'s Room {len(existing_perms) + 1}"

                user_pref = await self.get_user_setting(member.id)
                target_bitrate = None
                chan_limit = 0
                if user_pref:
                    if user_pref[0]: chan_name = user_pref[0]
                    if user_pref[1] is not None: chan_limit = user_pref[1]
                    if len(user_pref) > 2 and user_pref[2]:
                        target_bitrate = min(user_pref[2] * 1000, guild.bitrate_limit)

                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=True, read_message_history=True),
                    member: discord.PermissionOverwrite(
                        connect=True, view_channel=True, read_messages=True,
                        send_messages=True, read_message_history=True, manage_channels=True
                    )
                }
                bot_member = guild.me
                if bot_member:
                    overwrites[bot_member] = discord.PermissionOverwrite(
                        connect=True, view_channel=True, read_messages=True,
                        send_messages=True, read_message_history=True, manage_channels=True
                    )

                perm_channel = await guild.create_voice_channel(
                    name=chan_name,
                    category=category,
                    user_limit=chan_limit,
                    bitrate=target_bitrate,
                    overwrites=overwrites
                )

                try:
                    if member.voice and member.voice.channel:
                        await member.move_to(perm_channel)
                except Exception:
                    pass

                await self.register_temp_channel(member.id, perm_channel.id, is_permanent=1)
                self.knock_settings[perm_channel.id] = True

                try:
                    has_banner = os.path.exists(BANNER_PATH)
                    ctrl_view = VoiceControlLayoutView(self, member.display_avatar.url, member.display_name, has_banner=has_banner)
                    if has_banner:
                        file = discord.File(BANNER_PATH, filename="banner.jpg")
                        await perm_channel.send(file=file, view=ctrl_view)
                    else:
                        await perm_channel.send(view=ctrl_view)
                except Exception:
                    pass

                await self.log_voice_event(
                    guild,
                    title="Permanent Room Created",
                    description=f"**Room:** `{chan_name}` ({perm_channel.mention})\n**Host:** {member.mention}\n**Permanent:** `Yes (Never auto-deletes)`",
                    color=0xFEE75C
                )

            # 3. User Joined a Fixed-Name Themed Hub Channel
            if after.channel:
                hub = await self.get_voice_hub(after.channel.id)
                if hub:
                    loop_now = asyncio.get_event_loop().time()
                    if member.id in self.cooldowns and (loop_now - self.cooldowns[member.id]) < 4:
                        return
                    self.cooldowns[member.id] = loop_now

                    hub_id, h_guild_id, h_cat_id, h_join_id, h_interface_id, fixed_name, user_limit, lock_name = hub

                    # If this member ALREADY has an active voice room, move them back to it
                    existing_chan_id = await self.get_owner_channel(member.id)
                    if existing_chan_id:
                        existing_chan = guild.get_channel(existing_chan_id)
                        if existing_chan and isinstance(existing_chan, discord.VoiceChannel):
                            try:
                                await member.move_to(existing_chan)
                                print(f"[VoiceClaw] Moved {member.display_name} back to existing room {existing_chan.name}")
                                return
                            except Exception:
                                pass
                        else:
                            await self.delete_temp_channel_record(existing_chan_id)

                    category = guild.get_channel(h_cat_id)
                    if isinstance(category, discord.CategoryChannel):
                        asyncio.create_task(self.cleanup_empty_category_channels(category, h_join_id))
                    else:
                        category = None

                    chan_name = fixed_name
                    chan_limit = user_limit if user_limit else 0

                    print(f"[VoiceClaw] Creating fixed-name temporary room '{chan_name}' for {member.display_name}...")

                    bot_user = self.bot.user
                    bot_member = guild.me or (guild.get_member(bot_user.id) if bot_user else None)
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=True, read_message_history=True),
                        member: discord.PermissionOverwrite(
                            connect=True, view_channel=True, read_messages=True,
                            send_messages=True, read_message_history=True, manage_channels=True
                        )
                    }
                    if bot_member:
                        overwrites[bot_member] = discord.PermissionOverwrite(
                            connect=True, view_channel=True, read_messages=True,
                            send_messages=True, read_message_history=True, manage_channels=True
                        )

                    temp_channel = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        user_limit=chan_limit,
                        overwrites=overwrites
                    )

                    try:
                        if member.voice and member.voice.channel:
                            await member.move_to(temp_channel)
                            print(f"[VoiceClaw] Instantly moved {member.display_name} to {temp_channel.name} ({temp_channel.id})")
                        else:
                            if len(temp_channel.members) == 0:
                                await temp_channel.delete(reason="VoiceClaw: Member left before being moved")
                                return
                    except discord.HTTPException as move_err:
                        print(f"[VoiceClaw] Could not move member {member.display_name}: {move_err}")
                        if len(temp_channel.members) == 0:
                            try:
                                await temp_channel.delete(reason="VoiceClaw: Member not in voice")
                            except Exception:
                                pass
                            return

                    await self.register_temp_channel(member.id, temp_channel.id, is_permanent=0, is_locked_name=lock_name)
                    self.knock_settings[temp_channel.id] = True

                    try:
                        has_banner = os.path.exists(BANNER_PATH)
                        ctrl_view = VoiceControlLayoutView(self, member.display_avatar.url, member.display_name, has_banner=has_banner)
                        if has_banner:
                            file = discord.File(BANNER_PATH, filename="banner.jpg")
                            await temp_channel.send(file=file, view=ctrl_view)
                        else:
                            await temp_channel.send(view=ctrl_view)
                    except Exception as send_err:
                        print(f"[VoiceClaw Error] Failed to send interface message into {temp_channel.name}: {send_err}")

                    await self.log_voice_event(
                        guild,
                        title="✦ Fixed-Name Themed Room Created",
                        description=f"**Room:** `{chan_name}` ({temp_channel.mention})\n**Host:** {member.mention}\n**Fixed Name:** `Locked`",
                        color=0x5865F2
                    )

            # 4. Member Left a Voice Channel
            is_hub_join = await self.is_hub_join_channel(before.channel.id) if before.channel else False
            if before.channel and (not master_channel_id or before.channel.id != master_channel_id) and (not perm_channel_id or before.channel.id != perm_channel_id) and not is_hub_join:
                chan_id = before.channel.id
                owner_id = await self.get_channel_owner(chan_id)
                if owner_id:
                    if len(before.channel.members) == 0:
                        is_perm = await self.is_channel_permanent(chan_id)
                        if is_perm:
                            # Permanent rooms stay forever!
                            return
                        try:
                            await before.channel.delete(reason="VoiceClaw: Temporary channel empty")
                            print(f"[VoiceClaw] Cleaned up empty temporary channel {chan_id}")
                        except Exception:
                            pass
                        await self.delete_temp_channel_record(chan_id)
                        self.knock_settings.pop(chan_id, None)
                        self.afk_tracker.pop(chan_id, None)

                        await self.log_voice_event(
                            guild,
                            title="✕ Temporary Room Deleted",
                            description=f"Room `{before.channel.name}` was cleaned up after all members departed.",
                            color=0xED4245
                        )

        except Exception as e:
            print(f"[VoiceClaw Error] on_voice_state_update failed: {e}")
            traceback.print_exc()

    # --- Common Voice Channel Helper for Commands ---
    async def _require_channel_host(self, ctx: commands.Context) -> typing.Tuple[typing.Optional[discord.VoiceChannel], typing.Optional[int]]:
        voice_state = ctx.author.voice
        if not voice_state or not voice_state.channel:
            await ctx.send("✕ You must be connected to your voice room to use this command!", ephemeral=True)
            return None, None

        channel = voice_state.channel
        owner_id = await self.get_channel_owner(channel.id)
        if not owner_id:
            owner_id = ctx.author.id
            await self.register_temp_channel(ctx.author.id, channel.id)

        if ctx.author.id != owner_id and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"✕ Only the room host (<@{owner_id}>) can use this command.", ephemeral=True)
            return None, None

        return channel, owner_id

    # ==========================================
    # HYBRID & SLASH COMMANDS (/voice and .voice)
    # ==========================================

    @commands.hybrid_group(name="voice", description="VoiceClaw Dynamic Temporary Voice Engine", fallback="info", invoke_without_command=True)
    async def voice_group(self, ctx: commands.Context):
        """View info about your active temporary voice channel"""
        voice_state = ctx.author.voice
        if not voice_state or not voice_state.channel:
            return await ctx.send("✕ You are not connected to a voice channel!", ephemeral=True)

        channel = voice_state.channel
        owner_id = await self.get_channel_owner(channel.id)
        if not owner_id:
            owner_id = ctx.author.id
            await self.register_temp_channel(ctx.author.id, channel.id)

        owner = ctx.guild.get_member(owner_id)
        owner_name = owner.mention if owner else f"User ID: {owner_id}"
        limit_text = "Unlimited" if channel.user_limit == 0 else f"{len(channel.members)}/{channel.user_limit}"
        knock_mode = "Enabled" if self.knock_settings.get(channel.id, True) else "Muted"
        region_str = channel.rtc_region.capitalize() if channel.rtc_region else "Automatic"

        desc = (
            f"• **Host:** {owner_name}\n"
            f"• **Occupancy:** `{limit_text}`\n"
            f"• **Bitrate:** `{channel.bitrate // 1000} kbps`\n"
            f"• **Region:** `{region_str}`\n"
            f"• **Doorbell (Knock):** `{knock_mode}`"
        )
        view = make_v2_card(f"ℹ Room Overview • {channel.name}", desc)
        await ctx.send(view=view, ephemeral=True)

    @voice_group.command(name="lock", description="Lock your room to restrict public connections")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def v_lock(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(ctx.guild.default_role, connect=False)
        await ctx.send("🔒 **Channel locked!** Unauthorized members cannot connect (they can still knock).", ephemeral=True)

    @voice_group.command(name="unlock", description="Unlock your room to allow connections from everyone")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def v_unlock(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(ctx.guild.default_role, connect=True)
        await ctx.send("🔓 **Channel unlocked!** Public connection allowed.", ephemeral=True)

    @voice_group.command(name="ghost", description="Hide your room from the server channel sidebar")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def v_ghost(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(ctx.guild.default_role, view_channel=False, connect=False)
        await ctx.send("◈ **Ghost Mode Activated!** The room is hidden from @everyone.", ephemeral=True)

    @voice_group.command(name="reveal", description="Make your room visible on the server sidebar again")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def v_reveal(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.send("◇ **Channel revealed!** Visible on the sidebar again.", ephemeral=True)

    @voice_group.command(name="rename", description="Rename your temporary voice channel (leave blank or 'reset' to restore default)")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @app_commands.describe(name="New channel name (or leave empty to reset)")
    async def v_rename(self, ctx: commands.Context, *, name: typing.Optional[str] = None):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if await self.is_channel_locked_name(channel.id):
            return await ctx.send(
                f"✕ This voice room has a locked name (`{channel.name}`) configured by server administration and cannot be renamed.",
                ephemeral=True
            )
        if not name or name.strip().lower() in ("reset", "default"):
            clean_name = " ".join(ctx.author.display_name.split())
            new_name = f"{clean_name}'s Room"
            await self.save_user_setting(ctx.author.id, clear_name=True)
            is_reset = True
        else:
            new_name = name.strip()
            is_reset = False
            await self.save_user_setting(ctx.author.id, channel_name=new_name)

        # Discord 2 renames per 10 minutes rate limit check
        wait_sec = self.check_channel_rename_ratelimit(channel.id)
        if wait_sec:
            mins = wait_sec // 60
            secs = wait_sec % 60
            time_msg = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            return await ctx.send(
                f"⏳ **Rate Limited by Discord:** Discord strictly limits channel renames to **2 times per 10 minutes**.\n"
                f"Please wait `{time_msg}` before renaming this channel again.",
                ephemeral=True
            )

        try:
            await channel.edit(name=new_name)
            self.record_channel_rename(channel.id)
            msg = f"↺ Channel name reset to default: **{new_name}**" if is_reset else f"✦ Channel renamed to **{new_name}**"
            await ctx.send(msg, ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="↺ Room Name Reset" if is_reset else "✎ Room Renamed",
                description=f"Host {ctx.author.mention} {'reset room name to default' if is_reset else f'renamed `{channel.name}` to **{new_name}**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " in a few minutes"
                await ctx.send(f"⏳ **Discord Rate Limit:** Too many requests sent to Discord. Please try again{wait_text}.", ephemeral=True)
            else:
                await ctx.send(f"✕ Failed to rename channel: {e}", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Failed to rename channel: {e}", ephemeral=True)

    @voice_group.command(name="limit", description="Set maximum user capacity for your room (0 or leave blank to reset/unlimited)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(limit="Capacity limit (0 = Unlimited, max 99, leave empty to reset)")
    async def v_limit(self, ctx: commands.Context, limit: typing.Optional[int] = None):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if limit is None:
            guild_pref = await self.get_guild_setting(ctx.guild.id)
            limit = guild_pref[1] if guild_pref and guild_pref[1] is not None else 0
            is_reset = True
            await self.save_user_setting(ctx.author.id, clear_limit=True)
        else:
            if limit < 0 or limit > 99:
                return await ctx.send("✕ Limit must be between 0 and 99.", ephemeral=True)
            is_reset = False
            await self.save_user_setting(ctx.author.id, channel_limit=limit)

        try:
            await channel.edit(user_limit=limit)
            txt = "Unlimited" if limit == 0 else str(limit)
            msg = f"↺ User limit reset to default (**{txt}**)" if is_reset else f"✦ User limit set to **{txt}**"
            await ctx.send(msg, ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="↺ User Limit Reset" if is_reset else "⌗ User Limit Changed",
                description=f"Host {ctx.author.mention} {'reset room limit to default' if is_reset else f'set capacity of `{channel.name}` to **{txt}**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await ctx.send(f"⏳ **Rate Limited:** Discord API limit reached. Try again{wait_text}.", ephemeral=True)
            else:
                await ctx.send(f"✕ Failed to update limit: {e}", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Failed to update limit: {e}", ephemeral=True)

    @voice_group.command(name="bitrate", description="Adjust audio bitrate in kbps (leave blank to reset to default)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(kbps="Bitrate in kbps (e.g. 64, 96, 128, 256, 384, or leave empty to reset)")
    async def v_bitrate(self, ctx: commands.Context, kbps: typing.Optional[int] = None):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        max_kbps = ctx.guild.bitrate_limit // 1000
        if kbps is None:
            kbps = min(64, max_kbps)
            is_reset = True
            await self.save_user_setting(ctx.author.id, clear_bitrate=True)
        else:
            if kbps < 8 or kbps > max_kbps:
                return await ctx.send(f"✕ Bitrate must be between 8 kbps and {max_kbps} kbps for this server.", ephemeral=True)
            is_reset = False
            await self.save_user_setting(ctx.author.id, bitrate=kbps)

        try:
            await channel.edit(bitrate=kbps * 1000)
            msg = f"↺ Audio bitrate reset to default (**{kbps} kbps**)!" if is_reset else f"🔊 Audio bitrate set to **{kbps} kbps**!"
            await ctx.send(msg, ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="↺ Bitrate Reset" if is_reset else "🔊 Room Bitrate Changed",
                description=f"Host {ctx.author.mention} {'reset bitrate to default' if is_reset else f'adjusted bitrate of `{channel.name}` to **{kbps} kbps**'}.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await ctx.send(f"⏳ **Rate Limited:** Discord API limit reached. Try again{wait_text}.", ephemeral=True)
            else:
                await ctx.send(f"✕ Failed to update bitrate: {e}", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Failed to update bitrate: {e}", ephemeral=True)

    @voice_group.command(name="reset", description="Reset your voice room settings (name, limit, bitrate) back to default")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def v_reset(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        clean_name = " ".join(ctx.author.display_name.split())
        default_name = f"{clean_name}'s Room"
        guild_pref = await self.get_guild_setting(ctx.guild.id)
        default_limit = guild_pref[1] if guild_pref and guild_pref[1] is not None else 0
        default_bitrate = min(64000, ctx.guild.bitrate_limit)

        rename_wait = self.check_channel_rename_ratelimit(channel.id) if channel.name != default_name else None
        edit_kwargs = {"user_limit": default_limit, "bitrate": default_bitrate}
        if not rename_wait and channel.name != default_name:
            edit_kwargs["name"] = default_name

        try:
            await channel.edit(**edit_kwargs)
            if "name" in edit_kwargs:
                self.record_channel_rename(channel.id)
            await self.reset_user_settings(ctx.author.id)
            
            note_str = ""
            if rename_wait:
                mins = rename_wait // 60
                secs = rename_wait % 60
                t_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                note_str = f"\n\n*(Note: Name reset was deferred because Discord limits channel renames to 2 times per 10 minutes. Available in {t_str})*"

            view = discord.ui.LayoutView()
            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### ↺ Room Reset Successful\n"
                    f"• **Name:** `{channel.name if rename_wait else default_name}`\n"
                    f"• **Limit:** `{'Unlimited' if default_limit == 0 else default_limit}`\n"
                    f"• **Bitrate:** `{default_bitrate // 1000} kbps`\n\n"
                    f"All custom room preferences have been restored to defaults.{note_str}"
                ),
                accent_color=None
            )
            view.add_item(container)
            await ctx.send(view=view, ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="↺ Room Reset",
                description=f"Host {ctx.author.mention} reset settings of `{channel.name}` back to default.",
                color=0x5865F2
            )
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', None)
                wait_text = f" in `{round(retry_after, 1)}s`" if retry_after else " shortly"
                await ctx.send(f"⏳ **Rate Limited:** Discord API limit reached. Try again{wait_text}.", ephemeral=True)
            else:
                await ctx.send(f"✕ Failed to reset room: {e}", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Failed to reset room: {e}", ephemeral=True)

    @voice_group.command(name="region", description="Switch RTC datacenter region to optimize voice ping")
    @app_commands.describe(region="Voice server region")
    async def v_region(self, ctx: commands.Context, region: typing.Literal[
        "Automatic", "Singapore", "India", "Hong Kong", "Rotterdam", "US-Central", "US-East", "US-West", "Sydney", "Japan", "Brazil"
    ]):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        region_val = RTC_REGIONS_MAP.get(region)
        try:
            await channel.edit(rtc_region=region_val)
            await ctx.send(f"🌐 Voice server region set to **{region}**!", ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="🌐 Room Region Changed",
                description=f"Host {ctx.author.mention} switched RTC region of `{channel.name}` to **{region}**.",
                color=0x5865F2
            )
        except Exception as e:
            await ctx.send(f"✕ Failed to update region: {e}", ephemeral=True)

    @voice_group.command(name="activity", description="Launch Discord Activity (Watch Together or Games) in room")
    @app_commands.describe(game="Select game or activity")
    async def v_activity(self, ctx: commands.Context, game: typing.Literal[
        "YouTube Watch Together", "Chess in the Park", "Checkers in the Park", "Poker Night", "Betrayal.io", "Gartic Phone", "SpellCast", "Letter League", "Sketch Heads", "Putt Party", "Bobble League", "Rythm"
    ]):
        voice_state = ctx.author.voice
        if not voice_state or not voice_state.channel:
            return await ctx.send("✕ You must be in a voice channel to launch an activity!", ephemeral=True)
        channel = voice_state.channel
        app_id = DISCORD_ACTIVITIES.get(game)
        if not app_id:
            return await ctx.send("✕ Unknown activity.", ephemeral=True)
        try:
            invite = await channel.create_invite(
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=app_id,
                max_age=86400,
                max_uses=0,
                unique=False,
                reason=f"Activity launched by {ctx.author.name}"
            )
            btn = discord.ui.Button(label=f"🎮 Join {game}", url=invite.url, style=discord.ButtonStyle.link)
            v = discord.ui.View()
            v.add_item(btn)
            await ctx.send(
                f"### 🎮 {game}\nClick below to launch **{game}** in {channel.mention}:",
                view=v
            )
        except Exception as e:
            await ctx.send(f"✕ Could not launch activity: {e}", ephemeral=True)

    @voice_group.command(name="soundboard", description="Enable or disable soundboard audio for members in your room")
    @app_commands.describe(mode="Enable or disable soundboard")
    async def v_soundboard(self, ctx: commands.Context, mode: typing.Literal["Enable", "Disable"]):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        allow = (mode == "Enable")
        await channel.set_permissions(ctx.guild.default_role, use_soundboard=allow, use_external_sounds=allow)
        status_txt = "ENABLED" if allow else "MUTED"
        await ctx.send(f"🔊 Soundboard is now **{status_txt}** in this room.", ephemeral=True)

    @voice_group.command(name="stream", aliases=["video"], description="Enable or disable screen sharing & video in your room")
    @app_commands.describe(mode="Enable or disable screen share")
    async def v_stream(self, ctx: commands.Context, mode: typing.Literal["Enable", "Disable"]):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        allow = (mode == "Enable")
        await channel.set_permissions(ctx.guild.default_role, stream=allow)
        status_txt = "ENABLED" if allow else "MUTED"
        await ctx.send(f"📺 Screen sharing & video is now **{status_txt}** in this room.", ephemeral=True)

    @voice_group.command(name="trust", description="Grant VIP trust to a member to bypass channel lock")
    @app_commands.describe(member="Member to trust")
    async def v_trust(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(member, connect=True, view_channel=True, speak=True, stream=True)
        await ctx.send(f"👤+ **{member.mention}** is now a **Trusted Member**! They can bypass channel lock.", ephemeral=True)

    @voice_group.command(name="untrust", description="Remove trusted status from a member")
    @app_commands.describe(member="Member to untrust")
    async def v_untrust(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(member, overwrite=None)
        await ctx.send(f"👤- Removed trusted status from **{member.mention}**.", ephemeral=True)

    @voice_group.command(name="block", description="Block and banish a member from your room")
    @app_commands.describe(member="Member to block")
    async def v_block(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if member in channel.members:
            try:
                await member.move_to(None)
            except Exception:
                pass
        await channel.set_permissions(member, connect=False, view_channel=False)
        await ctx.send(f"🚫 **{member.mention}** has been blocked and removed from this room.", ephemeral=True)
        await self.log_voice_event(
            ctx.guild,
            title="🚫 Member Blocked",
            description=f"Host {ctx.author.mention} blocked {member.mention} from `{channel.name}`.",
            color=0xED4245
        )

    @voice_group.command(name="unblock", description="Unblock a previously blocked member")
    @app_commands.describe(member="Member to unblock")
    async def v_unblock(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        await channel.set_permissions(member, overwrite=None)
        await ctx.send(f"✓ **{member.mention}** has been unblocked.", ephemeral=True)

    @voice_group.command(name="kick", description="Disconnect a member from your room")
    @app_commands.describe(member="Member to kick")
    async def v_kick(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if member not in channel.members:
            return await ctx.send("✕ That member is not currently inside your room!", ephemeral=True)
        try:
            await member.move_to(None)
            await ctx.send(f"⎋ Kicked **{member.mention}** from the room.", ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="⎋ Member Kicked",
                description=f"Host {ctx.author.mention} kicked {member.mention} from `{channel.name}`.",
                color=0xED4245
            )
        except Exception as e:
            await ctx.send(f"✕ Could not kick member: {e}", ephemeral=True)

    @voice_group.command(name="claim", description="Claim ownership of the room if the previous host left")
    async def v_claim(self, ctx: commands.Context):
        voice_state = ctx.author.voice
        if not voice_state or not voice_state.channel:
            return await ctx.send("✕ You must be in the voice channel to claim it!", ephemeral=True)

        channel = voice_state.channel
        owner_id = await self.get_channel_owner(channel.id)
        if not owner_id:
            return await ctx.send("✕ This is not a VoiceClaw temporary room.", ephemeral=True)

        if ctx.author.id == owner_id:
            return await ctx.send("ℹ You are already the owner of this channel!", ephemeral=True)

        owner_member = channel.guild.get_member(owner_id)
        if owner_member and owner_member in channel.members:
            return await ctx.send(f"✕ Cannot claim: the owner {owner_member.mention} is still in the room!", ephemeral=True)

        await self.set_channel_owner(channel.id, ctx.author.id)
        await channel.set_permissions(ctx.author, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await ctx.send(f"👑 **Congratulations!** You are now the new owner of {channel.name}.")
        await self.log_voice_event(
            ctx.guild,
            title="👑 Channel Claimed",
            description=f"{ctx.author.mention} claimed ownership of `{channel.name}` (former host: <@{owner_id}>).",
            color=0xFEE75C
        )

    @voice_group.command(name="transfer", description="Transfer room ownership to another member inside the room")
    @app_commands.describe(member="Member inside your room to make host")
    async def v_transfer(self, ctx: commands.Context, member: discord.Member):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if member not in channel.members:
            return await ctx.send("✕ The target member must currently be inside the room!", ephemeral=True)
        await self.set_channel_owner(channel.id, member.id)
        await channel.set_permissions(member, connect=True, view_channel=True, read_messages=True, manage_channels=True)
        await ctx.send(f"♔ Ownership transferred to {member.mention}!")
        await self.log_voice_event(
            ctx.guild,
            title="♔ Ownership Transferred",
            description=f"Host {ctx.author.mention} transferred room `{channel.name}` to {member.mention}.",
            color=0xFEE75C
        )

    @voice_group.command(name="delete", description="Instantly delete your temporary voice room")
    async def v_delete(self, ctx: commands.Context):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        if not await self.can_delete_voice_channel(ctx.guild, ctx.author):
            return await ctx.send(
                "✕ **Voice channel deletion via command is restricted on this server.**\n"
                "Only the **Server Owner** and **Whitelisted Members/Roles** can manually delete voice rooms.\n"
                "*(Your channel will automatically delete when everyone leaves).* ",
                ephemeral=True
            )
        await ctx.send("🗑 **Deleting voice room...**", ephemeral=True)
        await self.delete_temp_channel_record(channel.id)
        self.knock_settings.pop(channel.id, None)
        try:
            await channel.delete(reason=f"Deleted by channel host {ctx.author.name}")
        except Exception:
            pass

    # ==========================================
    # VC DELETION WHITELIST & POLICY (/vcwhitelist)
    # ==========================================

    @commands.hybrid_group(name="vcwhitelist", aliases=["delete_whitelist", "delwhitelist"], description="Manage VC deletion authorization whitelist", invoke_without_command=True)
    async def del_wl_group(self, ctx: commands.Context):
        """View all members and roles whitelisted for VC deletion"""
        await self.del_wl_list(ctx)

    @del_wl_group.command(name="refresh", description="Refresh the delete whitelist overview")
    async def del_wl_refresh(self, ctx: commands.Context):
        await self.del_wl_list(ctx)

    @del_wl_group.command(name="add_user", description="Whitelist a member to allow deleting voice channels")
    @commands.has_permissions(administrator=True)
    async def del_wl_add_user(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO deleteWhitelist (guildID, targetType, targetID, addedBy) VALUES (?, 'user', ?, ?)", (ctx.guild.id, member.id, ctx.author.id))
            await db.commit()
        await ctx.send(f"✓ **{member.mention}** has been whitelisted to delete voice channels.", ephemeral=True)

    @del_wl_group.command(name="add_role", description="Whitelist a role to allow deleting voice channels")
    @commands.has_permissions(administrator=True)
    async def del_wl_add_role(self, ctx: commands.Context, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO deleteWhitelist (guildID, targetType, targetID, addedBy) VALUES (?, 'role', ?, ?)", (ctx.guild.id, role.id, ctx.author.id))
            await db.commit()
        await ctx.send(f"✓ Role **{role.mention}** has been whitelisted to delete voice channels.", ephemeral=True)

    @del_wl_group.command(name="remove_user", description="Remove a member from the VC delete whitelist")
    @commands.has_permissions(administrator=True)
    async def del_wl_rm_user(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM deleteWhitelist WHERE guildID = ? AND targetType = 'user' AND targetID = ?", (ctx.guild.id, member.id))
            await db.commit()
        await ctx.send(f"✓ Removed **{member.mention}** from VC delete whitelist.", ephemeral=True)

    @del_wl_group.command(name="remove_role", description="Remove a role from the VC delete whitelist")
    @commands.has_permissions(administrator=True)
    async def del_wl_rm_role(self, ctx: commands.Context, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM deleteWhitelist WHERE guildID = ? AND targetType = 'role' AND targetID = ?", (ctx.guild.id, role.id))
            await db.commit()
        await ctx.send(f"✓ Removed role **{role.mention}** from VC delete whitelist.", ephemeral=True)

    @del_wl_group.command(name="list", description="View all members and roles whitelisted for VC deletion")
    async def del_wl_list(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT targetType, targetID FROM deleteWhitelist WHERE guildID = ?", (ctx.guild.id,)) as cur:
                rows = await cur.fetchall()
            async with db.execute("SELECT allowPublicDelete FROM guildPolicy WHERE guildID = ?", (ctx.guild.id,)) as cur:
                pol = await cur.fetchone()
        is_public = pol and pol[0] == 1
        pol_str = "Enabled (Anyone can delete their own room)" if is_public else "Restricted (Server Owner & Whitelist only)"
        user_mentions = [f"<@{r[1]}>" for r in rows if r[0] == 'user']
        role_mentions = [f"<@&{r[1]}>" for r in rows if r[0] == 'role']
        desc = (
            f"**Current Policy:** `{pol_str}`\n\n"
            f"**Whitelisted Roles:**\n{', '.join(role_mentions) if role_mentions else 'None'}\n\n"
            f"**Whitelisted Members:**\n{', '.join(user_mentions) if user_mentions else 'None'}"
        )
        view = make_v2_card("✦ VC Delete Whitelist & Policy", desc)
        await ctx.send(view=view, ephemeral=True)

    @del_wl_group.command(name="toggle_public", description="Toggle whether regular room hosts can manually delete their rooms")
    @commands.has_permissions(administrator=True)
    async def del_wl_toggle_public(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT allowPublicDelete FROM guildPolicy WHERE guildID = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
            curr = row[0] if row else 0
            new_val = 1 if curr == 0 else 0
            await db.execute("INSERT OR REPLACE INTO guildPolicy (guildID, allowPublicDelete) VALUES (?, ?)", (ctx.guild.id, new_val))
            await db.commit()
        state_str = "Enabled (Room hosts can manually delete their room)" if new_val == 1 else "Restricted (Only Server Owner & Whitelisted can delete)"
        await ctx.send(f"✓ VC Delete Policy updated: **{state_str}**", ephemeral=True)

    @voice_group.command(name="logchannel", description="Set the voice audit log channel for server moderation (Admin only)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="Text channel to receive voice audit logs")
    async def v_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.set_guild_log_channel(ctx.guild.id, channel.id)
        await ctx.send(f"✓ Voice audit log channel set to {channel.mention}!")

    @voice_group.command(name="setup", description="Interactive setup wizard for Voice Channels and Interfaces (Admin only)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(mode="Setup mode: 'menu' (interactive dropdown), 'temp', 'perm', or 'dual'")
    async def v_setup(self, ctx: commands.Context, mode: typing.Optional[str] = None):
        await self.standalone_setup(ctx, mode=mode)

    @voice_group.command(name="interface", aliases=["panel"], description="Deploy or refresh the VoiceClaw Interface panel")
    @commands.has_permissions(administrator=True)
    async def v_interface(self, ctx: commands.Context):
        guild = ctx.guild
        guild_cfg = await self.get_guild_config(guild.id)

        cat = None
        if guild_cfg and len(guild_cfg) > 3 and guild_cfg[3]:
            cat = guild.get_channel(guild_cfg[3])

        if not cat or not isinstance(cat, discord.CategoryChannel):
            for c in guild.categories:
                if "voice" in c.name.lower() and "permanent" not in c.name.lower():
                    cat = c
                    break

        if not cat:
            cat = await guild.create_category("Voice Channels")

        existing_join_vc = discord.utils.get(cat.voice_channels, name="＋ Join to Create")
        if not existing_join_vc:
            existing_join_vc = await guild.create_voice_channel("＋ Join to Create", category=cat)

        target_chan = discord.utils.get(cat.text_channels, name="interface")
        if not target_chan:
            target_chan = await guild.create_text_channel(
                "interface",
                category=cat,
                topic="VoiceClaw Temporary Voice Channel Control Interface"
            )
            await target_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await target_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO guild (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guildID) DO UPDATE SET 
                    voiceCategoryID = excluded.voiceCategoryID,
                    voiceChannelID = COALESCE(guild.voiceChannelID, excluded.voiceChannelID),
                    interfaceChannelID = excluded.interfaceChannelID
            ''', (guild.id, ctx.author.id, existing_join_vc.id, cat.id, target_chan.id))
            await db.commit()

        try:
            async for m in target_chan.history(limit=50):
                if m.author == self.bot.user or not m.pinned:
                    try:
                        await m.delete()
                    except Exception:
                        pass
        except Exception:
            pass

        has_banner = os.path.exists(BANNER_PATH)
        ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner)
        if has_banner:
            file = discord.File(BANNER_PATH, filename="banner.jpg")
            await target_chan.send(file=file, view=ctrl_view)
        else:
            await target_chan.send(view=ctrl_view)

        await ctx.send(f"✓ VoiceClaw Interface deployed to {target_chan.mention}!", ephemeral=True)

    @voice_group.command(name="refresh", aliases=["reloadpanel"], description="Refresh and update VoiceClaw interface panels with latest layout (Admin only)")
    @commands.has_permissions(administrator=True)
    async def v_refresh(self, ctx: commands.Context):
        """Purges old panels and deploys the fresh VoiceClaw V2 interface"""
        await self.execute_full_refresh(ctx)

    async def execute_full_refresh(self, ctx: commands.Context):
        """Purges old interface panels and deploys the latest VoiceClaw V2 layout to all interface channels (Premium only)"""
        # Premium Check: Only VoiceClaw Premium users or guilds can use refresh
        if not await self.is_premium_user_or_guild(ctx.author, ctx.guild):
            prem_card = make_v2_card(
                "👑 VoiceClaw Premium Feature",
                "✕ **The `.refresh` / `/refresh` system is an exclusive VoiceClaw Premium perk!**\n\n"
                "Upgrade to VoiceClaw Premium to instantly refresh and customize control panels, unlock bulk purges, and access priority room processing.\n"
                "Use `/premium status` to check your current subscription."
            )
            if ctx.interaction:
                return await ctx.send(view=prem_card, ephemeral=True)
            else:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
                return await ctx.send(view=prem_card, delete_after=6)

        guild = ctx.guild
        guild_cfg = await self.get_guild_config(guild.id)

        target_channels = []

        # 1. Temporary JTC interface channel
        temp_iface_id = guild_cfg[4] if guild_cfg and len(guild_cfg) > 4 else None
        if temp_iface_id:
            c = guild.get_channel(temp_iface_id)
            if c and isinstance(c, discord.TextChannel) and c not in target_channels:
                target_channels.append(c)

        # 2. Permanent VC interface channel
        perm_iface_id = guild_cfg[7] if guild_cfg and len(guild_cfg) > 7 else None
        if perm_iface_id:
            c = guild.get_channel(perm_iface_id)
            if c and isinstance(c, discord.TextChannel) and c not in target_channels:
                target_channels.append(c)

        # 3. Fallback: Search for any text channel named 'interface' in voice categories
        for cat in guild.categories:
            if any(k in cat.name.lower() for k in ["voice", "permanent", "rooms", "hub"]):
                for tc in cat.text_channels:
                    if "interface" in tc.name.lower() and tc not in target_channels:
                        target_channels.append(tc)

        # 4. If current channel is named interface and not yet in list
        if isinstance(ctx.channel, discord.TextChannel) and "interface" in ctx.channel.name.lower() and ctx.channel not in target_channels:
            target_channels.append(ctx.channel)

        if not target_channels:
            return await ctx.send("✕ No active VoiceClaw interface channels found to refresh! Run `/voice setup` or `/setup` first.", ephemeral=True)

        refreshed_mentions = []
        has_banner = os.path.exists(BANNER_PATH)

        for channel in target_channels:
            try:
                # Clean up / purge old bot messages and lingering refresh calls from the interface channel
                def is_cleanup_msg(m):
                    if m.author == self.bot.user:
                        return True
                    content = m.content.strip().lower()
                    return content.startswith((".refresh", "!refresh", "/refresh", ".panel", ".interface"))

                try:
                    await channel.purge(limit=35, check=is_cleanup_msg)
                except Exception:
                    async for msg in channel.history(limit=25):
                        if is_cleanup_msg(msg):
                            try:
                                await msg.delete()
                            except Exception:
                                pass

                # Deploy the fresh modern layout view with top banner and in-panel refresh button
                ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner)
                if has_banner:
                    file = discord.File(BANNER_PATH, filename="banner.jpg")
                    await channel.send(file=file, view=ctrl_view)
                else:
                    await channel.send(view=ctrl_view)

                refreshed_mentions.append(channel.mention)
            except Exception:
                pass

        channels_text = ", ".join(refreshed_mentions) if refreshed_mentions else "None"
        card = make_v2_card(
            "✦ VoiceClaw Interfaces Refreshed",
            f"Successfully purged outdated panels and deployed the latest Discord Components V2 interface.\n\n"
            f"• **Refreshed Channels:** {channels_text}\n"
            f"• **Layout Updates:** Media banner at top, frosted anime dock with matching secondary buttons, no side colors."
        )

        if ctx.interaction:
            await ctx.send(view=card, ephemeral=True)
            async def _auto_del_interaction():
                await asyncio.sleep(3)
                try:
                    await ctx.interaction.delete_original_response()
                except Exception:
                    pass
            asyncio.create_task(_auto_del_interaction())
        else:
            try:
                await ctx.message.delete()
            except Exception:
                pass
            conf_msg = await ctx.send(view=card)
            async def _auto_del_prefix_msg(m):
                await asyncio.sleep(3)
                try:
                    await m.delete()
                except Exception:
                    pass
            asyncio.create_task(_auto_del_prefix_msg(conf_msg))

    # --- Preset Group (/preset and .preset ...) ---
    @commands.hybrid_group(name="preset", description="Manage your customized room presets", fallback="list", invoke_without_command=True)
    async def preset_group(self, ctx: commands.Context):
        """List your saved presets"""
        presets = await self.get_user_presets(ctx.author.id)
        if not presets:
            return await ctx.send("ℹ You have no saved presets yet! Use `/voice preset save <name>` or `.preset save <name>`.", ephemeral=True)
        lines = []
        for p in presets:
            lines.append(f"• **{p[0]}**: Name: `{p[1]}` | Limit: `{p[2]}` | Bitrate: `{p[3] or 64} kbps`")
        desc = "\n".join(lines) + "\n\n*Load a preset with `/voice preset load <name>`*"
        view = make_v2_card(f"💾 Saved Presets for {ctx.author.display_name}", desc)
        await ctx.send(view=view, ephemeral=True)

    @preset_group.command(name="refresh", description="Refresh your saved presets list")
    async def p_refresh(self, ctx: commands.Context):
        await self.preset_group(ctx)

    @preset_group.command(name="save", description="Save your current room configuration as a preset")
    @app_commands.describe(name="Preset identifier name (e.g. Gaming, Chill)")
    async def p_save(self, ctx: commands.Context, name: str):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        bitrate_kbps = channel.bitrate // 1000
        await self.save_user_preset(
            user_id=ctx.author.id,
            preset_name=name.strip(),
            channel_name=channel.name,
            channel_limit=channel.user_limit,
            bitrate=bitrate_kbps
        )
        await ctx.send(
            f"💾 **Preset '{name}' Saved!**\n"
            f"• **Name:** `{channel.name}`\n"
            f"• **Limit:** `{channel.user_limit if channel.user_limit > 0 else 'Unlimited'}`\n"
            f"• **Bitrate:** `{bitrate_kbps} kbps`",
            ephemeral=True
        )

    @preset_group.command(name="load", description="Apply a saved preset to your active room")
    @app_commands.describe(name="Preset name to load")
    async def p_load(self, ctx: commands.Context, name: str):
        channel, owner_id = await self._require_channel_host(ctx)
        if not channel: return
        preset = await self.get_user_preset(ctx.author.id, name.strip())
        if not preset:
            return await ctx.send(f"✕ Preset '{name}' not found. Use `/voice preset list` to view saved profiles.", ephemeral=True)

        p_name, chan_name, limit, bitrate = preset
        edit_kwargs = {}
        if chan_name and not await self.is_channel_locked_name(channel.id):
            edit_kwargs["name"] = chan_name
        if limit is not None: edit_kwargs["user_limit"] = limit
        if bitrate: edit_kwargs["bitrate"] = min(bitrate * 1000, ctx.guild.bitrate_limit)

        try:
            await channel.edit(**edit_kwargs)
            await self.save_user_setting(ctx.author.id, channel_name=chan_name, channel_limit=limit, bitrate=bitrate)
            await ctx.send(f"📂 Applied preset **{p_name}** to your room!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Failed to apply preset: {e}", ephemeral=True)

    @preset_group.command(name="delete", description="Delete a saved preset")
    @app_commands.describe(name="Preset name to delete")
    async def p_delete(self, ctx: commands.Context, name: str):
        await self.delete_user_preset(ctx.author.id, name.strip())
        await ctx.send(f"✓ Preset '{name}' deleted.", ephemeral=True)

    # ==========================================
    # PERMANENT VOICE COMMANDS (/permanent and .permanent)
    # ==========================================
    @commands.hybrid_group(name="permanent", aliases=["perm"], description="Manage your permanent custom voice room", fallback="info", invoke_without_command=True)
    async def perm_group(self, ctx: commands.Context):
        """View your permanent voice channel status"""
        existing_perms = await self.get_user_permanent_channels(ctx.guild.id, ctx.author.id)
        if not existing_perms:
            return await ctx.send("ℹ You do not currently own any permanent rooms. Join `＋ Create Permanent VC` or use `/permanent create <name>` to make one!", ephemeral=True)

        lines = []
        for idx, chan in enumerate(existing_perms, 1):
            limit_str = chan.user_limit if chan.user_limit > 0 else 'Unlimited'
            lines.append(f"**{idx}.** {chan.mention} (`{chan.name}`) • Limit: `{limit_str}` • Bitrate: `{chan.bitrate // 1000} kbps`")

        desc = "\n".join(lines) + "\n\nThese rooms remain active 24/7 even when empty. Control them using the interface panel!"
        view = make_v2_card(f"Permanent Voice Rooms ({len(existing_perms)}/3)", desc)
        await ctx.send(view=view, ephemeral=True)

    @perm_group.command(name="refresh", description="Refresh your permanent voice channel overview")
    async def perm_refresh(self, ctx: commands.Context):
        await self.perm_group(ctx)

    @perm_group.command(name="create", description="Create your own permanent custom voice room")
    @app_commands.describe(name="Name for your permanent voice room")
    async def perm_create(self, ctx: commands.Context, *, name: str):
        existing_perms = await self.get_user_permanent_channels(ctx.guild.id, ctx.author.id)
        if len(existing_perms) >= 3:
            return await ctx.send(f"✕ You already own {len(existing_perms)} permanent rooms! (Maximum limit: 3 permanent rooms per user).", ephemeral=True)

        guild_cfg = await self.get_guild_config(ctx.guild.id)
        perm_cat_id = guild_cfg[6] if guild_cfg and len(guild_cfg) > 6 else None
        category = ctx.guild.get_channel(perm_cat_id) if perm_cat_id else None

        if not category:
            for c in ctx.guild.categories:
                if "permanent" in c.name.lower():
                    category = c
                    break

        if not category:
            category = await ctx.guild.create_category("Permanent Rooms")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, permCategoryID)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guildID) DO UPDATE SET permCategoryID = excluded.permCategoryID
                ''', (ctx.guild.id, ctx.author.id, category.id))
                await db.commit()

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, read_message_history=True),
            ctx.author: discord.PermissionOverwrite(
                connect=True, view_channel=True, read_messages=True,
                send_messages=True, read_message_history=True, manage_channels=True
            )
        }
        if ctx.guild.me:
            overwrites[ctx.guild.me] = discord.PermissionOverwrite(
                connect=True, view_channel=True, read_messages=True,
                send_messages=True, read_message_history=True, manage_channels=True
            )

        chan_name = name.strip()
        perm_chan = await ctx.guild.create_voice_channel(
            name=chan_name,
            category=category,
            overwrites=overwrites
        )

        await self.register_temp_channel(ctx.author.id, perm_chan.id, is_permanent=1)
        self.knock_settings[perm_chan.id] = True

        if ctx.author.voice and ctx.author.voice.channel:
            try:
                await ctx.author.move_to(perm_chan)
            except Exception:
                pass

        try:
            has_banner = os.path.exists(BANNER_PATH)
            ctrl_view = VoiceControlLayoutView(self, ctx.author.display_avatar.url, ctx.author.display_name, has_banner=has_banner)
            if has_banner:
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await perm_chan.send(
                    content="### Permanent Voice Room\nUse the buttons below to manage your channel.",
                    file=file,
                    view=ctrl_view
                )
            else:
                await perm_chan.send(
                    content="### Permanent Voice Room\nUse the buttons below to manage your channel.",
                    view=ctrl_view
                )
        except Exception:
            pass

        await ctx.send(f"✓ Permanent room created: {perm_chan.mention}", ephemeral=True)
        await self.log_voice_event(
            ctx.guild,
            title="Permanent Room Created",
            description=f"Host {ctx.author.mention} created permanent room `{chan_name}` ({perm_chan.mention}).",
            color=0xFEE75C
        )

    @perm_group.command(name="delete", description="Delete your permanent voice room")
    async def perm_delete(self, ctx: commands.Context):
        existing_perms = await self.get_user_permanent_channels(ctx.guild.id, ctx.author.id)
        if not existing_perms:
            return await ctx.send("✕ You do not own an active permanent room.", ephemeral=True)

        if len(existing_perms) == 1:
            chan = existing_perms[0]
            chan_name = chan.name
            await self.delete_temp_channel_record(chan.id)
            self.knock_settings.pop(chan.id, None)
            self.afk_tracker.pop(chan.id, None)
            try:
                await chan.delete(reason=f"Deleted by permanent room owner {ctx.author.name}")
            except Exception:
                pass
            await ctx.send(f"✓ Your permanent voice room `{chan_name}` has been deleted.", ephemeral=True)
            await self.log_voice_event(
                ctx.guild,
                title="Permanent Room Deleted",
                description=f"Host {ctx.author.mention} deleted their permanent room `{chan_name}`.",
                color=0xED4245
            )
        else:
            view = DeleteChannelSelectView(self, existing_perms)
            await ctx.send("### 🗑️ Delete Permanent Voice Room\nYou own multiple permanent rooms. Select which room you want to delete:", view=view, ephemeral=True)

    @perm_group.command(name="interface", aliases=["panel"], description="Deploy or refresh the VoiceClaw Interface panel in the Permanent category (Admin only)")
    @commands.has_permissions(administrator=True)
    async def perm_interface(self, ctx: commands.Context):
        guild = ctx.guild
        guild_cfg = await self.get_guild_config(guild.id)
        perm_cat_id = guild_cfg[6] if guild_cfg and len(guild_cfg) > 6 else None

        cat = None
        if perm_cat_id:
            cat = guild.get_channel(perm_cat_id)

        if not cat or not isinstance(cat, discord.CategoryChannel):
            for c in guild.categories:
                if "permanent" in c.name.lower():
                    cat = c
                    perm_cat_id = c.id
                    break

        if not cat:
            cat = await guild.create_category("Permanent Rooms")
            perm_cat_id = cat.id

        existing_perm_vc = discord.utils.get(cat.voice_channels, name="＋ Create Permanent VC")
        if not existing_perm_vc:
            existing_perm_vc = await guild.create_voice_channel("＋ Create Permanent VC", category=cat)

        target_chan = discord.utils.get(cat.text_channels, name="interface")
        if not target_chan:
            target_chan = await guild.create_text_channel(
                "interface",
                category=cat,
                topic="VoiceClaw Permanent Voice Channel Control Interface"
            )
            await target_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await target_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute('''
                    INSERT INTO guild (guildID, ownerID, permCategoryID, permChannelID, permInterfaceID)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(guildID) DO UPDATE SET 
                        permCategoryID = excluded.permCategoryID,
                        permChannelID = excluded.permChannelID,
                        permInterfaceID = excluded.permInterfaceID
                ''', (guild.id, ctx.author.id, cat.id, existing_perm_vc.id, target_chan.id))
                await db.commit()
            except Exception:
                pass

        try:
            async for m in target_chan.history(limit=50):
                if m.author == self.bot.user or not m.pinned:
                    try:
                        await m.delete()
                    except Exception:
                        pass
        except Exception:
            pass

        has_banner = os.path.exists(BANNER_PATH)
        ctrl_view = VoiceControlLayoutView(self, has_banner=has_banner)
        if has_banner:
            file = discord.File(BANNER_PATH, filename="banner.jpg")
            await target_chan.send(file=file, view=ctrl_view)
        else:
            await target_chan.send(view=ctrl_view)

        await ctx.send(f"✓ Permanent Interface panel deployed to {target_chan.mention}!", ephemeral=True)

    # ==========================================
    # FIXED-NAME THEMED HUBS (/hub and .hub ...)
    # ==========================================

    @commands.hybrid_group(name="hub", description="Manage Fixed-Name Themed Temp VC Hubs (Admin only)", fallback="list", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def hub_group(self, ctx: commands.Context):
        """List all active fixed-name hubs in this server"""
        await self.hub_list_overview(ctx)

    @hub_group.command(name="refresh", description="Refresh the themed hubs overview")
    @commands.has_permissions(administrator=True)
    async def hub_refresh(self, ctx: commands.Context):
        await self.hub_list_overview(ctx)

    async def hub_list_overview(self, ctx: commands.Context):
        hubs = await self.get_guild_hubs(ctx.guild.id)
        if not hubs:
            return await ctx.send("ℹ️ No Fixed-Name Hubs are configured in this server. Use `/hub create` to set one up!", ephemeral=True)

        h_lines = []
        for h in hubs:
            hub_id, g_id, cat_id, join_id, iface_id, fixed_name, limit, lock_name = h
            cat = ctx.guild.get_channel(cat_id)
            join_ch = ctx.guild.get_channel(join_id)
            cat_str = cat.name if cat else f"Category ID {cat_id}"
            join_str = join_ch.mention if join_ch else f"Channel ID {join_id}"
            h_lines.append(
                f"**Hub #{hub_id}: {fixed_name}**\n"
                f"• **Category:** `{cat_str}`\n"
                f"• **Join Channel:** {join_str}\n"
                f"• **Fixed Room Name:** `{fixed_name}`\n"
                f"• **Default Capacity:** `{limit if limit > 0 else 'Unlimited'}`\n"
                f"• **Renaming Locked:** `{'Yes' if lock_name else 'No'}`\n"
            )
        desc = "All active category hubs where voice channels have locked/preset names:\n\n" + "\n".join(h_lines)
        if os.path.exists(HUBS_BANNER_PATH):
            view = make_v2_card("🏷️ Fixed-Name Themed VC Hubs", desc, banner_filename="hubs.jpg")
            file = discord.File(HUBS_BANNER_PATH, filename="hubs.jpg")
            await ctx.send(file=file, view=view, ephemeral=True)
        else:
            view = make_v2_card("🏷️ Fixed-Name Themed VC Hubs", desc)
            await ctx.send(view=view, ephemeral=True)

    @hub_group.command(name="create", aliases=["setup"], description="Create a new Fixed-Name Themed Temp VC Hub")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        fixed_name="Fixed channel name every created room will have (e.g. Gaming or Minecraft)",
        category_name="Optional custom category name (defaults to '🎮 <fixed_name> Hub')",
        join_name="Optional join-to-create channel name (defaults to '＋ Create VC')",
        user_limit="Optional default user capacity (0 = Unlimited)"
    )
    async def hub_create(
        self,
        ctx: commands.Context,
        fixed_name: typing.Optional[str] = None,
        category_name: typing.Optional[str] = None,
        join_name: typing.Optional[str] = None,
        user_limit: typing.Optional[int] = 0
    ):
        if not fixed_name and ctx.interaction:
            return await ctx.interaction.response.send_modal(HubSetupModal(self))

        if not fixed_name:
            return await ctx.send("✕ Please specify the fixed room name (e.g. `/hub create fixed_name:Gaming` or `.hub create Gaming`).", ephemeral=True)

        guild = ctx.guild
        cat_name = category_name or f"🎮 {fixed_name} Hub"
        j_name = join_name or "＋ Create VC"
        limit = user_limit if user_limit and user_limit > 0 else 0

        if hasattr(ctx, "defer"):
            try:
                await ctx.defer()
            except Exception:
                pass

        try:
            new_cat = await guild.create_category(cat_name)
            interface_chan = await guild.create_text_channel(
                "interface",
                category=new_cat,
                topic=f"VoiceClaw Control Interface for {fixed_name} Rooms"
            )
            await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
            await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

            join_chan = await guild.create_voice_channel(j_name, category=new_cat)

            ctrl_view = VoiceControlLayoutView(self, has_banner=os.path.exists(BANNER_PATH))
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                await interface_chan.send(file=file, view=ctrl_view)
            else:
                await interface_chan.send(view=ctrl_view)

            await self.create_voice_hub(
                guild_id=guild.id,
                category_id=new_cat.id,
                join_channel_id=join_chan.id,
                interface_channel_id=interface_chan.id,
                fixed_name=fixed_name,
                user_limit=limit,
                lock_name=1
            )

            desc = (
                f"• **Category:** `{new_cat.name}`\n"
                f"• **Join Channel:** {join_chan.mention}\n"
                f"• **Interface:** {interface_chan.mention}\n"
                f"• **Fixed Room Name:** `{fixed_name}` *(Locked from renaming)*\n"
                f"• **Default Capacity:** `{limit if limit > 0 else 'Unlimited'}`\n\n"
                f"Anyone joining {join_chan.mention} will get a temporary room named **`{fixed_name}`** that auto-deletes when empty!"
            )
            view = make_v2_card("✦ Fixed-Name Themed Hub Created", desc)
            await ctx.send(view=view)
        except Exception as e:
            await ctx.send(f"✕ Hub creation failed: {e}", ephemeral=True)

    @hub_group.command(name="delete", description="Delete a Fixed-Name Themed VC Hub")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(join_channel="The join-to-create channel of the hub to remove")
    async def hub_delete(self, ctx: commands.Context, join_channel: discord.VoiceChannel):
        hub = await self.get_voice_hub(join_channel.id)
        if not hub:
            return await ctx.send(f"✕ {join_channel.mention} is not registered as a Fixed-Name Hub.", ephemeral=True)

        await self.delete_voice_hub_by_join(join_channel.id)
        await ctx.send(f"✓ Fixed-Name Hub for {join_channel.mention} (`{hub[5]}`) has been deleted from bot database.", ephemeral=True)

    # ==========================================
    # STANDALONE HYBRID COMMANDS (/knock and /leaderboard)
    # ==========================================

    @commands.hybrid_command(name="knock", description="Request permission to join a locked or ghosted voice room")
    @app_commands.describe(target="Host or member inside the locked room")
    async def knock_cmd(self, ctx: commands.Context, target: typing.Optional[discord.Member] = None):
        user = ctx.author
        now = time.time()
        if user.id in self.knock_cooldowns and (now - self.knock_cooldowns[user.id]) < 30:
            rem = int(30 - (now - self.knock_cooldowns[user.id]))
            return await ctx.send(f"⏳ Please wait {rem} seconds before knocking again.", ephemeral=True)

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
            return await ctx.send("❓ Please mention the room host or a member inside the room! (e.g. `/knock @Host` or `.knock @Host`)", ephemeral=True)

        if user in target_channel.members:
            return await ctx.send("ℹ You are already inside that voice channel!", ephemeral=True)

        if not self.knock_settings.get(target_channel.id, True):
            return await ctx.send("✕ This room has Knock Mode disabled (Do Not Disturb).", ephemeral=True)

        self.knock_cooldowns[user.id] = now

        doorbell_view = KnockResponseView(self, target_channel, user, owner_id)
        await target_channel.send(content=f"<@{owner_id}>", view=doorbell_view)
        await ctx.send(f"⌬ Knock sent to **{target_channel.name}**! Waiting for host response...", ephemeral=True)

    @commands.hybrid_command(name="leaderboard", aliases=["top"], description="View top active voice chatter rankings in the server")
    async def leaderboard_cmd(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT userID, totalSeconds FROM voiceTime WHERE guildID = ? ORDER BY totalSeconds DESC LIMIT 10",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await ctx.send("📊 No voice activity recorded in this server yet! Join a voice room to get on the board.", ephemeral=True)

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for rank, (uid, sec) in enumerate(rows, start=1):
            badge = medals[rank - 1] if rank <= 3 else f"`#{rank}`"
            hours = sec // 3600
            mins = (sec % 3600) // 60
            time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            lines.append(f"{badge} <@{uid}> — **{time_str}**")

        desc = "\n".join(lines) + "\n\n*Tracks total active voice chat time in the server*"
        view = make_v2_card(f"🏆 Voice Activity Leaderboard • {ctx.guild.name}", desc)
        await ctx.send(view=view)

    @commands.hybrid_command(name="interface", aliases=["panel"], description="Deploy or refresh the VoiceClaw Interface panel (Admin only)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(system="Which system interface to deploy ('temp' or 'perm')")
    async def standalone_interface(self, ctx: commands.Context, system: typing.Optional[str] = None):
        choice = (system or "").lower().strip()
        is_perm = False
        if choice in ["perm", "permanent"]:
            is_perm = True
        elif choice in ["temp", "temporary"]:
            is_perm = False
        elif ctx.channel.category and "permanent" in ctx.channel.category.name.lower():
            is_perm = True

        if is_perm:
            await self.perm_interface(ctx)
        else:
            await self.v_interface(ctx)

    @commands.hybrid_command(name="refresh", aliases=["reloadpanel", "refreshpanel", "fixpanel", "updatepanel"], description="Refresh and update all VoiceClaw panels & interfaces with latest features (Admin only)")
    @commands.has_permissions(administrator=True)
    async def standalone_refresh(self, ctx: commands.Context):
        """Refreshes and redeploys the latest VoiceClaw panels across the server"""
        await self.execute_full_refresh(ctx)

    @commands.hybrid_command(name="setup", description="Interactive setup wizard for Voice Channels and Interfaces (Admin only)")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(mode="Setup mode: 'menu' (interactive dropdown), 'temp', 'perm', or 'dual'")
    @app_commands.choices(mode=[
        app_commands.Choice(name="✦ Interactive Setup Wizard (Dropdown Menu)", value="menu"),
        app_commands.Choice(name="🌀 Temporary Dynamic Voice (JTC)", value="temp"),
        app_commands.Choice(name="👑 Permanent 24/7 Voice Rooms", value="perm"),
        app_commands.Choice(name="🌟 Dual Setup (Both Temp & Perm)", value="dual"),
        app_commands.Choice(name="🏷️ Fixed-Name Themed Hub", value="hub"),
    ])
    async def standalone_setup(self, ctx: commands.Context, mode: typing.Optional[str] = None):
        choice = (mode or "menu").lower().strip()
        if choice in ["menu", "wizard", "select"]:
            view = SetupLayoutView(self, ctx.author.id)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                return await ctx.send(file=file, view=view)
            else:
                return await ctx.send(view=view)

        if choice in ["hub", "fixed", "themed"]:
            if ctx.interaction:
                return await ctx.interaction.response.send_modal(HubSetupModal(self))
            else:
                return await ctx.send("Use `/hub create` to configure a Fixed-Name Themed Hub.", ephemeral=True)

        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        if choice in ["temp", "temporary", "quick"]:
            temp_cat, temp_chan, interface_chan = await self.perform_temp_setup(ctx.guild, ctx.author.id)
            desc = (
                f"• **Category:** `{temp_cat.name}`\n"
                f"• **Join Channel:** {temp_chan.mention}\n"
                f"• **Interface Panel:** {interface_chan.mention}\n\n"
                f"Join {temp_chan.mention} to start your dynamic temporary voice room, and control it from {interface_chan.mention}!"
            )
            view = make_v2_card("✦ Temporary Voice Setup Complete", desc, banner_filename="banner.jpg" if os.path.exists(BANNER_PATH) else None)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                return await ctx.send(file=file, view=view)
            return await ctx.send(view=view)

        elif choice in ["perm", "permanent"]:
            perm_cat, perm_chan, perm_interface = await self.perform_perm_setup(ctx.guild, ctx.author.id)
            desc = (
                f"• **Category:** `{perm_cat.name}`\n"
                f"• **Create Channel:** {perm_chan.mention}\n"
                f"• **Interface Panel:** {perm_interface.mention}\n\n"
                f"Join {perm_chan.mention} to claim your permanent voice room!"
            )
            view = make_v2_card("✦ Permanent Voice Setup Complete", desc, banner_filename="banner.jpg" if os.path.exists(BANNER_PATH) else None)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                return await ctx.send(file=file, view=view)
            return await ctx.send(view=view)

        elif choice in ["dual", "both", "all"]:
            temp_cat, temp_chan, interface_chan, perm_cat, perm_chan, perm_interface = await self.perform_dual_setup(ctx.guild, ctx.author.id)
            desc = (
                f"**🌀 Temporary Voice System:**\n"
                f"• Category: `{temp_cat.name}`\n"
                f"• Join Channel: {temp_chan.mention}\n"
                f"• Interface Panel: {interface_chan.mention}\n\n"
                f"**✦ Permanent Voice System:**\n"
                f"• Category: `{perm_cat.name}`\n"
                f"• Create Channel: {perm_chan.mention}\n"
                f"• Interface Panel: {perm_interface.mention}\n\n"
                f"All voice channels & control interfaces are fully configured and ready!"
            )
            view = make_v2_card("✦ VoiceClaw Dual Voice Setup Complete", desc, banner_filename="banner.jpg" if os.path.exists(BANNER_PATH) else None)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                return await ctx.send(file=file, view=view)
            return await ctx.send(view=view)

        else:
            view = SetupLayoutView(self, ctx.author.id)
            if os.path.exists(BANNER_PATH):
                file = discord.File(BANNER_PATH, filename="banner.jpg")
                return await ctx.send(file=file, view=view)
            else:
                return await ctx.send(view=view)

    # ==========================================
    # STANDALONE PREFIX ALIAS SHORTCUTS (.lock, .unlock, etc.)
    # ==========================================

    @commands.command(name="lock")
    async def p_lock_alias(self, ctx):
        await self.v_lock(ctx)

    @commands.command(name="unlock")
    async def p_unlock_alias(self, ctx):
        await self.v_unlock(ctx)

    @commands.command(name="ghost")
    async def p_ghost_alias(self, ctx):
        await self.v_ghost(ctx)

    @commands.command(name="reveal")
    async def p_reveal_alias(self, ctx):
        await self.v_reveal(ctx)

    @commands.command(name="rename")
    async def p_rename_alias(self, ctx, *, name: str):
        await self.v_rename(ctx, name=name)

    @commands.command(name="limit")
    async def p_limit_alias(self, ctx, limit: int):
        await self.v_limit(ctx, limit=limit)

    @commands.command(name="bitrate")
    async def p_bitrate_alias(self, ctx, kbps: int):
        await self.v_bitrate(ctx, kbps=kbps)

    @commands.command(name="region")
    async def p_region_alias(self, ctx, region: str):
        matched = None
        for k in RTC_REGIONS_MAP.keys():
            if k.lower() == region.lower():
                matched = k
                break
        if not matched:
            regions_list = ", ".join(RTC_REGIONS_MAP.keys())
            return await ctx.send(f"✕ Invalid region. Available: `{regions_list}`")
        await self.v_region(ctx, region=matched)

    @commands.command(name="activity")
    async def p_activity_alias(self, ctx, *, game: str):
        matched = None
        for k in DISCORD_ACTIVITIES.keys():
            if game.lower() in k.lower():
                matched = k
                break
        if not matched:
            activities_list = ", ".join(DISCORD_ACTIVITIES.keys())
            return await ctx.send(f"✕ Activity not found. Available: `{activities_list}`")
        await self.v_activity(ctx, game=matched)

    @commands.command(name="soundboard")
    async def p_soundboard_alias(self, ctx, mode: str):
        m = "Enable" if mode.lower() in ["enable", "on", "true", "allow"] else "Disable"
        await self.v_soundboard(ctx, mode=m)

    @commands.command(name="stream", aliases=["video"])
    async def p_stream_alias(self, ctx, mode: str):
        m = "Enable" if mode.lower() in ["enable", "on", "true", "allow"] else "Disable"
        await self.v_stream(ctx, mode=m)

    @commands.command(name="trust")
    async def p_trust_alias(self, ctx, member: discord.Member):
        await self.v_trust(ctx, member=member)

    @commands.command(name="untrust")
    async def p_untrust_alias(self, ctx, member: discord.Member):
        await self.v_untrust(ctx, member=member)

    @commands.command(name="block")
    async def p_block_alias(self, ctx, member: discord.Member):
        await self.v_block(ctx, member=member)

    @commands.command(name="unblock")
    async def p_unblock_alias(self, ctx, member: discord.Member):
        await self.v_unblock(ctx, member=member)

    @commands.command(name="kick")
    async def p_kick_alias(self, ctx, member: discord.Member):
        await self.v_kick(ctx, member=member)

    @commands.command(name="claim")
    async def p_claim_alias(self, ctx):
        await self.v_claim(ctx)

    @commands.command(name="transfer")
    async def p_transfer_alias(self, ctx, member: discord.Member):
        await self.v_transfer(ctx, member=member)

    @commands.command(name="delete")
    async def p_delete_alias(self, ctx):
        await self.v_delete(ctx)


    @commands.hybrid_command(name="help", aliases=["guide", "systemguide", "helpmenu"], description="VoiceClaw setup, management & system guide")
    @app_commands.describe(category="Select guide category (optional)")
    @app_commands.choices(category=[
        app_commands.Choice(name="✦ System Overview", value="overview"),
        app_commands.Choice(name="✦ Bot Setup Guide (/setup)", value="setup"),
        app_commands.Choice(name="✦ Themed Hubs (/hub)", value="hubs"),
        app_commands.Choice(name="✦ Permanent Rooms & Presets", value="permanent"),
        app_commands.Choice(name="✦ Maintenance & Logs", value="maintenance"),
        app_commands.Choice(name="✦ Voice Interface (JTC)", value="interface"),
        app_commands.Choice(name="✦ Server Profile & Reset (/bot)", value="profile"),
        app_commands.Choice(name="✦ Premium & Moderation", value="premium"),
    ])
    async def help_cmd(self, ctx: commands.Context, category: typing.Optional[str] = "overview"):
        """VoiceClaw setup, management & system guide powered by Discord Components v2"""
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass
        elif hasattr(ctx, "typing"):
            try:
                await ctx.typing()
            except Exception:
                pass

        target_cat = category or "overview"
        view = HelpLayoutView(category=target_cat)
        if os.path.exists(GUIDE_BANNER_PATH):
            file = discord.File(GUIDE_BANNER_PATH, filename="guide.jpg")
            await ctx.send(file=file, view=view)
        else:
            await ctx.send(view=view)


    # ==========================================
    # VOICECLAW PREMIUM SYSTEM & COMMANDS
    # ==========================================

    @commands.hybrid_group(name="premium", description="VoiceClaw Premium status & management", invoke_without_command=True)
    async def premium_group(self, ctx: commands.Context):
        """Check VoiceClaw Premium status for this server"""
        await self.premium_status(ctx)

    @premium_group.command(name="status", description="Check VoiceClaw Premium status for this server")
    async def premium_status(self, ctx: commands.Context):
        is_prem = await self.is_guild_premium(ctx.guild)
        status_text = "✦ ACTIVE (VoiceClaw Premium Server)" if is_prem else "✕ INACTIVE (Free Server)"
        desc = (
            f"**Server:** `{ctx.guild.name}`\n"
            f"**Status:** `{status_text}`\n\n"
            f"**Unlocked Features:**\n"
            f"• **Custom Server Bot Profile:** Custom Avatar, Banner & Bio (`/bot`)\n"
            f"• **Advanced Purge:** Bulk purge with Role/User whitelist (`/purge`)\n"
            f"• **High-Fidelity Audio:** Enhanced audio bitrate support\n"
            f"• **Priority Processing:** Zero delay Join-to-Create room generation"
        )
        if os.path.exists(PREMIUM_BANNER_PATH):
            view = make_v2_card("✦ VoiceClaw Premium Status", desc, banner_filename="premium.jpg")
            file = discord.File(PREMIUM_BANNER_PATH, filename="premium.jpg")
            await ctx.send(file=file, view=view, ephemeral=True)
        else:
            view = make_v2_card("✦ VoiceClaw Premium Status", desc)
            await ctx.send(view=view, ephemeral=True)

    @premium_group.command(name="grant_user", description="Grant Premium status to a user (Bot Owner only)")
    @app_commands.describe(user="User or Member to grant Premium to", plan="Plan name or duration (e.g. Lifetime, 1 Year)")
    async def prem_grant_user(self, ctx: commands.Context, user: discord.User, plan: typing.Optional[str] = "Lifetime"):
        if not await self.is_bot_owner(ctx.author):
            return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.", ephemeral=True)
        target_plan = plan or "Lifetime"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO premiumUsers (userID, plan, grantedBy) VALUES (?, ?, ?)", (user.id, target_plan, ctx.author.id))
            await db.commit()
        desc = (
            f"Successfully granted **VoiceClaw Premium ({target_plan})** to {user.mention} (`{user.id}`)!\n\n"
            f"✦ **Perk:** Any Discord server owned by {user.mention} is now automatically recognized as **Premium**."
        )
        view = make_v2_card("👑 VoiceClaw Premium Granted", desc)
        await ctx.send(view=view, ephemeral=False)

    @premium_group.command(name="grant_server", description="Grant Premium status to a Discord server (Bot Owner only)")
    @app_commands.describe(server_id="Discord server ID to grant Premium to", plan="Plan name or duration (e.g. Lifetime, 1 Year)")
    async def prem_grant_server(self, ctx: commands.Context, server_id: str, plan: typing.Optional[str] = "Lifetime"):
        if not await self.is_bot_owner(ctx.author):
            return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.", ephemeral=True)
        try:
            gid = int(server_id.strip())
        except ValueError:
            return await ctx.send("✕ Invalid server ID provided.", ephemeral=True)
        target_plan = plan or "Lifetime"
        target_guild = self.bot.get_guild(gid)
        g_name = target_guild.name if target_guild else f"Server ID {gid}"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO premiumGuilds (guildID, plan, grantedBy) VALUES (?, ?, ?)", (gid, target_plan, ctx.author.id))
            await db.commit()
        desc = (
            f"Successfully activated **VoiceClaw Premium ({target_plan})** for **{g_name}** (`{gid}`)!\n\n"
            f"✦ Unlocked custom bot profile (`/bot`), bulk `/purge`, and full premium voice features."
        )
        view = make_v2_card("👑 VoiceClaw Premium Activated", desc)
        await ctx.send(view=view, ephemeral=False)

    @premium_group.command(name="revoke_user", description="Revoke Premium status from a user (Bot Owner only)")
    @app_commands.describe(user="User or Member to revoke Premium from")
    async def prem_revoke_user(self, ctx: commands.Context, user: discord.User):
        if not await self.is_bot_owner(ctx.author):
            return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM premiumUsers WHERE userID = ?", (user.id,))
            await db.commit()
        await ctx.send(f"✓ Revoked VoiceClaw Premium from {user.mention} (`{user.id}`).", ephemeral=True)

    @premium_group.command(name="revoke_server", description="Revoke Premium status from a server (Bot Owner only)")
    @app_commands.describe(server_id="Discord server ID to revoke Premium from")
    async def prem_revoke_server(self, ctx: commands.Context, server_id: str):
        if not await self.is_bot_owner(ctx.author):
            return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.", ephemeral=True)
        try:
            gid = int(server_id.strip())
        except ValueError:
            return await ctx.send("✕ Invalid server ID provided.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM premiumGuilds WHERE guildID = ?", (gid,))
            await db.commit()
        await ctx.send(f"✓ Revoked VoiceClaw Premium from server `{gid}`.", ephemeral=True)

    @premium_group.command(name="list", description="List all active Premium users and servers (Bot Owner only)")
    async def prem_list(self, ctx: commands.Context):
        if not await self.is_bot_owner(ctx.author):
            return await ctx.send("✕ This command is reserved exclusively for the Bot Developer / Owner.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT userID, plan, addedAt FROM premiumUsers") as cur:
                users = await cur.fetchall()
            async with db.execute("SELECT guildID, plan, addedAt FROM premiumGuilds") as cur:
                guilds = await cur.fetchall()
        u_lines = [f"• <@{u[0]}> (`{u[0]}`) — Plan: `{u[1]}`" for u in users]
        g_lines = [f"• Server `{g[0]}` — Plan: `{g[1]}`" for g in guilds]
        desc = (
            f"**Premium Users ({len(users)}):**\n{chr(10).join(u_lines) if u_lines else 'None'}\n\n"
            f"**Premium Servers ({len(guilds)}):**\n{chr(10).join(g_lines) if g_lines else 'None'}"
        )
        view = make_v2_card("👑 VoiceClaw Premium Directory", desc)
        await ctx.send(view=view, ephemeral=True)

    # ==========================================
    # CUSTOM SERVER BOT PROFILE (PREMIUM ONLY)
    # ==========================================

    @commands.hybrid_group(name="bot", description="Customize VoiceClaw server profile (VoiceClaw Premium)", invoke_without_command=True)
    async def b_profile_group(self, ctx: commands.Context):
        """View custom bot profile for this server"""
        await self.b_profile_view(ctx)

    @b_profile_group.command(name="nickname", description="Change bot's nickname in this server (Premium)")
    @commands.has_permissions(manage_nicknames=True)
    async def b_nick(self, ctx: commands.Context, nickname: str):
        is_owner = await self.is_bot_owner(ctx.author)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 Custom server bot profile is an exclusive **VoiceClaw Premium** feature.", ephemeral=True)
        try:
            await ctx.guild.me.edit(nick=nickname)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT INTO serverBotProfile (guildID, serverNickname) VALUES (?, ?) ON CONFLICT(guildID) DO UPDATE SET serverNickname = ?", (ctx.guild.id, nickname, nickname))
                await db.commit()
            await ctx.send(f"✓ Bot nickname in this server set to **{nickname}**!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Could not change nickname: {e}", ephemeral=True)

    @b_profile_group.command(name="serveravatar", description="Change bot's server avatar in this server (Premium)")
    @commands.has_permissions(administrator=True)
    async def b_server_avatar(self, ctx: commands.Context, image: typing.Optional[discord.Attachment] = None, reset: bool = False):
        is_owner = await self.is_bot_owner(ctx.author)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 Custom server bot avatar is an exclusive **VoiceClaw Premium** feature.", ephemeral=True)
        if reset or image is None:
            try:
                route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'avatar': None})
            except Exception:
                pass
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverAvatar = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            return await ctx.send("✓ Bot server avatar has been reset to default!", ephemeral=True)

        try:
            img_bytes = await image.read()
            b64_data = discord.utils._bytes_to_base64_data(img_bytes)
            route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
            await self.bot.http.request(route, json={'avatar': b64_data})
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT INTO serverBotProfile (guildID, serverAvatar) VALUES (?, ?) ON CONFLICT(guildID) DO UPDATE SET serverAvatar = ?", (ctx.guild.id, image.url, image.url))
                await db.commit()
            await ctx.send("✓ Successfully updated bot's server avatar for this server!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Could not update server avatar: {e}", ephemeral=True)

    @b_profile_group.command(name="serverbanner", description="Set custom banner image for bot embeds & voice panel in this server (Premium)")
    @commands.has_permissions(administrator=True)
    async def b_server_banner(self, ctx: commands.Context, banner: typing.Optional[discord.Attachment] = None, reset: bool = False):
        is_owner = await self.is_bot_owner(ctx.author)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 Custom server banner is an exclusive **VoiceClaw Premium** feature.", ephemeral=True)
        if reset or banner is None:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverBanner = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            try:
                route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'banner': None})
            except Exception:
                pass
            await self.refresh_all_guild_interfaces(ctx.guild)
            return await ctx.send("✓ Custom server banner has been reset to default!", ephemeral=True)

        try:
            banner_bytes = await banner.read()
            try:
                b64_banner = discord.utils._bytes_to_base64_data(banner_bytes)
                route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'banner': b64_banner})
            except Exception:
                pass
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT INTO serverBotProfile (guildID, serverBanner) VALUES (?, ?) ON CONFLICT(guildID) DO UPDATE SET serverBanner = ?", (ctx.guild.id, banner.url, banner.url))
                await db.commit()
            await self.refresh_all_guild_interfaces(ctx.guild)
            await ctx.send(f"✓ Custom server banner set to: {banner.url}\nVoice Control Panel in this server has been updated with your new banner!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"✕ Could not update banner: {e}", ephemeral=True)

    @b_profile_group.command(name="serverbio", description="Set custom about/bio for the bot in this server (Premium)")
    @commands.has_permissions(administrator=True)
    async def b_server_bio(self, ctx: commands.Context, bio: str):
        is_owner = await self.is_bot_owner(ctx.author)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 Custom server bot bio is an exclusive **VoiceClaw Premium** feature.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO serverBotProfile (guildID, serverBio) VALUES (?, ?) ON CONFLICT(guildID) DO UPDATE SET serverBio = ?", (ctx.guild.id, bio, bio))
            await db.commit()
        await ctx.send(
            f"✓ Custom server bot bio updated!\n"
            f"View your customized profile anytime using `/bot profile`.\n\n"
            f"> *Note: Discord's native client popup bio for bot accounts is controlled globally via the Discord Developer Portal Description field.*",
            ephemeral=True
        )

    @b_profile_group.command(name="reset", description="Reset bot's server avatar, banner, bio, or nickname to default")
    @commands.has_permissions(administrator=True)
    async def b_reset(self, ctx: commands.Context, target: typing.Literal["all", "avatar", "banner", "bio", "nickname"] = "all"):
        is_owner = await self.is_bot_owner(ctx.author)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 Custom server bot profile is an exclusive **VoiceClaw Premium** feature.", ephemeral=True)
        
        results = []
        if target in ["avatar", "all"]:
            try:
                route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'avatar': None})
            except Exception:
                pass
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverAvatar = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            results.append("• Server avatar reset to default")

        if target in ["banner", "all"]:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverBanner = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            try:
                route = discord.http.Route('PATCH', '/guilds/{guild_id}/members/@me', guild_id=ctx.guild.id)
                await self.bot.http.request(route, json={'banner': None})
            except Exception:
                pass
            await self.refresh_all_guild_interfaces(ctx.guild)
            results.append("• Server banner & interface panel reset to default")

        if target in ["bio", "all"]:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverBio = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            results.append("• Server bio reset to default")

        if target in ["nickname", "all"]:
            try:
                await ctx.guild.me.edit(nick=None)
            except Exception:
                pass
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE serverBotProfile SET serverNickname = NULL WHERE guildID = ?", (ctx.guild.id,))
                await db.commit()
            results.append("• Server nickname reset to default")

        res_text = "\n".join(results)
        await ctx.send(f"✓ **Profile Reset Completed:**\n{res_text}", ephemeral=True)

    @b_profile_group.command(name="resetavatar", description="Reset bot's server avatar back to default")
    @commands.has_permissions(administrator=True)
    async def b_reset_avatar(self, ctx: commands.Context):
        await self.b_reset(ctx, target="avatar")

    @b_profile_group.command(name="resetbanner", description="Reset bot's server banner and interface panel back to default")
    @commands.has_permissions(administrator=True)
    async def b_reset_banner(self, ctx: commands.Context):
        await self.b_reset(ctx, target="banner")

    @b_profile_group.command(name="profile", description="View custom bot profile for this server")
    async def b_profile_view(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT serverAvatar, serverBanner, serverBio, serverNickname FROM serverBotProfile WHERE guildID = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
        is_prem = await self.is_guild_premium(ctx.guild)
        avatar = row[0] if row and row[0] else ctx.guild.me.display_avatar.url
        banner = row[1] if row and row[1] else None
        bio = row[2] if row and row[2] else "Next-generation dynamic voice bot for Discord."
        nick = row[3] if row and row[3] else ctx.guild.me.display_name

        desc = (
            f"**Bio:**\n{bio}\n\n"
            f"**Status:** `{'👑 VoiceClaw Premium' if is_prem else 'Free Tier'}`"
        )
        view = make_v2_card(f"✦ {nick} • Server Profile", desc)
        await ctx.send(view=view, ephemeral=True)

    # ==========================================
    # PURGE SYSTEM & WHITELIST (PREMIUM ONLY)
    # ==========================================

    @commands.hybrid_command(name="purge", aliases=["allpurge", "clear"], description="Bulk delete messages in this channel (VoiceClaw Premium)")
    @app_commands.describe(
        amount="Number of messages to delete (e.g. 20, 50, 100) or 'all'",
        member="Only delete messages from this member (optional)",
        contains="Only delete messages containing this phrase (optional)"
    )
    async def purge(
        self,
        ctx: commands.Context,
        amount: typing.Optional[str] = None,
        member: typing.Optional[discord.Member] = None,
        contains: typing.Optional[str] = None
    ):
        is_owner = await self.is_bot_owner(ctx.author)
        is_prem = await self.is_guild_premium(ctx.guild)
        if not is_prem and not is_owner:
            return await ctx.send(
                "👑 **VoiceClaw Premium Feature**\n"
                "`/purge` is an exclusive feature for **VoiceClaw Premium** servers.\n"
                "To unlock, ask the bot owner to grant premium using `/premium grant_server` or `/premium grant_user`.",
                ephemeral=True
            )
        if not await self.can_purge_messages(ctx.guild, ctx.author):
            return await ctx.send(
                "✕ **Access Denied.** You are not authorized to purge messages on this server.\n"
                "Only the **Server Owner**, **Bot Owner**, and **Whitelisted Roles/Members** can use `/purge`.",
                ephemeral=True
            )

        # Handle .allpurge alias or default
        invoked_name = (ctx.invoked_with or "").lower()
        if invoked_name in ["allpurge", "clear"] and not amount:
            amount = "all"
        elif not amount:
            return await ctx.send("✕ Please specify how many messages to delete or use `all`. Example: `.purge 50` or `.purge all`", ephemeral=True)

        two_weeks_ago = discord.utils.utcnow() - datetime.timedelta(days=14)
        amount_clean = amount.strip().lower()
        if amount_clean in ["all", "everything"]:
            purge_limit = 200
        else:
            try:
                purge_limit = int(amount_clean)
                if purge_limit < 1:
                    return await ctx.send("✕ Amount must be at least 1.", ephemeral=True)
                if purge_limit > 500:
                    return await ctx.send("✕ Maximum purge limit is 500 messages at once.", ephemeral=True)
            except ValueError:
                return await ctx.send("✕ Invalid amount. Specify a number (e.g. `20`) or `all`. Example: `.purge all`", ephemeral=True)

        if ctx.interaction:
            try:
                await ctx.defer(ephemeral=True)
            except Exception:
                pass

        def check(m):
            if member and m.author.id != member.id:
                return False
            if contains and contains.lower() not in m.content.lower():
                return False
            return True

        try:
            actual_limit = purge_limit if amount_clean in ["all", "everything"] else (purge_limit + 1 if not ctx.interaction else purge_limit)
            deleted = await ctx.channel.purge(limit=actual_limit, after=two_weeks_ago, check=check, bulk=True)
            del_count = len(deleted)
            if not ctx.interaction and ctx.message in deleted:
                del_count = max(0, del_count - 1)

            if ctx.interaction:
                await ctx.send(f"✓ Successfully purged **{del_count}** messages.", ephemeral=True)
            else:
                await ctx.send(f"✓ Successfully purged **{del_count}** messages.", delete_after=5)

            await self.log_voice_event(
                ctx.guild,
                title="🧹 Messages Purged",
                description=f"{ctx.author.mention} purged **{del_count}** messages in {ctx.channel.mention}.",
                color=None
            )
        except Exception as e:
            if ctx.interaction:
                await ctx.send(f"✕ Purge error: {e}", ephemeral=True)
            else:
                await ctx.send(f"✕ Purge error: {e}", delete_after=6)

    @commands.hybrid_group(name="purgewhitelist", aliases=["purge_whitelist", "pwl"], description="Manage whitelist for /purge (Server Owner / Admin)", invoke_without_command=True)
    async def purge_wl(self, ctx: commands.Context):
        """List all roles and members whitelisted to use /purge"""
        await self.purge_wl_list(ctx)

    @purge_wl.command(name="add_role", description="Whitelist a role to allow using /purge")
    @app_commands.describe(role="Role to authorize for /purge")
    async def purge_wl_add_role(self, ctx: commands.Context, role: discord.Role):
        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can manage the Purge whitelist.", ephemeral=True)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 This server requires **VoiceClaw Premium** to use Purge and its whitelist system.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO purgeWhitelist (guildID, targetType, targetID, addedBy) VALUES (?, 'role', ?, ?)", (ctx.guild.id, role.id, ctx.author.id))
            await db.commit()
        await ctx.send(f"✓ Role **{role.mention}** is now whitelisted for `/purge`.", ephemeral=True)

    @purge_wl.command(name="add_user", description="Whitelist a member to allow using /purge")
    @app_commands.describe(member="Member to authorize for /purge")
    async def purge_wl_add_user(self, ctx: commands.Context, member: discord.Member):
        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can manage the Purge whitelist.", ephemeral=True)
        if not await self.is_guild_premium(ctx.guild) and not is_owner:
            return await ctx.send("👑 This server requires **VoiceClaw Premium** to use Purge and its whitelist system.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO purgeWhitelist (guildID, targetType, targetID, addedBy) VALUES (?, 'user', ?, ?)", (ctx.guild.id, member.id, ctx.author.id))
            await db.commit()
        await ctx.send(f"✓ Member **{member.mention}** is now whitelisted for `/purge`.", ephemeral=True)

    @purge_wl.command(name="remove_role", description="Remove a role from the /purge whitelist")
    @app_commands.describe(role="Role to remove from whitelist")
    async def purge_wl_rm_role(self, ctx: commands.Context, role: discord.Role):
        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can manage the Purge whitelist.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM purgeWhitelist WHERE guildID = ? AND targetType = 'role' AND targetID = ?", (ctx.guild.id, role.id))
            await db.commit()
        await ctx.send(f"✓ Removed role **{role.mention}** from `/purge` whitelist.", ephemeral=True)

    @purge_wl.command(name="remove_user", description="Remove a member from the /purge whitelist")
    @app_commands.describe(member="Member to remove from whitelist")
    async def purge_wl_rm_user(self, ctx: commands.Context, member: discord.Member):
        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can manage the Purge whitelist.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM purgeWhitelist WHERE guildID = ? AND targetType = 'user' AND targetID = ?", (ctx.guild.id, member.id))
            await db.commit()
        await ctx.send(f"✓ Removed **{member.mention}** from `/purge` whitelist.", ephemeral=True)

    @purge_wl.command(name="list", description="List all roles and members whitelisted to use /purge")
    async def purge_wl_list(self, ctx: commands.Context):
        if not await self.can_purge_messages(ctx.guild, ctx.author):
            return await ctx.send("✕ You do not have permission to view the Purge whitelist.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT targetType, targetID FROM purgeWhitelist WHERE guildID = ?", (ctx.guild.id,)) as cur:
                rows = await cur.fetchall()
        roles = [f"<@&{r[1]}>" for r in rows if r[0] == 'role']
        users = [f"<@{r[1]}>" for r in rows if r[0] == 'user']
        desc = (
            f"**Server Owner:** <@{ctx.guild.owner_id}>\n\n"
            f"**Whitelisted Roles:**\n{', '.join(roles) if roles else 'None'}\n\n"
            f"**Whitelisted Members:**\n{', '.join(users) if users else 'None'}"
        )
        view = make_v2_card("✦ Purge Authorization Whitelist", desc)
        await ctx.send(view=view, ephemeral=True)

    # ==========================================
    # SERVER PREFIX MANAGEMENT COMMANDS
    # ==========================================

    @commands.hybrid_group(
        name="prefix",
        invoke_without_command=True,
        description="View or configure the server's command prefix"
    )
    async def prefix_group(self, ctx: commands.Context):
        """View the current prefix for this server"""
        if not ctx.guild:
            return await ctx.send("✕ This command can only be used within a server.", ephemeral=True)

        current_prefix = getattr(self.bot, 'guild_prefixes', {}).get(ctx.guild.id, os.getenv("BOT_PREFIX", "."))
        desc = (
            f"**Current Server Prefix:** `{current_prefix}`\n\n"
            f"• **Change Prefix:** `{current_prefix}prefix set <new_prefix>` or `/prefix set <new_prefix>`\n"
            f"• **Reset Prefix:** `{current_prefix}prefix reset` or `/prefix reset`\n"
            f"• **Quick Alias:** `{current_prefix}setprefix <new_prefix>`\n"
            f"• **Bot Mention:** You can also always mention the bot: <@{self.bot.user.id}>\n\n"
            f"*(Server Owners and Administrators can change the prefix)*"
        )
        view = make_v2_card("✦ Server Bot Prefix", desc)
        await ctx.send(view=view, ephemeral=True)

    @prefix_group.command(name="set", description="Set a custom command prefix for this server")
    @app_commands.describe(new_prefix="New prefix (e.g. !, ?, v., vc!)")
    async def prefix_set(self, ctx: commands.Context, *, new_prefix: str):
        """Set a custom command prefix for this server (Server Owner / Admin only)"""
        if not ctx.guild:
            return await ctx.send("✕ This command can only be used within a server.", ephemeral=True)

        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can change the bot prefix.", ephemeral=True)

        new_prefix = new_prefix.strip()
        if not new_prefix:
            return await ctx.send("✕ Prefix cannot be empty.", ephemeral=True)
        if len(new_prefix) > 5:
            return await ctx.send("✕ Prefix cannot be longer than 5 characters.", ephemeral=True)
        if any(c in new_prefix for c in [" ", "`", "@", "#"]):
            return await ctx.send("✕ Prefix cannot contain spaces, backticks, or `@`/`#` characters.", ephemeral=True)

        if not hasattr(self.bot, 'guild_prefixes'):
            self.bot.guild_prefixes = {}
        self.bot.guild_prefixes[ctx.guild.id] = new_prefix

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM guildSettings WHERE guildID = ?", (ctx.guild.id,)) as cur:
                exists = await cur.fetchone()
            if exists:
                await db.execute("UPDATE guildSettings SET prefix = ? WHERE guildID = ?", (new_prefix, ctx.guild.id))
            else:
                await db.execute("INSERT INTO guildSettings (guildID, prefix) VALUES (?, ?)", (ctx.guild.id, new_prefix))
            await db.commit()

        desc = (
            f"The command prefix for **{ctx.guild.name}** has been successfully updated!\n\n"
            f"• **New Prefix:** `{new_prefix}`\n"
            f"• **Example:** `{new_prefix}help` or `{new_prefix}voice`\n"
            f"• **Bot Mention:** You can also trigger commands using: <@{self.bot.user.id}>"
        )
        view = make_v2_card("✦ Prefix Updated", desc)
        await ctx.send(view=view)

    @prefix_group.command(name="reset", description="Reset the server prefix back to default")
    async def prefix_reset(self, ctx: commands.Context):
        """Reset the server prefix back to default (Server Owner / Admin only)"""
        if not ctx.guild:
            return await ctx.send("✕ This command can only be used within a server.", ephemeral=True)

        is_owner = await self.is_bot_owner(ctx.author)
        if ctx.author.id != ctx.guild.owner_id and not is_owner and not ctx.author.guild_permissions.administrator:
            return await ctx.send("✕ Only the **Server Owner** or **Administrators** can reset the bot prefix.", ephemeral=True)

        default_prefix = os.getenv("BOT_PREFIX", ".")
        if hasattr(self.bot, 'guild_prefixes') and ctx.guild.id in self.bot.guild_prefixes:
            del self.bot.guild_prefixes[ctx.guild.id]

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE guildSettings SET prefix = NULL WHERE guildID = ?", (ctx.guild.id,))
            await db.commit()

        desc = (
            f"The command prefix for **{ctx.guild.name}** has been reset to default!\n\n"
            f"• **Current Prefix:** `{default_prefix}`\n"
            f"• **Example:** `{default_prefix}help` or `{default_prefix}voice`"
        )
        view = make_v2_card("✦ Prefix Reset", desc)
        await ctx.send(view=view)

    @commands.command(name="setprefix")
    async def setprefix_alias(self, ctx: commands.Context, *, new_prefix: typing.Optional[str] = None):
        """Quick shortcut alias to change prefix: .setprefix <new_prefix>"""
        if new_prefix is None:
            return await self.prefix_group(ctx)
        await self.prefix_set(ctx, new_prefix=new_prefix)


async def setup(bot):
    await bot.add_cog(voice(bot))

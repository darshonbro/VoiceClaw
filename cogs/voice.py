import asyncio
import os
import time
import traceback
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


# ==========================================
# Discord UI Components v2 - Setup Select & LayoutView
# ==========================================

class SetupSelect(discord.ui.Select):
    def __init__(self, cog, author_id: int):
        options = [
            discord.SelectOption(
                label="✦  Quick Setup",
                value="quick",
                description="Automatically creates 'Voice Channels' category & join channel"
            ),
            discord.SelectOption(
                label="◈  Custom Setup",
                value="custom",
                description="Configure custom category and channel names"
            ),
            discord.SelectOption(
                label="✕  Cancel Setup",
                value="cancel",
                description="Abort and cancel this setup configuration"
            )
        ]
        super().__init__(
            placeholder="Select a setup configuration...",
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
        if selected == "quick":
            await interaction.response.defer()
            guild = interaction.guild
            try:
                new_cat = await guild.create_category("Voice Channels")
                interface_chan = await guild.create_text_channel(
                    "interface",
                    category=new_cat,
                    topic="VoiceClaw Temporary Voice Channel Control Interface"
                )
                await interface_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
                await interface_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

                new_chan = await guild.create_voice_channel("＋ Join to Create", category=new_cat)

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

                success_view = discord.ui.LayoutView()
                container = discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"### ✦ Setup Complete\n"
                        f"• **Category:** `{new_cat.name}`\n"
                        f"• **Interface:** {interface_chan.mention}\n"
                        f"• **Root Channel:** {new_chan.mention}\n\n"
                        f"Join {new_chan.mention} to start your private room, and control it from {interface_chan.mention}."
                    ),
                    accent_color=None
                )
                success_view.add_item(container)
                await interaction.edit_original_response(view=success_view)
            except Exception as e:
                await interaction.followup.send(f"✕ Error creating channels: {e}", ephemeral=True)

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
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id

        # Minimalist Hero Banner without ANY blue sidebar stripe
        gallery_item = discord.MediaGalleryItem("attachment://banner.jpg")
        gallery = discord.ui.MediaGallery(gallery_item)

        # Header description above the dropdown
        header_text = discord.ui.TextDisplay("### VoiceClaw • Dynamic Voice Engine\nConfigure your server's automated temporary voice channels.")

        # Dropdown Select Menu placed directly INSIDE the Components v2 Container under the text
        setup_select = SetupSelect(cog, author_id)
        action_row = discord.ui.ActionRow(setup_select)

        container = discord.ui.Container(
            gallery,
            header_text,
            action_row,
            accent_color=None
        )
        self.add_item(container)

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

        # Send Doorbell alert to host in the channel
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
# Discord UI Components v2 - Advanced Access & Moderation Views
# ==========================================

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
            f"🚫 **{member.mention}** has been **blocked** and banned from this room.",
            ephemeral=True
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
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to disconnect (kick)...", min_values=1, max_values=1)
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
        except Exception as e:
            await interaction.response.send_message(f"✕ Could not kick member: {e}", ephemeral=True)


class KickSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(KickUserSelect(channel))


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


class MuteUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to server mute...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        if member not in self.channel.members:
            return await interaction.response.send_message("✕ That member is not currently inside this voice room!", ephemeral=True)

        try:
            await member.edit(mute=True, reason=f"Muted by room host {interaction.user.name}")
            await interaction.response.send_message(f"🔇 Muted **{member.mention}** in this room.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"✕ Could not mute member: {e}", ephemeral=True)


class MuteSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(MuteUserSelect(channel))


class UnmuteUserSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Select a member to unmute...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if isinstance(member, discord.User):
            member = interaction.guild.get_member(member.id)
        if not member:
            return await interaction.response.send_message("✕ Member not found.", ephemeral=True)

        if member not in self.channel.members:
            return await interaction.response.send_message("✕ That member is not currently inside this voice room!", ephemeral=True)

        try:
            await member.edit(mute=False, reason=f"Unmuted by room host {interaction.user.name}")
            await interaction.response.send_message(f"🔊 Unmuted **{member.mention}** in this room.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"✕ Could not unmute member: {e}", ephemeral=True)


class UnmuteSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(UnmuteUserSelect(channel))


# ==========================================
# Discord UI Components v2 - Voice Room LayoutView
# ==========================================

# Custom VoiceClaw Application Emojis (Uploaded directly to bot application)
APP_EMOJIS = {
    "lock": discord.PartialEmoji(name="vc_lock", id=1553938960890339412),
    "unlock": discord.PartialEmoji(name="vc_unlock", id=1553938974798651395),
    "ghost": discord.PartialEmoji(name="vc_ghost", id=1553938948907081749),
    "reveal": discord.PartialEmoji(name="vc_reveal", id=1553938967186116739),
    "rename": discord.PartialEmoji(name="vc_rename", id=1553938964799299627),
    "limit": discord.PartialEmoji(name="vc_limit", id=1553938959288107088),
    "mute": discord.PartialEmoji(name="vc_mute", id=1553938963147001980),
    "unmute": discord.PartialEmoji(name="vc_unmute", id=1553938976782680225),
    "trust": discord.PartialEmoji(name="vc_trust", id=1553938971095072798),
    "untrust": discord.PartialEmoji(name="vc_untrust", id=1553938978338644108),
    "invite": discord.PartialEmoji(name="vc_invite", id=1553938952921284679),
    "kick": discord.PartialEmoji(name="vc_kick", id=1553938955635003412),
    "block": discord.PartialEmoji(name="vc_block", id=1553938943433777233),
    "unblock": discord.PartialEmoji(name="vc_unblock", id=1553938972986712194),
    "knock": discord.PartialEmoji(name="vc_knock", id=1553938957480370286),
    "claim": discord.PartialEmoji(name="vc_claim", id=1553938945442840657),
    "transfer": discord.PartialEmoji(name="vc_transfer", id=1553938969165824031),
    "info": discord.PartialEmoji(name="vc_info", id=1553938951012880487),
    "delete": discord.PartialEmoji(name="vc_delete", id=1553938947271557190),
}


class VoiceControlSelect(discord.ui.Select):
    def __init__(self, cog):
        options = [
            discord.SelectOption(label="Lock Channel", emoji=APP_EMOJIS["lock"], value="lock", description="Restrict connections to your room"),
            discord.SelectOption(label="Unlock Channel", emoji=APP_EMOJIS["unlock"], value="unlock", description="Open connection to everyone"),
            discord.SelectOption(label="Ghost Channel", emoji=APP_EMOJIS["ghost"], value="ghost", description="Hide room from server sidebar"),
            discord.SelectOption(label="Reveal Channel", emoji=APP_EMOJIS["reveal"], value="reveal", description="Make room visible on sidebar"),
            discord.SelectOption(label="Rename Channel", emoji=APP_EMOJIS["rename"], value="rename", description="Change channel name via popup modal"),
            discord.SelectOption(label="Set Member Limit", emoji=APP_EMOJIS["limit"], value="limit", description="Set user capacity limit via modal"),
            discord.SelectOption(label="Mute Member", emoji=APP_EMOJIS["mute"], value="mute", description="Server mute member in your room"),
            discord.SelectOption(label="Unmute Member", emoji=APP_EMOJIS["unmute"], value="unmute", description="Unmute member in your room"),
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
    def __init__(self, cog, member_avatar_url: str = None, member_name: str = None, has_banner: bool = False):
        super().__init__(timeout=None)
        self.cog = cog

        clean_name = " ".join(member_name.split()) if member_name else None
        title = f"### VoiceClaw • {clean_name}'s Room" if clean_name else "### VoiceClaw Interface"

        guide_text = (
            f"{title}\n"
            "Use the buttons below to manage your voice channel.\n\n"
            "**Control Buttons**\n"
            f"<:vc_lock:1553938960890339412> - `Lock` your voice channel\n"
            f"<:vc_unlock:1553938974798651395> - `Unlock` your voice channel\n"
            f"<:vc_ghost:1553938948907081749> - `Hide` your voice channel\n"
            f"<:vc_reveal:1553938967186116739> - `Reveal` your voice channel\n"
            f"<:vc_rename:1553938964799299627> - `Rename` your voice channel\n"
            f"<:vc_limit:1553938959288107088> - `Limit` your voice channel user limit\n"
            f"<:vc_mute:1553938963147001980> - `Mute` a user\n"
            f"<:vc_unmute:1553938976782680225> - `Unmute` a user\n"
            f"<:vc_trust:1553938971095072798> - `Trust` a user (VIP access)\n"
            f"<:vc_untrust:1553938978338644108> - `Untrust` a user\n"
            f"<:vc_invite:1553938952921284679> - `Invite` a user\n"
            f"<:vc_kick:1553938955635003412> - `Kick` a user\n"
            f"<:vc_block:1553938943433777233> - `Block` a user\n"
            f"<:vc_unblock:1553938972986712194> - `Unblock` a user\n"
            f"<:vc_knock:1553938957480370286> - `Knock` waiting room doorbell\n"
            f"<:vc_claim:1553938945442840657> - `Claim` ownership\n"
            f"<:vc_transfer:1553938969165824031> - `Transfer` ownership\n"
            f"<:vc_info:1553938951012880487> - `Info` room stats\n"
            f"<:vc_delete:1553938947271557190> - `Delete` temporary channel"
        )

        ctrl_select = VoiceControlSelect(self.cog)
        select_row = discord.ui.ActionRow(ctrl_select)

        if member_avatar_url:
            section = discord.ui.Section(
                discord.ui.TextDisplay(guide_text),
                accessory=discord.ui.Thumbnail(member_avatar_url)
            )
            container = discord.ui.Container(section, select_row, accent_color=None)
        else:
            text_desc = discord.ui.TextDisplay(guide_text)
            container = discord.ui.Container(text_desc, select_row, accent_color=None)

        self.add_item(container)

        # Row 0: Privacy & Room Edit (5 square icon buttons)
        btn_lock = discord.ui.Button(emoji=APP_EMOJIS["lock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_lock")
        btn_unlock = discord.ui.Button(emoji=APP_EMOJIS["unlock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_unlock")
        btn_ghost = discord.ui.Button(emoji=APP_EMOJIS["ghost"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_ghost")
        btn_reveal = discord.ui.Button(emoji=APP_EMOJIS["reveal"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_reveal")
        btn_rename = discord.ui.Button(emoji=APP_EMOJIS["rename"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_rename")

        btn_lock.callback = self.lock_callback
        btn_unlock.callback = self.unlock_callback
        btn_ghost.callback = self.ghost_callback
        btn_reveal.callback = self.reveal_callback
        btn_rename.callback = self.rename_callback

        row0 = discord.ui.ActionRow(btn_lock, btn_unlock, btn_ghost, btn_reveal, btn_rename)
        self.add_item(row0)

        # Row 1: Capacity, Audio & Trust (5 square icon buttons)
        btn_limit = discord.ui.Button(emoji=APP_EMOJIS["limit"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_limit")
        btn_mute = discord.ui.Button(emoji=APP_EMOJIS["mute"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_mute")
        btn_unmute = discord.ui.Button(emoji=APP_EMOJIS["unmute"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_unmute")
        btn_trust = discord.ui.Button(emoji=APP_EMOJIS["trust"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_trust")
        btn_untrust = discord.ui.Button(emoji=APP_EMOJIS["untrust"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_untrust")

        btn_limit.callback = self.limit_callback
        btn_mute.callback = self.mute_callback
        btn_unmute.callback = self.unmute_callback
        btn_trust.callback = self.trust_callback
        btn_untrust.callback = self.untrust_callback

        row1 = discord.ui.ActionRow(btn_limit, btn_mute, btn_unmute, btn_trust, btn_untrust)
        self.add_item(row1)

        # Row 2: Invite, Kick, Block & Waiting Room (5 square icon buttons)
        btn_invite = discord.ui.Button(emoji=APP_EMOJIS["invite"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_invite")
        btn_kick = discord.ui.Button(emoji=APP_EMOJIS["kick"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_kick")
        btn_block = discord.ui.Button(emoji=APP_EMOJIS["block"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_block")
        btn_unblock = discord.ui.Button(emoji=APP_EMOJIS["unblock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_unblock")
        btn_knock = discord.ui.Button(emoji=APP_EMOJIS["knock"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_knock_toggle")

        btn_invite.callback = self.invite_callback
        btn_kick.callback = self.kick_callback
        btn_block.callback = self.block_callback
        btn_unblock.callback = self.unblock_callback
        btn_knock.callback = self.knock_toggle_callback

        row2 = discord.ui.ActionRow(btn_invite, btn_kick, btn_block, btn_unblock, btn_knock)
        self.add_item(row2)

        # Row 3: Ownership, Stats & Deletion (4 square icon buttons)
        btn_claim = discord.ui.Button(emoji=APP_EMOJIS["claim"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_claim")
        btn_transfer = discord.ui.Button(emoji=APP_EMOJIS["transfer"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_transfer")
        btn_info = discord.ui.Button(emoji=APP_EMOJIS["info"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_info")
        btn_delete = discord.ui.Button(emoji=APP_EMOJIS["delete"], style=discord.ButtonStyle.secondary, custom_id="vc_btn_delete")

        btn_claim.callback = self.claim_callback
        btn_transfer.callback = self.transfer_callback
        btn_info.callback = self.info_callback
        btn_delete.callback = self.delete_callback

        row3 = discord.ui.ActionRow(btn_claim, btn_transfer, btn_info, btn_delete)
        self.add_item(row3)

    async def dispatch_action(self, interaction: discord.Interaction, action: str):
        mapping = {
            "lock": self.lock_callback,
            "unlock": self.unlock_callback,
            "ghost": self.ghost_callback,
            "reveal": self.reveal_callback,
            "knock": self.knock_toggle_callback,
            "rename": self.rename_callback,
            "limit": self.limit_callback,
            "trust": self.trust_callback,
            "untrust": self.untrust_callback,
            "invite": self.invite_callback,
            "kick": self.kick_callback,
            "mute": self.mute_callback,
            "unmute": self.unmute_callback,
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

        # If user is host of an active channel: manage room's doorbell
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

        # Outside user: allow knocking on an active locked channel
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
            return await interaction.response.send_message(
                "✕ There are no active private rooms to knock on right now.",
                ephemeral=True
            )

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

        await interaction.response.send_modal(ChannelRenameModal(self.cog, channel))

    async def limit_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can change the limit.", ephemeral=True)

        await interaction.response.send_modal(ChannelLimitModal(self.cog, channel))

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

        await interaction.response.send_message("Select a member inside this room to kick:", view=KickSelectView(channel), ephemeral=True)

    async def mute_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can mute members.", ephemeral=True)

        await interaction.response.send_message("Select a member inside this room to server mute:", view=MuteSelectView(channel), ephemeral=True)

    async def unmute_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can unmute members.", ephemeral=True)

        await interaction.response.send_message("Select a member inside this room to unmute:", view=UnmuteSelectView(channel), ephemeral=True)

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

    async def transfer_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can transfer ownership.", ephemeral=True)

        await interaction.response.send_message("Select a room member to pass channel ownership to:", view=TransferOwnerView(self.cog, channel), ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        channel, owner_id = await self._get_voice_context(interaction)
        if not channel: return
        if interaction.user.id != owner_id:
            return await interaction.response.send_message(f"✕ Only the channel host (<@{owner_id}>) can delete this room.", ephemeral=True)

        await interaction.response.send_message("🗑 **Deleting voice room...**", ephemeral=True)
        await self.cog.delete_temp_channel_record(channel.id)
        self.cog.knock_settings.pop(channel.id, None)
        try:
            await channel.delete(reason=f"Deleted by channel host {interaction.user.name}")
        except Exception:
            pass

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
        """Initialize database tables, register views, and clean stale rooms"""
        await self.init_db()
        self.bot.add_view(VoiceControlLayoutView(self))
        asyncio.create_task(self.cleanup_stale_channels())

    async def cleanup_stale_channels(self):
        """Sweep and delete any leftover empty temp channels on startup"""
        await self.bot.wait_until_ready()
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
                    interfaceChannelID INTEGER
                )
            ''')
            try:
                await db.execute("ALTER TABLE guild ADD COLUMN interfaceChannelID INTEGER")
            except Exception:
                pass
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
            async with db.execute("SELECT guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID FROM guild WHERE guildID = ?", (guild_id,)) as cursor:
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

        try:
            guild = member.guild
            guild_cfg = await self.get_guild_config(guild.id)
            if not guild_cfg:
                return

            master_channel_id = guild_cfg[2]
            category_id = guild_cfg[3]

            # 1. User Joined the "Join to Create" Master Channel
            if after.channel and after.channel.id == master_channel_id:
                now = asyncio.get_event_loop().time()
                if member.id in self.cooldowns and (now - self.cooldowns[member.id]) < 4:
                    return

                self.cooldowns[member.id] = now

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

                # Sweep any empty temporary channels in category before creating a new one
                category = guild.get_channel(category_id)
                if isinstance(category, discord.CategoryChannel):
                    for c in category.voice_channels:
                        if c.id != master_channel_id and len(c.members) == 0:
                            is_temp = await self.get_channel_owner(c.id)
                            if is_temp:
                                try:
                                    await c.delete(reason="VoiceClaw: Auto-cleanup empty temp room")
                                    print(f"[VoiceClaw] Cleaned empty channel {c.name} ({c.id})")
                                except Exception:
                                    pass
                                await self.delete_temp_channel_record(c.id)
                                self.knock_settings.pop(c.id, None)
                else:
                    category = None

                user_pref = await self.get_user_setting(member.id)
                guild_pref = await self.get_guild_setting(guild.id)

                clean_name = " ".join(member.display_name.split())
                chan_name = f"{clean_name}'s Room"
                chan_limit = 0

                if guild_pref:
                    chan_limit = guild_pref[1]

                if user_pref:
                    if user_pref[0]: chan_name = user_pref[0]
                    if user_pref[1] is not None: chan_limit = user_pref[1]

                print(f"[VoiceClaw] Creating temporary room '{chan_name}' for {member.display_name}...")
                temp_channel = await guild.create_voice_channel(
                    name=chan_name,
                    category=category,
                    user_limit=chan_limit
                )

                await temp_channel.set_permissions(self.bot.user, connect=True, view_channel=True, read_messages=True, send_messages=True, read_message_history=True, manage_channels=True)
                await temp_channel.set_permissions(member, connect=True, view_channel=True, read_messages=True, send_messages=True, read_message_history=True, manage_channels=True)
                await temp_channel.set_permissions(guild.default_role, read_messages=True, read_message_history=True)

                await member.move_to(temp_channel)
                await self.register_temp_channel(member.id, temp_channel.id)
                self.knock_settings[temp_channel.id] = True
                print(f"[VoiceClaw] Moved {member.display_name} to {temp_channel.name} ({temp_channel.id})")

                # Send Minimalist Discord Components v2 LayoutView (Ultra-compact, matching VoiceMaster/Zynarix)
                try:
                    ctrl_view = VoiceControlLayoutView(self, member.display_avatar.url, member.display_name)
                    msg = await temp_channel.send(view=ctrl_view)
                    print(f"[VoiceClaw] Successfully sent interface message ({msg.id}) into {temp_channel.name}")
                except Exception as send_err:
                    print(f"[VoiceClaw Error] Failed to send interface message into {temp_channel.name}: {send_err}")
                    traceback.print_exc()

            # 2. Member Left a Temporary Channel
            if before.channel and before.channel.id != master_channel_id:
                chan_id = before.channel.id
                owner_id = await self.get_channel_owner(chan_id)
                if owner_id:
                    if len(before.channel.members) == 0:
                        try:
                            await before.channel.delete(reason="VoiceClaw: Temporary channel empty")
                            print(f"[VoiceClaw] Cleaned up empty temporary channel {chan_id}")
                        except Exception:
                            pass
                        await self.delete_temp_channel_record(chan_id)
                        self.knock_settings.pop(chan_id, None)

        except Exception as e:
            print(f"[VoiceClaw Error] on_voice_state_update failed: {e}")
            traceback.print_exc()

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

    @voice_cmd.command(name="interface", aliases=["panel"])
    @commands.has_permissions(administrator=True)
    async def interface_cmd(self, ctx):
        """Deploy or refresh the VoiceClaw Interface panel directly"""
        guild = ctx.guild
        guild_cfg = await self.get_guild_config(guild.id)

        target_chan = ctx.channel
        if guild_cfg and len(guild_cfg) > 3 and guild_cfg[3]:
            cat = guild.get_channel(guild_cfg[3])
            if cat and isinstance(cat, discord.CategoryChannel):
                existing = discord.utils.get(cat.text_channels, name="interface")
                if existing:
                    target_chan = existing
                else:
                    target_chan = await guild.create_text_channel(
                        "interface",
                        category=cat,
                        topic="VoiceClaw Temporary Voice Channel Control Interface"
                    )
                    await target_chan.set_permissions(guild.default_role, read_messages=True, send_messages=False, read_message_history=True)
                    await target_chan.set_permissions(guild.me, read_messages=True, send_messages=True, manage_channels=True)

                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE guild SET interfaceChannelID = ? WHERE guildID = ?", (target_chan.id, guild.id))
                        await db.commit()

        ctrl_view = VoiceControlLayoutView(self)
        await target_chan.send(view=ctrl_view)

        if target_chan.id != ctx.channel.id:
            await ctx.send(f"✦ VoiceClaw Interface deployed to {target_chan.mention}!", delete_after=10)

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

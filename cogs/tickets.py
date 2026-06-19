import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import db
from cogs.transcripts import save_transcript, build_html_transcript


# ── Shared TTL config cache (60s) ─────────────────────────────────────────────
_config_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60


async def get_cached_config(guild_id: str) -> dict:
    now = time.monotonic()
    if guild_id in _config_cache:
        ts, data = _config_cache[guild_id]
        if now - ts < _CACHE_TTL:
            return data
    data = await asyncio.to_thread(db.get_all_config, guild_id)
    _config_cache[guild_id] = (now, data)
    return data


def invalidate_config_cache(guild_id: str):
    _config_cache.pop(str(guild_id), None)


async def is_mm_or_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg      = await get_cached_config(str(member.guild.id))
    mm_id    = cfg.get("mm_role", "")
    admin_id = cfg.get("admin_role", "")
    role_ids = {r.id for r in member.roles}
    if mm_id    and mm_id.isdigit()    and int(mm_id)    in role_ids: return True
    if admin_id and admin_id.isdigit() and int(admin_id) in role_ids: return True
    return False


async def is_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg      = await get_cached_config(str(member.guild.id))
    admin_id = cfg.get("admin_role", "")
    if admin_id and admin_id.isdigit() and int(admin_id) in {r.id for r in member.roles}:
        return True
    return False


def _embed(title: str, description: str, color: discord.Color, footer: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    if footer:
        e.set_footer(text=footer)
    return e


class TicketButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="ticket_claim", emoji="✋")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can claim tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This does not appear to be a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        if ticket["claimed_by"]:
            claimer = interaction.guild.get_member(int(ticket["claimed_by"]))
            name = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
            await interaction.followup.send(embed=_embed("⚠️ Already Claimed", f"This ticket is already claimed by {name}.", discord.Color.yellow()), ephemeral=True)
            return
        await asyncio.to_thread(db.claim_ticket, str(interaction.channel_id), str(interaction.user.id))
        await interaction.channel.send(embed=discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket and will be assisting you.",
            color=discord.Color.green()
        ).set_footer(text="Use the Unclaim button or /unclaim to release this ticket."))
        await interaction.followup.send("✅ Claimed!", ephemeral=True)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="ticket_unclaim", emoji="🔓")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can unclaim tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This does not appear to be a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        if not ticket["claimed_by"]:
            await interaction.followup.send(embed=_embed("⚠️ Not Claimed", "This ticket has not been claimed yet.", discord.Color.yellow()), ephemeral=True)
            return
        await asyncio.to_thread(db.claim_ticket, str(interaction.channel_id), None)
        await interaction.channel.send(embed=discord.Embed(
            title="🔓 Ticket Unclaimed",
            description=f"{interaction.user.mention} has unclaimed this ticket.\n\nAny available MM staff can now claim it using the **Claim** button.",
            color=discord.Color.orange()
        ).set_footer(text="Press Claim to take this ticket."))
        await interaction.followup.send("🔓 Unclaimed!", ephemeral=True)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.blurple, custom_id="ticket_adduser", emoji="➕")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket_close", emoji="🔒")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can close tickets.", discord.Color.red()), ephemeral=True)
            return
        await interaction.channel.send(embed=_embed("🔒 Closing Ticket", "Saving transcript and closing channel...", discord.Color.red()))
        await interaction.delete_original_response()
        await close_ticket_channel(interaction.channel, interaction.guild, interaction.user)


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    user_id = discord.ui.TextInput(label="User ID or mention", placeholder="123456789012345678")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can add users.", discord.Color.red()), ephemeral=True)
            return
        raw = self.user_id.value.strip().strip("<@!>")
        try:
            uid = int(raw)
        except ValueError:
            await interaction.followup.send(embed=_embed("❌ Invalid Input", "Please provide a valid User ID.", discord.Color.red()), ephemeral=True)
            return
        member = interaction.guild.get_member(uid)
        if not member:
            await interaction.followup.send(embed=_embed("❌ Not Found", "That user was not found in this server.", discord.Color.red()), ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await asyncio.to_thread(db.add_ticket_user, str(interaction.channel_id), str(uid))
        await interaction.followup.send(embed=_embed("➕ User Added", f"{member.mention} has been added to this ticket.", discord.Color.blurple()), ephemeral=True)
        await interaction.channel.send(embed=discord.Embed(
            description=f"➕ {member.mention} has been added to this ticket.",
            color=discord.Color.blurple()
        ))


async def close_ticket_channel(channel: discord.TextChannel, guild: discord.Guild, closer: discord.Member):
    import io as _io
    ticket     = await asyncio.to_thread(db.get_ticket, str(channel.id))
    plain_text = await save_transcript(channel, guild)
    await asyncio.to_thread(db.close_ticket, str(channel.id), plain_text)
    html_bytes = await build_html_transcript(channel, guild, ticket or {}, closer)

    cfg                   = await get_cached_config(str(guild.id))
    transcript_channel_id = cfg.get("transcript_channel", "")
    if transcript_channel_id:
        tc = guild.get_channel(int(transcript_channel_id))
        if tc:
            opener_id   = ticket["opener_id"]  if ticket else None
            opener      = guild.get_member(int(opener_id))  if opener_id  else None
            claimed_id  = ticket["claimed_by"] if ticket else None
            claimer     = guild.get_member(int(claimed_id)) if claimed_id else None
            ticket_type = (ticket.get("ticket_type") or "trade").title() if ticket else "Trade"
            msg_count   = plain_text.count("\n") + 1 if plain_text.strip() else 0

            embed = discord.Embed(title=f"📄 Transcript — #{channel.name}", color=discord.Color.blurple())
            embed.add_field(name="Type",      value=ticket_type,                                      inline=True)
            embed.add_field(name="Opened by", value=opener.mention if opener else str(opener_id),     inline=True)
            embed.add_field(name="Closed by", value=closer.mention,                                   inline=True)
            if claimer:
                embed.add_field(name="Claimed by", value=claimer.mention, inline=True)
            embed.add_field(name="Messages", value=str(msg_count), inline=True)
            embed.set_footer(text="Open the .html file in any browser to view the full transcript")
            await tc.send(
                embed=embed,
                file=discord.File(fp=_io.BytesIO(html_bytes), filename=f"transcript-{channel.name}.html")
            )

    log_channel_id = cfg.get("log_channel", "")
    if log_channel_id:
        lc = guild.get_channel(int(log_channel_id))
        if lc:
            await lc.send(embed=discord.Embed(
                title="🔒 Ticket Closed",
                description=f"**Channel:** `{channel.name}`\n**Closed by:** {closer.mention}",
                color=discord.Color.red()
            ))

    await channel.delete(reason=f"Ticket closed by {closer}")


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketButtons())

    async def open_ticket(self, guild: discord.Guild, opener: discord.Member, ticket_type="trade"):
        bl = await asyncio.to_thread(db.is_blacklisted, str(opener.id), str(guild.id))
        if bl:
            return None, "blacklisted"

        cfg          = await get_cached_config(str(guild.id))
        category_key = "ticket_category" if ticket_type == "trade" else (
            "automm_category" if ticket_type == "automm" else "support_category"
        )
        cat_id   = cfg.get(category_key, "")
        category = guild.get_channel(int(cat_id)) if cat_id and cat_id.isdigit() else None

        mm_id    = cfg.get("mm_role", "")
        admin_id = cfg.get("admin_role", "")
        mm_role    = guild.get_role(int(mm_id))    if mm_id    and mm_id.isdigit()    else None
        admin_role = guild.get_role(int(admin_id)) if admin_id and admin_id.isdigit() else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            opener:             discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        if mm_role:    overwrites[mm_role]    = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if admin_role: overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        prefix  = {"trade": "trade", "support": "support", "automm": "automm"}.get(ticket_type, ticket_type)
        channel = await guild.create_text_channel(
            name=f"{prefix}-{opener.name}",
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {opener}"
        )
        await asyncio.to_thread(db.create_ticket, str(channel.id), str(guild.id), str(opener.id), ticket_type)

        if ticket_type == "automm":
            automm_cog = self.bot.get_cog("AutoMM")
            if automm_cog:
                await automm_cog._start_session(channel, guild, opener)

        log_channel_id = cfg.get("log_channel", "")
        if log_channel_id:
            lc = guild.get_channel(int(log_channel_id))
            if lc:
                await lc.send(embed=discord.Embed(
                    title="🎫 Ticket Opened",
                    description=f"**Opened by:** {opener.mention}\n**Channel:** {channel.mention}\n**Type:** `{ticket_type}`",
                    color=discord.Color.green()
                ))

        return channel, None

    # ── Slash Commands ────────────────────────────────────────────────────────

    @app_commands.command(name="claim", description="Claim this ticket as MM staff")
    async def claim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can claim tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        if ticket["claimed_by"]:
            claimer = interaction.guild.get_member(int(ticket["claimed_by"]))
            name = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
            await interaction.followup.send(embed=_embed("⚠️ Already Claimed", f"This ticket is already claimed by {name}.", discord.Color.yellow()), ephemeral=True)
            return
        await asyncio.to_thread(db.claim_ticket, str(interaction.channel_id), str(interaction.user.id))
        await interaction.channel.send(embed=discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket and will be assisting you.",
            color=discord.Color.green()
        ).set_footer(text="Use /unclaim or the Unclaim button to release this ticket."))
        await interaction.followup.send("✅ Claimed!", ephemeral=True)

    @app_commands.command(name="unclaim", description="Release your claim on this ticket so another MM can take it")
    async def unclaim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can unclaim tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        if not ticket["claimed_by"]:
            await interaction.followup.send(embed=_embed("⚠️ Not Claimed", "This ticket has not been claimed by anyone.", discord.Color.yellow()), ephemeral=True)
            return
        await asyncio.to_thread(db.claim_ticket, str(interaction.channel_id), None)
        await interaction.channel.send(embed=discord.Embed(
            title="🔓 Ticket Unclaimed",
            description=f"{interaction.user.mention} has unclaimed this ticket.\n\nAny available MM staff can now claim it using the **Claim** button.",
            color=discord.Color.orange()
        ).set_footer(text="Press Claim to take this ticket."))
        await interaction.followup.send("🔓 Unclaimed!", ephemeral=True)

    @app_commands.command(name="close", description="Close and archive this ticket")
    async def close(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can close tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        await interaction.followup.send(embed=_embed("🔒 Closing Ticket", "Saving transcript and closing channel...", discord.Color.red()))
        await close_ticket_channel(interaction.channel, interaction.guild, interaction.user)

    @app_commands.command(name="adduser", description="Add a user to this ticket")
    @app_commands.describe(user="The user to add")
    async def adduser(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can add users.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
        await asyncio.to_thread(db.add_ticket_user, str(interaction.channel_id), str(user.id))
        await interaction.followup.send(embed=_embed("➕ User Added", f"{user.mention} has been added.", discord.Color.blurple()), ephemeral=True)
        await interaction.channel.send(embed=discord.Embed(description=f"➕ {user.mention} has been added to this ticket.", color=discord.Color.blurple()))

    @app_commands.command(name="removeuser", description="Remove a user from this ticket")
    @app_commands.describe(user="The user to remove")
    async def removeuser(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can remove users.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, overwrite=None)
        await asyncio.to_thread(db.remove_ticket_user, str(interaction.channel_id), str(user.id))
        await interaction.followup.send(embed=_embed("➖ User Removed", f"{user.mention} has been removed.", discord.Color.orange()), ephemeral=True)
        await interaction.channel.send(embed=discord.Embed(description=f"➖ {user.mention} has been removed from this ticket.", color=discord.Color.orange()))

    @app_commands.command(name="transfer", description="Transfer this ticket to another middleman")
    @app_commands.describe(mm="The MM to transfer to")
    async def transfer(self, interaction: discord.Interaction, mm: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=_embed("🚫 Access Denied", "Only MM staff can transfer tickets.", discord.Color.red()), ephemeral=True)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(interaction.channel_id))
        if not ticket:
            await interaction.followup.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), ephemeral=True)
            return
        await asyncio.to_thread(db.transfer_ticket, str(interaction.channel_id), str(mm.id))
        await interaction.channel.set_permissions(mm, read_messages=True, send_messages=True)
        await interaction.channel.send(embed=discord.Embed(
            title="🔀 Ticket Transferred",
            description=f"This ticket has been transferred to {mm.mention} by {interaction.user.mention}.",
            color=discord.Color.orange()
        ).set_footer(text="The new MM will be assisting you shortly."))
        await interaction.followup.send("✅ Transferred!", ephemeral=True)

    # ── Prefix Commands ───────────────────────────────────────────────────────

    @commands.command(name="claim")
    async def claim_prefix(self, ctx: commands.Context):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can claim tickets.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        if ticket["claimed_by"]:
            claimer = ctx.guild.get_member(int(ticket["claimed_by"]))
            name = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
            await ctx.send(embed=_embed("⚠️ Already Claimed", f"Already claimed by {name}.", discord.Color.yellow()))
            return
        await asyncio.to_thread(db.claim_ticket, str(ctx.channel.id), str(ctx.author.id))
        await ctx.send(embed=discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{ctx.author.mention} has claimed this ticket and will be assisting you.",
            color=discord.Color.green()
        ).set_footer(text="Use $unclaim or the Unclaim button to release this ticket."))

    @commands.command(name="unclaim")
    async def unclaim_prefix(self, ctx: commands.Context):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can unclaim tickets.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        if not ticket["claimed_by"]:
            await ctx.send(embed=_embed("⚠️ Not Claimed", "This ticket has not been claimed yet.", discord.Color.yellow()))
            return
        await asyncio.to_thread(db.claim_ticket, str(ctx.channel.id), None)
        await ctx.send(embed=discord.Embed(
            title="🔓 Ticket Unclaimed",
            description=f"{ctx.author.mention} has unclaimed this ticket.\n\nAny available MM staff can now claim it using the **Claim** button.",
            color=discord.Color.orange()
        ).set_footer(text="Press Claim to take this ticket."))

    @commands.command(name="close")
    async def close_prefix(self, ctx: commands.Context):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can close tickets.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        await ctx.send(embed=_embed("🔒 Closing Ticket", "Saving transcript and closing channel...", discord.Color.red()))
        await close_ticket_channel(ctx.channel, ctx.guild, ctx.author)

    @commands.command(name="adduser")
    async def adduser_prefix(self, ctx: commands.Context, user: discord.Member):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can add users.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
        await asyncio.to_thread(db.add_ticket_user, str(ctx.channel.id), str(user.id))
        await ctx.send(embed=discord.Embed(description=f"➕ {user.mention} has been added to this ticket.", color=discord.Color.blurple()))

    @commands.command(name="removeuser")
    async def removeuser_prefix(self, ctx: commands.Context, user: discord.Member):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can remove users.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        await ctx.channel.set_permissions(user, overwrite=None)
        await asyncio.to_thread(db.remove_ticket_user, str(ctx.channel.id), str(user.id))
        await ctx.send(embed=discord.Embed(description=f"➖ {user.mention} has been removed from this ticket.", color=discord.Color.orange()))

    @commands.command(name="transfer")
    async def transfer_prefix(self, ctx: commands.Context, mm: discord.Member):
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=_embed("🚫 Access Denied", "Only MM staff can transfer tickets.", discord.Color.red()), delete_after=10)
            return
        ticket = await asyncio.to_thread(db.get_ticket, str(ctx.channel.id))
        if not ticket:
            await ctx.send(embed=_embed("❌ Not Found", "This is not a ticket channel.", discord.Color.red()), delete_after=10)
            return
        await asyncio.to_thread(db.transfer_ticket, str(ctx.channel.id), str(mm.id))
        await ctx.channel.set_permissions(mm, read_messages=True, send_messages=True)
        await ctx.send(embed=discord.Embed(
            title="🔀 Ticket Transferred",
            description=f"This ticket has been transferred to {mm.mention} by {ctx.author.mention}.",
            color=discord.Color.orange()
        ).set_footer(text="The new MM will be assisting you shortly."))


async def setup(bot):
    await bot.add_cog(Tickets(bot))

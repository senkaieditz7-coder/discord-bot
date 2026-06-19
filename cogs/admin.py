import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import db


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blacklist", description="Blacklist a user from opening tickets")
    @app_commands.describe(user="User to blacklist", reason="Reason for blacklist")
    async def blacklist(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_admin
        if not await is_admin(interaction.user):
            await interaction.followup.send("Only admins can blacklist users.", ephemeral=True)
            return
        await asyncio.to_thread(db.blacklist_user, str(user.id), str(interaction.guild_id), reason, str(interaction.user.id))
        embed = discord.Embed(title="User Blacklisted 🚫", description=f"{user.mention} has been blacklisted.", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=f"By {interaction.user}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="unblacklist", description="Remove a user from the blacklist")
    @app_commands.describe(user="User to unblacklist")
    async def unblacklist(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_admin
        if not await is_admin(interaction.user):
            await interaction.followup.send("Only admins can unblacklist users.", ephemeral=True)
            return
        await asyncio.to_thread(db.unblacklist_user, str(user.id), str(interaction.guild_id))
        await interaction.followup.send(embed=discord.Embed(
            title="User Unblacklisted ✅",
            description=f"{user.mention} has been removed from the blacklist.",
            color=discord.Color.green()
        ))

    @app_commands.command(name="tradeinfo", description="Get details on a trade ticket by channel")
    @app_commands.describe(channel="The ticket channel (leave blank for current channel)")
    async def tradeinfo(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can view trade info.", ephemeral=True)
            return
        ch = channel or interaction.channel
        ticket = await asyncio.to_thread(db.get_ticket, str(ch.id))
        if not ticket:
            await interaction.followup.send("No ticket found for that channel.", ephemeral=True)
            return
        opener = interaction.guild.get_member(int(ticket["opener_id"]))
        claimer_text = "Unclaimed"
        if ticket["claimed_by"]:
            claimer = interaction.guild.get_member(int(ticket["claimed_by"]))
            claimer_text = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
        users = await asyncio.to_thread(db.get_ticket_users, str(ch.id))
        user_mentions = [f"<@{u}>" for u in users] or ["None"]
        embed = discord.Embed(title=f"Trade Info — #{ch.name}", color=discord.Color.blurple())
        embed.add_field(name="ID",      value=str(ticket["id"]),                                                      inline=True)
        embed.add_field(name="Type",    value=ticket["ticket_type"],                                                   inline=True)
        embed.add_field(name="Status",  value=ticket["status"],                                                        inline=True)
        embed.add_field(name="Opened by",  value=opener.mention if opener else f"<@{ticket['opener_id']}>",           inline=True)
        embed.add_field(name="Claimed by", value=claimer_text,                                                         inline=True)
        embed.add_field(name="Opened at",  value=ticket["created_at"][:19].replace("T", " "),                         inline=True)
        embed.add_field(name="Users in ticket", value=", ".join(user_mentions),                                        inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="stats", description="View full bot statistics")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can view stats.", ephemeral=True)
            return
        s = await asyncio.to_thread(db.get_stats, str(interaction.guild_id))
        embed = discord.Embed(title="Bot Statistics 📊", color=discord.Color.blurple())
        embed.add_field(name="Total Tickets",       value=str(s["total_tickets"]),  inline=True)
        embed.add_field(name="Open Tickets",        value=str(s["open_tickets"]),   inline=True)
        embed.add_field(name="Total Vouches",       value=str(s["total_vouches"]),  inline=True)
        embed.add_field(name="Total Confirmations", value=str(s["total_confirms"]), inline=True)
        embed.add_field(name="Total Deposits",      value=str(s["total_deposits"]), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="purge", description="Bulk delete messages in this channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
        from cogs.tickets import is_admin
        if not await is_admin(interaction.user):
            await interaction.response.send_message("Only admins can purge messages.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

    @app_commands.command(name="say", description="[Admin] Send a custom message or embed as the bot")
    @app_commands.describe(
        message="The message text / embed body",
        channel="Channel to send to (defaults to current channel)",
        embed_title="Embed title — if set, sends as an embed instead of plain text",
        embed_color="Embed colour as hex (e.g. ff0000 for red, default blurple)",
        image_url="Image URL to attach to the embed",
        anonymous="Hide your name from the embed footer (default: False)",
        button_label="Link button label (also requires button_url)",
        button_url="Link button URL (must start with https://)"
    )
    async def say(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None,
                  embed_title: str = None, embed_color: str = None, image_url: str = None,
                  anonymous: bool = False, button_label: str = None, button_url: str = None):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_admin
        if not await is_admin(interaction.user):
            await interaction.followup.send("Only admins can use this command.", ephemeral=True)
            return
        target = channel or interaction.channel
        view = None
        if button_label and button_url and button_url.startswith("http"):
            view = discord.ui.View()
            view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=button_label, url=button_url))
        if embed_title:
            try:
                color_val = int((embed_color or "5865F2").lstrip("#"), 16)
            except ValueError:
                color_val = 0x5865F2
            embed = discord.Embed(title=embed_title, description=message, color=color_val)
            if image_url:
                embed.set_image(url=image_url)
            if not anonymous:
                embed.set_footer(text=f"Sent by {interaction.user}")
            await target.send(embed=embed, view=view)
        else:
            await target.send(message, view=view)
        await interaction.followup.send(f"✅ Message sent to {target.mention}.", ephemeral=True)

    @app_commands.command(name="aboutus", description="Display the About Us embed")
    async def aboutus(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin, get_cached_config
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff or higher can use this command.", ephemeral=True)
            return
        cfg     = await get_cached_config(str(interaction.guild_id))
        message = cfg.get("aboutus_message", "We are a trusted middleman service for safe trades.")
        image   = cfg.get("aboutus_image", "")
        embed   = discord.Embed(title=f"About {interaction.guild.name}", description=message, color=discord.Color.blurple())
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        if image:
            embed.set_image(url=image)
        await interaction.followup.send(embed=embed)

    # ── Prefix Commands ───────────────────────────────────────────────────────

    @commands.command(name="blacklist")
    async def blacklist_prefix(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        from cogs.tickets import is_admin
        if not await is_admin(ctx.author):
            await ctx.send("Only admins can blacklist users.", delete_after=10)
            return
        await asyncio.to_thread(db.blacklist_user, str(user.id), str(ctx.guild.id), reason, str(ctx.author.id))
        embed = discord.Embed(title="User Blacklisted 🚫", description=f"{user.mention} has been blacklisted.", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)

    @commands.command(name="unblacklist")
    async def unblacklist_prefix(self, ctx: commands.Context, user: discord.Member):
        from cogs.tickets import is_admin
        if not await is_admin(ctx.author):
            await ctx.send("Only admins can unblacklist users.", delete_after=10)
            return
        await asyncio.to_thread(db.unblacklist_user, str(user.id), str(ctx.guild.id))
        await ctx.send(embed=discord.Embed(
            title="User Unblacklisted ✅",
            description=f"{user.mention} has been removed from the blacklist.",
            color=discord.Color.green()
        ))

    @commands.command(name="tradeinfo")
    async def tradeinfo_prefix(self, ctx: commands.Context, channel: discord.TextChannel = None):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only staff can view trade info.", delete_after=10)
            return
        ch = channel or ctx.channel
        ticket = await asyncio.to_thread(db.get_ticket, str(ch.id))
        if not ticket:
            await ctx.send("No ticket found for that channel.")
            return
        opener = ctx.guild.get_member(int(ticket["opener_id"]))
        claimer_text = "Unclaimed"
        if ticket["claimed_by"]:
            claimer = ctx.guild.get_member(int(ticket["claimed_by"]))
            claimer_text = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
        users = await asyncio.to_thread(db.get_ticket_users, str(ch.id))
        user_mentions = [f"<@{u}>" for u in users] or ["None"]
        embed = discord.Embed(title=f"Trade Info — #{ch.name}", color=discord.Color.blurple())
        embed.add_field(name="ID",      value=str(ticket["id"]),                                            inline=True)
        embed.add_field(name="Type",    value=ticket["ticket_type"],                                         inline=True)
        embed.add_field(name="Status",  value=ticket["status"],                                              inline=True)
        embed.add_field(name="Opened by",  value=opener.mention if opener else f"<@{ticket['opener_id']}>", inline=True)
        embed.add_field(name="Claimed by", value=claimer_text,                                               inline=True)
        embed.add_field(name="Opened at",  value=ticket["created_at"][:19].replace("T", " "),               inline=True)
        embed.add_field(name="Users in ticket", value=", ".join(user_mentions),                              inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="stats")
    async def stats_prefix(self, ctx: commands.Context):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only staff can view stats.", delete_after=10)
            return
        s = await asyncio.to_thread(db.get_stats, str(ctx.guild.id))
        embed = discord.Embed(title="Bot Statistics 📊", color=discord.Color.blurple())
        embed.add_field(name="Total Tickets",       value=str(s["total_tickets"]),  inline=True)
        embed.add_field(name="Open Tickets",        value=str(s["open_tickets"]),   inline=True)
        embed.add_field(name="Total Vouches",       value=str(s["total_vouches"]),  inline=True)
        embed.add_field(name="Total Confirmations", value=str(s["total_confirms"]), inline=True)
        embed.add_field(name="Total Deposits",      value=str(s["total_deposits"]), inline=True)
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    @commands.command(name="purge")
    async def purge_prefix(self, ctx: commands.Context, amount: int = 10):
        from cogs.tickets import is_admin
        if not await is_admin(ctx.author):
            await ctx.send("Only admins can purge messages.", delete_after=10)
            return
        amount = max(1, min(100, amount))
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"Deleted {len(deleted)} messages.")
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass

    @commands.command(name="aboutus")
    async def aboutus_prefix(self, ctx: commands.Context):
        from cogs.tickets import is_mm_or_admin, get_cached_config
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff or higher can use this command.", delete_after=10)
            return
        cfg     = await get_cached_config(str(ctx.guild.id))
        message = cfg.get("aboutus_message", "We are a trusted middleman service for safe trades.")
        image   = cfg.get("aboutus_image", "")
        embed   = discord.Embed(title=f"About {ctx.guild.name}", description=message, color=discord.Color.blurple())
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
        if image:
            embed.set_image(url=image)
        await ctx.send(embed=embed)

    @commands.command(name="say")
    async def say_prefix(self, ctx: commands.Context, *, message: str):
        from cogs.tickets import is_admin
        if not await is_admin(ctx.author):
            await ctx.send("Only admins can use this command.", delete_after=10)
            return
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(message)


async def setup(bot):
    await bot.add_cog(Admin(bot))

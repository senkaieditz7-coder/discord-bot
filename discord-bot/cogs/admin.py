import discord
from discord.ext import commands
from discord import app_commands
import db




class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_admin(self, member: discord.Member):
        admin_role_id = db.get_config(str(member.guild.id), "admin_role")
        if admin_role_id and any(r.id == int(admin_role_id) for r in member.roles):
            return True
        return member.guild_permissions.administrator

    @app_commands.command(name="blacklist", description="Blacklist a user from opening tickets")
    @app_commands.describe(user="User to blacklist", reason="Reason for blacklist")
    async def blacklist(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        if not self._is_admin(interaction.user):
            await interaction.response.send_message("Only admins can blacklist users.", ephemeral=True)
            return
        db.blacklist_user(str(user.id), str(interaction.guild_id), reason, str(interaction.user.id))
        embed = discord.Embed(
            title="User Blacklisted 🚫",
            description=f"{user.mention} has been blacklisted.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=f"By {interaction.user}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unblacklist", description="Remove a user from the blacklist")
    @app_commands.describe(user="User to unblacklist")
    async def unblacklist(self, interaction: discord.Interaction, user: discord.Member):
        if not self._is_admin(interaction.user):
            await interaction.response.send_message("Only admins can unblacklist users.", ephemeral=True)
            return
        db.unblacklist_user(str(user.id), str(interaction.guild_id))
        await interaction.response.send_message(
            embed=discord.Embed(
                title="User Unblacklisted ✅",
                description=f"{user.mention} has been removed from the blacklist.",
                color=discord.Color.green()
            )
        )

    @app_commands.command(name="tradeinfo", description="Get details on a trade ticket by channel")
    @app_commands.describe(channel="The ticket channel (leave blank for current channel)")
    async def tradeinfo(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can view trade info.", ephemeral=True)
            return
        ch = channel or interaction.channel
        ticket = db.get_ticket(str(ch.id))
        if not ticket:
            await interaction.response.send_message("No ticket found for that channel.", ephemeral=True)
            return

        opener = interaction.guild.get_member(int(ticket["opener_id"]))
        claimer_text = "Unclaimed"
        if ticket["claimed_by"]:
            claimer = interaction.guild.get_member(int(ticket["claimed_by"]))
            claimer_text = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"

        users = db.get_ticket_users(str(ch.id))
        user_mentions = [f"<@{u}>" for u in users] or ["None"]

        embed = discord.Embed(title=f"Trade Info — #{ch.name}", color=discord.Color.blurple())
        embed.add_field(name="ID", value=str(ticket["id"]), inline=True)
        embed.add_field(name="Type", value=ticket["ticket_type"], inline=True)
        embed.add_field(name="Status", value=ticket["status"], inline=True)
        embed.add_field(name="Opened by", value=opener.mention if opener else f"<@{ticket['opener_id']}>", inline=True)
        embed.add_field(name="Claimed by", value=claimer_text, inline=True)
        embed.add_field(name="Opened at", value=ticket["created_at"][:19].replace("T", " "), inline=True)
        embed.add_field(name="Users in ticket", value=", ".join(user_mentions), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="stats", description="View full bot statistics")
    async def stats(self, interaction: discord.Interaction):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can view stats.", ephemeral=True)
            return
        s = db.get_stats(str(interaction.guild_id))
        embed = discord.Embed(title="Bot Statistics 📊", color=discord.Color.blurple())
        embed.add_field(name="Total Tickets", value=str(s["total_tickets"]), inline=True)
        embed.add_field(name="Open Tickets", value=str(s["open_tickets"]), inline=True)
        embed.add_field(name="Total Vouches", value=str(s["total_vouches"]), inline=True)
        embed.add_field(name="Total Confirmations", value=str(s["total_confirms"]), inline=True)
        embed.add_field(name="Total Deposits", value=str(s["total_deposits"]), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="Bulk delete messages in this channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 10):
        if not self._is_admin(interaction.user):
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
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None,
        embed_title: str = None,
        embed_color: str = None,
        image_url: str = None,
        anonymous: bool = False,
        button_label: str = None,
        button_url: str = None,
    ):
        if not self._is_admin(interaction.user):
            await interaction.response.send_message("Only admins can use this command.", ephemeral=True)
            return

        target = channel or interaction.channel

        view = None
        if button_label and button_url and button_url.startswith("http"):
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=button_label,
                url=button_url
            ))

        if embed_title:
            try:
                color_val = int((embed_color or "5865F2").lstrip("#"), 16)
            except ValueError:
                color_val = 0x5865F2

            embed = discord.Embed(
                title=embed_title,
                description=message,
                color=color_val
            )
            if image_url:
                embed.set_image(url=image_url)
            if not anonymous:
                embed.set_footer(text=f"Sent by {interaction.user}")

            await target.send(embed=embed, view=view)
        else:
            await target.send(message, view=view)

        await interaction.response.send_message(
            f"✅ Message sent to {target.mention}.", ephemeral=True
        )

    @app_commands.command(name="aboutus", description="Display the About Us embed")
    async def aboutus(self, interaction: discord.Interaction):
        cfg = db.get_all_config(str(interaction.guild_id))
        message = cfg.get("aboutus_message", "We are a trusted middleman service for safe trades.")
        image = cfg.get("aboutus_image", "")

        embed = discord.Embed(
            title=f"About {interaction.guild.name}",
            description=message,
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        if image:
            embed.set_image(url=image)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Admin(bot))

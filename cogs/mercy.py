import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import db


class MercyView(discord.ui.View):
    def __init__(self, inviter: discord.Member, invitee: discord.Member, role_id: int):
        super().__init__(timeout=300)
        self.inviter = inviter
        self.invitee = invitee
        self.role_id = role_id
        self.responded = False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invitee.id:
            await interaction.response.send_message("This invite is not for you.", ephemeral=True)
            return
        if self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded = True
        self.stop()

        role = interaction.guild.get_role(self.role_id)
        if role:
            try:
                await self.invitee.add_roles(role, reason="Mercy invite accepted")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            title="Mercy Invite Accepted ✅",
            description=f"{self.invitee.mention} has accepted the mercy invite from {self.inviter.mention}.",
            color=discord.Color.green()
        )
        if role:
            embed.add_field(name="Role Granted", value=role.mention)
        await interaction.response.edit_message(embed=embed, view=None)

        cfg = await asyncio.to_thread(db.get_all_config, str(interaction.guild_id))
        dm_title = cfg.get("mercy_dm_title", "").strip() or "🎉 Mercy Invite Accepted"
        dm_body = cfg.get("mercy_dm_body", "").strip() or (
            f"Welcome! Your mercy invite from **{interaction.guild.name}** has been accepted "
            f"and your role has been granted."
        )
        dm_image = cfg.get("mercy_dm_image", "").strip()

        dm_embed = discord.Embed(
            title=dm_title,
            description=dm_body,
            color=discord.Color.green()
        )
        dm_embed.set_footer(text=interaction.guild.name)
        if dm_image:
            dm_embed.set_image(url=dm_image)

        try:
            await self.invitee.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invitee.id:
            await interaction.response.send_message("This invite is not for you.", ephemeral=True)
            return
        if self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded = True
        self.stop()
        embed = discord.Embed(
            title="Mercy Invite Declined ❌",
            description=f"{self.invitee.mention} has declined the mercy invite.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        pass


class Mercy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mercy", description="Send a mercy/special invite embed to a user")
    @app_commands.describe(user="The user to invite")
    async def mercy(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff can send mercy invites.", ephemeral=True)
            return

        if user.bot:
            await interaction.followup.send("Cannot send mercy invites to bots.", ephemeral=True)
            return

        cfg = await asyncio.to_thread(db.get_all_config, str(interaction.guild_id))
        mercy_role_id_str = cfg.get("mercy_role", "")
        mercy_message = cfg.get("mercy_message", "You have been selected for a special opportunity. Do you accept?")

        role_id = int(mercy_role_id_str) if mercy_role_id_str.isdigit() else 0
        role = interaction.guild.get_role(role_id) if role_id else None

        embed = discord.Embed(
            title="🌟 You've Been Invited",
            description=f"{user.mention}\n\n{mercy_message}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Invited by {interaction.user}")
        if role:
            embed.add_field(name="Role on Acceptance", value=role.mention)

        view = MercyView(interaction.user, user, role_id)
        await interaction.followup.send(content=user.mention, embed=embed, view=view)

    # ── Prefix Command ────────────────────────────────────────────────────────

    @commands.command(name="mercy")
    async def mercy_prefix(self, ctx: commands.Context, user: discord.Member):
        """Send a mercy/special invite embed to a user."""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff can send mercy invites.", delete_after=10)
            return

        if user.bot:
            await ctx.send("Cannot send mercy invites to bots.", delete_after=10)
            return

        cfg = await asyncio.to_thread(db.get_all_config, str(ctx.guild.id))
        mercy_role_id_str = cfg.get("mercy_role", "")
        mercy_message = cfg.get("mercy_message", "You have been selected for a special opportunity. Do you accept?")

        role_id = int(mercy_role_id_str) if mercy_role_id_str.isdigit() else 0
        role = ctx.guild.get_role(role_id) if role_id else None

        embed = discord.Embed(
            title="🌟 You've Been Invited",
            description=f"{user.mention}\n\n{mercy_message}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Invited by {ctx.author}")
        if role:
            embed.add_field(name="Role on Acceptance", value=role.mention)

        view = MercyView(ctx.author, user, role_id)
        await ctx.send(content=user.mention, embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Mercy(bot))

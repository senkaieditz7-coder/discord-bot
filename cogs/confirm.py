import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import db


class ConfirmView(discord.ui.View):
    def __init__(self, conf_id: int, user1: discord.Member, user2: discord.Member):
        super().__init__(timeout=300)
        self.conf_id = conf_id
        self.user1 = user1
        self.user2 = user2

    def _status_text(self, conf: dict) -> str:
        if not conf:
            return "Confirmation not found."

        def fmt(uid, status):
            emoji = {"pending": "⏳", "confirmed": "✅", "declined": "❌"}.get(status, "⏳")
            return f"{emoji} <@{uid}> — **{status.capitalize()}**"

        return (
            f"{fmt(conf['user1_id'], conf['user1_status'])}\n"
            f"{fmt(conf['user2_id'], conf['user2_status'])}"
        )

    async def _update_embed(self, message: discord.Message):
        cfg    = await asyncio.to_thread(db.get_all_config, str(message.guild.id))
        title  = cfg.get("confirm_title",  "Trade Confirmation")
        desc   = cfg.get("confirm_desc",   "Both traders must confirm to proceed with the trade.")
        footer = cfg.get("confirm_footer", "")
        image  = cfg.get("confirm_image",  "")

        conf = await asyncio.to_thread(db.get_confirmation, self.conf_id)

        embed = discord.Embed(
            title=title,
            description=f"{desc}\n\n{self._status_text(conf)}",
            color=discord.Color.gold()
        )
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)

        s1 = conf["user1_status"] if conf else "pending"
        s2 = conf["user2_status"] if conf else "pending"

        if s1 == "declined" or s2 == "declined":
            embed.color = discord.Color.red()
            embed.title = "Trade Declined"
            self.stop()
        elif s1 == "confirmed" and s2 == "confirmed":
            embed.color = discord.Color.green()
            embed.title = "Trade Confirmed!"
            self.stop()

        await message.edit(embed=embed, view=self if not self.is_finished() else None)

    async def _handle(self, interaction: discord.Interaction, action: str):
        uid  = str(interaction.user.id)
        conf = await asyncio.to_thread(db.get_confirmation, self.conf_id)
        if not conf:
            await interaction.response.send_message("Confirmation expired.", ephemeral=True)
            return

        if uid == conf["user1_id"] and conf["user1_status"] == "pending":
            await asyncio.to_thread(db.update_confirmation, self.conf_id, None, action, None)
        elif uid == conf["user2_id"] and conf["user2_status"] == "pending":
            await asyncio.to_thread(db.update_confirmation, self.conf_id, None, None, action)
        else:
            await interaction.response.send_message(
                "You are not part of this confirmation or already responded.", ephemeral=True
            )
            return

        await interaction.response.defer()
        await self._update_embed(interaction.message)

        conf = await asyncio.to_thread(db.get_confirmation, self.conf_id)
        if conf and conf["user1_status"] != "pending" and conf["user2_status"] != "pending":
            await asyncio.to_thread(db.resolve_confirmation, self.conf_id)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "confirmed")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "declined")

    async def on_timeout(self):
        conf = await asyncio.to_thread(db.get_confirmation, self.conf_id)
        if conf and conf["user1_status"] == "pending" and conf["user2_status"] == "pending":
            await asyncio.to_thread(db.resolve_confirmation, self.conf_id)


class Confirm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="confirm", description="Send a trade confirmation to two traders")
    @app_commands.describe(user1="First trader", user2="Second trader")
    async def confirm(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only MM staff can initiate confirmations.", ephemeral=True)
            return

        if user1.bot or user2.bot:
            await interaction.response.send_message("Cannot confirm trades with bots.", ephemeral=True)
            return

        await interaction.response.defer()

        conf_id = await asyncio.to_thread(
            db.create_confirmation,
            str(interaction.channel_id),
            str(interaction.guild_id),
            str(user1.id),
            str(user2.id)
        )

        cfg    = await asyncio.to_thread(db.get_all_config, str(interaction.guild_id))
        title  = cfg.get("confirm_title",  "Trade Confirmation")
        desc   = cfg.get("confirm_desc",   "Both traders must confirm to proceed with the trade.")
        footer = cfg.get("confirm_footer", "Confirmation expires in 5 minutes.")
        image  = cfg.get("confirm_image",  "")

        def fmt(uid, status):
            emoji = {"pending": "⏳", "confirmed": "✅", "declined": "❌"}.get(status, "⏳")
            return f"{emoji} <@{uid}> — **{status.capitalize()}**"

        embed = discord.Embed(
            title=title,
            description=f"{desc}\n\n{fmt(str(user1.id), 'pending')}\n{fmt(str(user2.id), 'pending')}",
            color=discord.Color.gold()
        )
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)

        view = ConfirmView(conf_id, user1, user2)
        await interaction.followup.send(
            content=f"{user1.mention} {user2.mention}",
            embed=embed,
            view=view
        )
        msg = await interaction.original_response()
        await asyncio.to_thread(db.update_confirmation, conf_id, str(msg.id), None, None)

    # ── Prefix Command ────────────────────────────────────────────────────────

    @commands.command(name="confirm")
    async def confirm_prefix(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member):
        """Send a trade confirmation to two traders."""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff can initiate confirmations.", delete_after=10)
            return

        if user1.bot or user2.bot:
            await ctx.send("Cannot confirm trades with bots.", delete_after=10)
            return

        conf_id = await asyncio.to_thread(
            db.create_confirmation,
            str(ctx.channel.id),
            str(ctx.guild.id),
            str(user1.id),
            str(user2.id)
        )

        cfg    = await asyncio.to_thread(db.get_all_config, str(ctx.guild.id))
        title  = cfg.get("confirm_title",  "Trade Confirmation")
        desc   = cfg.get("confirm_desc",   "Both traders must confirm to proceed with the trade.")
        footer = cfg.get("confirm_footer", "Confirmation expires in 5 minutes.")
        image  = cfg.get("confirm_image",  "")

        def fmt(uid, status):
            emoji = {"pending": "⏳", "confirmed": "✅", "declined": "❌"}.get(status, "⏳")
            return f"{emoji} <@{uid}> — **{status.capitalize()}**"

        embed = discord.Embed(
            title=title,
            description=f"{desc}\n\n{fmt(str(user1.id), 'pending')}\n{fmt(str(user2.id), 'pending')}",
            color=discord.Color.gold()
        )
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)

        view = ConfirmView(conf_id, user1, user2)
        msg = await ctx.send(content=f"{user1.mention} {user2.mention}", embed=embed, view=view)
        await asyncio.to_thread(db.update_confirmation, conf_id, str(msg.id), None, None)


async def setup(bot):
    await bot.add_cog(Confirm(bot))

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

    def _status_text(self):
        conf = db.get_confirmation(self.conf_id)
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
        cfg = db.get_all_config(str(message.guild.id))
        title = cfg.get("confirm_title", "Trade Confirmation")
        desc = cfg.get("confirm_desc", "Both traders must confirm to proceed with the trade.")
        footer = cfg.get("confirm_footer", "")
        image = cfg.get("confirm_image", "")

        embed = discord.Embed(
            title=title,
            description=f"{desc}\n\n{self._status_text()}",
            color=discord.Color.gold()
        )
        if footer:
            embed.set_footer(text=footer)
        if image:
            embed.set_image(url=image)

        conf = db.get_confirmation(self.conf_id)
        s1 = conf["user1_status"]
        s2 = conf["user2_status"]

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
        uid = str(interaction.user.id)
        conf = db.get_confirmation(self.conf_id)
        if not conf:
            await interaction.response.send_message("Confirmation expired.", ephemeral=True)
            return

        if uid == conf["user1_id"] and conf["user1_status"] == "pending":
            db.update_confirmation(self.conf_id, user1_status=action)
        elif uid == conf["user2_id"] and conf["user2_status"] == "pending":
            db.update_confirmation(self.conf_id, user2_status=action)
        else:
            await interaction.response.send_message("You are not part of this confirmation or already responded.", ephemeral=True)
            return

        await interaction.response.defer()
        await self._update_embed(interaction.message)

        conf = db.get_confirmation(self.conf_id)
        if conf["user1_status"] != "pending" and conf["user2_status"] != "pending":
            db.resolve_confirmation(self.conf_id)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "confirmed")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle(interaction, "declined")

    async def on_timeout(self):
        conf = db.get_confirmation(self.conf_id)
        if conf and conf["user1_status"] == "pending" and conf["user2_status"] == "pending":
            db.resolve_confirmation(self.conf_id)


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

        conf_id = db.create_confirmation(
            str(interaction.channel_id),
            str(interaction.guild_id),
            str(user1.id),
            str(user2.id)
        )

        cfg = db.get_all_config(str(interaction.guild_id))
        title = cfg.get("confirm_title", "Trade Confirmation")
        desc = cfg.get("confirm_desc", "Both traders must confirm to proceed with the trade.")
        footer = cfg.get("confirm_footer", "Confirmation expires in 5 minutes.")
        image = cfg.get("confirm_image", "")

        def fmt(uid, status):
            emoji = {"pending": "⏳", "confirmed": "✅", "declined": "❌"}.get(status, "⏳")
            return f"{emoji} <@{uid}> — **{status.capitalize()}**"

        embed = discord.Embed(
            title=title,
            description=f"{desc}\n\n{fmt(str(user1.id), 'pending')}\n{fmt(str(user2.id), 'pending')}",
            color=discord.Color.gold()
        )
        if footer:
            embed.set_footer(text=footer)
        if image:
            embed.set_image(url=image)

        view = ConfirmView(conf_id, user1, user2)
        await interaction.response.send_message(
            content=f"{user1.mention} {user2.mention}",
            embed=embed,
            view=view
        )
        msg = await interaction.original_response()
        db.update_confirmation(conf_id, message_id=str(msg.id))


async def setup(bot):
    await bot.add_cog(Confirm(bot))

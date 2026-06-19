import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import db


class FeeSplitView(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self._done = False

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if self._done:
            await interaction.response.send_message("A fee option has already been selected.", ephemeral=True)
            return False
        self._done = True
        return True

    @discord.ui.button(label="⚖️ Split Fee", style=discord.ButtonStyle.blurple)
    async def split_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self._disable_all()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=discord.Embed(
            title="⚖️ Split Fee Selected",
            description="Both traders will each cover **half** of the middleman fee.\nThe MM will confirm the exact amount in chat.",
            color=discord.Color.blurple()
        ))

    @discord.ui.button(label="💯 Full Fee (One Side)", style=discord.ButtonStyle.red)
    async def full_fee(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self._disable_all()
        await interaction.message.edit(view=self)
        await interaction.response.send_message(embed=discord.Embed(
            title="💯 Full Fee — One Side Selected",
            description="One trader will cover the **entire** middleman fee.\nThe MM will confirm the exact amount in chat.",
            color=discord.Color.red()
        ))


class Fees(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fees", description="Post the middleman service fee embed with split options")
    async def fees(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff or higher can post the fee embed.", ephemeral=True)
            return

        cfg = await asyncio.to_thread(db.get_all_config, str(interaction.guild_id))
        title  = cfg.get("fees_title") or "Middleman Service Fee"
        desc   = cfg.get("fees_desc")  or (
            "Your items are currently being held by the middleman.\n\n"
            "The MM will list the service fee price in chat. "
            "Please discuss with the other trader whether to split the fee or have one side cover it fully.\n\n"
            "⚠️ **Once you click a button, you can't redo it.**"
        )
        footer = cfg.get("fees_footer", "")
        image  = cfg.get("fees_image",  "")

        embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)

        await interaction.followup.send(embed=embed, view=FeeSplitView(str(interaction.guild_id)))

    @commands.command(name="fees")
    async def fees_prefix(self, ctx: commands.Context):
        """Post the middleman service fee embed. (MM or higher only)"""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff or higher can post the fee embed.", delete_after=10)
            return

        cfg = await asyncio.to_thread(db.get_all_config, str(ctx.guild.id))
        title  = cfg.get("fees_title") or "Middleman Service Fee"
        desc   = cfg.get("fees_desc")  or (
            "Your items are currently being held by the middleman.\n\n"
            "The MM will list the service fee price in chat. "
            "Please discuss with the other trader whether to split the fee or have one side cover it fully.\n\n"
            "⚠️ **Once you click a button, you can't redo it.**"
        )
        footer = cfg.get("fees_footer", "")
        image  = cfg.get("fees_image",  "")

        embed = discord.Embed(title=title, description=desc, color=discord.Color.green())
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)

        await ctx.send(embed=embed, view=FeeSplitView(str(ctx.guild.id)))


async def setup(bot):
    await bot.add_cog(Fees(bot))

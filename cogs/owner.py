import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
from config import BOT_OWNER_ID


class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="botrestart", description="[Bot Owner] Restart the bot process")
    async def botrestart(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            await interaction.response.send_message(
                "❌ Only the bot owner can use this command.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔄 Restarting...",
            description="The bot is restarting. It will be back online in a few seconds.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        await asyncio.sleep(1)
        os.execv(sys.executable, ["python"] + sys.argv)


async def setup(bot):
    await bot.add_cog(Owner(bot))

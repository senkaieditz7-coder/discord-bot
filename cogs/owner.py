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

    # ── $sync — instant guild slash command sync (no 1-hour global delay) ─────
    @commands.command(name="sync")
    async def sync_prefix(self, ctx: commands.Context):
        """[Owner] Sync slash commands to this guild instantly, then globally."""
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("❌ Only the bot owner can sync commands.", delete_after=10)
            return

        msg = await ctx.send("⏳ Syncing slash commands…")

        # Guild sync — instant, shows up in seconds
        guild_obj = discord.Object(id=ctx.guild.id)
        self.bot.tree.copy_global_to(guild=guild_obj)
        guild_cmds = await self.bot.tree.sync(guild=guild_obj)

        # Global sync — takes up to 1 hour to propagate to all servers
        global_cmds = await self.bot.tree.sync()

        await msg.edit(content=(
            f"✅ Synced **{len(guild_cmds)}** commands to this guild (instant).\n"
            f"✅ Synced **{len(global_cmds)}** commands globally (takes up to 1 hour to propagate)."
        ))

    # ── $debug — show bot health at a glance ─────────────────────────────────
    @commands.command(name="debug")
    async def debug_prefix(self, ctx: commands.Context):
        """[Owner] Show bot status: intents, cogs, command counts."""
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("❌ Only the bot owner can use debug.", delete_after=10)
            return

        intents = self.bot.intents
        prefix_cmds = list(self.bot.commands)
        slash_cmds  = list(self.bot.tree.get_commands())
        cog_list    = list(self.bot.cogs.keys())

        intent_lines = [
            f"{'✅' if intents.message_content else '❌'} **message_content** — prefix commands {'work' if intents.message_content else 'BROKEN (enable in Developer Portal → Bot → Privileged Intents)'}",
            f"{'✅' if intents.members else '❌'} **members**",
            f"{'✅' if intents.guilds else '❌'} **guilds**",
        ]

        embed = discord.Embed(
            title="🤖 Bot Debug Info",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🔌 Intents",
            value="\n".join(intent_lines),
            inline=False
        )
        embed.add_field(
            name=f"📦 Cogs ({len(cog_list)})",
            value=", ".join(cog_list) or "None",
            inline=False
        )
        embed.add_field(
            name="⌨️ Prefix commands",
            value=f"{len(prefix_cmds)} loaded (prefix: `{self.bot.command_prefix}`)",
            inline=True
        )
        embed.add_field(
            name="🔷 Slash commands",
            value=f"{len(slash_cmds)} registered",
            inline=True
        )
        embed.add_field(
            name="📡 Latency",
            value=f"{round(self.bot.latency * 1000)}ms",
            inline=True
        )
        embed.set_footer(text=f"Bot ID: {self.bot.user.id}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))

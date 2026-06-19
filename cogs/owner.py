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
            await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🔄 Restarting...",
            description="The bot is restarting. It will be back online in a few seconds.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(1)
        os.execv(sys.executable, ["python"] + sys.argv)

    # ── $sync — guild-only sync (instant, no duplicates) ─────────────────────
    @commands.command(name="sync")
    async def sync_prefix(self, ctx: commands.Context):
        """[Owner] Sync slash commands to THIS guild only (instant). No global duplication."""
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("❌ Only the bot owner can sync commands.", delete_after=10)
            return

        msg = await ctx.send("⏳ Syncing slash commands to this guild…")

        guild_obj = discord.Object(id=ctx.guild.id)
        self.bot.tree.copy_global_to(guild=guild_obj)
        guild_cmds = await self.bot.tree.sync(guild=guild_obj)

        await msg.edit(content=(
            f"✅ Synced **{len(guild_cmds)}** commands to this guild instantly.\n"
            f"💡 If you still see duplicates, run `$clearglobal` once to wipe globally-registered commands."
        ))

    # ── $clearglobal — one-time fix for duplicate commands ───────────────────
    @commands.command(name="clearglobal")
    async def clearglobal_prefix(self, ctx: commands.Context):
        """[Owner] Clear all globally-registered slash commands. Fixes duplicate command lists."""
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("❌ Only the bot owner can use this.", delete_after=10)
            return

        msg = await ctx.send("⏳ Clearing global slash commands…")
        self.bot.tree.clear_commands(guild=None)
        cleared = await self.bot.tree.sync()
        await msg.edit(content=(
            f"✅ Global slash commands cleared ({len(cleared)} remaining globally).\n"
            f"Commands are now **guild-only** — no more duplicates.\n"
            f"Run `$sync` to make sure guild commands are up to date."
        ))

    # ── $debug — show bot health at a glance ─────────────────────────────────
    @commands.command(name="debug")
    async def debug_prefix(self, ctx: commands.Context):
        """[Owner] Show bot status: intents, cogs, command counts, latency."""
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("❌ Only the bot owner can use debug.", delete_after=10)
            return

        intents      = self.bot.intents
        prefix_cmds  = list(self.bot.commands)
        slash_cmds   = list(self.bot.tree.get_commands())
        guild_obj    = discord.Object(id=ctx.guild.id)
        guild_cmds   = self.bot.tree.get_commands(guild=guild_obj)
        cog_list     = list(self.bot.cogs.keys())

        intent_lines = [
            f"{'✅' if intents.message_content else '❌'} **message_content** — prefix commands {'work' if intents.message_content else 'BROKEN'}",
            f"{'✅' if intents.members else '❌'} **members**",
            f"{'✅' if intents.guilds else '❌'} **guilds**",
        ]

        embed = discord.Embed(title="🤖 Bot Debug Info", color=discord.Color.blurple())
        embed.add_field(name="🔌 Intents",              value="\n".join(intent_lines),                     inline=False)
        embed.add_field(name=f"📦 Cogs ({len(cog_list)})", value=", ".join(cog_list) or "None",            inline=False)
        embed.add_field(name="⌨️ Prefix commands",       value=f"{len(prefix_cmds)} (prefix: `{self.bot.command_prefix}`)", inline=True)
        embed.add_field(name="🌐 Global slash cmds",     value=str(len(slash_cmds)),                        inline=True)
        embed.add_field(name="🏠 Guild slash cmds",      value=str(len(guild_cmds)),                        inline=True)
        embed.add_field(name="📡 Latency",               value=f"{round(self.bot.latency * 1000)}ms",       inline=True)
        embed.set_footer(text=f"Bot ID: {self.bot.user.id}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))

import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
from config import BOT_OWNER_ID

print('[owner] module loaded OK, BOT_OWNER_ID=' + str(BOT_OWNER_ID), flush=True)


class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print('[owner] cog __init__ done', flush=True)

    @app_commands.command(name='botrestart', description='[Bot Owner] Restart the bot process')
    async def botrestart(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            await interaction.response.send_message('Only the bot owner can use this.', ephemeral=True)
            return
        embed = discord.Embed(title='Restarting...', color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(1)
        os.execv(sys.executable, ['python'] + sys.argv)

    @commands.command(name='sync')
    async def sync_prefix(self, ctx: commands.Context):
        print('[owner] dollar sync called by ' + str(ctx.author.id), flush=True)
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send('Only the bot owner can sync commands.', delete_after=10)
            return
        msg = await ctx.send('Syncing...')
        try:
            guild_obj = discord.Object(id=ctx.guild.id)
            self.bot.tree.copy_global_to(guild=guild_obj)
            cmds = await self.bot.tree.sync(guild=guild_obj)
            await msg.edit(content='Synced ' + str(len(cmds)) + ' commands to this guild. Run dollar clearglobal to remove global duplicates.')
        except Exception as e:
            print('[owner] sync error: ' + str(e), flush=True)
            await msg.edit(content='Sync failed: ' + str(e))

    @commands.command(name='clearglobal')
    async def clearglobal_prefix(self, ctx: commands.Context):
        print('[owner] dollar clearglobal called by ' + str(ctx.author.id), flush=True)
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send('Only the bot owner can use this.')
            return
        msg = await ctx.send('Clearing global slash commands...')
        try:
            app_id = self.bot.application_id
            print('[owner] clearglobal app_id=' + str(app_id), flush=True)
            if app_id is None:
                await msg.edit(content='application_id not ready. Try again.')
                return
            await self.bot.http.bulk_upsert_global_commands(app_id, [])
            self.bot.tree.clear_commands(guild=None)
            print('[owner] clearglobal done', flush=True)
            await msg.edit(content='All global slash commands cleared. Run dollar sync to refresh.')
        except Exception as e:
            print('[owner] clearglobal error: ' + str(e), flush=True)
            await msg.edit(content='Failed: ' + str(e))

    @commands.command(name='debug')
    async def debug_prefix(self, ctx: commands.Context):
        print('[owner] dollar debug called by ' + str(ctx.author.id), flush=True)
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send('Only the bot owner can use debug.', delete_after=10)
            return
        prefix_cmds = list(self.bot.commands)
        slash_cmds = list(self.bot.tree.get_commands())
        guild_obj = discord.Object(id=ctx.guild.id)
        guild_cmds = self.bot.tree.get_commands(guild=guild_obj)
        cog_list = list(self.bot.cogs.keys())
        intents = self.bot.intents
        embed = discord.Embed(title='Bot Debug Info', color=discord.Color.blurple())
        embed.add_field(name='Intents', value=('MC:' + ('Y' if intents.message_content else 'N') + ' Mem:' + ('Y' if intents.members else 'N')), inline=True)
        embed.add_field(name='Cogs', value=', '.join(cog_list) or 'None', inline=False)
        embed.add_field(name='Prefix cmds', value=str(len(prefix_cmds)), inline=True)
        embed.add_field(name='Global slash', value=str(len(slash_cmds)), inline=True)
        embed.add_field(name='Guild slash', value=str(len(guild_cmds)), inline=True)
        embed.add_field(name='Latency', value=str(round(self.bot.latency * 1000)) + 'ms', inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))

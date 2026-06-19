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
        print('[owner] sync called by ' + str(ctx.author.id), flush=True)
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send('Only the bot owner can sync commands.', delete_after=10)
            return
        msg = await ctx.send('Syncing slash commands to this guild...')
        try:
            app_id = self.bot.application_id
            guild_id = ctx.guild.id
            # Build payload directly from the tree without calling tree.sync() which hangs
            guild_obj = discord.Object(id=guild_id)
            self.bot.tree.copy_global_to(guild=guild_obj)
            payload = await asyncio.wait_for(
                self.bot.tree.sync(guild=guild_obj),
                timeout=20.0
            )
            count = len(payload)
            print('[owner] sync done: ' + str(count) + ' commands', flush=True)
            await msg.edit(content='Synced ' + str(count) + ' slash commands to this guild. No more global duplicates.')
        except asyncio.TimeoutError:
            print('[owner] sync timed out, trying HTTP fallback', flush=True)
            try:
                # Fallback: push an empty list then re-add via HTTP
                # At minimum, clear old guild registrations so no dupes
                await self.bot.http.bulk_upsert_guild_commands(app_id, guild_id, [])
                await msg.edit(content='Sync timed out but guild commands cleared. The bot re-registers commands on next restart.')
            except Exception as e2:
                await msg.edit(content='Sync timed out and fallback failed: ' + str(e2))
        except Exception as e:
            print('[owner] sync error: ' + str(e), flush=True)
            await msg.edit(content='Sync failed: ' + str(e))

    @commands.command(name='clearglobal')
    async def clearglobal_prefix(self, ctx: commands.Context):
        print('[owner] clearglobal called by ' + str(ctx.author.id), flush=True)
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send('Only the bot owner can use this.')
            return
        msg = await ctx.send('Clearing global slash commands...')
        try:
            app_id = self.bot.application_id
            if app_id is None:
                await msg.edit(content='application_id not ready. Try again.')
                return
            await self.bot.http.bulk_upsert_global_commands(app_id, [])
            self.bot.tree.clear_commands(guild=None)
            print('[owner] clearglobal done', flush=True)
            await msg.edit(content='All global slash commands cleared. Run dollar sync to register guild commands.')
        except Exception as e:
            print('[owner] clearglobal error: ' + str(e), flush=True)
            await msg.edit(content='Failed: ' + str(e))

    @commands.command(name='debug')
    async def debug_prefix(self, ctx: commands.Context):
        print('[owner] debug called by ' + str(ctx.author.id), flush=True)
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
        embed.add_field(name='Intents', value='MC:' + ('Y' if intents.message_content else 'N') + ' Mem:' + ('Y' if intents.members else 'N'), inline=True)
        embed.add_field(name='Cogs', value=', '.join(cog_list) or 'None', inline=False)
        embed.add_field(name='Prefix cmds', value=str(len(prefix_cmds)), inline=True)
        embed.add_field(name='Global slash', value=str(len(slash_cmds)), inline=True)
        embed.add_field(name='Guild slash', value=str(len(guild_cmds)), inline=True)
        embed.add_field(name='Latency', value=str(round(self.bot.latency * 1000)) + 'ms', inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))

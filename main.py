import discord
from discord.ext import commands
import os
import asyncio
import db

TOKEN = os.environ.get('DISCORD_BOT_TOKEN')

COGS = [
    'cogs.transcripts',
    'cogs.tickets',
    'cogs.confirm',
    'cogs.vouches',
    'cogs.deposits',
    'cogs.admin',
    'cogs.fees',
    'cogs.botedit',
    'cogs.panels',
    'cogs.mercy',
    'cogs.automm',
    'cogs.help',
    'cogs.owner',
    'cogs.boost',
    'cogs.fill',
]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='$', intents=intents, help_command=None)

    async def setup_hook(self):
        print('[main] setup_hook start — BUILD v3', flush=True)
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print('[main] loaded ' + cog, flush=True)
            except Exception as e:
                print('[main] FAILED to load ' + cog + ': ' + str(e), flush=True)
        print('[main] all cogs attempted. Prefix commands: ' + str(len(list(self.commands))), flush=True)
        print('[main] No global sync — use dollar sync for guild commands.', flush=True)

    async def on_ready(self):
        print('[main] on_ready: ' + str(self.user) + ' (' + str(self.user.id) + ')', flush=True)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name='over trades | /help'
            )
        )

    async def on_guild_join(self, guild):
        print('[main] joined guild: ' + guild.name + ' (' + str(guild.id) + ')', flush=True)

    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Missing argument: ' + str(error.param.name), delete_after=15)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send('Bad argument: ' + str(error), delete_after=15)
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('You do not have permission.', delete_after=10)
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send('I am missing permissions: ' + str(error.missing_permissions), delete_after=10)
            return
        print('[main] prefix cmd error — ' + str(ctx.command) + ': ' + str(error), flush=True)
        try:
            await ctx.send('An error occurred: ' + str(error), delete_after=20)
        except Exception as send_err:
            print('[main] could not send error reply: ' + str(send_err), flush=True)

    async def on_app_command_error(self, interaction, error):
        print('[main] slash cmd error — ' + str(interaction.command) + ': ' + str(error), flush=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message('An error occurred: ' + str(error), ephemeral=True)
            else:
                await interaction.followup.send('An error occurred: ' + str(error), ephemeral=True)
        except Exception as send_err:
            print('[main] could not send slash error reply: ' + str(send_err), flush=True)


async def main():
    if not TOKEN:
        print('[main] DISCORD_BOT_TOKEN not set!', flush=True)
        return
    db.init_db()
    print('[main] DB initialized', flush=True)
    bot = Bot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == '__main__':
    asyncio.run(main())

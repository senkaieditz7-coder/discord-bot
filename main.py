import discord
from discord.ext import commands
import os
import asyncio
import db

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

COGS = [
    "cogs.transcripts",
    "cogs.tickets",
    "cogs.confirm",
    "cogs.vouches",
    "cogs.deposits",
    "cogs.admin",
    "cogs.fees",
    "cogs.botedit",
    "cogs.panels",
    "cogs.mercy",
    "cogs.automm",
    "cogs.help",
    "cogs.owner",
    "cogs.boost",
    "cogs.fill",
]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="$", intents=intents, help_command=None)

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"[+] Loaded {cog}", flush=True)
            except Exception as e:
                print(f"[!] Failed to load {cog}: {e}", flush=True)
        # No global sync here — use $sync to register guild commands,
        # and $clearglobal to wipe any leftover global commands.
        print("[✓] Cogs loaded. Use $sync to register slash commands.", flush=True)

    async def on_ready(self):
        print(f"[✓] Logged in as {self.user} ({self.user.id})", flush=True)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over trades | /help"
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        print(f"[+] Joined guild: {guild.name} ({guild.id})", flush=True)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`", delete_after=15)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}", delete_after=15)
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to use this command.", delete_after=10)
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"I am missing permissions: {error.missing_permissions}", delete_after=10)
            return
        print(f"[!] Prefix command error — {ctx.command} in #{ctx.channel} by {ctx.author}: {error}", flush=True)
        try:
            await ctx.send(f"An error occurred: {error}", delete_after=20)
        except Exception as send_err:
            print(f"[!] Could not send error reply: {send_err}", flush=True)

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        msg = f"An error occurred: {error}"
        print(f"[!] Slash command error — /{interaction.command} by {interaction.user}: {error}", flush=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception as send_err:
            print(f"[!] Could not send slash error reply: {send_err}", flush=True)


async def main():
    if not TOKEN:
        print("[!] DISCORD_BOT_TOKEN is not set. Please add it to your secrets.", flush=True)
        return

    db.init_db()
    print("[✓] Database initialized.", flush=True)

    bot = Bot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

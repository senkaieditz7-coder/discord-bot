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
]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"[+] Loaded {cog}")
            except Exception as e:
                print(f"[!] Failed to load {cog}: {e}")
        try:
            synced = await self.tree.sync()
            print(f"[✓] Synced {len(synced)} slash commands globally.")
        except Exception as e:
            print(f"[!] Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"[✓] Logged in as {self.user} ({self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over trades | /help"
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        print(f"[+] Joined guild: {guild.name} ({guild.id})")

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        msg = f"An error occurred: {error}"
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass
        print(f"[!] Command error in {interaction.command}: {error}")


async def main():
    if not TOKEN:
        print("[!] DISCORD_BOT_TOKEN is not set. Please add it to your secrets.")
        return

    db.init_db()
    print("[✓] Database initialized.")

    bot = Bot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())

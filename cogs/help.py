import discord
from discord.ext import commands
from discord import app_commands
import asyncio


COMMANDS = {
    "🎫 Tickets": [
        ("/claim  or  $claim", "Claim this ticket as MM staff"),
        ("/close  or  $close", "Close and delete this ticket channel"),
        ("/adduser @user  or  $adduser @user", "Add a user to this ticket"),
        ("/removeuser @user  or  $removeuser @user", "Remove a user from this ticket"),
        ("/transfer @mm  or  $transfer @mm", "Transfer this ticket to another middleman"),
    ],
    "✅ Trade Confirmation": [
        ("/confirm @user1 @user2  or  $confirm @user1 @user2", "Send a trade confirmation to two traders — both must accept or decline"),
    ],
    "⭐ Vouches": [
        ("/vouch @user [note]  or  $vouch @user [note]", "Leave a vouch for a user after a trade (24h spam protection)"),
        ("/rep [@user]  or  $rep [@user]", "Check a user's reputation and vouch count"),
        ("/setvouches @user count  or  $setvouches @user count", "[Staff] Manually set a user's vouch count"),
        ("/deletevouch @user @voucher  or  $deletevouch @user @voucher", "[Staff] Delete the latest vouch from one user to another"),
    ],
    "💰 Deposits": [
        ("/depositset @user type", "[MM+] Log a deposit (In-Game / Real Money / Custom) — slash only"),
        ("/depositcheck @user  or  $depositcheck @user", "[Staff] View full deposit history for a user"),
        ("/depositdelete @user id  or  $depositdelete @user id", "[Staff] Delete a deposit record by ID"),
    ],
    "🛡️ Admin": [
        ("/blacklist @user [reason]  or  $blacklist @user [reason]", "[Admin] Blacklist a user from opening tickets"),
        ("/unblacklist @user  or  $unblacklist @user", "[Admin] Remove a user from the blacklist"),
        ("/tradeinfo [channel]  or  $tradeinfo", "[Staff] View details on a trade ticket"),
        ("/stats  or  $stats", "[Staff] View full bot statistics"),
        ("/purge amount  or  $purge [amount]", "[Admin] Bulk delete 1–100 messages in a channel"),
        ("/say message ...  or  $say message", "[Admin] Send a message as the bot"),
        ("/aboutus  or  $aboutus", "[MM+] Display the About Us embed"),
    ],
    "💸 Fees": [
        ("/fees  or  $fees", "[MM+] Post the middleman fee embed with split options"),
    ],
    "🎛️ Bot Config": [
        ("/botedit", "[Bot Owner only] Edit all bot settings — roles, channels, panels, modals, and more — slash only"),
        ("/botrestart", "[Bot Owner only] Restart the bot process"),
    ],
    "🎨 Panels": [
        ("/ticketpanel", "[Staff] Post the trade ticket panel — slash only"),
        ("/supportpanel", "[Staff] Post the support ticket panel — slash only"),
        ("/autommpanel", "[Staff] Post the Auto MM panel — slash only"),
    ],
    "🌟 Mercy": [
        ("/mercy @user  or  $mercy @user", "[Staff] Send a mercy/special invite embed to a user with Accept/Decline buttons"),
    ],
    "🎭 Fill": [
        ("/fill  or  $fill", "[MM+] Grant yourself all roles below your highest role that you don't already have"),
    ],
    "🤖 Auto MM": [
        ("Open ticket from panel", "Select a service from the dropdown → MM is pinged → bot walks you through the trade"),
        ("`done` (type in ticket)", "Confirm you are ready to proceed — both traders must type this"),
        ("`.automm` (any channel)", "Money sender: confirm payment sent — bot will DM you to verify"),
        ("`.done` (type in ticket)", "Mark trade complete — funds released when both traders type this"),
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=cat, value=cat) for cat in COMMANDS]
        super().__init__(placeholder="Browse command categories…", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        cmds = COMMANDS[category]
        embed = discord.Embed(title=f"Help — {category}", color=discord.Color.blurple())
        for name, desc in cmds:
            embed.add_field(name=f"`{name}`", value=desc, inline=False)
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpSelect())


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Display all bot commands")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff or higher can use the help command.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📖 Bot Help",
            description=(
                "Use the dropdown below to browse commands by category.\n"
                "Most commands support both `/slash` and `$prefix` syntax.\n\n"
                + "\n".join(f"**{cat}** — {len(cmds)} command(s)" for cat, cmds in COMMANDS.items())
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Select a category to see detailed commands.")
        await interaction.followup.send(embed=embed, view=HelpView(), ephemeral=True)

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        """Display all bot commands. (MM or higher only)"""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff or higher can use the help command.", delete_after=10)
            return

        embed = discord.Embed(
            title="📖 Bot Help",
            description=(
                "Use the dropdown below to browse commands by category.\n"
                "Most commands support both `/slash` and `$prefix` syntax.\n\n"
                + "\n".join(f"**{cat}** — {len(cmds)} command(s)" for cat, cmds in COMMANDS.items())
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Select a category to see detailed commands.")
        await ctx.send(embed=embed, view=HelpView())


async def setup(bot):
    await bot.add_cog(Help(bot))

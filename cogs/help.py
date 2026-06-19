import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# ── Prefix support chart (which commands have $prefix variants) ───────────────
PREFIX_CHART = """```
Command            Prefix ($)   Slash (/)
─────────────────────────────────────────
vouch              ✅            ✅
rep                ✅            ✅
setvouches         ✅            ✅
deletevouch        ✅            ✅
fees               ✅            ✅
fill               ✅            ✅
help               ✅            ✅
aboutus            ✅            ✅
claim              ✅            ✅
close              ✅            ✅
adduser            ✅            ✅
removeuser         ✅            ✅
transfer           ✅            ✅
confirm            ✅            ✅
mercy              ✅            ✅
blacklist          ✅            ✅
unblacklist        ✅            ✅
tradeinfo          ✅            ✅
stats              ✅            ✅
purge              ✅            ✅
say                ✅            ✅
depositcheck       ✅            ✅
depositdelete      ✅            ✅
sync               ✅            ❌
debug              ✅            ❌
─────────────────────────────────────────
depositset         ❌            ✅  (modal required)
botedit            ❌            ✅  (owner only)
botrestart         ❌            ✅  (owner only)
ticketpanel        ❌            ✅
supportpanel       ❌            ✅
autommpanel        ❌            ✅
```"""

COMMANDS = {
    "📋 Prefix Chart": [
        ("Chart shows all commands and whether they support $ prefix or / slash", PREFIX_CHART),
    ],
    "🎫 Tickets": [
        ("$claim  /  /claim", "[MM+] Claim this ticket as your own"),
        ("$close  /  /close", "[MM+] Close and delete this ticket channel"),
        ("$adduser @user  /  /adduser @user", "[MM+] Add a user to this ticket"),
        ("$removeuser @user  /  /removeuser @user", "[MM+] Remove a user from this ticket"),
        ("$transfer @mm  /  /transfer @mm", "[MM+] Transfer ticket to another middleman"),
    ],
    "✅ Trade Confirmation": [
        ("$confirm @user1 @user2  /  /confirm @user1 @user2", "[MM+] Send a trade confirmation — both traders must Accept or Decline"),
    ],
    "⭐ Vouches": [
        ("$vouch @user [note]  /  /vouch @user [note]", "[MM+] Leave a vouch after a trade (24h spam protection)"),
        ("$rep [@user]  /  /rep [@user]", "[MM+] Check a user's reputation and vouch count"),
        ("$setvouches @user count  /  /setvouches @user count", "[MM+] Manually set a user's vouch count"),
        ("$deletevouch @user @voucher  /  /deletevouch @user @voucher", "[MM+] Delete the latest vouch between two users"),
    ],
    "💰 Deposits": [
        ("/depositset @user type", "[MM+] Log a deposit — In-Game / Real Money / Custom (slash only — uses modal)"),
        ("$depositcheck @user  /  /depositcheck @user", "[MM+] View full deposit history for a user"),
        ("$depositdelete @user deposit_id  /  /depositdelete @user id", "[MM+] Delete a deposit record by ID"),
    ],
    "🛡️ Admin": [
        ("$blacklist @user [reason]  /  /blacklist @user [reason]", "[Admin] Blacklist a user from opening tickets"),
        ("$unblacklist @user  /  /unblacklist @user", "[Admin] Remove a user from the blacklist"),
        ("$tradeinfo [#channel]  /  /tradeinfo [channel]", "[MM+] View full details on a ticket"),
        ("$stats  /  /stats", "[MM+] View full bot statistics"),
        ("$purge [amount]  /  /purge amount", "[Admin] Bulk delete 1–100 messages"),
        ("$say message  /  /say message ...", "[Admin] Send a message or embed as the bot"),
        ("$aboutus  /  /aboutus", "[MM+] Display the About Us embed"),
    ],
    "💸 Fees": [
        ("$fees  /  /fees", "[MM+] Post the middleman fee embed with Split / Full-Fee buttons"),
    ],
    "🌟 Mercy": [
        ("$mercy @user  /  /mercy @user", "[MM+] Send a mercy/special invite embed with Accept/Decline buttons"),
    ],
    "🎭 Fill": [
        ("$fill  /  /fill", "[MM+] Grant yourself all roles below your highest role"),
    ],
    "🎨 Panels": [
        ("/ticketpanel", "[MM+] Post the trade ticket panel (slash only)"),
        ("/supportpanel", "[MM+] Post the support ticket panel (slash only)"),
        ("/autommpanel", "[MM+] Post the Auto MM panel (slash only)"),
    ],
    "🤖 Auto MM": [
        ("Open ticket from panel", "Select a service from the dropdown → bot walks both traders through the trade"),
        ("`done` (type in ticket channel)", "Mark yourself ready — both traders must type this to proceed"),
        ("`.automm` (type in any channel)", "Sender: confirm payment has been sent"),
        ("`.done` (type in ticket channel)", "Mark trade complete — funds released when both traders type this"),
    ],
    "🎛️ Bot Config": [
        ("/botedit", "[Owner only] Edit ALL bot settings — roles, channels, panels, modals (slash only)"),
        ("/botrestart", "[Owner only] Restart the bot process (slash only)"),
        ("$sync", "[Owner only] Instantly sync slash commands to this guild"),
        ("$debug", "[Owner only] Show bot health — intents, cogs, command counts, latency"),
    ],
}


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=cat, value=cat) for cat in COMMANDS]
        super().__init__(placeholder="Browse command categories…", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        entries  = COMMANDS[category]

        embed = discord.Embed(title=f"Help — {category}", color=discord.Color.blurple())

        if category == "📋 Prefix Chart":
            # Special display: full chart as a single field
            embed.description = entries[0][1]
            embed.set_footer(text="✅ = supported   ❌ = not available for that style")
        else:
            for name, desc in entries:
                embed.add_field(name=f"`{name}`", value=desc, inline=False)

        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpSelect())


def _overview_embed():
    lines = []
    for cat, cmds in COMMANDS.items():
        if cat == "📋 Prefix Chart":
            lines.append(f"**{cat}** — shows which commands have `$` prefix support")
        else:
            lines.append(f"**{cat}** — {len(cmds)} command(s)")
    embed = discord.Embed(
        title="📖 Bot Help",
        description=(
            "Use the dropdown to browse commands by category.\n"
            "Commands marked **[MM+]** require MM role or higher.\n"
            "Commands marked **[Admin]** require the Admin role.\n"
            "Commands marked **[Owner]** are restricted to the bot owner only.\n\n"
            + "\n".join(lines)
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Select a category to see detailed commands and syntax.")
    return embed


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
        await interaction.followup.send(embed=_overview_embed(), view=HelpView(), ephemeral=True)

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        """Display all bot commands. (MM or higher only)"""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff or higher can use the help command.", delete_after=10)
            return
        await ctx.send(embed=_overview_embed(), view=HelpView())


async def setup(bot):
    await bot.add_cog(Help(bot))

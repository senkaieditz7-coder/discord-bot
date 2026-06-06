import discord
from discord.ext import commands
from discord import app_commands


COMMANDS = {
    "🎫 Tickets": [
        ("/claim", "Claim this ticket as MM staff"),
        ("/close", "Close and delete this ticket channel"),
        ("/adduser @user", "Add a user to this ticket"),
        ("/removeuser @user", "Remove a user from this ticket"),
        ("/transfer @mm", "Transfer this ticket to another middleman"),
    ],
    "✅ Trade Confirmation": [
        ("/confirm @user1 @user2", "Send a trade confirmation to two traders — both must accept or decline"),
    ],
    "⭐ Vouches": [
        ("/vouch @user [note]", "Leave a vouch for a user after a trade (24h spam protection)"),
        ("/rep [@user]", "Check a user's reputation and vouch count"),
        ("/setvouches @user count", "[Staff] Manually set a user's vouch count"),
        ("/deletevouch @user @voucher", "[Staff] Delete the latest vouch from one user to another"),
    ],
    "💰 Deposits": [
        ("/depositset @user type", "[MM+] Log a deposit (In-Game / Real Money / Custom)"),
        ("/depositcheck @user", "[Staff] View full deposit history for a user"),
        ("/depositdelete @user id", "[Staff] Delete a deposit record by ID"),
    ],
    "🛡️ Admin": [
        ("/blacklist @user [reason]", "[Admin] Blacklist a user from opening tickets"),
        ("/unblacklist @user", "[Admin] Remove a user from the blacklist"),
        ("/tradeinfo [channel]", "[Staff] View details on a trade ticket"),
        ("/stats", "[Staff] View full bot statistics"),
        ("/purge amount", "[Admin] Bulk delete 1–100 messages in a channel"),
        ("/say message [channel] [embed_title] [embed_color] [image_url] [anonymous] [button_label] [button_url]", "[Admin] Send a plain message or styled embed — optional link button"),
        ("/aboutus", "Display the About Us embed"),
    ],
    "💸 Fees": [
        ("/fees amount", "Calculate and display the middleman fee for a trade value"),
    ],
    "🎛️ Bot Config": [
        ("/botedit", "[Bot Owner only] Edit all bot settings — roles, channels, panels, modals, and more"),
        ("/botrestart", "[Bot Owner only] Restart the bot process"),
    ],
    "🎨 Panels": [
        ("/ticketpanel", "[Staff] Post the trade ticket panel — users fill in a form before ticket is created"),
        ("/supportpanel", "[Staff] Post the support ticket panel — users fill in a form before ticket is created"),
        ("/autommpanel", "[Staff] Post the Auto MM panel — users pick a service from a dropdown"),
    ],
    "🌟 Mercy": [
        ("/mercy @user", "[Staff] Send a mercy/special invite embed to a user with Accept/Decline buttons"),
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
        options = [
            discord.SelectOption(label=cat, value=cat)
            for cat in COMMANDS
        ]
        super().__init__(placeholder="Browse command categories…", options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        cmds = COMMANDS[category]
        embed = discord.Embed(
            title=f"Help — {category}",
            color=discord.Color.blurple()
        )
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
        embed = discord.Embed(
            title="📖 Bot Help",
            description=(
                "Use the dropdown below to browse commands by category.\n\n"
                + "\n".join(
                    f"**{cat}** — {len(cmds)} command(s)"
                    for cat, cmds in COMMANDS.items()
                )
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Select a category to see detailed commands.")
        await interaction.response.send_message(embed=embed, view=HelpView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))

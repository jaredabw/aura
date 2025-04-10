import discord

class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=10)
        self.user_id = user_id
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.value is not None:
            await interaction.response.defer()

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You are not authorised to confirm this action.", ephemeral=True
            )
            return

        self.value = True
        await interaction.message.edit(content="Action confirmed.", view=None)
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.value is not None:
            await interaction.response.defer()

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You are not authorised to cancel this action.", ephemeral=True
            )
            return

        self.value = False
        await interaction.message.edit(content="Action cancelled.", view=None)
        await interaction.response.defer()
        self.stop()

import os
import disnake
from disnake.ext import commands
from database import db

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))
WELCOME_ROLE_ID = int(os.getenv("WELCOME_ROLE_ID", 0))


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member):
        """Приветствие новых участников"""
        settings = await db.get_welcome_settings(member.guild.id)
        
        channel_id = settings["channel_id"] if settings else WELCOME_CHANNEL_ID
        role_id = settings["role_id"] if settings else WELCOME_ROLE_ID
        
        # Выдача роли
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role)
                except disnake.Forbidden:
                    print(f"Нет прав для выдачи роли {role_id}")
        
        # Приветственное сообщение
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                message_template = settings["message_template"] if settings else None
                
                if message_template:
                    content = message_template.format(
                        user=member.mention,
                        guild=member.guild.name,
                        member_count=member.guild.member_count
                    )
                else:
                    content = (
                        f"🎉 Привет, {member.mention}! Добро пожаловать на сервер **{member.guild.name}**!\n"
                        f"Теперь нас {member.guild.member_count} участников!"
                    )
                
                embed = disnake.Embed(
                    title=f"Добро пожаловать на {member.guild.name}!",
                    color=0x2f3136,
                    timestamp=disnake.utils.utcnow()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"ID: {member.id}")
                
                await channel.send(embed=embed)
    
    @commands.command(name="test_welcome")
    @commands.has_permissions(administrator=True)
    async def test_welcome(self, ctx, member: disnake.Member = None):
        """Тест системы приветствий (админская команда)"""
        member = member or ctx.author
        
        settings = await db.get_welcome_settings(ctx.guild.id)
        role_id = settings["role_id"] if settings else WELCOME_ROLE_ID
        
        assigned_roles = []
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                assigned_roles.append(role.mention)
        
        embed = disnake.Embed(
            title=f"[ТЕСТ] Добро пожаловать на {ctx.guild.name}!",
            color=0x99aab5,
            timestamp=disnake.utils.utcnow()
        )
        embed.add_field(name="Пользователь", value=member.mention, inline=False)
        embed.add_field(name="Участников на сервере", value=str(ctx.guild.member_count), inline=True)
        embed.add_field(
            name="Выданные роли", 
            value=", ".join(assigned_roles) if assigned_roles else "Нет", 
            inline=True
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id} | Тестовое сообщение")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="welcome_setup")
    @commands.has_permissions(administrator=True)
    async def welcome_setup_cmd(
        self, 
        ctx, 
        channel: disnake.TextChannel, 
        role: disnake.Role, 
        *, 
        message: str = None
    ):
        """Настроить систему приветствий
        Использование: !welcome_setup #канал @роль [сообщение]
        В сообщении используй {user}, {guild}, {member_count}"""
        
        await db.set_welcome_settings(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            role_id=role.id,
            message_template=message
        )
        
        await ctx.send(
            f"✅ Настройки приветствий сохранены!\n"
            f"📺 Канал: {channel.mention}\n"
            f"👤 Роль: {role.mention}\n"
            f"📝 Шаблон: {message or 'Стандартный'}"
        )


def setup(bot):
    bot.add_cog(WelcomeCog(bot))

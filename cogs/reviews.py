import os
import disnake
from disnake.ext import commands
from database import db

REVIEWS_CHANNEL_ID = int(os.getenv("REVIEWS_CHANNEL_ID", 0))


class ReviewModal(disnake.ui.Modal):
    """Модальное окно для создания отзыва"""
    
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Оценка (1-5)",
                placeholder="Введите число от 1 до 5",
                custom_id="review_rating",
                style=disnake.TextInputStyle.short,
                min_length=1,
                max_length=1,
                required=True
            ),
            disnake.ui.TextInput(
                label="Текст отзыва",
                placeholder="Напишите ваш отзыв...",
                custom_id="review_text",
                style=disnake.TextInputStyle.paragraph,
                min_length=5,
                max_length=1000,
                required=True
            ),
        ]
        super().__init__(
            title="Оставить отзыв",
            custom_id="review_modal",
            components=components
        )
    
    async def callback(self, inter: disnake.ModalInteraction):
        rating_str = inter.text_values["review_rating"]
        text = inter.text_values["review_text"]
        
        try:
            rating = int(rating_str)
            if rating < 1 or rating > 5:
                raise ValueError()
        except ValueError:
            await inter.response.send_message(
                "❌ Оценка должна быть числом от 1 до 5!", 
                ephemeral=True
            )
            return
        
        review_id = await db.create_review(
            user_id=inter.user.id,
            username=str(inter.user),
            rating=rating,
            text=text
        )
        
        if REVIEWS_CHANNEL_ID:
            channel = inter.bot.get_channel(REVIEWS_CHANNEL_ID)
            if channel:
                stars = "⭐" * rating
                embed = disnake.Embed(
                    title=f"📝 Новый отзыв #{review_id}",
                    description=text,
                    color=0x2f3136,
                    timestamp=disnake.utils.utcnow()
                )
                embed.add_field(name="Оценка", value=f"{stars} ({rating}/5)", inline=True)
                embed.add_field(name="Автор", value=inter.user.mention, inline=True)
                embed.set_footer(text=f"ID отзыва: {review_id}")
                
                msg = await channel.send(embed=embed)
                await db.update_review_message_id(review_id, msg.id)
        
        await inter.response.send_message(
            f"✅ Ваш отзыв #{review_id} успешно опубликован!", 
            ephemeral=True
        )


class ReviewButtonView(disnake.ui.View):
    """Персистентная кнопка для создания отзыва - работает после рестарта"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @disnake.ui.button(
        label="Оставить отзыв", 
        style=disnake.ButtonStyle.success,
        emoji="⭐",
        custom_id="persistent_review_button"
    )
    async def create_review_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(ReviewModal())


class ReviewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Регистрируем персистентный View сразу
        self.bot.add_view(ReviewButtonView())
        print("✅ ReviewButtonView зарегистрирован")
    
    @commands.command(name="button_rew")
    @commands.has_permissions(administrator=True)
    async def button_rew(self, ctx):
        """Отправить embed с кнопкой создания отзыва"""
        embed = disnake.Embed(
            title="📝 Оставить отзыв",
            description="Нажмите кнопку ниже, чтобы оставить отзыв.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Оценку от 1 до 5\n"
                        "• Текст отзыва",
            color=0x2f3136
        )
        
        view = ReviewButtonView()
        await ctx.send(embed=embed, view=view)

    @commands.slash_command(name="setup_review", description="Отправить панель создания отзыва")
    @commands.has_permissions(administrator=True)
    async def setup_review_slash(self, inter: disnake.ApplicationCommandInteraction):
        """Слеш-команда для отправки панели отзыва"""
        embed = disnake.Embed(
            title="📝 Оставить отзыв",
            description="Нажмите кнопку ниже, чтобы оставить отзыв.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Оценку от 1 до 5\n"
                        "• Текст отзыва",
            color=0x2f3136
        )
        
        view = ReviewButtonView()
        await inter.response.send_message(embed=embed, view=view)

    @commands.slash_command(name="stats", description="Статистика бота")
    async def stats_slash(self, inter: disnake.ApplicationCommandInteraction):
        """Слеш-команда для статистики бота"""
        embed = disnake.Embed(
            title="📊 Статистика бота",
            color=0x2f3136
        )
        embed.add_field(name="Серверов", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Участников", value=sum(g.member_count for g in self.bot.guilds), inline=True)
        
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="test_reviews")
    @commands.has_permissions(administrator=True)
    async def test_reviews(self, ctx):
        """Тест системы отзывов (админская команда)"""
        embed = disnake.Embed(
            title="[ТЕСТ] Система отзывов",
            description="Проверка работы системы отзывов...",
            color=0x99aab5,
            timestamp=disnake.utils.utcnow()
        )
        
        # Создаем тестовый отзыв
        test_review_id = await db.create_review(
            user_id=ctx.author.id,
            username=str(ctx.author),
            rating=5,
            text="Тестовый отзыв для проверки системы!"
        )
        
        embed.add_field(name="Статус", value="✅ База данных работает", inline=False)
        embed.add_field(name="Тестовый отзыв", value=f"ID: #{test_review_id}", inline=True)
        embed.add_field(name="Канал отзывов", value=f"<#{REVIEWS_CHANNEL_ID}>" if REVIEWS_CHANNEL_ID else "❌ Не настроен", inline=True)
        
        # Отправляем тестовое сообщение с кнопкой
        test_view = ReviewButtonView()
        embed2 = disnake.Embed(
            title="[ТЕСТ] Кнопка отзыва",
            description="Нажмите кнопку ниже для теста модального окна",
            color=0x2f3136
        )
        
        await ctx.send(embed=embed)
        await ctx.send(embed=embed2, view=test_view)


def setup(bot):
    bot.add_cog(ReviewsCog(bot))

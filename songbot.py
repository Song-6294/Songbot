import discord
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
import asyncio
import os

intents = discord.Intents.default()
intents.message_content = True  # 메시지 읽기 권한
bot = commands.Bot(command_prefix="!", intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6로 인한 문제 방지
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class SearchResultView(View):
    def __init__(self, ctx, results):
        super().__init__(timeout=30)  # 30초 동안 유효한 버튼
        self.ctx = ctx
        self.results = results

        # 각 검색 결과에 대해 버튼 추가
        for i, result in enumerate(results):
            button = Button(label=result['title'], style=discord.ButtonStyle.primary, custom_id=str(i))
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Interaction 응답 대기 상태 설정

        index = int(interaction.data["custom_id"])
        selected_track = self.results[index]

        try:
            # 선택한 곡을 바로 재생
            player = await YTDLSource.from_url(selected_track['url'], loop=bot.loop, stream=True)

            # 음성 채널 연결
            voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
            if not voice_client:
                if not interaction.user.voice:
                    await interaction.followup.send("먼저 음성 채널에 입장해야 합니다.", ephemeral=True)
                    return
                channel = interaction.user.voice.channel
                voice_client = await channel.connect()

            # 현재 재생 중이면 대기열에 추가
            if voice_client.is_playing():
                queue.append(player)
                await interaction.followup.send(
                    f"현재 재생 중인 곡이 있습니다. **{player.title}**이(가) 대기열에 추가되었습니다.",
                    ephemeral=True,
                )
            else:
                # 재생
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))

                # 재생 메시지 전송
                embed = discord.Embed(
                    title="🎵 현재 재생 중",
                    description=f"**{player.title}**\n[링크 바로가기]({selected_track['url']})",
                    color=0x00FF00,
                )
                embed.set_footer(text=f"요청자: {interaction.user}", icon_url=interaction.user.avatar.url)
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"오류가 발생했습니다: {e}", ephemeral=True)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.event
async def on_ready():
    print('다음으로 로그인합니다: ')
    print(bot.user.name)
    print('connection was successful')

    # 봇 상태 변경
    await bot.change_presence(status=discord.Status.online, activity=discord.Game("!재생 !정지"))


    # 재생 목록 관리용 리스트
queue = []

@bot.command(name="검색")
async def search(ctx, *, query: str):
    # yt_dlp를 사용하여 검색 결과 가져오기
    ytdl_search_options = {
        'quiet': True,
        'format': 'bestaudio/best',
        'default_search': 'ytsearch5',  # YouTube에서 최대 3개의 검색 결과 가져오기
        'noplaylist': True
    }
    ytdl = yt_dlp.YoutubeDL(ytdl_search_options)

    # 검색 결과 추출
    try:
        info = ytdl.extract_info(query, download=False)
        if 'entries' not in info or not info['entries']:
            await ctx.send("검색 결과가 없습니다.")
            return

        # 검색 결과에서 필요한 정보만 추출
        results = [{
            'title': entry['title'],
            'url': entry['webpage_url']
        } for entry in info['entries']]

    except Exception as e:
        await ctx.send(f"검색 중 오류가 발생했습니다: {e}")
        return

    # 검색 결과를 Embed 형식으로 표시
    embed = discord.Embed(
        title="🔍 검색 결과",
        description="\n".join([f"{i + 1}. {result['title']}" for i, result in enumerate(results)]),
        color=0x1E90FF
    )
    embed.set_footer(text="30초 안에 원하는 곡을 선택하세요.")

    # View를 사용하여 버튼 추가
    view = SearchResultView(ctx, results)
    await ctx.send(embed=embed, view=view)


@bot.command(name="재생")
async def play(ctx, url: str):
    if not ctx.message.author.voice:
        await ctx.send("먼저 음성 채널에 입장해야 합니다.")
        return

    channel = ctx.message.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if not voice_client:
        voice_client = await channel.connect()

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        queue.append(player)

        # 임베드 형식으로 메시지 표시
        embed = discord.Embed(
            title="🎶 곡이 추가되었습니다!",
            description=f"**{player.title}**\n[링크 바로가기]({url})",
            color=0x1E90FF
        )
        embed.set_footer(text=f"요청자: {ctx.author}", icon_url=ctx.author.avatar.url)
        await ctx.send(embed=embed)

        if len(queue) == 1:
            await play_next(ctx)

async def play_next(ctx):
    if queue:
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and not voice_client.is_playing():
            player = queue.pop(0)
            voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

            # 현재 재생 중 곡을 임베드로 표시
            embed = discord.Embed(
                title="🎵 현재 재생 중",
                description=f"**{player.title}**",
                color=0x00FF00
            )
            embed.set_footer(text="즐거운 시간 되세요!")
            await ctx.send(embed=embed)
    else:
        await ctx.send("재생할 곡이 없습니다.")

@bot.command(name="목록")
async def show_queue(ctx):
    if queue:
        embed = discord.Embed(
            title="📜 현재 재생 목록",
            description="\n".join([f"{i+1}. {track.title}" for i, track in enumerate(queue)]),
            color=0xFFD700
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("현재 재생 목록이 비어 있습니다.")

@bot.command(name="정지")
async def stop(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        embed = discord.Embed(
            title="⏹ 음악 정지",
            description="음악을 멈추고 봇이 퇴장했습니다.",
            color=0xFF4500
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("봇이 음성 채널에 있지 않습니다.")

@bot.command(name="스킵")
async def skip(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("현재 곡이 스킵되었습니다.")
        await play_next(ctx)
    else:
        await ctx.send("현재 재생 중인 음악이 없습니다.")

@bot.command(name="현재곡")
async def now_playing(ctx):
    # 현재 음성 클라이언트를 가져오기
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if not voice_client or not voice_client.is_playing():
        await ctx.send("현재 재생 중인 곡이 없습니다.")
        return

    # 현재 재생 중인 곡 가져오기
    current_player = voice_client.source  # PCMVolumeTransformer 객체
    
    if isinstance(current_player, YTDLSource):
        embed = discord.Embed(
            title="🎶 현재 재생 중인 곡",
            description=f"**{current_player.title}**",
            color=0x1E90FF
        )
        embed.add_field(name="링크", value=f"[바로가기]({current_player.url})", inline=False)
        embed.set_footer(text=f"요청자: {ctx.author}", icon_url=ctx.author.avatar.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("현재 재생 중인 곡 정보를 가져올 수 없습니다.")

# 토큰으로 봇 실행
bot.run('MTMxODIzMTc3NTIzMDgyNDQ0OA.GO-7vX.eADxFFpQAcXqxmtYFem8oGM7GHs8C8fUqOCJjM')
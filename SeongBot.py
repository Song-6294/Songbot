import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

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
        # URL을 재생 목록에 추가
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        queue.append(player)
        await ctx.send(f'곡이 재생 목록에 추가되었습니다: {player.title}')

        # 재생 목록이 비어 있지 않으면 첫 번째 곡부터 자동으로 재생
        if len(queue) == 1:
            await play_next(ctx)

    # 자동으로 다음 곡을 재생하는 함수
async def play_next(ctx):
    if len(queue) > 0:
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client and not voice_client.is_playing():
            player = queue.pop(0)  # 재생 목록에서 첫 번째 곡을 꺼냄
            voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            await ctx.send(f'재생 중: {player.title}')
    else:
        await ctx.send("재생할 곡이 없습니다.")

@bot.command(name="정지")
async def stop(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("음악을 멈추고 봇이 퇴장했습니다.")
    else:
        await ctx.send("봇이 음성 채널에 있지 않습니다.")


# 일시 정지 명령어
@bot.command(name="일시정지")
async def pause(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("음악이 일시 정지되었습니다.")
    else:
        await ctx.send("현재 재생 중인 음악이 없습니다.")

# 재개 명령어
@bot.command(name="재개")
async def resume(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("음악이 재개되었습니다")
    else:
        await ctx.send("현재 일시 정지된 음악이 없습니다.")

        # 재생 목록 보기 명령어
@bot.command(name="목록")
async def show_queue(ctx):
    if queue:
        await ctx.send("현재 재생 목록:\n" + "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(queue)]))
    else:
        await ctx.send("현재 재생 목록에 곡이 없습니다.")

# 재생 목록에서 특정 곡 삭제 명령어
@bot.command(name="삭제")
async def remove_from_queue(ctx, index: int):
    if 0 < index <= len(queue):
        removed_track = queue.pop(index - 1)
        await ctx.send(f"곡 '{removed_track.title}'이(가) 재생 목록에서 제거되었습니다.")
    else:
        await ctx.send("잘못된 번호입니다.")


        # 스킵 명령어
@bot.command(name="스킵")
async def skip(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    
    if voice_client and voice_client.is_playing():
        voice_client.stop()  # 현재 곡을 멈춤
        await ctx.send("현재 곡이 스킵되었습니다.")
        await play_next(ctx)  # 다음 곡을 재생
    else:
        await ctx.send("현재 재생 중인 음악이 없습니다.")

# 환경변수에서 토큰 로드
bot.run(os.getenv('DISCORD_TOKEN'))  # .env 파일에서 로드된 토큰 사용
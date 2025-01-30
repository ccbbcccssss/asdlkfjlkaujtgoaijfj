import discord
from discord.ext import commands
from discord import PCMVolumeTransformer
import yt_dlp as youtube_dl
from collections import deque
import asyncio
import os
import certifi

# Set SSL certificate paths
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

TOKEN = 'MY_TOKEN'

queues = {}

# Updated YouTubeDL configuration with search fixes
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'nocheckcertificate': True,
    'default_search': 'ytsearch:',  # Force YouTube search prefix
    'source_address': '0.0.0.0',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

class YTDLSource(PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_query(cls, query, *, loop=None):
        try:
            # Auto-add ytsearch: prefix if not a URL
            if not query.startswith(('http://', 'https://')):
                query = f'ytsearch:{query}'
            
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                return [ydl.sanitize_info(entry) for entry in info['entries']] if 'entries' in info else [ydl.sanitize_info(info)]
        except Exception as e:
            raise Exception(f"Search failed: {str(e)}")

async def play_next(ctx):
    guild_id = ctx.guild.id
    try:
        if queues[guild_id]['queue']:
            next_song = queues[guild_id]['queue'].popleft()
            queues[guild_id]['now_playing'] = next_song

            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn -b:a 128k'
            }
            
            source = discord.FFmpegPCMAudio(next_song['url'], **ffmpeg_options)
            source = discord.PCMVolumeTransformer(source)
            source.volume = 1.0
            
            ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            await ctx.send(f"🔊 현재 재생중: {next_song['title']}")
    except Exception as e:
        await ctx.send(f"❌ Playback Error: {str(e)}")

@bot.command(name='play')
async def play(ctx, *, query):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ 음성 채널에 들어가있지 않습니다!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            data = await YTDLSource.from_query(query)
            
            guild_id = ctx.guild.id
            if guild_id not in queues:
                queues[guild_id] = {'queue': deque(), 'now_playing': None}
            
            # Always take first result from search
            song = data[0] if data else None
            if song:
                queues[guild_id]['queue'].append(song)
                await ctx.send(f"🎶 대기됨: {song['title']}")
            
                if not voice_client.is_playing():
                    await play_next(ctx)
            else:
                await ctx.send("❌ 결과를 못찾았습니다")
                
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ 일시 중지")
    else:
        await ctx.send("❌ 재생 중이 아닙니다.")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ 재개")
    else:
        await ctx.send("❌ 일시 중지되어 있지 않습니다")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        if ctx.guild.id in queues:
            queues[ctx.guild.id]['queue'].clear()
            queues[ctx.guild.id]['now_playing'] = None
        ctx.voice_client.stop()
        await ctx.send("⏹️ 재생을 멈추고 대기열을 초기화 합니다")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("⏭️ 스킵")
        await play_next(ctx)

@bot.command(name='queue')
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and (queues[guild_id]['queue'] or queues[guild_id]['now_playing']):
        message = []
        if queues[guild_id]['now_playing']:
            message.append(f"**현재 재생중:** {queues[guild_id]['now_playing']['title']}")
        
        if queues[guild_id]['queue']:
            message.append("\n**Queue:**")
            for i, song in enumerate(queues[guild_id]['queue'], 1):
                message.append(f"{i}. {song['title']}")
        
        await ctx.send("\n".join(message[:10]))
    else:
        await ctx.send("❌ 대기열이 비었습니다")

@bot.command(name='loop')
async def loop(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id]['loop'] = not queues[guild_id]['loop']
        status = "✅ 활성화" if queues[guild_id]['loop'] else "❌ 비활성화"
        await ctx.send(f"🔁 Loop {status}")
    else:
        await ctx.send("❌ 대기열이 비었습니다")

@bot.command(name='volume', help='Adjust volume (0-100)')
async def volume(ctx, volume: int):
    if ctx.voice_client.source:
        if 0 < volume <= 100:
            ctx.voice_client.source.volume = volume / 100
            await ctx.send(f"🔊 불륨이 {volume}%로 설정되었습니다")
        else:
            await ctx.send("❌ 불륨은 1에서 100사이여야 합니다")

@bot.command(name='join')
async def join(ctx):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ 당신은 음성 채널에 참가하지 않았습니다!")
            
        # Check existing connection
        if ctx.voice_client:
            if ctx.voice_client.channel == ctx.author.voice.channel:
                return await ctx.send("✅ 이미 음성 채널에 참가했습니다")
            await ctx.voice_client.move_to(ctx.author.voice.channel)
            return await ctx.send(f"🚚 {ctx.author.voice.channel.name}로 이동했습니다")
            
        await ctx.author.voice.channel.connect()
        await ctx.send(f"✅ 참가함 {ctx.author.voice.channel.name}")
        
    except Exception as e:
        await ctx.send(f"❌ Connection error: {str(e)}")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ 음성 채널에 나갔습니다")
    else:
        await ctx.send("❌ 음성 채널에 들어가있지 않습니다")
        

@bot.command(name='test')
async def test(ctx):
    try:
        # Get existing voice client or connect
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        # Stop any existing playback
        if voice_client.is_playing():
            voice_client.stop()
            
        # Play test audio
        source = discord.FFmpegPCMAudio('https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3')
        voice_client.play(source)
        await ctx.send("✅ 오디오 테스트 시작")
        
    except AttributeError:
        await ctx.send("❗ 먼저 음성 채널에 들어가야 합니다!")
    except Exception as e:
        await ctx.send(f"❌ Test failed: {str(e)}")



bot.run(TOKEN)

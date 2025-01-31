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

# Combined configuration with extractor args and cookies
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
    'cookiefile': os.path.join(os.getcwd(), 'cookies.txt'),  # Method 2
    'extractor_args': {  # Method 1
        'youtube': {
            'player_client': ['android', 'web'],
            'skip': ['dash', 'hls']
        }
    },
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    },
    'retries': 3,
    'fragment_retries': 10,
    'skip_unavailable_fragments': True
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
            # Auto-detect search query vs URL
            if not query.startswith(('http://', 'https://')):
                query = f'ytsearch:{query}'
            
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                return [ydl.sanitize_info(entry) for entry in info['entries']] if 'entries' in info else [ydl.sanitize_info(info)]
        except youtube_dl.utils.DownloadError as e:
            if "NSIG" in str(e):
                raise Exception("YouTube access failed - try updating cookies.txt or wait before retrying")
            raise


async def play_next(ctx):
    guild_id = ctx.guild.id
    try:
        if guild_id not in queues or not queues[guild_id]['queue']:
            return

        voice_client = ctx.voice_client
        if not voice_client or voice_client.is_playing():
            return

        next_song = queues[guild_id]['queue'].popleft()
        
        # Audio source creation
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -b:a 128k'
        }
        
        source = discord.FFmpegPCMAudio(next_song['url'], **ffmpeg_options)
        source = discord.PCMVolumeTransformer(source)
        source.volume = 1.0

        def after_play(error):
            if error:
                print(f'Player error: {error}')
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        voice_client.play(source, after=after_play)
        await ctx.send(f"🔊 현재 재생중: {next_song.get('title', 'Unknown Track')}")

    except Exception as e:
        await ctx.send(f"❌ Playback Error: {str(e)}")
        print(f"Detailed error: {repr(e)}")

@bot.command(name='play')
async def play(ctx, *, query):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ 음성 채널에 참가하지 않았습니다!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            data = await YTDLSource.from_query(query)
            
            guild_id = ctx.guild.id
            if guild_id not in queues:
                queues[guild_id] = {'queue': deque(), 'loop': False, 'now_playing': None}
            
            # Filter invalid entries
            valid_songs = [song for song in data if song and 'url' in song]
            if not valid_songs:
                return await ctx.send("❌ 노래를 찾을 수 없습니다")
            
            for song in valid_songs:
                queues[guild_id]['queue'].append(song)
                await ctx.send(f"🎶 대기됨: {song.get('title', 'Unknown Track')}")
            
            if not voice_client.is_playing():
                await play_next(ctx)
                
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
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        # Disconnect after callback temporarily
        voice_client.stop()
        await ctx.send("⏭️ 곡을 스킵합니다")
        
        # Wait for clean stop
        await asyncio.sleep(0.5)
        
        # Manually trigger next track
        await play_next(ctx)
    else:
        await ctx.send("❌ 스킵할 것이 없습니다")

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
        await ctx.send(f"🔁 반복 재생 {status}")
        
        # Only force restart if not already playing
        if queues[guild_id]['loop'] and not ctx.voice_client.is_playing():
            await play_next(ctx, force=True)
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
            return await ctx.send(f"🚚 {ctx.author.voice.channel.name}으로 이동했습니다")
            
        await ctx.author.voice.channel.connect()
        await ctx.send(f"✅ {ctx.author.voice.channel.name}에 참가했습니다")
        
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

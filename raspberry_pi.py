import discord
from discord.ext import commands
from discord import PCMVolumeTransformer
import yt_dlp as youtube_dl
from collections import deque
import asyncio
import os
import certifi

# SSL Certificate Configuration
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

TOKEN = 'YOUR_BOT_TOKEN'

# Pi-specific optimizations
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -threads 2',
    'options': '-vn -b:a 128k -filter:a "volume=0.8"'
}

queues = {}

ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'cookiefile': os.path.join(os.getcwd(), 'cookies.txt'),
    'extractor_args': {
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
        'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    },
    'retries': 5,
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
        self.title = data.get('title', 'Unknown Track')

    @classmethod
    async def from_query(cls, query):
        try:
            if not query.startswith(('http://', 'https://')):
                query = f'ytsearch:{query}'
            
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                return [ydl.sanitize_info(entry) for entry in info.get('entries', [])]
        except Exception as e:
            raise Exception(f"YoutubeDL Error: {str(e)}")

async def play_next(ctx):
    guild_id = ctx.guild.id
    try:
        if not queues.get(guild_id) or not queues[guild_id]['queue']:
            return

        voice_client = ctx.voice_client
        if not voice_client or voice_client.is_playing():
            return

        next_song = queues[guild_id]['queue'].popleft()
        queues[guild_id]['now_playing'] = next_song

        # Pi-optimized audio source
        source = discord.FFmpegPCMAudio(next_song['url'], **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source)
        source.volume = 1.0

        def after_play(error):
            if error:
                print(f'Playback error: {error}')
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        voice_client.play(source, after=after_play)
        await ctx.send(f"🔊 Now playing: {next_song.get('title', 'Unknown Track')}")

    except Exception as e:
        await ctx.send(f"❌ Playback Error: {str(e)}")
        print(f"Pi Debug: {repr(e)}")

@bot.command(name='play')
async def play(ctx, *, query):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ Join a voice channel first!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            data = await YTDLSource.from_query(query)
            
            guild_id = ctx.guild.id
            if guild_id not in queues:
                queues[guild_id] = {'queue': deque(), 'loop': False, 'now_playing': None}
            
            valid_songs = [song for song in data if song and 'url' in song]
            if not valid_songs:
                return await ctx.send("❌ No valid songs found")
            
            for song in valid_songs:
                queues[guild_id]['queue'].append(song)
                await ctx.send(f"🎶 Queued: {song.get('title', 'Unknown Track')}")
            
            if not voice_client.is_playing():
                await play_next(ctx)
                
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='skip')
async def skip(ctx):
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏭️ Skipped current song")
        await asyncio.sleep(0.5)  # Pi-friendly delay
        await play_next(ctx)
    else:
        await ctx.send("❌ Nothing to skip")

# [Include other commands: pause, resume, stop, queue, loop, volume, join, leave]

@bot.command(name='test')
async def test(ctx):
    """Test audio playback without YouTube dependencies"""
    try:
        voice_client = await ctx.author.voice.channel.connect()
        source = discord.FFmpegPCMAudio('https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3', **FFMPEG_OPTIONS)
        voice_client.play(source)
        await ctx.send("✅ Playing test audio")
    except Exception as e:
        await ctx.send(f"❌ Test failed: {str(e)}")

bot.run(TOKEN)

"""
cogs/tts.py — TTS봇
- /TTS채널설정 으로 텍스트 채널 지정
- 지정 채널에 채팅 입력 시, 채팅 친 유저가 있는 음성 채널로 자동 입장해서 읽어줌
- 봇이 이미 음성채널에 있으면 이동하지 않고 현재 채널에서 계속 읽음
- /TTS끄기 / /TTS켜기 로 토글 가능
"""

import asyncio
import os
import sqlite3
import tempfile
import discord
from discord.ext import commands
from discord import app_commands
import edge_tts
from gtts import gTTS  # 백업용

MAX_TTS_LENGTH = 100  

# === Edge TTS 설정 (완전 무료) ===
EDGE_VOICE = "ko-KR-SunHiNeural"  # 예지 느낌: 여성 밝음
# 다른 추천: ko-KR-InJoonNeural (남성), ko-KR-HyunsuNeural, ko-KR-JiMinNeural

def _init_db():
    conn = sqlite3.connect("bdo_data.db", timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tts_settings (
            guild_id    INTEGER PRIMARY KEY,
            text_ch_id  INTEGER,
            voice_ch_id INTEGER,
            enabled     INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def _get_tts_settings(guild_id: int) -> dict | None:
    conn = sqlite3.connect("bdo_data.db", timeout=30, check_same_thread=False)
    row = conn.execute(
        "SELECT text_ch_id, voice_ch_id, enabled FROM tts_settings WHERE guild_id=?",
        (guild_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"text_ch_id": row[0], "voice_ch_id": row[1], "enabled": bool(row[2])}

def _upsert_tts(guild_id: int, **kwargs):
    conn = sqlite3.connect("bdo_data.db", timeout=30, check_same_thread=False)
    row = conn.execute(
        "SELECT text_ch_id, voice_ch_id, enabled FROM tts_settings WHERE guild_id=?",
        (guild_id,)
    ).fetchone()
    if row:
        current = {"text_ch_id": row[0], "voice_ch_id": row[1], "enabled": row[2]}
        current.update(kwargs)
        conn.execute(
            "UPDATE tts_settings SET text_ch_id=?, voice_ch_id=?, enabled=? WHERE guild_id=?",
            (current["text_ch_id"], current["voice_ch_id"], current["enabled"], guild_id)
        )
    else:
        conn.execute(
            "INSERT INTO tts_settings (guild_id, text_ch_id, voice_ch_id, enabled) VALUES (?,?,?,?)",
            (guild_id, kwargs.get("text_ch_id"), kwargs.get("voice_ch_id"), kwargs.get("enabled", 1))
        )
    conn.commit()
    conn.close()

class TTSCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}  
        _init_db()

    def get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]


    @app_commands.command(name="tts채널설정", description="[관리자] TTS가 읽을 텍스트 채널을 지정합니다")
    @app_commands.default_permissions(administrator=True)
    async def set_tts_text_ch(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        _upsert_tts(interaction.guild.id, text_ch_id=channel.id)
        await interaction.response.send_message(
            f"✅ TTS 텍스트 채널이 {channel.mention}으로 설정되었습니다.", ephemeral=True
        )

    @app_commands.command(name="tts켜기", description="[관리자] TTS를 활성화합니다")
    @app_commands.default_permissions(administrator=True)
    async def tts_on(self, interaction: discord.Interaction):
        _upsert_tts(interaction.guild.id, enabled=1)
        await interaction.response.send_message("✅ TTS가 활성화되었습니다.", ephemeral=True)

    @app_commands.command(name="tts끄기", description="[관리자] TTS를 비활성화합니다")
    @app_commands.default_permissions(administrator=True)
    async def tts_off(self, interaction: discord.Interaction):
        _upsert_tts(interaction.guild.id, enabled=0)
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
        await interaction.response.send_message("🔇 TTS가 비활성화되었습니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = _get_tts_settings(message.guild.id)
        if not settings or not settings["enabled"]:
            return
        if not settings["text_ch_id"] or message.channel.id != settings["text_ch_id"]:
            return

        # 채팅 친 유저가 음성채널에 있는지 확인
        if not message.author.voice or not message.author.voice.channel:
            return  # 음성채널 미입장 유저 무시 (조용히 스킵)

        text = message.clean_content.strip()
        if not text:
            return
        if text.startswith("http://") or text.startswith("https://"):
            return
        if len(text) > MAX_TTS_LENGTH:
            text = text[:MAX_TTS_LENGTH] + "..."

        read_text = f"{message.author.display_name}. {text}"
        user_voice_ch = message.author.voice.channel

        await self._speak(message.guild, user_voice_ch, read_text)

    async def _speak(self, guild: discord.Guild, user_voice_ch: discord.VoiceChannel, text: str):
        lock = self.get_lock(guild.id)
        async with lock:
            vc = guild.voice_client

            try:
                if not vc or not vc.is_connected():
                    # 봇이 음성채널에 없으면 → 유저 채널로 입장
                    vc = await user_voice_ch.connect()
                else:
                    # 봇이 이미 음성채널에 있으면 → 이동하지 않고 현재 채널에서 그대로 읽음
                    pass
            except Exception as e:
                print(f"⚠️ TTS 음성채널 입장 실패: {e}")
                return

            tmp_path = None
            try:
                # --- Edge TTS (무료) ---
                communicate = edge_tts.Communicate(text, EDGE_VOICE)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name
                # edge_tts는 async, 여기선 동기화
                import asyncio
                asyncio.run(communicate.save(tmp_path))
                # 백업: gTTS

                done = asyncio.Event()
                def after(err):
                    done.set()

                source = discord.FFmpegPCMAudio(tmp_path)
                source = discord.PCMVolumeTransformer(source, volume=0.8)
                vc.play(source, after=after)
                await done.wait()

            except Exception as e:
                print(f"⚠️ TTS 재생 오류: {e}")
                # CLOVA 실패 시 gTTS로 폴백
                try:
                    print("→ gTTS로 폴백 시도")
                    tts = gTTS(text=text, lang="ko")
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        tmp_path = tmp.name
                    tts.save(tmp_path)
                except Exception as e2:
                    print(f"⚠️ gTTS 폴백도 실패: {e2}")
                    return
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TTSCog(bot))

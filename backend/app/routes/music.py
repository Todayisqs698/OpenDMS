"""Music API routes."""
from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_MUSIC_DIR = os.path.join(_PROJECT_ROOT, "data", "music")
os.makedirs(_MUSIC_DIR, exist_ok=True)

router = APIRouter(prefix="/api/music", tags=["music"])


def _scan_local_music(query: str = "") -> list:
    """Scan data/music/ for local audio files."""
    results = []
    if not os.path.isdir(_MUSIC_DIR):
        return results
    for fname in sorted(os.listdir(_MUSIC_DIR)):
        if not fname.lower().endswith((".mp3", ".wav", ".flac", ".m4a", ".ogg")):
            continue
        name = os.path.splitext(fname)[0]
        artist, title = "本地音乐", name
        if " - " in name:
            parts = name.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        if query and query.lower() not in name.lower():
            continue
        results.append({
            "id": hash(fname) % 1000000,
            "name": title,
            "artist": artist,
            "album": "",
            "duration": 0,
            "url": f"/static/music/{quote(fname)}",
            "source": "local",
        })
    return results


_MUSIC_API_BASE = "http://localhost:3000"

_music_state = {
    "playing": False,
    "current_song": {"id": 0, "name": "", "artist": "", "album": "", "url": "", "cover": "", "duration": 0},
    "playlist": [],
    "playlist_index": -1,
    "volume": 80,
    "message": "",
}


@router.get("/state")
def get_music_state():
    """返回当前音乐播放状态"""
    return {"status": "ok", "data": _music_state}


class MusicSearchRequest(BaseModel):
    keyword: str = ""


@router.post("/search")
async def music_search(req: MusicSearchRequest):
    """搜索歌曲：优先本地文件，失败时降级网易云API"""
    # 1. 先扫本地
    local = _scan_local_music(req.keyword)
    if local:
        return {"status": "ok", "songs": local}
    # 2. 本地无结果，尝试网易云API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_MUSIC_API_BASE}/cloudsearch",
                params={"keywords": req.keyword},
            )
            data = resp.json()
            # 网易云 API 返回非 200 表示需要登录/Cookie失效，直接降级
            if data.get("code") != 200:
                raise ValueError(f"网易云API错误: code={data.get('code')}")
            songs = []
            result_songs = data.get("result", {}).get("songs", [])
            for s in result_songs[:10]:
                artists_list = s.get("ar") or s.get("artists", [])
                artists = ", ".join(a.get("name", "") for a in artists_list)
                album = s.get("al") or s.get("album") or {}
                songs.append({
                    "id": s.get("id", 0),
                    "name": s.get("name", ""),
                    "artist": artists,
                    "album": album.get("name", ""),
                    "duration": s.get("duration", 0),
                    "cover": (album.get("picUrl") or "") + "?param=300y300",
                })
            return {"status": "ok", "songs": songs}
    except Exception:
        pass
    # 3. 兜底：本地+在线都不可用时返回演示曲目
    demo_all = [
        # 王菲
        {"id": 1, "name": "传奇", "artist": "王菲", "album": "传奇", "duration": 262, "cover": "", "source": "demo"},
        {"id": 2, "name": "红豆", "artist": "王菲", "album": "唱游", "duration": 253, "cover": "", "source": "demo"},
        {"id": 3, "name": "匆匆那年", "artist": "王菲", "album": "匆匆那年", "duration": 241, "cover": "", "source": "demo"},
        {"id": 4, "name": "因为爱情", "artist": "王菲 & 陈奕迅", "album": "将爱", "duration": 228, "cover": "", "source": "demo"},
        {"id": 5, "name": "如愿", "artist": "王菲", "album": "如愿", "duration": 275, "cover": "", "source": "demo"},
        # 周杰伦
        {"id": 6, "name": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269, "cover": "", "source": "demo"},
        {"id": 7, "name": "七里香", "artist": "周杰伦", "album": "七里香", "duration": 299, "cover": "", "source": "demo"},
        {"id": 8, "name": "夜曲", "artist": "周杰伦", "album": "十一月的萧邦", "duration": 226, "cover": "", "source": "demo"},
        {"id": 9, "name": "稻香", "artist": "周杰伦", "album": "魔杰座", "duration": 223, "cover": "", "source": "demo"},
        # 林忆莲
        {"id": 10, "name": "至少还有你", "artist": "林忆莲", "album": "林忆莲's", "duration": 276, "cover": "", "source": "demo"},
        {"id": 11, "name": "爱上一个不回家的人", "artist": "林忆莲", "album": "都市触觉", "duration": 297, "cover": "", "source": "demo"},
        # 张学友
        {"id": 12, "name": "吻别", "artist": "张学友", "album": "吻别", "duration": 316, "cover": "", "source": "demo"},
        {"id": 13, "name": "她来听我的演唱会", "artist": "张学友", "album": "走过1999", "duration": 286, "cover": "", "source": "demo"},
        # 刘德华
        {"id": 14, "name": "忘情水", "artist": "刘德华", "album": "忘情水", "duration": 262, "cover": "", "source": "demo"},
        {"id": 15, "name": "今天", "artist": "刘德华", "album": "真永远", "duration": 276, "cover": "", "source": "demo"},
        # 邓紫棋
        {"id": 16, "name": "光年之外", "artist": "邓紫棋", "album": "光年之外", "duration": 235, "cover": "", "source": "demo"},
        {"id": 17, "name": "泡沫", "artist": "邓紫棋", "album": "Xposed", "duration": 262, "cover": "", "source": "demo"},
        # 陈奕迅
        {"id": 18, "name": "十年", "artist": "陈奕迅", "album": "黑白灰", "duration": 219, "cover": "", "source": "demo"},
        {"id": 19, "name": "浮夸", "artist": "陈奕迅", "album": "U87", "duration": 284, "cover": "", "source": "demo"},
        # 薛之谦
        {"id": 20, "name": "演员", "artist": "薛之谦", "album": "绅士", "duration": 261, "cover": "", "source": "demo"},
        {"id": 21, "name": "丑八怪", "artist": "薛之谦", "album": "初学者", "duration": 239, "cover": "", "source": "demo"},
        # 林俊杰
        {"id": 22, "name": "修炼爱情", "artist": "林俊杰", "album": "因你而在", "duration": 283, "cover": "", "source": "demo"},
        {"id": 23, "name": "江南", "artist": "林俊杰", "album": "第二天堂", "duration": 267, "cover": "", "source": "demo"},
        # 蔡依林
        {"id": 24, "name": "倒带", "artist": "蔡依林", "album": "城堡", "duration": 249, "cover": "", "source": "demo"},
        # 五月天
        {"id": 25, "name": "倔强", "artist": "五月天", "album": "神的孩子都在跳舞", "duration": 248, "cover": "", "source": "demo"},
        {"id": 26, "name": "突然好想你", "artist": "五月天", "album": "后青春期的诗", "duration": 275, "cover": "", "source": "demo"},
        # 孙燕姿
        {"id": 27, "name": "遇见", "artist": "孙燕姿", "album": "The Moment", "duration": 243, "cover": "", "source": "demo"},
        {"id": 28, "name": "我怀念的", "artist": "孙燕姿", "album": "逆光", "duration": 269, "cover": "", "source": "demo"},
        # 梁静茹
        {"id": 29, "name": "勇气", "artist": "梁静茹", "album": "勇气", "duration": 275, "cover": "", "source": "demo"},
        # 莫文蔚
        {"id": 30, "name": "忽然之间", "artist": "莫文蔚", "album": "就是莫文蔚", "duration": 253, "cover": "", "source": "demo"},
    ]
    q = req.keyword.strip().lower()
    if q:
        demo_all = [d for d in demo_all if q in d["name"].lower() or q in d["artist"].lower()]
    return {"status": "ok", "songs": demo_all, "hint": "演示曲目（启动 localhost:3000 或放入 MP3 到 data/music/ 获取真实播放）"}


class MusicPlayRequest(BaseModel):
    song_id: int = 0


@router.post("/play")
async def music_play(req: MusicPlayRequest):
    """播放指定歌曲：优先本地文件，否则演示曲目，最后尝试网易云API"""
    global _music_state
    # 演示曲目映射
    _demo_map = {
        1: {"name": "传奇", "artist": "王菲", "album": "传奇", "duration": 262},
        2: {"name": "红豆", "artist": "王菲", "album": "唱游", "duration": 253},
        3: {"name": "匆匆那年", "artist": "王菲", "album": "匆匆那年", "duration": 241},
        4: {"name": "因为爱情", "artist": "王菲 & 陈奕迅", "album": "将爱", "duration": 228},
        5: {"name": "如愿", "artist": "王菲", "album": "如愿", "duration": 275},
        6: {"name": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269},
        7: {"name": "七里香", "artist": "周杰伦", "album": "七里香", "duration": 299},
        8: {"name": "夜曲", "artist": "周杰伦", "album": "十一月的萧邦", "duration": 226},
    }
    try:
        # 1. 本地文件
        local_songs = _scan_local_music("")
        local_match = next((s for s in local_songs if s["id"] == req.song_id), None)
        if local_match and local_match.get("url"):
            _music_state["current_song"] = {
                "id": req.song_id, "name": local_match["name"],
                "artist": local_match["artist"], "album": "",
                "url": local_match["url"], "cover": "", "duration": 0,
            }
            _music_state["playing"] = True
            return {"status": "ok", "data": _music_state}

        # 2. 演示曲目（无真实音频，仅展示"播放中"状态）
        if req.song_id in _demo_map:
            song = _demo_map[req.song_id]
            _music_state["current_song"] = {
                "id": req.song_id, "name": song["name"],
                "artist": song["artist"], "album": song["album"],
                "url": "", "cover": "", "duration": song["duration"],
            }
            _music_state["playing"] = False
            _music_state["message"] = "No playable audio source. Start localhost:3000 music API or add MP3/WAV files to data/music/."
            return {"status": "needs_audio", "data": _music_state, "message": _music_state["message"]}

        # 否则尝试网易云API
        async with httpx.AsyncClient(timeout=10) as client:
            # 获取播放URL
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": req.song_id, "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""

            # 获取歌曲详情（名称、封面等）
            detail_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/detail",
                params={"ids": str(req.song_id)},
            )
            detail_data = detail_resp.json()
            songs = detail_data.get("songs", [])
            song_info = songs[0] if songs else {}

            artists = ", ".join(a.get("name", "") for a in (song_info.get("ar") or song_info.get("artists", [])))
            album = song_info.get("al") or song_info.get("album") or {}
            cover_url = (album.get("picUrl") or "") + "?param=300y300"
            duration = song_info.get("duration", 0)

            # 更新播放列表索引
            idx = -1
            for i, item in enumerate(_music_state["playlist"]):
                if item.get("id") == req.song_id:
                    idx = i
                    break
            if idx == -1:
                _music_state["playlist"].append({
                    "id": req.song_id,
                    "name": song_info.get("name", ""),
                    "artist": artists,
                    "album": album.get("name", ""),
                    "cover": cover_url,
                    "duration": duration,
                })
                _music_state["playlist_index"] = len(_music_state["playlist"]) - 1
            else:
                _music_state["playlist_index"] = idx

            _music_state["current_song"] = {
                "id": req.song_id,
                "name": song_info.get("name", ""),
                "artist": artists,
                "album": album.get("name", ""),
                "url": play_url,
                "cover": cover_url,
                "duration": duration,
            }
            if not play_url:
                _music_state["playing"] = False
                _music_state["message"] = "Music API did not return a playable URL. The song may require login or be copyright restricted."
                return {"status": "needs_audio", "data": _music_state, "message": _music_state["message"]}
            _music_state["playing"] = True
            _music_state["message"] = ""

            return {"status": "ok", "data": _music_state}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@router.post("/pause")
def music_pause():
    """切换播放/暂停状态"""
    global _music_state
    if not _music_state.get("playing") and not _music_state.get("current_song", {}).get("url"):
        _music_state["message"] = "No playable audio source selected."
        return {"status": "needs_audio", "data": _music_state, "message": _music_state["message"]}
    _music_state["playing"] = not _music_state["playing"]
    _music_state["message"] = ""
    return {"status": "ok", "data": _music_state}


@router.post("/next")
async def music_next():
    """播放列表下一首"""
    global _music_state
    pl = _music_state["playlist"]
    if not pl:
        return {"status": "ok", "data": _music_state}
    _music_state["playlist_index"] = (_music_state["playlist_index"] + 1) % len(pl)
    next_song = pl[_music_state["playlist_index"]]
    # 自动获取播放URL
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": next_song["id"], "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""
            next_song["url"] = play_url
    except Exception:
        pass

    _music_state["current_song"] = {
        "id": next_song.get("id", 0),
        "name": next_song.get("name", ""),
        "artist": next_song.get("artist", ""),
        "album": next_song.get("album", ""),
        "url": next_song.get("url", ""),
        "cover": next_song.get("cover", ""),
        "duration": next_song.get("duration", 0),
    }
    _music_state["playing"] = True
    return {"status": "ok", "data": _music_state}


@router.post("/prev")
async def music_prev():
    """播放列表上一首"""
    global _music_state
    pl = _music_state["playlist"]
    if not pl:
        return {"status": "ok", "data": _music_state}
    _music_state["playlist_index"] = (_music_state["playlist_index"] - 1) % len(pl)
    prev_song = pl[_music_state["playlist_index"]]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": prev_song["id"], "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""
            prev_song["url"] = play_url
    except Exception:
        pass

    _music_state["current_song"] = {
        "id": prev_song.get("id", 0),
        "name": prev_song.get("name", ""),
        "artist": prev_song.get("artist", ""),
        "album": prev_song.get("album", ""),
        "url": prev_song.get("url", ""),
        "cover": prev_song.get("cover", ""),
        "duration": prev_song.get("duration", 0),
    }
    _music_state["playing"] = True
    return {"status": "ok", "data": _music_state}


class MusicVolumeRequest(BaseModel):
    volume: int = 80


@router.post("/volume")
def music_volume(req: MusicVolumeRequest):
    """设置音量 (0-100)"""
    global _music_state
    _music_state["volume"] = max(0, min(int(req.volume), 100))
    return {"status": "ok", "data": _music_state}



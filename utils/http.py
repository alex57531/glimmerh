import asyncio
import io
import json
from time import time

import aiohttp
import cfscrape
import websockets
from typing import Iterable

from objects import errors
from objects.chunks import BigChunk, ChunkPzi, ChunkPz, PxlsBoard


async def fetch_chunks(chunks: Iterable):
    c = next(iter(chunks))
    if type(c) is BigChunk:
        await _fetch_chunks_pixelcanvas(chunks)
    elif type(c) is ChunkPzi:
        await _fetch_chunks_pixelzio(chunks)
    elif type(c) is ChunkPz:
        await _fetch_chunks_pixelzone(chunks)
    else:
        await _fetch_pxlsspace(chunks)


async def _fetch_chunks_pixelcanvas(bigchunks: Iterable[BigChunk]):
    async with aiohttp.ClientSession() as session:
        for bc in bigchunks:
            await asyncio.sleep(0)
            if not bc.is_in_bounds():
                continue
            data = None
            attempts = 0
            while attempts < 3:
                try:
                    async with session.get(bc.url) as resp:
                        data = await resp.read()
                        if len(data) == 460800:
                            break
                except aiohttp.ClientPayloadError:
                    pass
                data = None
                attempts += 1
            if not data:
                raise errors.HttpCanvasError('pixelcanvas')
            bc.load(data)


async def _fetch_chunks_pixelzio(chunks: Iterable[ChunkPzi]):
    async with cfscrape.create_scraper_async() as session:
        for ch in chunks:
            await asyncio.sleep(0)
            if not ch.is_in_bounds():
                continue
            async with session.get(ch.url) as resp:
                ch.load(await resp.read())


async def _fetch_chunks_pixelzone(chunks: Iterable[ChunkPz]):
    socket_url = "{0}://pixelzone.io/socket.io/?EIO=3&transport={1}"
    pkts_expected = 0
    async with aiohttp.ClientSession() as session:
        async with session.get(socket_url.format("http", "polling")) as r:
            sid = json.loads(str((await r.read())[4:-4], "utf-8"))['sid']
    async with websockets.connect(socket_url.format("ws", "websocket&sid=") + sid) as ws:
        await ws.send("2probe")
        await ws.recv()
        await ws.send("5")
        await ws.recv()
        for ch in chunks:
            await asyncio.sleep(0)
            if not ch.is_in_bounds():
                continue
            await ws.send(ch.url)
            pkts_expected += 1
        if pkts_expected > 0:
            pkts_loaded = 0
            async for msg in ws:
                d = json.loads(msg[msg.find('['):])
                if d[0] == "chunkData":
                    data = d[1]
                    ch = next((x for x in chunks if x.x == data['cx'] and x.y == data['cy']))
                    ch.load(data['data'])
                    pkts_loaded += 1
                if pkts_loaded == pkts_expected:
                    break


async def _fetch_pxlsspace(chunks: Iterable[PxlsBoard]):
    board = next(iter(chunks))
    async with aiohttp.ClientSession() as session:
        async with session.get("http://pxls.space/info") as resp:
            info = json.loads(await resp.read())
        board.set_board_info(info)

        async with session.get("http://pxls.space/boarddata?={0:.0f}".format(time())) as resp:
            board.load(await resp.read())


async def get_changelog(version):
    url = "https://api.github.com/repos/DiamondIceNS/StarlightGlimmer/releases"
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url) as resp:
            if resp.status != 200:
                raise errors.HttpGeneralError
            data = json.loads(await resp.read())
            return next((x for x in data if x['tag_name'] == "v{}".format(version)), None)


async def get_template(url):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url) as resp:
            if resp.status != 200:
                raise errors.TemplateHttpError
            if resp.content_type == "image/jpg" or resp.content_type == "image/jpeg":
                raise errors.NoJpegsError
            if resp.content_type != "image/png":
                raise errors.NotPngError
            return io.BytesIO(await resp.read())

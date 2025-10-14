import asyncio
import faulthandler
import sys
import time

import aioredis as redis

THRESH = 2.0

async def main():
    r = redis.from_url("redis://127.0.0.1:6379", decode_responses=True)
    print("Client constructed")
    # ping (возможно прогревает соединение)
    t0 = time.monotonic()
    try:
        await r.ping()
    except Exception as e:
        print("Ping error:", e)
        await r.close()
        return
    print("Ping took", time.monotonic() - t0, "s")
    # планируем фоновый дамп стека если зависнет
    def on_timeout():
        print(">>> First SET is taking too long, dumping Python stack via faulthandler", file=sys.stderr)
        faulthandler.dump_traceback(file=sys.stderr)
    # запускаем set и измеряем
    t1 = time.monotonic()
    # запускаем отложенный дамп через THRESH секунд
    import threading
    timer = threading.Timer(THRESH, on_timeout)
    timer.start()
    try:
        await r.set("diag:first_set", "x"*100)  # попробуй маленькое значение
    finally:
        took = time.monotonic() - t1
        timer.cancel()
    print("First SET took", took, "s")
    await r.close()

if __name__ == "__main__":
    asyncio.run(main())

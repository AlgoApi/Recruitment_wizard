# save test_asyncpg.py
import asyncio, asyncpg, time
async def main():
    try:
        t0 = time.monotonic()
        conn = await asyncpg.connect(user='tester', password='tester_pass', database='testesteron', host='127.0.0.1', port=5432, timeout=10.0)
        print("connected in", time.monotonic()-t0)
        await conn.close()
    except Exception as e:
        print("ERR", type(e), e)

asyncio.run(main())

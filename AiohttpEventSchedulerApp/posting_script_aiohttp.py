import pandas as pd
import asyncio,aiohttp
import time



print('loading Excel File!')
df = pd.read_excel('slipstream_event_schedule.xlsx', engine='openpyxl', index_col='Time Block',parse_dates=True)
post_this_json = df.to_json(orient="index")
print('extracting data from the Excel file success!')


print('posting data to API now!')
post_url = 'http://10.200.200.224:5000/update/data'
get_url = 'http://10.200.200.224:5000/payload/current'


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.post(post_url,json=post_this_json) as resp:
            print(resp.status)
            print(await resp.text())


        if resp.status == 200:
            print('GREAT!, SUCCESS')

            async with session.get(get_url) as resp:
                print('Current Payload Check')
                print(resp.status)
                print(await resp.text())

loop = asyncio.get_event_loop()
loop.run_until_complete(main())





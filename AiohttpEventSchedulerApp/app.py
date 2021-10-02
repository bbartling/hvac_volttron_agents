# https://stackoverflow.com/questions/51645324/how-to-setup-a-aiohttp-https-server-and-client/51646535


import asyncio
from time import strftime
import time
import pytz
from datetime import datetime, timezone, timedelta
import pytz
from typing import Any, AsyncIterator, Awaitable, Callable, Dict
from aiohttp import web
import pandas as pd
import datetime




tz = pytz.timezone('America/Chicago')
routes = web.RouteTableDef()

def handle_json_error(
    func: Callable[[web.Request], Awaitable[web.Response]]
) -> Callable[[web.Request], Awaitable[web.Response]]:
    async def handler(request: web.Request) -> web.Response:
        try:
            return await func(request)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            return web.json_response(
                {"status": "failed", "info": str(ex)}, status=400
            )

    return handler



def get_state_from_df():


    df = df_in_memory
    df.rename(columns={'index':'Time Block'}, inplace=True)
    df.set_index('Time Block')
    df['Time Block'] = pd.to_datetime(df['Time Block']).dt.round(freq='T')
    utc_time = datetime.datetime.utcnow()
    utc_time = utc_time.replace(tzinfo=pytz.UTC)   
    corrected_time = utc_time.astimezone(tz) 
    current_block = corrected_time.replace(minute = (corrected_time.minute - corrected_time.minute % 15), second=0, microsecond=0)
    current_block_no_tz = current_block.replace(tzinfo=None)

    # brute force through excel file to find a matching date
    for row in df.iterrows():
        if row[1][0].replace(second=0, microsecond=0) == current_block_no_tz:
            date = row[1][0].replace(second=0, microsecond=0)
            info = f'timeblock is {date}'
            response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':row[1][1]}
            print(response_obj)   
            return web.json_response(response_obj)


    info = "timeblock not found"
    response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
    print(response_obj)   
    return web.json_response(response_obj)
    
    


def get_hourly_from_df():

    hours = 4
    df = df_in_memory
    df.rename(columns={'index':'Time Block'}, inplace=True)
    df.set_index('Time Block')
    df['Time Block'] = pd.to_datetime(df['Time Block']).dt.round(freq='T')
    utc_time = datetime.datetime.utcnow()
    utc_time = utc_time.replace(tzinfo=pytz.UTC)   
    corrected_time = utc_time.astimezone(tz) 
    current_block = corrected_time.replace(minute = (corrected_time.minute - corrected_time.minute % 15), second=0, microsecond=0)
    current_block_no_tz = current_block.replace(tzinfo=None)

    # brute force through excel file to find a matching date
    for row in df.iterrows():
        if row[1][0].replace(second=0, microsecond=0) == current_block_no_tz:
            date = row[1][0].replace(second=0, microsecond=0)
            info = f'timeblock is {date}'
            
            slice_start = row[0]
            slice_end = row[0] + hours
            sliced_df = df[slice_start:slice_end]
            sliced_data = sliced_df.to_json(orient='records')
            
            response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':row[1][1],'hourly':sliced_data}
            print(response_obj)   
            return web.json_response(response_obj)


    info = "Internal Server Error - unable to compile future results"
    response_obj = {'status':'fail','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz)}
    print(response_obj)   
    return web.json_response(response_obj)


@routes.get('/payload/current')
@handle_json_error
def event_state_current(request: web.Request) -> web.Response:
    return get_state_from_df()    


@routes.get('/payload/hourly')
@handle_json_error
def event_state_hourly(request: web.Request) -> web.Response:
    return get_hourly_from_df()    



@routes.post('/update/data')
@handle_json_error
async def api_new_payload_data(request: web.Request) -> web.Response:

    r = await request.json()
    r = request.json
    print('r is ',r)
    df_in_memory = pd.read_json(r).T
    print('df is ',df_in_memory)

    response_obj = {'status':'success','info':'parsed and saved success','timezone_config':str(tz)}
    print(response_obj)   
    return web.json_response(response_obj)   





async def init_app() -> web.Application:
    app = web.Application()
    app.add_routes([web.get('/payload/current', event_state_current)])
    app.add_routes([web.get('/payload/hourly', event_state_hourly)])
    app.add_routes([web.post('/update/data', api_new_payload_data)])
    return app


web.run_app(init_app()  , host='0.0.0.0', port=8080)
